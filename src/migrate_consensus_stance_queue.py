"""migrate_consensus_stance_queue.py

One-time migration: adds entity_spans, parent_id, and link_id columns to
the EXISTING data/hitl/queue_consensus_stance.csv without touching the
152 real human ratings already in it (preserves human_stance/notes
exactly as-is, only adds new columns).

Run once: python3.12 src/migrate_consensus_stance_queue.py
"""
import os
import sys
import re
import json
import duckdb
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from refine_thesis_models import build_regex
from consensus_experts_verified import VERIFIED_CONSENSUS_EXPERTS

QUEUE_PATH = "data/hitl/queue_consensus_stance.csv"
EMPATH_PATH = "data/processed/empath_scores_full.parquet"


def main():
    print("Loading existing queue (preserving all existing ratings)...")
    df = pd.read_csv(QUEUE_PATH)
    print(f"{len(df)} rows, {df['human_stance'].notna().sum()} already rated")

    rx = build_regex(list(VERIFIED_CONSENSUS_EXPERTS))

    print("Computing entity spans for each row...")
    spans_col = []
    for text in df["full_text"].astype(str):
        spans = [{"start": m.start(), "end": m.end(), "text": m.group(0)} for m in rx.finditer(text)]
        spans_col.append(json.dumps(spans))
    df["entity_spans"] = spans_col

    print("Looking up parent_id / link_id from the raw corpus...")
    con = duckdb.connect()
    ids = df["id"].astype(str).tolist()
    id_list_sql = ",".join(f"'{i}'" for i in ids)
    # NOTE: empath_scores_full.parquet has ~58,669 duplicate `id` rows
    # (a known, separately-documented data-quality issue in the core
    # corpus files -- see ANTIGRAVITY_HANDOFF.md). QUALIFY here to take
    # exactly one row per id, or this merge fans out and duplicates queue
    # rows (confirmed: first version of this script did exactly that,
    # 240 rows -> 243, caught before saving over the real ratings).
    lookup = con.execute(f"""
        SELECT id, parent_id, link_id
        FROM read_parquet('{EMPATH_PATH}')
        WHERE id IN ({id_list_sql})
        QUALIFY ROW_NUMBER() OVER (PARTITION BY id) = 1
    """).df()
    lookup["id"] = lookup["id"].astype(str)
    df["id"] = df["id"].astype(str)
    df = df.merge(lookup, on="id", how="left")

    df.to_csv(QUEUE_PATH, index=False)
    print(f"Saved migrated queue to {QUEUE_PATH}")
    print(f"Verification: human_stance still has {df['human_stance'].notna().sum()} ratings (should match count above)")
    print(f"Rows with a matched entity span: {(df['entity_spans'] != '[]').sum()} / {len(df)}")
    print(f"Rows with parent_id resolved: {df['parent_id'].notna().sum()} / {len(df)}")


if __name__ == "__main__":
    main()
