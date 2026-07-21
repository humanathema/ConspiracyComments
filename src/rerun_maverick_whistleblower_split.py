"""rerun_maverick_whistleblower_split.py

Splits the pooled `maverick` construct into two sub-groups and re-runs the
stance-direction regression (cascade model, all 3 specs from
rerun_regressions_with_stance_cascade.py) separately for each, instead of
pooling them into one `maverick_stance_score`/`maverick_lean` coefficient:

  - `whistleblower`: WikiLeaks, Assange, Snowden, Greenwald, etc.
  - `other_maverick`: catch-all -- Alex Jones, JFK/911/covid/antivax/flat-earth theorists, QAnon figures, etc.

This refactored version loads pre-computed subgroup-merged scores directly from the centralized long-format cache:
  - data/processed/entity_mentions_cache_2stage_pooled.parquet

This completely avoids any aggregation-granularity mismatch (scoring merged windows at the subgroup level)
and supports both:
  1. "uncorrected" (reproducing the original run's alias blind spot exactly)
  2. "corrected" (using the scientifically correct category mappings)
"""
import os
import sys
import numpy as np
import pandas as pd
import duckdb
import statsmodels.formula.api as smf

sys.path.insert(0, os.path.dirname(__file__))
from rerun_refined_regressions_v2 import (
    STAGED_PATH, EMPATH_PATH, THREAD_PATH, PRESENCE_PATH, BRIGADE_PATH,
    POLITICS_SCORED_PATH,
)

CACHE_PATH = 'data/processed/entity_mentions_cache_2stage_pooled.parquet'
OUT_PATH_CORRECTED = 'data/processed/regression_results_maverick_whistleblower_split.csv'
OUT_PATH_UNCORRECTED = 'data/processed/regression_results_maverick_whistleblower_split_uncorrected.csv'
EPS = 1e-9


def run_specs(mention_df, subgroup_name, results, subreddit, construct_label):
    n_mentions = len(mention_df)
    print(f"\n[{subreddit}/{construct_label}] subgroup-merged N={n_mentions}")
    if n_mentions < 20:
        print(f"  too sparse (N={n_mentions}) -- skipping all 3 specs.")
        for spec in ["shrinkage", "filtered", "two_covariate"]:
            results.append({
                "subreddit": subreddit, "construct": construct_label, "spec": spec,
                "variable": np.nan, "coef": np.nan, "se": np.nan, "pvalue": np.nan,
                "n_obs": n_mentions, "note": f"excluded, too sparse (N={n_mentions})",
            })
        return

    # Strict cache-presence assertion
    assert mention_df["p_hostile"].notna().all(), f"Error: missing cached probability rows in subset {subreddit}/{construct_label}!"

    stance_col = "stance_score"
    lean_col = "lean"
    eval_col = "p_evaluative"
    other_col = "predicted_other"

    formula = f"high_traction ~ {stance_col} + pe_prob + ps_prob + has_link + log_char_length"
    try:
        m = smf.logit(formula, data=mention_df).fit(disp=0, maxiter=100)
        for c in [stance_col, "pe_prob", "ps_prob", "has_link", "log_char_length"]:
            if c in m.params:
                results.append({
                    "subreddit": subreddit, "construct": construct_label, "spec": "shrinkage",
                    "variable": c if c != stance_col else f"{subgroup_name}_stance_score", 
                    "coef": m.params[c], "se": m.bse[c],
                    "pvalue": m.pvalues[c], "n_obs": int(m.nobs), "note": "",
                })
    except Exception as e:
        print(f"  [shrinkage] Model failed: {e}")

    clear_df = mention_df[mention_df[other_col] == 0]
    n_excluded = n_mentions - len(clear_df)
    print(f"  [filtered] excluding {n_excluded:,}/{n_mentions:,} ({n_excluded / n_mentions:.1%}) predicted 'other' -- N remaining={len(clear_df)}")
    if len(clear_df) < 20:
        results.append({
            "subreddit": subreddit, "construct": construct_label, "spec": "filtered",
            "variable": np.nan, "coef": np.nan, "se": np.nan, "pvalue": np.nan,
            "n_obs": len(clear_df), "note": f"excluded, too sparse after filtering (N={len(clear_df)})",
        })
    else:
        formula_filtered = f"high_traction ~ {lean_col} + pe_prob + ps_prob + has_link + log_char_length"
        try:
            m = smf.logit(formula_filtered, data=clear_df).fit(disp=0, maxiter=100)
            for c in [lean_col, "pe_prob", "ps_prob", "has_link", "log_char_length"]:
                if c in m.params:
                    results.append({
                        "subreddit": subreddit, "construct": construct_label, "spec": "filtered",
                        "variable": c if c != lean_col else f"{subgroup_name}_lean", 
                        "coef": m.params[c], "se": m.bse[c],
                        "pvalue": m.pvalues[c], "n_obs": int(m.nobs),
                        "note": f"{n_excluded / n_mentions:.1%} of mentions excluded (predicted other)",
                    })
        except Exception as e:
            print(f"  [filtered] Model failed: {e}")

    formula_2cov = f"high_traction ~ {lean_col} + {eval_col} + pe_prob + ps_prob + has_link + log_char_length"
    try:
        m = smf.logit(formula_2cov, data=mention_df).fit(disp=0, maxiter=100)
        for c in [lean_col, eval_col, "pe_prob", "ps_prob", "has_link", "log_char_length"]:
            if c in m.params:
                results.append({
                    "subreddit": subreddit, "construct": construct_label, "spec": "two_covariate",
                    "variable": c if c != lean_col else f"{subgroup_name}_lean" if c != eval_col else f"{subgroup_name}_p_evaluative", 
                    "coef": m.params[c], "se": m.bse[c],
                    "pvalue": m.pvalues[c], "n_obs": int(m.nobs), "note": "",
                })
    except Exception as e:
        print(f"  [two_covariate] Model failed: {e}")


