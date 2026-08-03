"""embed_large_post_sample.py

Embeds the 20,000-post sample (build_large_post_sample.py) with Gemini,
same model/pattern as every other embedding job tonight. Uses
tobiasnash-vertex-frontier (the project confirmed to actually have
working quota) with explicit per-thread credentials, not the machine's
default ADC.

Output: data/processed/large_post_embeddings_gemini.npy (20000, 3072)
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

PROJECT = "tobiasnash-vertex-frontier"
ACCOUNT = "contact@tobiasnash.co.nz"
LOCATION = "global"
WORKERS = 20
OUT_PATH = "data/processed/large_post_embeddings_gemini.npy"

_thread_local = threading.local()


def get_client():
    if not hasattr(_thread_local, "client"):
        import subprocess
        from google import genai
        from google.oauth2.credentials import Credentials
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token", f"--account={ACCOUNT}"]
        ).decode().strip()
        creds = Credentials(token=token)
        _thread_local.client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION, credentials=creds)
    return _thread_local.client


def embed_one(i_doc):
    i, doc = i_doc
    for attempt in range(3):
        try:
            resp = get_client().models.embed_content(model="gemini-embedding-2", contents=doc[:4000])
            return i, resp.embeddings[0].values
        except Exception as e:
            if "429" in str(e):
                time.sleep(5 * (attempt + 1))
                continue
            return i, None
    return i, None


def main():
    posts = pd.read_parquet("data/processed/large_post_sample.parquet")
    texts = posts["combined_text"].tolist()
    results = [None] * len(texts)
    print(f"Embedding {len(texts):,} posts with Gemini...", flush=True)

    completed = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(embed_one, (i, d)) for i, d in enumerate(texts)]
        for fut in as_completed(futures):
            i, vec = fut.result()
            results[i] = vec
            completed += 1
            if completed % 2000 == 0:
                print(f"  {completed:,}/{len(texts):,} done", flush=True)

    dim = next(len(v) for v in results if v is not None)
    n_failed = sum(1 for v in results if v is None)
    print(f"{n_failed} failed embeddings", flush=True)
    results = [v if v is not None else [0.0] * dim for v in results]
    emb = np.array(results, dtype=np.float32)
    np.save(OUT_PATH, emb)
    print(f"Saved {emb.shape} to {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
