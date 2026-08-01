"""build_entity_stance_tier2_sample.py

Entity-mention counterpart to build_source_stance_tier2_sample.py -- see
that file's docstring for the confidence-signal design note (uses the
existing production stance classifier's own softmax margin, already
computed at full-corpus scale, rather than a new embedding pipeline).

Samples from the LOW and MID confidence bands only (bottom ~50% by
margin).

Output: data/processed/entity_stance_tier2_sample.parquet
  platform | comment_id | entity_key | construct | predicted_label |
  p_hostile | p_endorsement | p_other | margin | text_window
"""
import os
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from stance_window_utils import extract_entity_window, filter_quoted_spans

N_PER_PLATFORM = 3000
RNG_SEED = 42
OUT_PATH = 'data/processed/entity_stance_tier2_sample.parquet'


def add_margin(df):
    probs = df[['p_hostile', 'p_endorsement', 'p_other']].to_numpy()
    probs_sorted = np.sort(probs, axis=1)
    df = df.copy()
    df['margin'] = probs_sorted[:, -1] - probs_sorted[:, -2]
    return df


def sample_reddit():
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='4GB'")

    cache_df = con.execute(
        "SELECT * FROM read_parquet('data/processed/entity_mentions_cache_2stage_pooled.parquet')"
    ).df()
    cache_df = add_margin(cache_df)
    cutoff = cache_df['margin'].quantile(0.5)
    uncertain = cache_df[cache_df['margin'] <= cutoff]
    print(f"[reddit] {len(cache_df):,} total rows, {len(uncertain):,} in low/mid-confidence band "
          f"(margin <= {cutoff:.3f}).")

    sample = uncertain.sample(n=min(N_PER_PLATFORM, len(uncertain)), random_state=RNG_SEED)
    print(f"[reddit] {len(sample):,} rows sampled, regenerating windows...")

    con.register('sample_df', sample)
    joined = con.execute("""
        SELECT s.comment_id, s.entity_key, s.construct, s.predicted_label,
               s.p_hostile, s.p_endorsement, s.p_other, s.margin, e.text
        FROM sample_df s
        JOIN read_parquet('data/processed/empath_scores_full_mapped.parquet') e ON e.id = s.comment_id
    """).df()

    rows = []
    for row in joined.itertuples(index=False):
        idx = row.text.lower().find(row.entity_key.lower())
        spans = [{"start": idx, "end": idx + len(row.entity_key), "text": row.entity_key}] if idx >= 0 else []
        spans = filter_quoted_spans(row.text, spans)
        if not spans:
            continue
        win = extract_entity_window(row.text, spans)
        rows.append({
            'platform': 'reddit', 'comment_id': row.comment_id, 'entity_key': row.entity_key,
            'construct': row.construct, 'predicted_label': row.predicted_label,
            'p_hostile': row.p_hostile, 'p_endorsement': row.p_endorsement, 'p_other': row.p_other,
            'margin': row.margin, 'text_window': win[:600],
        })
    df_out = pd.DataFrame(rows)
    print(f"[reddit] Final sample: {len(df_out):,} rows.")
    return df_out


def sample_ats():
    df = pd.read_parquet('data/processed/ats_entity_examples_stance.parquet')
    df = add_margin(df)
    cutoff = df['margin'].quantile(0.5)
    uncertain = df[df['margin'] <= cutoff]
    print(f"[ats] {len(df):,} total rows, {len(uncertain):,} in low/mid-confidence band "
          f"(margin <= {cutoff:.3f}).")

    sample = uncertain.sample(n=min(N_PER_PLATFORM, len(uncertain)), random_state=RNG_SEED)
    out = sample[['comment_id', 'entity_key', 'construct', 'predicted_label',
                  'p_hostile', 'p_endorsement', 'p_other', 'margin', 'text_window']].copy()
    out['platform'] = 'ats'
    out['text_window'] = out['text_window'].str.slice(0, 600)
    print(f"[ats] Final sample: {len(out):,} rows.")
    return out


def main():
    reddit_sample = sample_reddit()
    ats_sample = sample_ats()
    combined = pd.concat([reddit_sample, ats_sample], ignore_index=True)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    combined.to_parquet(OUT_PATH, index=False)
    print(f"\nSaved {len(combined):,} total sample rows to {OUT_PATH}")
    print(combined.groupby(['platform', 'construct']).size())


if __name__ == '__main__':
    main()
