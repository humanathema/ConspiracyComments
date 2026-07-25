"""src/run_full_corpus_topic_era_analysis.py

Full-corpus, granular-topic successor to run_pure_50k_topic_analysis.py --
see handoff/task_topic_era_rerun_corrected_constructs.md for the original
scope (corrected entity lists, 5-tier link taxonomy, hs_prob) and the
2026-07-24 conversation for why this went further than that task asked:

1. Population: the full pure r/conspiracy population (~2M comments, same
   elasticity/insider-presence/brigade filters as the original script's
   query), not a 50k sample. The sample existed to solve upvote-selection
   bias in the OLD model's live BERTopic .transform() -- moot now that
   topic assignment is already materialized for the whole corpus for free.
2. Topic granularity: the original stratified by a hardcoded 6-bucket
   Super-Topic map keyed to the OLD 97-topic model's topic IDs -- those IDs
   don't correspond to the same topics in the new 100-topic model at all
   (BERTopic topic IDs aren't stable across refits), so reusing that map
   would silently misclassify. This uses granular topic_name from the new
   model directly, matching the "granular over super-topic" call made
   earlier this session (demonstrated concretely: the topic x
   credentials-problem crosstab found real effects that a 6-bucket
   collapse would have averaged away).
3. Trade-off, stated plainly: more N per cell (more power to detect real
   effects the 50k/6-bucket version couldn't) but also more simultaneous
   tests (up to ~100 topics vs 6 buckets), which pushes the Bonferroni
   threshold stricter. Both cuts are reported side by side, not framed as
   a strict improvement.

Population, entity lists, link taxonomy, and hs_prob join all reuse the
exact same helpers as run_pure_50k_topic_analysis.py -- only the topic
source and the population size changed.
"""
import os
import sys

