"""per_entity_stance_breakdown.py

Breaks the pooled has_maverick/has_consensus_expert stance results down by
INDIVIDUAL entity (Alex Jones, Edward Snowden, Anthony Fauci, ...) instead
of treating "maverick" and "consensus expert" as single lumped buckets.

This refactored version loads pre-computed per-entity scores directly from the centralized long-format cache:
  - data/processed/entity_mentions_cache_2stage_pooled.parquet

This completely avoids redundant, expensive regex matches and model scoring passes.
"""
import os
import sys
import argparse
import numpy as np
import pandas as pd
import duckdb

sys.path.insert(0, os.path.dirname(__file__))
from rerun_refined_regressions_v2 import (
    STAGED_PATH, EMPATH_PATH, THREAD_PATH, BRIGADE_PATH, PRESENCE_PATH,
)

CACHE_PATH = 'data/processed/entity_mentions_cache_2stage_pooled.parquet'
CLASSES = ['hostile', 'endorsement', 'other']
MIN_MENTIONS_TO_REPORT = 20


def summarize(long_df, construct_label, classes):
    if long_df.empty:
        return pd.DataFrame()
        
    # Pre-compute indicator columns for fast aggregation (avoiding slow python applies)
    long_df['is_hostile'] = (long_df['predicted_label'] == 'hostile').astype(float)
    long_df['is_endorsement'] = (long_df['predicted_label'] == 'endorsement').astype(float)
    long_df['is_other'] = (long_df['predicted_label'] == 'other').astype(float)

    g = long_df.groupby('entity')
    summary = g.size().rename('mention_count').reset_index()
    
    summary['mean_p_hostile'] = g['p_hostile'].mean().values
    summary['mean_p_endorsement'] = g['p_endorsement'].mean().values
    summary['mean_p_other'] = g['p_other'].mean().values
    
    summary['pct_predicted_hostile'] = g['is_hostile'].mean().values
    summary['pct_predicted_endorsement'] = g['is_endorsement'].mean().values
    summary['pct_predicted_other'] = g['is_other'].mean().values
    
    summary['pct_list_dump'] = g['is_list_dump'].mean().values
    summary['pct_hostile'] = summary['pct_predicted_hostile']
    summary['construct'] = construct_label
    
    return summary.sort_values('mention_count', ascending=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--population', default='unfiltered', choices=['unfiltered', 'pure'],
                         help="'unfiltered' = crosspost/brigade-excluded only (default); "
                              "'pure' = also elasticity<=33rd percentile + insider-presence>=0.75, "
                              "the curated core-community population used elsewhere in this project.")
    args = parser.parse_args()
    
    out_path = f'data/processed/per_entity_stance_breakdown_{args.population}.csv'

    print(f"=== Per-entity stance breakdown (r/conspiracy, {args.population} population) ===")

    if not os.path.exists(CACHE_PATH):
        print(f"Missing centralized cache: {CACHE_PATH}. Run build_entity_mentions_cache.py first.")
        sys.exit(1)

    print(f"Loading centralized mentions cache from {CACHE_PATH}...")
    cache_df = pd.read_parquet(CACHE_PATH)
    print(f"Loaded cache containing {len(cache_df):,} rows.")

    # Filter cache to only per-entity rows (excluding construct-merged rows)
    per_entity_cache = cache_df[~cache_df['entity_key'].str.startswith('merged_')].copy()

    con = duckdb.connect()
    print(f"Loading r/conspiracy {args.population} population IDs...")
    if args.population == 'pure':
        query = f"""
            SELECT s.id
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
    else:
        query = f"""
            SELECT s.id
            FROM '{STAGED_PATH}' s
            JOIN '{EMPATH_PATH}' e ON s.id = e.id
            JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
            LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
            WHERE t.is_high_crosspost = 0
              AND COALESCE(b.brigade_upvote_flag, 0) = 0
              AND COALESCE(b.brigade_downvote_flag, 0) = 0
            QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
        """
    pop_df = con.execute(query).df()
    pop_ids = set(pop_df['id'].astype(str))
    print(f"  Loaded {len(pop_ids):,} active population IDs.")

    # Filter cache rows to those in the active population
    long_df = per_entity_cache[per_entity_cache['comment_id'].astype(str).isin(pop_ids)].copy()
    long_df = long_df.rename(columns={'entity_key': 'entity'})
    print(f"  Filtered cache to {len(long_df):,} mentions matching active population.")

    print("\nBuilding per-entity long table (maverick)...")
    long_mav = long_df[long_df['construct'] == 'maverick'].copy()
    print("Building per-entity long table (consensus)...")
    long_con = long_df[long_df['construct'] == 'consensus'].copy()

    summary_mav = summarize(long_mav, 'maverick', CLASSES)
    summary_con = summarize(long_con, 'consensus', CLASSES)
    
    summary = pd.concat([summary_mav, summary_con], ignore_index=True)
    summary.to_csv(out_path, index=False)
    print(f"\nSaved full per-entity breakdown to {out_path}")

    print(f"\n=== Top 30 mavericks by mention count (min {MIN_MENTIONS_TO_REPORT} mentions) ===")
    top_mav = summary_mav[summary_mav['mention_count'] >= MIN_MENTIONS_TO_REPORT].head(30)
    print(top_mav[['entity', 'mention_count', 'pct_predicted_hostile', 'pct_predicted_endorsement', 'pct_predicted_other']].to_string(index=False))

    print(f"\n=== Top 30 consensus figures by mention count (min {MIN_MENTIONS_TO_REPORT} mentions) ===")
    top_con = summary_con[summary_con['mention_count'] >= MIN_MENTIONS_TO_REPORT].head(30)
    print(top_con[['entity', 'mention_count', 'pct_predicted_hostile', 'pct_predicted_endorsement', 'pct_predicted_other']].to_string(index=False))

    # Direct test of the "prominence predicts hostility" hypothesis
    for label, s in [("maverick", summary_mav), ("consensus", summary_con)]:
        s_filtered = s[s['mention_count'] >= MIN_MENTIONS_TO_REPORT]
        if len(s_filtered) >= 5:
            corr = s_filtered['mention_count'].corr(s_filtered['pct_hostile'], method='spearman')
            print(f"\nSpearman correlation (mention_count vs pct_hostile), {label}: {corr:.3f} "
                  f"(n={len(s_filtered)} entities)")

    print("\nDone.")


if __name__ == "__main__":
    main()
