#!/usr/bin/env python3
"""Builds the stratified and blinded queue for consensus expert stance checking.

Draws from pure r/conspiracy comments matching has_consensus_expert == 1.
Stratum A: high_traction == 1 (up to 120 comments)
Stratum B: high_traction == 0 (up to 120 comments)
"""
import os
import sys
import re
import numpy as np
import pandas as pd
import duckdb

sys.path.insert(0, os.path.dirname(__file__))
from refine_thesis_models import build_regex
from consensus_experts_verified import VERIFIED_CONSENSUS_EXPERTS

STAGED_PATH = 'data/processed/research_corpus_staged_scores_full21m.parquet'
EMPATH_PATH = 'data/processed/empath_scores_full.parquet'
THREAD_PATH = 'data/processed/thread_quality_metrics.csv'
PRESENCE_PATH = 'data/processed/thread_insider_presence.csv'
BRIGADE_PATH = 'data/processed/comment_brigade_flags.csv'

QUEUE_PATH = 'data/hitl/queue_consensus_stance.csv'
MAP_PATH = 'data/processed/consensus_stance_queue_strata_map.csv'

CODING_DEFINITIONS = """# coding definitions:
# endorsement — figure/institution treated as legitimate backing for the commenter's own point
# hostile — figure is target of blame, accusation, mockery, or is quoted against itself ("even the CDC admits...")
# neutral — factual/descriptive reference, no clear evaluative stance
# ambiguous — genuinely unclear or mixed
"""

def main():
    print("=== Building Consensus Expert Stance Spot-Check Queue ===")

    # 1. Compile consensus regex
    consensus = list(VERIFIED_CONSENSUS_EXPERTS)
    rx_con = build_regex(consensus)
    print(f"Loaded {len(consensus)} consensus experts for regex construction.")

    # 2. Query identical population from rerun_refined_regressions_v2.py
    con = duckdb.connect()
    print("Re-deriving r/conspiracy pure comment population...")
    query = f"""
        SELECT s.id, e.text, e.upvotes, e.char_length, s.pe_prob, s.ps_prob, e.has_link
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
    """
    df_con = con.execute(query).df()
    print(f"Successfully loaded {len(df_con):,} pure r/conspiracy comments.")

    # 3. Derive variables
    df_con['has_consensus_expert'] = df_con['text'].apply(lambda x: 1 if bool(rx_con.search(str(x))) else 0)
    df_con['high_traction'] = (df_con['upvotes'] >= 5).astype(int)

    # 4. Print the exact crosstab
    print("\n--- Population Crosstab (has_consensus_expert x high_traction) ---")
    ct = pd.crosstab(df_con['has_consensus_expert'], df_con['high_traction'])
    print(ct)
    print("------------------------------------------------------------------")

    # Filter to has_consensus_expert == 1
    df_con_exp = df_con[df_con['has_consensus_expert'] == 1].copy()
    print(f"Total positive has_consensus_expert cases in population: {len(df_con_exp):,}")

    # 5. Extract strata
    df_stratum_a = df_con_exp[df_con_exp['high_traction'] == 1]
    df_stratum_b = df_con_exp[df_con_exp['high_traction'] == 0]

    n_stratum_a_avail = len(df_stratum_a)
    n_stratum_b_avail = len(df_stratum_b)

    print(f"Available Stratum A (high_traction == 1): {n_stratum_a_avail}")
    print(f"Available Stratum B (high_traction == 0): {n_stratum_b_avail}")

    # Draw samples
    sample_a = df_stratum_a.sample(n=min(120, n_stratum_a_avail), random_state=42).copy()
    sample_b = df_stratum_b.sample(n=min(120, n_stratum_b_avail), random_state=42).copy()

    # Log sizes and flag sparsity warnings
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

    # 7. Write blinded queue file
    os.makedirs(os.path.dirname(QUEUE_PATH), exist_ok=True)
    
    # Construct blinded DataFrame
    df_queue = pd.DataFrame({
        'id': shuffled['id'].astype(str),
        'full_text': shuffled['text'],
        'human_stance': '',
        'notes': ''
    })

    df_queue.to_csv(QUEUE_PATH, index=False)
    print(f"Saved blinded queue file to {QUEUE_PATH}")

    # Write separate CODEBOOK.md file
    codebook_path = 'data/hitl/queue_consensus_stance_CODEBOOK.md'
    coding_definitions_md = """# Consensus Stance Coding Definitions

Please use these definitions when rating the consensus stance:

- **endorsement** — figure/institution treated as legitimate backing for the commenter's own point (e.g. "the CDC's own study confirmed...", used approvingly)
- **hostile** — figure is target of blame, accusation, mockery, or is quoted against itself ("even the CDC admits...", using their words as a weapon)
- **neutral** — factual/descriptive reference, no clear evaluative stance (e.g. "Fauci was NIAID director")
- **ambiguous** — genuinely unclear or mixed
"""
    with open(codebook_path, 'w', encoding='utf-8') as f:
        f.write(coding_definitions_md)
    print(f"Saved separate coding definitions to {codebook_path}")
    print("Blinded queue columns checked: exactly id, full_text, human_stance, notes (no traction/upvote data).")

if __name__ == "__main__":
    main()
