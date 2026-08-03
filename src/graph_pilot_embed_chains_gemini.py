"""graph_pilot_embed_chains_gemini.py

Nash's refinement 2026-08-02: instead of embedding individual comments
and mean-pooling per chain afterward (which throws away cross-comment
context -- each comment gets embedded blind to the rest of its chain),
concatenate each chain's member comments' text IN ORDER and embed the
WHOLE CHAIN as a single Gemini call. One real embedding per chain,
holistic over the conversation flow, not an average of independent
embeddings.

Reuses the chain decomposition already computed in
graph_pilot_chain_clustering.py's earlier (MiniLM-based) run --
chains.parquet's member_ids column, which is model-independent (it's
pure tree structure, doesn't depend on which embedding was used).
Processing order follows chain_idx, i.e. the same walk order the
decomposition produced (post-by-post, branch-by-branch), not an
arbitrary/parallel flat order over individual comments.

Fewer total calls than per-comment embedding (29,913 chains vs 89,994
comments) since text volume is the same, just batched by chain instead
of by comment.

Truncation: 2000 chars was fine for single short comments
(score_boundary_candidates_vertex.py's convention) but chains can run
up to 283 comments concatenated -- using a wider 8000-char cap here so
long chains aren't reduced to just their opening exchange. Still a cap,
not the true unbounded chain text -- gemini-embedding-2's real max
input wasn't verified against docs in this session, 8000 chars is a
judgment call, not a confirmed model limit.

Output: data/processed/graph_pilot_top200_depth/chain_embeddings_gemini.npy
  (row i = chains.parquet's chain_idx i)
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

PILOT_DIR = "data/processed/graph_pilot_top200_depth"
PROJECT = "nashpncc-vertex-frontier"
LOCATION = "global"
WORKERS = 30
CHECKPOINT_EVERY = 1000
TRUNCATE_CHARS = 8000
CHECKPOINT_PATH = f"{PILOT_DIR}/chain_embeddings_gemini_checkpoint.npy"
DONE_MASK_PATH = f"{PILOT_DIR}/chain_embeddings_gemini_done_mask.npy"
FINAL_PATH = f"{PILOT_DIR}/chain_embeddings_gemini.npy"
EMBED_DIM = 3072


def build_chain_texts():
    chains = pd.read_parquet(f"{PILOT_DIR}/chains.parquet").sort_values("chain_idx").reset_index(drop=True)
    comments = pd.read_parquet(f"{PILOT_DIR}/comments.parquet")
    text_by_id = dict(zip(comments["id"], comments["text"].fillna("")))

    texts = []
    for _, row in chains.iterrows():
        member_ids = row["member_ids"].split(",")
        # in chain order (root -> leaf), each comment separated so the
        # embedding sees this as a sequence of turns, not one run-on blob
        joined = " >> ".join(text_by_id.get(cid, "") for cid in member_ids)
        texts.append(joined[:TRUNCATE_CHARS])
    return chains, texts


def embed_gemini(docs, workers=WORKERS):
    from google import genai
    import threading
    tl = threading.local()

    def client():
        if not hasattr(tl, "c"):
            tl.c = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
        return tl.c

    def one(i_doc):
        i, doc = i_doc
        for attempt in range(3):
            try:
                resp = client().models.embed_content(model="gemini-embedding-2", contents=doc)
                return i, resp.embeddings[0].values
            except Exception as e:
                if "429" in str(e):
                    time.sleep(5 * (attempt + 1))
                    continue
                return i, None
        return i, None

    n = len(docs)
    if os.path.exists(CHECKPOINT_PATH) and os.path.exists(DONE_MASK_PATH):
        results_arr = np.load(CHECKPOINT_PATH)
        done_mask = np.load(DONE_MASK_PATH)
        print(f"  resuming from checkpoint: {done_mask.sum():,}/{n} already embedded", flush=True)
    else:
        results_arr = np.zeros((n, EMBED_DIM), dtype=np.float32)
        done_mask = np.zeros(n, dtype=bool)

    # process in chain_idx order (the existing decomposition's own walk
    # order -- post by post, branch by branch), not shuffled
    todo = [(i, d) for i, d in enumerate(docs) if not done_mask[i]]
    print(f"  {len(todo):,} remaining to embed, in chain_idx order", flush=True)

    t0 = time.time()
    done_this_run = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, item) for item in todo]
        for fut in as_completed(futures):
            i, vec = fut.result()
            if vec is not None:
                results_arr[i] = vec
            done_mask[i] = True
            done_this_run += 1
            if done_this_run % CHECKPOINT_EVERY == 0:
                np.save(CHECKPOINT_PATH, results_arr)
                np.save(DONE_MASK_PATH, done_mask)
                print(f"  embedded {done_this_run}/{len(todo)} this run "
                      f"({done_mask.sum():,}/{n} total, {time.time()-t0:.0f}s elapsed) -- checkpointed", flush=True)

    np.save(CHECKPOINT_PATH, results_arr)
    np.save(DONE_MASK_PATH, done_mask)
    n_failed = int((results_arr.sum(axis=1) == 0).sum())
    print(f"  {n_failed} rows have an all-zero embedding (failed)", flush=True)
    return results_arr


def main():
    chains, texts = build_chain_texts()
    print(f"Embedding {len(texts):,} whole chains with Gemini (project={PROJECT})...", flush=True)
    print(f"  chain length stats: min={chains['length'].min()}, max={chains['length'].max()}, "
          f"mean={chains['length'].mean():.2f}", flush=True)
    emb = embed_gemini(texts)
    np.save(FINAL_PATH, emb)
    print(f"Saved to {FINAL_PATH}, shape {emb.shape}", flush=True)


if __name__ == "__main__":
    main()
