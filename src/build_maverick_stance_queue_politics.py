#!/usr/bin/env python3
"""Builds the stratified and blinded queue for maverick stance checking in
the r/politics control sample.

Mirrors src/build_maverick_stance_queue.py exactly (same blinding/
stratification logic and schema), except the source population is
data/processed/comparison_politics_staged_scored.parquet (the fully
rebuilt N=140,824 r/politics sample) instead of the r/conspiracy pure
population, and has_maverick is computed with the same verified-list +
disambiguation-lookup logic (compute_has_maverick) used in
src/rerun_refined_regressions_v2.py, so this queue's population definition
matches the has_maverick coefficient actually reported for r/politics.

Draws from r/politics comments matching has_maverick == 1.
Stratum A: high_traction == 1 (up to 120 comments)
Stratum B: high_traction == 0 (up to 120 comments)
"""
import os
import sys
import json
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from refine_thesis_models import build_regex
from rerun_refined_regressions_v2 import load_entities_split_corrected, compute_has_maverick
from combined_maverick_detector import load_maverick_disambiguation_lookup

POLITICS_SCORED_PATH = 'data/processed/comparison_politics_staged_scored.parquet'
QUEUE_PATH = 'data/hitl/queue_maverick_stance_politics.csv'
MAP_PATH = 'data/processed/maverick_stance_politics_queue_strata_map.csv'


def main():
    print("=== Building Maverick Stance Spot-Check Queue (r/politics) ===")

    if not os.path.exists(POLITICS_SCORED_PATH):
        print(f"MISSING: {POLITICS_SCORED_PATH}")
        print("Run src/rerun_refined_regressions_v2.py first (it builds/caches this file).")
        sys.exit(1)

    mavericks, _, _ = load_entities_split_corrected()
    rx_mav = build_regex(mavericks)
    print(f"Loaded {len(mavericks)} mavericks for regex construction.")

    lookup = load_maverick_disambiguation_lookup()
    print(f"Loaded {len(lookup)} resolved bare-form entries from disambiguation lookup.")

    print(f"Loading r/politics scored sample from {POLITICS_SCORED_PATH}...")
    df_pol = pd.read_parquet(POLITICS_SCORED_PATH)
    print(f"Loaded {len(df_pol):,} r/politics comments.")

    df_pol['has_maverick'] = compute_has_maverick(df_pol, rx_mav, lookup)
    df_pol['high_traction'] = (df_pol['upvotes'] >= 5).astype(int)

    print("\n--- Population Crosstab (has_maverick x high_traction) ---")
    ct = pd.crosstab(df_pol['has_maverick'], df_pol['high_traction'])
    print(ct)
    print("------------------------------------------------------------")

    df_mav_exp = df_pol[df_pol['has_maverick'] == 1].copy()
    print(f"Total positive has_maverick cases in population: {len(df_mav_exp):,}")

    df_stratum_a = df_mav_exp[df_mav_exp['high_traction'] == 1]
    df_stratum_b = df_mav_exp[df_mav_exp['high_traction'] == 0]

    n_stratum_a_avail = len(df_stratum_a)
    n_stratum_b_avail = len(df_stratum_b)
    print(f"Available Stratum A (high_traction == 1): {n_stratum_a_avail}")
    print(f"Available Stratum B (high_traction == 0): {n_stratum_b_avail}")

    sample_a = df_stratum_a.sample(n=min(120, n_stratum_a_avail), random_state=42).copy()
    sample_b = df_stratum_b.sample(n=min(120, n_stratum_b_avail), random_state=42).copy()

    print(f"\nSampled {len(sample_a)} rows from Stratum A.")
    print(f"Sampled {len(sample_b)} rows from Stratum B.")
    if len(sample_a) < 40:
        print(f"WARNING: Stratum A is extremely sparse ({len(sample_a)} rows)!")
    if len(sample_b) < 40:
        print(f"WARNING: Stratum B is extremely sparse ({len(sample_b)} rows)!")

    sample_a['stratum'] = 'Stratum A (high_traction == 1)'
    sample_b['stratum'] = 'Stratum B (high_traction == 0)'

    combined = pd.concat([sample_a, sample_b], ignore_index=True)
    shuffled = combined.sample(frac=1, random_state=42).reset_index(drop=True)

    os.makedirs(os.path.dirname(MAP_PATH), exist_ok=True)
    df_map = shuffled[['id', 'stratum']].copy()
    df_map.to_csv(MAP_PATH, index=False)
    print(f"Saved unblinded stratum mapping file to {MAP_PATH}")

    print("Computing entity spans for highlighting...")
    spans_col = []
    for text in shuffled["text"].astype(str):
        spans = [{"start": m.start(), "end": m.end(), "text": m.group(0)} for m in rx_mav.finditer(text)]
        spans_col.append(json.dumps(spans))
    shuffled["entity_spans"] = spans_col

    os.makedirs(os.path.dirname(QUEUE_PATH), exist_ok=True)
    df_queue = pd.DataFrame({
        'id': shuffled['id'].astype(str),
        'full_text': shuffled['text'],
        'human_stance': '',
        'notes': '',
        'entity_spans': shuffled['entity_spans'],
        'parent_id': shuffled['parent_id'],
        'link_id': shuffled['link_id'],
    })

    df_queue.to_csv(QUEUE_PATH, index=False)
    print(f"Saved blinded queue file to {QUEUE_PATH}")
    print(f"Verification: {len(df_queue)} rows written to queue.")
    print(f"Rows with a matched entity span: {(df_queue['entity_spans'] != '[]').sum()} / {len(df_queue)}")
    print(f"Rows with parent_id resolved: {df_queue['parent_id'].notna().sum()} / {len(df_queue)}")


if __name__ == "__main__":
    main()
