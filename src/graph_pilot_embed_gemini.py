"""graph_pilot_embed_gemini.py

Embeds the graph pilot's real ~90k comments with Gemini, ordered along
reply chains. Third revision 2026-08-02 (Nash, in sequence):
1. Keep comment-by-comment embedding (separate from the whole-chain-
   as-one-string experiment in graph_pilot_embed_chains_gemini.py).
2. Order/batch the work along the reply chains already decomposed in
   chains.parquet, building each chain's cumulative trajectory as it
   goes, not just at the end.
3. Don't even wait for a whole chain to finish -- append each step to
   its chain's running cumulative vector THE MOMENT that step's comment
   is embedded, not after the whole chain completes.

The real complication in (3): the thread pool doesn't complete comments
in chain order (a chain's 3rd comment can finish before its 1st).
Handled with a per-chain "next expected step" pointer plus a pending
buffer -- a completed step gets appended to the trajectory immediately
if it's next in line; otherwise it waits in the buffer until earlier
steps land, then a chain reaction of appends fires once the gap closes.

Resumes from the existing checkpoint (partial progress from the prior
two revisions is kept, not re-embedded) -- on startup, any already-done
comments are fed through the same advance logic to catch the
trajectories up to where they'd already be.

Output: data/processed/graph_pilot_top200_depth/comment_embeddings_gemini.npy
        data/processed/graph_pilot_top200_depth/chain_trajectories_gemini.parquet
          (chain_idx, step, comment_id, cumulative_vector)
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
CHECKPOINT_EVERY = 2000
CHECKPOINT_PATH = f"{PILOT_DIR}/comment_embeddings_gemini_checkpoint.npy"
DONE_MASK_PATH = f"{PILOT_DIR}/comment_embeddings_gemini_done_mask.npy"
FINAL_PATH = f"{PILOT_DIR}/comment_embeddings_gemini.npy"
TRAJECTORIES_PATH = f"{PILOT_DIR}/chain_trajectories_gemini.parquet"
EMBED_DIM = 3072


class ChainTrajectoryBuilder:
    """Tracks, per chain, the next expected step and a buffer of
    completed-but-not-yet-appended steps. append() is safe to call in
    any order; it advances as far as the buffer allows each time."""

    def __init__(self, chain_members):
        self.chain_members = chain_members  # chain_idx -> ordered [comment_id, ...]
        self.step_of = {}  # comment_id -> (chain_idx, step)
        for cidx, members in chain_members.items():
            for step, cid in enumerate(members):
                self.step_of[cid] = (cidx, step)
        self.next_step = {cidx: 0 for cidx in chain_members}
        self.pending = {cidx: {} for cidx in chain_members}
        self.cumulative = {cidx: np.zeros(EMBED_DIM, dtype=np.float32) for cidx in chain_members}
        self.rows = []
        self.n_chains_completed = 0

    def append(self, comment_id, vec):
        loc = self.step_of.get(comment_id)
        if loc is None:
            return
        cidx, step = loc
        self.pending[cidx][step] = vec
        while self.next_step[cidx] in self.pending[cidx]:
            v = self.pending[cidx].pop(self.next_step[cidx])
            self.cumulative[cidx] = self.cumulative[cidx] + v
            self.rows.append({
                "chain_idx": cidx, "step": self.next_step[cidx],
                "comment_id": self.chain_members[cidx][self.next_step[cidx]],
                "cumulative_vector": self.cumulative[cidx].copy().tolist(),
            })
            self.next_step[cidx] += 1
            if self.next_step[cidx] == len(self.chain_members[cidx]):
                self.n_chains_completed += 1

    def save(self, path):
        if self.rows:
            pd.DataFrame(self.rows).to_parquet(path, index=False)


def embed_gemini_along_chains(docs, id_list, chain_members, workers=WORKERS):
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
                resp = client().models.embed_content(model="gemini-embedding-2", contents=doc[:2000])
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

    builder = ChainTrajectoryBuilder(chain_members)

    # catch the trajectory builder up on anything already done from a prior run
    n_preloaded = 0
    for i, cid in enumerate(id_list):
        if done_mask[i]:
            builder.append(cid, results_arr[i])
            n_preloaded += 1
    if n_preloaded:
        print(f"  fed {n_preloaded:,} already-embedded comments through the trajectory builder on startup", flush=True)

    todo = [(i, d) for i, d in enumerate(docs) if not done_mask[i]]
    print(f"  {len(todo):,} remaining to embed (full worker parallelism; each comment "
          f"extends its chain's trajectory the instant it lands, in order)", flush=True)

    t0 = time.time()
    done_this_run = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, item) for item in todo]
        for fut in as_completed(futures):
            i, vec = fut.result()
            if vec is not None:
                results_arr[i] = vec
            done_mask[i] = True
            builder.append(id_list[i], results_arr[i])
            done_this_run += 1
            if done_this_run % CHECKPOINT_EVERY == 0:
                np.save(CHECKPOINT_PATH, results_arr)
                np.save(DONE_MASK_PATH, done_mask)
                builder.save(TRAJECTORIES_PATH)
                print(f"  embedded {done_this_run}/{len(todo)} this run "
                      f"({done_mask.sum():,}/{n} total, {builder.n_chains_completed:,} chains fully complete, "
                      f"{len(builder.rows):,} trajectory steps so far, {time.time()-t0:.0f}s elapsed) -- checkpointed", flush=True)

    np.save(CHECKPOINT_PATH, results_arr)
    np.save(DONE_MASK_PATH, done_mask)
    builder.save(TRAJECTORIES_PATH)
    n_failed = int((results_arr.sum(axis=1) == 0).sum())
    print(f"  {n_failed} rows have an all-zero embedding (failed or empty text)", flush=True)
    print(f"  {builder.n_chains_completed:,}/{len(chain_members):,} chains fully complete, "
          f"{len(builder.rows):,} total trajectory steps saved to {TRAJECTORIES_PATH}", flush=True)

    return results_arr


def main():
    comments = pd.read_parquet(f"{PILOT_DIR}/comments.parquet")
    docs = comments["text"].fillna("").tolist()
    id_list = comments["id"].tolist()

    chains = pd.read_parquet(f"{PILOT_DIR}/chains.parquet")
    chain_members = {row["chain_idx"]: row["member_ids"].split(",") for _, row in chains.iterrows()}

    print(f"Embedding {len(docs):,} pilot comments with Gemini (project={PROJECT}), "
          f"ordered along {len(chain_members):,} reply chains...", flush=True)
    emb = embed_gemini_along_chains(docs, id_list, chain_members)
    np.save(FINAL_PATH, emb)
    print(f"Saved to {FINAL_PATH}, shape {emb.shape}", flush=True)


if __name__ == "__main__":
    main()
