"""compute_stance_direction.py

Nash's idea 2026-08-02 (late): the semantic layer's persistent degeneracy
tonight (giant-blob collapse in clique percolation, near-complete graph
in the chain-similarity layer, "everywhere dense, early-developmental-
brain" in the raw threshold sweep) might be because Gemini's embedding
space is dominated by register/affect/polarization more than by topic --
angry, hostile, conspiratorial comments clustering near each other
regardless of what they're actually about. If so, subtracting a
"stance direction" out of every embedding (same technique as Bolukbasi
et al. 2016's gender-bias-subspace removal for word embeddings) should
leave a residual that's cleaner on aboutness.

Deriving the direction empirically rather than guessing via blind PCA:
selects strongly-hostile vs strongly-endorsement examples from the
labeled stance training data, restricted to the 266 entities that have
BOTH (so the contrast isolates stance, not entity-identity or topic --
comparing hostile-about-Assange to endorsement-about-Assange, not
hostile-about-Assange to endorsement-about-Fauci). Embeds them with
Gemini (same model as everything else tonight), computes
mean(endorsement) - mean(hostile) as the stance direction.

Output: data/processed/graph_pilot_top200_depth/stance_direction_gemini.npy
  -- a single unit-normalized 3072-dim vector.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

PROJECT = "tobiasnash-vertex-frontier"
ACCOUNT = "contact@tobiasnash.co.nz"
LOCATION = "global"
MAX_PER_ENTITY_PER_STANCE = 3
OUT_PATH = "data/processed/graph_pilot_top200_depth/stance_direction_gemini.npy"

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


def embed_one(text):
    for attempt in range(3):
        try:
            resp = get_client().models.embed_content(model="gemini-embedding-2", contents=text[:4000])
            return resp.embeddings[0].values
        except Exception as e:
            if "429" in str(e):
                time.sleep(5 * (attempt + 1))
                continue
            return None
    return None


def select_examples():
    df = pd.read_parquet("data/processed/stance_classifier_training_data.parquet")
    scores = df["label_notes"].str.extract(r"frontier_score=(-?\d*\.?\d+)")[0].astype(float)
    df["stance_val"] = scores
    df.loc[df["stance_val"].isna() & (df["label"] == "hostile"), "stance_val"] = -1.0
    df.loc[df["stance_val"].isna() & (df["label"] == "endorsement"), "stance_val"] = 1.0

    strong_hostile = df[df["stance_val"] <= -0.7]
    strong_endorse = df[df["stance_val"] >= 0.7]
    entities_both = set(strong_hostile["target_entity"]) & set(strong_endorse["target_entity"])

    h_rows, e_rows = [], []
    for entity in entities_both:
        h = strong_hostile[strong_hostile["target_entity"] == entity].nsmallest(MAX_PER_ENTITY_PER_STANCE, "stance_val")
        e = strong_endorse[strong_endorse["target_entity"] == entity].nlargest(MAX_PER_ENTITY_PER_STANCE, "stance_val")
        h_rows.append(h)
        e_rows.append(e)

    hostile_df = pd.concat(h_rows, ignore_index=True).drop_duplicates(subset="text")
    endorse_df = pd.concat(e_rows, ignore_index=True).drop_duplicates(subset="text")
    print(f"{len(entities_both)} entities, {len(hostile_df):,} hostile examples, "
          f"{len(endorse_df):,} endorsement examples selected", flush=True)
    return hostile_df, endorse_df


def embed_texts(texts, label):
    results = [None] * len(texts)
    print(f"Embedding {len(texts)} {label} examples...", flush=True)
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(embed_one, t): i for i, t in enumerate(texts)}
        for fut in as_completed(futures):
            i = futures[fut]
            results[i] = fut.result()
    n_failed = sum(1 for r in results if r is None)
    print(f"  {n_failed} failed", flush=True)
    return np.array([r for r in results if r is not None])


def main():
    hostile_df, endorse_df = select_examples()

    hostile_emb = embed_texts(hostile_df["text"].tolist(), "hostile")
    endorse_emb = embed_texts(endorse_df["text"].tolist(), "endorsement")

    hostile_mean = hostile_emb.mean(axis=0)
    endorse_mean = endorse_emb.mean(axis=0)

    direction = endorse_mean - hostile_mean
    direction = direction / np.linalg.norm(direction)

    np.save(OUT_PATH, direction)
    print(f"\nStance direction saved to {OUT_PATH}, shape={direction.shape}", flush=True)


if __name__ == "__main__":
    main()
