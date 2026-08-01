"""build_entity_stance_aiitl_sample.py

Stratified sample of entity-mention stance-classifier windows (both
platforms), for an AIITL (small open-weight LLM, no paid API) validation
check -- the same technique already proven on the citation-window pipeline
(source_stance_aiitl_judged), applied to the entity dimension instead.
Directly answers the project lead's stated concern: the current headline
"media figures vs whistleblowers/leakers" findings rest on entities that
"maybe aren't the right ones" -- this gives an LLM-audited check at much
larger scale (2000+ rows) than the 99-row purely-human HITL queue, across
the actual entities used in per_entity_stance_breakdown.csv.

Output: data/processed/entity_stance_aiitl_sample.parquet
  platform | entity_key | construct | predicted_label | text_window
"""
import os
import sys

import duckdb
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from stance_window_utils import extract_entity_window, filter_quoted_spans

N_PER_PLATFORM = 1500
RNG_SEED = 42
OUT_PATH = 'data/processed/entity_stance_aiitl_sample.parquet'


def sample_reddit():
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='4GB'")

    entities = pd.read_csv('data/processed/per_entity_stance_breakdown.csv')
    target_entities = entities['entity'].tolist()
    print(f"[reddit] {len(target_entities)} entities from per_entity_stance_breakdown.csv")

    escaped = ",".join("'" + e.replace("'", "''") + "'" for e in target_entities)
    cache_df = con.execute(
        "SELECT * FROM read_parquet('data/processed/entity_mentions_cache_2stage_pooled.parquet') "
        f"WHERE entity_key IN ({escaped})"
    ).df()

    n_per_entity = max(1, N_PER_PLATFORM // max(1, len(target_entities)))
    sample = cache_df.groupby('entity_key', group_keys=False).apply(
        lambda g: g.sample(n=min(len(g), n_per_entity), random_state=RNG_SEED), include_groups=True
    )
    print(f"[reddit] {len(sample):,} rows sampled, regenerating windows...")

    con.register('sample_df', sample)
    joined = con.execute("""
        SELECT s.comment_id, s.entity_key, s.construct, s.predicted_label, e.text
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
            'platform': 'reddit', 'entity_key': row.entity_key, 'construct': row.construct,
            'predicted_label': row.predicted_label, 'text_window': win[:600],
        })
    df_out = pd.DataFrame(rows)
    print(f"[reddit] Final sample: {len(df_out):,} rows.")
    return df_out


def sample_ats():
    df = pd.read_parquet('data/processed/ats_entity_examples_stance.parquet')
    entities = pd.read_csv('data/processed/per_entity_stance_breakdown.csv')['entity'].tolist()
    df = df[df['entity_key'].isin(entities)]
    n_per_entity = max(1, N_PER_PLATFORM // max(1, df['entity_key'].nunique()))
    sample = df.groupby('entity_key', group_keys=False).apply(
        lambda g: g.sample(n=min(len(g), n_per_entity), random_state=RNG_SEED), include_groups=True
    )
    out = sample[['entity_key', 'construct', 'predicted_label', 'text_window']].copy()
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