os.environ["NUMBA_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import numpy as np
import pandas as pd
import duckdb
import statsmodels.formula.api as smf
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from rerun_refined_regressions_v2 import load_entities_split_corrected, compute_has_maverick, compute_has_consensus_expert
from refine_thesis_models import build_regex
from run_link_source_tier_regressions import determine_link_source_tier, build_source_authority_lookup
from combined_maverick_detector import load_maverick_disambiguation_lookup
from consensus_disambiguation_lookup import load_consensus_disambiguation_lookup
from run_pure_50k_topic_analysis import run_robust_regression, OUT_REGRESSIONS_PATH as OLD_50K_RESULTS_PATH

STAGED_PATH = 'data/processed/research_corpus_staged_scores_full21m.parquet'
HEDGED_SUSPICION_PATH = 'data/processed/hedged_suspicion_scores_full21m.parquet'
TOPIC_MAPPED_PATH = 'data/processed/empath_scores_full_mapped.parquet'
THREAD_PATH = 'data/processed/thread_quality_metrics.csv'
PRESENCE_PATH = 'data/processed/thread_insider_presence.csv'
BRIGADE_PATH = 'data/processed/comment_brigade_flags.csv'

OUT_RESULTS_PATH = 'data/processed/topic_time_regression_results_full_corpus.csv'
OUT_COMPARISON_PATH = 'data/processed/topic_era_50k_vs_full_corpus_comparison.csv'

MIN_STRATUM_N = 200
MIN_CONSENSUS_N = 15


def load_full_population():
    print("\n--- Phase 0: Loading the full pure r/conspiracy population (no sampling) ---")
    con = duckdb.connect()
    con.execute("SET memory_limit='3GB'; SET threads=3;")

    query = f"""
        SELECT s.id, e.author, e.created_utc, e.upvotes, e.char_length, s.pe_prob, s.ps_prob,
               h.hs_prob, e.has_link, e.text, e.assigned_topic, e.topic_name,
               SUBSTR(e.link_id, 4) AS post_id
        FROM '{STAGED_PATH}' s
        JOIN '{TOPIC_MAPPED_PATH}' e ON s.id = e.id
        JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
        LEFT JOIN '{PRESENCE_PATH}' p ON SUBSTR(e.link_id, 4) = p.post_id
        LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
        LEFT JOIN '{HEDGED_SUSPICION_PATH}' h ON s.id = h.id
        WHERE t.elasticity_ratio <= (SELECT quantile(elasticity_ratio, 0.33) FROM '{THREAD_PATH}')
          AND t.is_high_crosspost = 0
          AND p.insider_presence_ratio >= 0.75
          AND COALESCE(b.brigade_upvote_flag, 0) = 0
          AND COALESCE(b.brigade_downvote_flag, 0) = 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
    """
    df = con.execute(query).df()
    print(f"Loaded {len(df):,} rows (full pure population, topic already assigned).")
    return df


def add_epistemic_features(df):
    print("\n--- Phase 1: Feature Engineering & Entity Flagging ---")
    mavericks, canon, consensus = load_entities_split_corrected()
    rx_mav = build_regex(mavericks)
    rx_can = build_regex(canon)
    rx_con = build_regex(consensus)

    print("Loading disambiguation lookups...")
    maverick_lookup = load_maverick_disambiguation_lookup()
    consensus_lookup = load_consensus_disambiguation_lookup()

    print("Flagging entity mentions...")
    df['has_maverick'] = compute_has_maverick(df, rx_mav, maverick_lookup)
    df['has_canonical_expert'] = df['text'].apply(lambda x: 1 if bool(rx_can.search(str(x))) else 0)
    df['has_consensus_expert'] = compute_has_consensus_expert(df, rx_con, consensus_lookup)

    print("Building source authority and classifying link tiers...")
    build_source_authority_lookup()
    df['link_source_tier'] = df.apply(lambda r: determine_link_source_tier(r['text'], r['has_link']), axis=1)
    for tier in ['mainstream_reliable', 'mainstream_imperfect', 'alt_media', 'aggregator_or_platform', 'unmatched_link']:
        df[f'link_{tier}'] = (df['link_source_tier'] == tier).astype(int)

    df['log_char_length'] = np.log(df['char_length'] + 1)
    df['log_upvotes'] = np.log(df['upvotes'] - df['upvotes'].min() + 1)
    median_upvotes = df['upvotes'].median()
    print(f"Defining high_traction as upvotes >= {median_upvotes:.1f} (median of full population)")
    df['high_traction'] = (df['upvotes'] >= median_upvotes).astype(int)

    df['pe_prob'] = df['pe_prob'].fillna(0.0)
    df['ps_prob'] = df['ps_prob'].fillna(0.0)
    df['hs_prob'] = df['hs_prob'].fillna(0.0)

    df['dt'] = pd.to_datetime(df['created_utc'], unit='s')
    df['year'] = df['dt'].dt.year
    return df


def run_stratified_regressions(df):
    print("\n--- Phase 2: Fitting Stratified Regressions (granular topic x era, naive cov only) ---")
    formula = (
        "high_traction ~ pe_prob + ps_prob + hs_prob + "
        "link_mainstream_reliable + link_mainstream_imperfect + link_alt_media + link_aggregator_or_platform + link_unmatched_link + "
        "has_maverick + has_canonical_expert + has_consensus_expert + log_char_length"
    )
    results = []

    print("Fitting models by granular topic...")
    topic_counts = df['topic_name'].value_counts()
    eligible_topics = topic_counts[topic_counts >= MIN_STRATUM_N].index.tolist()
    print(f"{len(eligible_topics)} of {df['topic_name'].nunique()} topics clear the N >= {MIN_STRATUM_N} floor")
    for topic in eligible_topics:
        df_sub = df[df['topic_name'] == topic]
        res = run_robust_regression(formula, df_sub, f"Topic: {topic}")
        results.extend(res)

    print("\nFitting models by temporal era...")
    # Label kept identical to run_pure_50k_topic_analysis.py's era names so the
    # old-vs-new comparison below can match strata by exact string -- the mask
    # itself (year >= 2020, no upper bound) already covers through 2026, the
    # "2025" in the label is stale in BOTH scripts but changing it here would
    # silently break the comparison join, so it's flagged in the print instead.
    eras = [
        ("Pre-2016 Era (2008-2015)", df['year'] <= 2015),
        ("Political Realignment Era (2016-2019)", (df['year'] >= 2016) & (df['year'] <= 2019)),
        ("Pandemic & Modern Era (2020-2025)", df['year'] >= 2020),
    ]
    print("Note: 'Pandemic & Modern Era (2020-2025)' label is stale in both the old and new "
          "scripts -- the underlying mask (year >= 2020) actually covers through 2026 "
          "(1,283,265 rows from 2025, 529,615 from 2026 in the full mapped corpus).")
    for era_name, mask in eras:
        df_sub = df[mask]
        print(f"  Era: {era_name:<45} | N = {len(df_sub):,}")
        if len(df_sub) >= MIN_STRATUM_N:
            res = run_robust_regression(formula, df_sub, f"Era: {era_name}")
            results.extend(res)

    df_results = pd.DataFrame(results)
    df_results.to_csv(OUT_RESULTS_PATH, index=False)
    print(f"Saved {len(df_results):,} coefficient rows to {OUT_RESULTS_PATH}")
    return df_results


def compare_old_vs_new(df_new):
    print("\n--- Phase 3: Old (50k/6-bucket) vs New (full-corpus/granular) comparison ---")
    if not os.path.exists(OLD_50K_RESULTS_PATH):
        print(f"Old results not found at {OLD_50K_RESULTS_PATH}, skipping comparison.")
        return

    df_old = pd.read_csv(OLD_50K_RESULTS_PATH)
    df_old_ols = df_old[df_old['model_type'] == 'OLS (Log Upvotes)'].dropna(subset=['pvalue'])
    df_new_ols = df_new[df_new['model_type'] == 'OLS (Log Upvotes)'].dropna(subset=['pvalue'])

    n_old = len(df_old_ols)
    n_new = len(df_new_ols)
    alpha_old = 0.05 / n_old if n_old else float('nan')
    alpha_new = 0.05 / n_new if n_new else float('nan')

    print(f"Old (50k sample, 6-bucket super-topic): {n_old} OLS tests, Bonferroni alpha={alpha_old:.2e}")
    print(f"New (full corpus, granular topic):      {n_new} OLS tests, Bonferroni alpha={alpha_new:.2e}")

    # Era-only comparison is apples-to-apples (same stratification unit both sides).
    # Topic-level cannot be compared row-for-row: old used 6 hand-mapped
    # super-topic buckets keyed to stale topic IDs, new uses ~100 granular
    # topics from the retrained model -- there is no valid 1:1 mapping
    # between them, so only summarize counts, not per-cell deltas.
    old_era = df_old_ols[df_old_ols['stratum'].str.startswith('Era:')]
    new_era = df_new_ols[df_new_ols['stratum'].str.startswith('Era:')]

    comparison_rows = []
    for _, row in old_era.iterrows():
        match = new_era[(new_era['stratum'] == row['stratum']) & (new_era['variable'] == row['variable'])]
        new_row = match.iloc[0] if not match.empty else None
        comparison_rows.append({
            'stratum': row['stratum'], 'variable': row['variable'],
            'old_coef': row['coef'], 'old_pvalue': row['pvalue'],
            'old_survives_bonferroni': row['pvalue'] < alpha_old,
            'new_coef': new_row['coef'] if new_row is not None else None,
            'new_pvalue': new_row['pvalue'] if new_row is not None else None,
            'new_survives_bonferroni': (new_row['pvalue'] < alpha_new) if new_row is not None else None,
        })
    df_comparison = pd.DataFrame(comparison_rows)
    df_comparison.to_csv(OUT_COMPARISON_PATH, index=False)
    print(f"Saved era-level old-vs-new comparison ({len(df_comparison)} rows) to {OUT_COMPARISON_PATH}")

    flips = df_comparison[df_comparison['old_survives_bonferroni'] != df_comparison['new_survives_bonferroni']]
    if len(flips):
        print(f"\n{len(flips)} era x variable cells changed Bonferroni-survival status:")
        print(flips[['stratum', 'variable', 'old_pvalue', 'old_survives_bonferroni', 'new_pvalue', 'new_survives_bonferroni']].to_string(index=False))
    else:
        print("\nNo era x variable cell changed Bonferroni-survival status.")

    # Granular-topic headline: does ANY construct survive at all now, vs the
    # old "no cell survives" result -- this is the actual headline question,
    # reported directly rather than left implicit in the CSV.
    topic_new = df_new_ols[df_new_ols['stratum'].str.startswith('Topic:')]
    construct_vars = ['has_maverick', 'has_canonical_expert', 'has_consensus_expert', 'pe_prob', 'ps_prob', 'hs_prob']
    topic_construct = topic_new[topic_new['variable'].isin(construct_vars)]
    topic_survivors = topic_construct[topic_construct['pvalue'] < alpha_new]
    print(f"\n=== HEADLINE: granular-topic epistemic-construct cells surviving Bonferroni (alpha={alpha_new:.2e}) ===")
    if len(topic_survivors):
        print(topic_survivors[['stratum', 'variable', 'coef', 'pvalue', 'n_obs']].sort_values('pvalue').to_string(index=False))
    else:
        print("None. The 'no epistemic-construct effect survives correction' result holds even with far more power and granularity.")


def main():
    print("======================================================================")
    print("  FULL-CORPUS, GRANULAR-TOPIC TOPIC/ERA REGRESSIONS (successor to 50k) ")
    print("======================================================================")
    df = load_full_population()
    df = add_epistemic_features(df)
    df_results = run_stratified_regressions(df)
    compare_old_vs_new(df_results)
    print("\n======================================================================")
    print("                     PIPELINE EXECUTED SUCCESSFULLY                   ")
    print("======================================================================")


if __name__ == '__main__':
    main()
