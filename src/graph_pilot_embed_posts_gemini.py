"""graph_pilot_embed_posts_gemini.py

Nash's direction 2026-08-02: embed the pilot's 200 POSTS (title +
selftext) separately from the comment-level analysis, to see whether
thread-to-thread similarity via what a thread is nominally ABOUT
(its title) differs from comment-level semantic structure (what the
actual conversation ends up being about, which can drift far from the
post's stated subject). Different signal, complementary to everything
built at the comment level tonight.

Uses r_conspiracy_posts_for_context.parquet (already built earlier this
session, id/title/selftext for the full corpus) joined against the
pilot's 200 thread ids.

Output: data/processed/graph_pilot_top200_depth/post_embeddings_gemini.npy
        data/processed/graph_pilot_top200_depth/posts.parquet (link_id, title, selftext)
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import duckdb
import numpy as np
import pandas as pd

PILOT_DIR = "data/processed/graph_pilot_top200_depth"
PROJECT = "nashpncc-vertex-frontier"
LOCATION = "global"
WORKERS = 20


def main():
    comments = pd.read_parquet(f"{PILOT_DIR}/comments.parquet")
    post_ids = sorted(comments["link_id"].unique())
    stripped_ids = [p[3:] if p.startswith("t3_") else p for p in post_ids]

    con = duckdb.connect()
    ids_str = ", ".join(f"'{i}'" for i in stripped_ids)
    posts = con.execute(f"""
        SELECT id, title, selftext
        FROM read_parquet('data/processed/r_conspiracy_posts_for_context.parquet')
        WHERE id IN ({ids_str})
    """).df()
    posts["link_id"] = "t3_" + posts["id"]
    print(f"{len(posts)}/{len(post_ids)} pilot posts found with real title/selftext", flush=True)

    posts["combined_text"] = posts["title"].fillna("") + "\n" + posts["selftext"].fillna("")
    posts.to_parquet(f"{PILOT_DIR}/posts.parquet", index=False)

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
                resp = client().models.embed_content(model="gemini-embedding-2", contents=doc[:4000])
                return i, resp.embeddings[0].values
            except Exception as e:
                if "429" in str(e):
                    time.sleep(5 * (attempt + 1))
                    continue
                return i, None
        return i, None

    texts = posts["combined_text"].tolist()
    results = [None] * len(texts)
    print(f"Embedding {len(texts)} posts with Gemini...", flush=True)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(one, (i, d)) for i, d in enumerate(texts)]
        for fut in as_completed(futures):
            i, vec = fut.result()
            results[i] = vec

    dim = next(len(v) for v in results if v is not None)
    n_failed = sum(1 for v in results if v is None)
    print(f"{n_failed} failed embeddings", flush=True)
    results = [v if v is not None else [0.0] * dim for v in results]
    emb = np.array(results)
    np.save(f"{PILOT_DIR}/post_embeddings_gemini.npy", emb)
    print(f"Saved {emb.shape} to {PILOT_DIR}/post_embeddings_gemini.npy", flush=True)


if __name__ == "__main__":
    main()
