#!/usr/bin/env python3
"""Builds the stratified and blinded queue for maverick stance checking.

Draws from pure r/conspiracy comments matching has_maverick == 1.
Stratum A: high_traction == 1 (up to 120 comments)
Stratum B: high_traction == 0 (up to 120 comments)
"""
import os
import sys
import json
import numpy as np
import pandas as pd
import duckdb

sys.path.insert(0, os.path.dirname(__file__))
from refine_thesis_models import build_regex
from rerun_refined_regressions_v2 import load_entities_split_corrected

STAGED_PATH = 'data/processed/research_corpus_staged_scores_full21m.parquet'
EMPATH_PATH = 'data/processed/empath_scores_full.parquet'
THREAD_PATH = 'data/processed/thread_quality_metrics.csv'
PRESENCE_PATH = 'data/processed/thread_insider_presence.csv'
BRIGADE_PATH = 'data/processed/comment_brigade_flags.csv'

QUEUE_PATH = 'data/hitl/queue_maverick_stance.csv'
MAP_PATH = 'data/processed/maverick_stance_queue_strata_map.csv'

def main():
    print("=== Building Maverick Stance Spot-Check Queue ===")

    # 1. Compile mavericks regex
    mavericks, _, _ = load_entities_split_corrected()
    rx_mav = build_regex(mavericks)
    print(f"Loaded {len(mavericks)} mavericks for regex construction.")

    # 2. Query identical population from rerun_refined_regressions_v2.py (with parent_id/link_id)
    con = duckdb.connect()
    print("Re-deriving r/conspiracy pure comment population...")
    query = f"""
        SELECT s.id, e.text, e.upvotes, e.char_length, s.pe_prob, s.ps_prob, e.has_link, e.parent_id, e.link_id
        FROM '{STAGED_PATH}' s
        JOIN '{EMPATH_PATH}' e ON s.id = e.id
        JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
        LEFT JOIN '{PRESENCE_PATH}' p ON SUBSTR(e.link_id, 4) = p.post_id
        LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
        WHERE t.elasticity_ratio <= (SELECT quantile(elasticity_ratio, 0.33) FROM '{THREAD_PATH}')
          AND t.is_high_crosspost = 0
          AND p.insider_presence_ratio >= 0.75
          AND COALESCE(b.brigade_upvote_flag, 0) = 0
          AND COALESCE(b.brigade_downvote_flag, 0) = 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
    """
    df_con = con.execute(query).df()
    print(f"Successfully loaded {len(df_con):,} pure r/conspiracy comments.")

    # 3. Derive variables
    df_con['has_maverick'] = df_con['text'].apply(lambda x: 1 if bool(rx_mav.search(str(x))) else 0)
    df_con['high_traction'] = (df_con['upvotes'] >= 5).astype(int)

    # 4. Print population crosstab
    print("\n--- Population Crosstab (has_maverick x high_traction) ---")
    ct = pd.crosstab(df_con['has_maverick'], df_con['high_traction'])
    print(ct)
    print("----------------------------------------------------------")

    # Filter to has_maverick == 1
    df_mav_exp = df_con[df_con['has_maverick'] == 1].copy()
    print(f"Total positive has_maverick cases in population: {len(df_mav_exp):,}")

    # 5. Extract strata
    df_stratum_a = df_mav_exp[df_mav_exp['high_traction'] == 1]
    df_stratum_b = df_mav_exp[df_mav_exp['high_traction'] == 0]

    n_stratum_a_avail = len(df_stratum_a)
    n_stratum_b_avail = len(df_stratum_b)

    print(f"Available Stratum A (high_traction == 1): {n_stratum_a_avail}")
    print(f"Available Stratum B (high_traction == 0): {n_stratum_b_avail}")

    # Draw samples
    sample_a = df_stratum_a.sample(n=min(120, n_stratum_a_avail), random_state=42).copy()
    sample_b = df_stratum_b.sample(n=min(120, n_stratum_b_avail), random_state=42).copy()

    print(f"\nSampled {len(sample_a)} rows from Stratum A.")
    print(f"Sampled {len(sample_b)} rows from Stratum B.")

    if len(sample_a) < 40:
        print(f"WARNING: Stratum A is extremely sparse ({len(sample_a)} rows)!")
    if len(sample_b) < 40:
        print(f"WARNING: Stratum B is extremely sparse ({len(sample_b)} rows)!")

    # Assign strata labels for our unblinded mapping
    sample_a['stratum'] = 'Stratum A (high_traction == 1)'
    sample_b['stratum'] = 'Stratum B (high_traction == 0)'

    # Combine samples and shuffle with seed 42 to blind
    combined = pd.concat([sample_a, sample_b], ignore_index=True)
    shuffled = combined.sample(frac=1, random_state=42).reset_index(drop=True)

    # 6. Save the non-shown mapping file
    os.makedirs(os.path.dirname(MAP_PATH), exist_ok=True)
    df_map = shuffled[['id', 'stratum']].copy()
    df_map.to_csv(MAP_PATH, index=False)
    print(f"Saved unblinded stratum mapping file to {MAP_PATH}")

    # 7. Compute entity spans for highlighting
    print("Computing entity spans for highlighting...")
    spans_col = []
    for text in shuffled["text"].astype(str):
        spans = [{"start": m.start(), "end": m.end(), "text": m.group(0)} for m in rx_mav.finditer(text)]
        spans_col.append(json.dumps(spans))
    shuffled["entity_spans"] = spans_col

    # 8. Write blinded queue file
    os.makedirs(os.path.dirname(QUEUE_PATH), exist_ok=True)
    
    # Construct blinded DataFrame with the exact target schema
    df_queue = pd.DataFrame({
        'id': shuffled['id'].astype(str),
        'full_text': shuffled['text'],
        'human_stance': '',
        'notes': '',
        'entity_spans': shuffled['entity_spans'],
        'parent_id': shuffled['parent_id'],
        'link_id': shuffled['link_id']
    })

    df_queue.to_csv(QUEUE_PATH, index=False)
    print(f"Saved blinded queue file to {QUEUE_PATH}")
    print(f"Verification: {len(df_queue)} rows written to queue.")
    print(f"Rows with a matched entity span: {(df_queue['entity_spans'] != '[]').sum()} / {len(df_queue)}")
    print(f"Rows with parent_id resolved: {df_queue['parent_id'].notna().sum()} / {len(df_queue)}")

if __name__ == "__main__":
    main()
