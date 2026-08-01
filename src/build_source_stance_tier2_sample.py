"""build_source_stance_tier2_sample.py

Tier 2 (cascade design, see handoff/task_2026-07-28_session_wrapup.md
section 3) needs a larger labeled sample specifically drawn from the
low/mid-confidence band, at full-corpus scale, to train a distilled model
for the cases a cheap classifier can't confidently resolve.

Design note / simplification: the wrap-up describes Tier 1 as a *separate*
cheap classifier trained on frozen MiniLM embeddings. That classifier was
only ever validated on the small 2,809-row curated sample -- it was never
run at full-corpus scale, and no window-level embeddings exist at that
scale either (full-corpus embeddings that do exist are one vector per
whole comment, not per citation window). Rather than build a new
embedding pipeline just to reproduce a confidence signal, this uses the
existing production stance classifier's own softmax margin
(predicted_label's probability minus the second-highest of
p_hostile/p_endorsement/p_other) as the confidence signal for
stratification -- it's already computed at full-corpus scale in
source_mentions_cache.parquet / ats_source_mentions_cache.parquet, and is
the same quantity Tier 1 would need to be *good* at approximating anyway.

Samples from the LOW and MID confidence bands only (bottom ~50% by
margin) -- the high-confidence band is exactly what the cascade design
says doesn't need escalation.

Output: data/processed/source_stance_tier2_sample.parquet
  platform | comment_id | source_key | level | window_text |
  predicted_label | p_hostile | p_endorsement | p_other | margin
"""
import os
import re
import sys

import duckdb
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from build_source_stance import find_url_spans
from stance_window_utils import extract_entity_window, filter_quoted_spans

N_PER_PLATFORM = 3000
RNG_SEED = 42
OUT_PATH = 'data/processed/source_stance_tier2_sample.parquet'


def add_margin(df):
    import numpy as np
    probs = df[['p_hostile', 'p_endorsement', 'p_other']].to_numpy()
    probs_sorted = np.sort(probs, axis=1)  # ascending; top two are last two columns
    df = df.copy()
    df['margin'] = probs_sorted[:, -1] - probs_sorted[:, -2]
    return df


def sample_platform(platform, cache_path, corpus_path, id_col, text_col):
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='4GB'")

    cache_df = con.execute(f"SELECT * FROM '{cache_path}'").df()
    cache_df = add_margin(cache_df)

    # Low/mid band = bottom 50% by margin, computed SEPARATELY per predicted
    # label, not one global cutoff across all three classes.
    #
    # Bug found 2026-07-28: a global cutoff structurally under-samples any
    # class whose margin distribution runs higher than the others. In
    # practice the classifier is far more confident whenever it predicts
    # 'other' than when it predicts hostile/endorsement, so a single global
    # bottom-50% cutoff pulled 'other' almost entirely out of the "uncertain"
    # band (4/5998 rows in one run vs ~9% true base rate) -- leaving a sample
    # that was really "hostile vs endorsement, filtered to the hard cases"
    # while silently calling itself "the uncertain band" across all three
    # labels. That's what produced an implausible ~100% judge/classifier
    # agreement on the non-contaminated subset: the sample had been
    # accidentally narrowed to the easier binary call. Per-label cutoffs
    # guarantee each predicted class contributes its own bottom-50% to the
    # pool, so the combined sample's class mix tracks the true base rate.
    cache_df['_cutoff'] = cache_df.groupby('predicted_label')['margin'].transform('median')
    uncertain = cache_df[cache_df['margin'] <= cache_df['_cutoff']].drop(columns='_cutoff')
    print(f"[{platform}] {len(cache_df):,} total rows, {len(uncertain):,} in low/mid-confidence band "
          f"(per-label median-margin cutoff).")
    print(f"[{platform}] predicted_label mix in uncertain band:\n{uncertain['predicted_label'].value_counts(normalize=True)}")

    sample = uncertain.sample(n=min(N_PER_PLATFORM, len(uncertain)), random_state=RNG_SEED)
    print(f"[{platform}] {len(sample):,} rows sampled from uncertain band, regenerating windows...")

    con.register('sample_df', sample)
    joined = con.execute(f"""
        SELECT s.comment_id, s.source_key, s.level, s.predicted_label,
               s.p_hostile, s.p_endorsement, s.p_other, s.margin, e.{text_col} AS text
        FROM sample_df s
        JOIN '{corpus_path}' e ON e.{id_col} = s.comment_id
    """).df()

    rows = []
    for row in joined.itertuples(index=False):
        if row.level == 'url':
            spans = find_url_spans(row.text, row.source_key)
        else:
            idx = row.text.lower().find(row.source_key.lower())
            spans = [{"start": idx, "end": idx + len(row.source_key), "text": row.source_key}] if idx >= 0 else []
        spans = filter_quoted_spans(row.text, spans)
        if not spans:
            continue
        win = extract_entity_window(row.text, spans)
        rows.append({
            'platform': platform, 'comment_id': row.comment_id, 'source_key': row.source_key,
            'level': row.level, 'window_text': win[:600], 'predicted_label': row.predicted_label,
            'p_hostile': row.p_hostile, 'p_endorsement': row.p_endorsement, 'p_other': row.p_other,
            'margin': row.margin,
        })
    df_out = pd.DataFrame(rows)
    print(f"[{platform}] Final sample: {len(df_out):,} rows.")
    return df_out


def main():
    reddit_sample = sample_platform(
        'reddit',
        'data/processed/source_mentions_cache.parquet',
        'data/processed/empath_scores_full_mapped.parquet',
        'id', 'text',
    )
    ats_sample = sample_platform(
        'ats',
        'data/processed/ats_source_mentions_cache.parquet',
        'data/processed/ats_comments_final.parquet',
        'post_id', 'body',
    )
    combined = pd.concat([reddit_sample, ats_sample], ignore_index=True)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    combined.to_parquet(OUT_PATH, index=False)
    print(f"\nSaved {len(combined):,} total sample rows to {OUT_PATH}")
    print(combined.groupby('platform').size())


if __name__ == '__main__':
    main()
