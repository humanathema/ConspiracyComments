"""build_domain_epistemic_type_sample.py

Prepares top-cited domains (both platforms) with example citation windows,
for an AIITL (small open-weight LLM, no paid API) classifier to assign an
epistemic-type category. The existing domain_classification_lookup.csv is
a 269-domain manual list that only covers ~0.5% of ATS's 25,024 distinct
cited domains -- this is a first-pass automated expansion of that
coverage for the domains that actually carry citation volume, not an
attempt to cover the long tail.

Reuses the same window-extraction helpers as build_source_stance_aiitl_sample.py.

Output: data/processed/domain_epistemic_type_sample.parquet
  platform | domain | mention_count | example_windows (list[str])
"""
import os
import sys

import duckdb
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from build_source_stance import find_url_spans
from stance_window_utils import extract_entity_window, filter_quoted_spans

TOP_N = 400
OUT_PATH = 'data/processed/domain_epistemic_type_sample.parquet'


def sample_platform(platform, cache_path, corpus_path, id_col, text_col, breakdown_domain_path):
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='4GB'")

    dom_bd = pd.read_csv(breakdown_domain_path).sort_values('mention_count', ascending=False)
    target_domains = dom_bd.head(TOP_N)['domain'].tolist()
    print(f"[{platform}] Top {len(target_domains)} domains by mention_count selected.")

    cache_df = con.execute(f"SELECT * FROM '{cache_path}'").df()
    dom_rows = cache_df[(cache_df['level'] == 'domain') & (cache_df['source_key'].isin(target_domains))]

    sample = dom_rows.groupby('source_key', group_keys=False).apply(
        lambda g: g.sample(n=min(len(g), 3), random_state=42)
    )
    con.register('sample_df', sample)
    joined = con.execute(f"""
        SELECT s.comment_id, s.source_key, e.{text_col} AS text
        FROM sample_df s
        JOIN '{corpus_path}' e ON e.{id_col} = s.comment_id
    """).df()

    windows_by_domain = {}
    for row in joined.itertuples(index=False):
        idx = row.text.lower().find(row.source_key.lower())
        spans = [{"start": idx, "end": idx + len(row.source_key), "text": row.source_key}] if idx >= 0 else []
        spans = filter_quoted_spans(row.text, spans)
        if not spans:
            continue
        win = extract_entity_window(row.text, spans)
        windows_by_domain.setdefault(row.source_key, []).append(win[:300])

    rows = []
    for domain in target_domains:
        wins = windows_by_domain.get(domain, [])
        if not wins:
            continue
        mc = int(dom_bd[dom_bd['domain'] == domain]['mention_count'].iloc[0])
        rows.append({'platform': platform, 'domain': domain, 'mention_count': mc, 'example_windows': wins})

    df_out = pd.DataFrame(rows)
    print(f"[{platform}] {len(df_out):,} domains with example windows prepared.")
    return df_out


def main():
    reddit_sample = sample_platform(
        'reddit',
        'data/processed/source_mentions_cache.parquet',
        'data/processed/empath_scores_full_mapped.parquet',
        'id', 'text',
        'data/processed/domain_stance_breakdown.csv',
    )
    ats_sample = sample_platform(
        'ats',
        'data/processed/ats_source_mentions_cache.parquet',
        'data/processed/ats_comments_final.parquet',
        'post_id', 'body',
        'data/processed/ats_domain_stance_breakdown.csv',
    )
    combined = pd.concat([reddit_sample, ats_sample], ignore_index=True)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    combined.to_parquet(OUT_PATH, index=False)
    print(f"\nSaved {len(combined):,} total domain rows to {OUT_PATH}")


if __name__ == '__main__':
    main()