def run_split_analysis(cache_df, mode="corrected"):
    print(f"\n==========================================")
    print(f"Running Maverick Subgroup Splits: {mode.upper()} mode")
    print(f"==========================================")
    
    suffix = "_uncorrected" if mode == "uncorrected" else ""
    out_path = OUT_PATH_UNCORRECTED if mode == "uncorrected" else OUT_PATH_CORRECTED

    con = duckdb.connect()
    print("Loading r/conspiracy pure comments...")
    query = f"""
        SELECT s.id, e.upvotes, e.char_length, s.pe_prob, s.ps_prob, e.has_link, e.author, SUBSTR(e.link_id, 4) as post_id
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

    print("Loading r/conspiracy UNFILTERED comments...")
    query_unfiltered = f"""
        SELECT
            s.id, e.upvotes, e.char_length, s.pe_prob, s.ps_prob, e.has_link, e.author,
            SUBSTR(e.link_id, 4) as post_id
        FROM '{STAGED_PATH}' s
        JOIN '{EMPATH_PATH}' e ON s.id = e.id
        JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
        LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
        WHERE t.is_high_crosspost = 0
          AND COALESCE(b.brigade_upvote_flag, 0) = 0
          AND COALESCE(b.brigade_downvote_flag, 0) = 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
    """
    df_con_unf = con.execute(query_unfiltered).df()

    print("Loading r/politics scored sample...")
    df_pol = pd.read_parquet(POLITICS_SCORED_PATH)

    # Standard columns on full-corpus frames
    for df in [df_con, df_con_unf, df_pol]:
        df['id_str'] = df['id'].astype(str)
        df['log_char_length'] = np.log(df['char_length'] + 1)
        df['high_traction'] = (df['upvotes'] >= 5).astype(int)

    results = []
    pop_list = [
        ("r/conspiracy (pure)", df_con),
        ("r/conspiracy (unfiltered)", df_con_unf),
        ("r/politics", df_pol)
    ]

    for name, df_sub in pop_list:
        print(f"\n--- Subgroup splits for {name} ---")
        for subgroup in ['whistleblower', 'other_maverick']:
            # Load subgroup-merged key directly from cache
            sub_key = f"merged_{subgroup}{suffix}"
            sub_cache = cache_df[cache_df['entity_key'] == sub_key].copy()
            
            # Derive metrics
            sub_cache['p_evaluative'] = 1.0 - sub_cache['p_other']
            sub_cache['stance_score'] = 0.5 + 0.5 * (sub_cache['p_endorsement'] - sub_cache['p_hostile'])
            p_eval = sub_cache['p_evaluative'].values
            p_e = sub_cache['p_endorsement'].values
            p_h = sub_cache['p_hostile'].values
            sub_cache['lean'] = np.where(p_eval > EPS, p_e / np.clip(p_e + p_h, EPS, None), 0.5)
            sub_cache['predicted_other'] = (sub_cache['p_other'] >= 0.5).astype(int)

            # Left join back to population
            merged = df_sub.merge(sub_cache, left_on='id_str', right_on='comment_id', how='inner')
            run_specs(merged, subgroup, results, name, subgroup)

    out_df = pd.DataFrame(results)
    out_df.to_csv(out_path, index=False)
    print(f"\nSaved results to {out_path}")

    print("\n=== Summary: stance-direction coefficient per subgroup/spec ===")
    primary = out_df[out_df['variable'].astype(str).str.contains('stance_score|_lean', na=False, regex=True)]
    if len(primary):
        print(primary[['subreddit', 'construct', 'spec', 'variable', 'coef', 'pvalue', 'n_obs', 'note']].to_string(index=False))


def main():
    print("=== Maverick sub-split regression runner ===")

    if not os.path.exists(CACHE_PATH):
        print("Missing centralized cache. Run build_entity_mentions_cache.py first.")
        sys.exit(1)

    print(f"Loading centralized mentions cache from {CACHE_PATH}...")
    cache_df = pd.read_parquet(CACHE_PATH)
    print(f"Loaded cache containing {len(cache_df):,} rows.")

    # Run uncorrected mode to replicate the user's original uncorrected run
    run_split_analysis(cache_df, mode="uncorrected")
    
    # Run corrected mode for scientifically sound citable numbers
    run_split_analysis(cache_df, mode="corrected")


if __name__ == "__main__":
    main()
