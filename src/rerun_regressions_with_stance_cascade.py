"""rerun_regressions_with_stance_cascade.py

Re-runs rerun_regressions_with_stance.py's traction regression using the
two-stage cascade classifier, but refactored to read pre-computed scores directly
from the centralized long-format cache:
  - data/processed/entity_mentions_cache_2stage_pooled.parquet

This completely avoids redundant, expensive regex matches and model scoring passes.
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
OUT_PATH = 'data/processed/regression_results_with_stance_cascade.csv'
EPS = 1e-9


def main():
    print("=== Regression with continuous stance -- cascade model, 3 specs ===")

    if not os.path.exists(CACHE_PATH):
        print(f"MISSING CENTRALIZED CACHE: {CACHE_PATH}. Run src/build_entity_mentions_cache.py first.")
        sys.exit(1)
        
    print(f"Loading centralized mentions cache from {CACHE_PATH}...")
    cache_df = pd.read_parquet(CACHE_PATH)
    print(f"Loaded cache containing {len(cache_df):,} rows.")

    # Expose comment IDs that mentioned mavericks and consensus experts respectively (at construct-merged level)
    cache_mav_ids = set(cache_df.loc[cache_df['entity_key'] == 'merged_maverick', 'comment_id'])
    cache_con_ids = set(cache_df.loc[cache_df['entity_key'] == 'merged_consensus', 'comment_id'])

    con = duckdb.connect()
    print("\nLoading r/conspiracy pure comments...")
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
    print(f"Loaded {len(df_con):,} pure r/conspiracy comments.")

    print("\nLoading r/conspiracy UNFILTERED comments (no elasticity/insider-presence filter)...")
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
    print(f"Loaded {len(df_con_unf):,} unfiltered r/conspiracy comments.")

    print("Loading r/politics scored sample...")
    df_pol = pd.read_parquet(POLITICS_SCORED_PATH)
    print(f"Loaded {len(df_pol):,} r/politics comments.")

    # 1. Define mention flags using cache presence
    for df in [df_con, df_con_unf, df_pol]:
        df['id_str'] = df['id'].astype(str)
        df['has_maverick'] = df['id_str'].isin(cache_mav_ids).astype(int)
        df['has_consensus_expert'] = df['id_str'].isin(cache_con_ids).astype(int)
        df['log_char_length'] = np.log(df['char_length'] + 1)
        df['high_traction'] = (df['upvotes'] >= 5).astype(int)

    HAS_COL = {"maverick": "has_maverick", "consensus": "has_consensus_expert"}

    # 2. Join the pre-computed scores from the cache for each population & construct
    print("\nLoading cascade stance probabilities from centralized cache...")
    pop_list = [
        ("r/conspiracy (pure)", df_con),
        ("r/conspiracy (unfiltered)", df_con_unf),
        ("r/politics", df_pol),
    ]

    for name, df_sub in pop_list:
        for construct in ["maverick", "consensus"]:
            # Filter cache to the construct-merged rows
            construct_cache = cache_df[cache_df['entity_key'] == f'merged_{construct}'].copy()
            construct_cache = construct_cache.rename(columns={
                'p_hostile': f'{construct}_p_hostile',
                'p_endorsement': f'{construct}_p_endorsement',
                'p_other': f'{construct}_p_other',
                'predicted_label': f'{construct}_predicted_label',
                'is_list_dump': f'{construct}_is_list_dump',
            })[['comment_id', f'{construct}_p_hostile', f'{construct}_p_endorsement', f'{construct}_p_other', f'{construct}_predicted_label', f'{construct}_is_list_dump']]

            # Left join to df_sub
            df_sub = df_sub.merge(construct_cache, left_on='id_str', right_on='comment_id', how='left').drop(columns=['comment_id'])

            # Fill non-mention placeholders cleanly
            p_h_col = f'{construct}_p_hostile'
            p_e_col = f'{construct}_p_endorsement'
            p_o_col = f'{construct}_p_other'

            df_sub[p_h_col] = df_sub[p_h_col].fillna(0.0)
            df_sub[p_e_col] = df_sub[p_e_col].fillna(0.0)
            df_sub[p_o_col] = df_sub[p_o_col].fillna(0.0)

            df_sub[f"{construct}_p_evaluative"] = 1.0 - df_sub[p_o_col]
            df_sub[f"{construct}_stance_score"] = 0.5 + 0.5 * (df_sub[p_e_col] - df_sub[p_h_col])

            p_eval = df_sub[f"{construct}_p_evaluative"].values
            p_e = df_sub[p_e_col].values
            p_h = df_sub[p_h_col].values

            lean = np.where(p_eval > EPS, p_e / np.clip(p_e + p_h, EPS, None), 0.5)
            df_sub[f"{construct}_lean"] = lean
            df_sub[f"{construct}_predicted_other"] = (df_sub[p_o_col] >= 0.5).astype(int)

            mask = df_sub[HAS_COL[construct]] == 1
            print(f"[{name}/{construct}] n_mentions={int(mask.sum())}, "
                  f"mean stance_score={df_sub.loc[mask, f'{construct}_stance_score'].mean():.3f}, "
                  f"pct predicted 'other'={df_sub.loc[mask, f'{construct}_predicted_other'].mean():.1%}")

        # Update the references in our list to hold the newly merged DataFrames
        if name == "r/conspiracy (pure)":
            df_con = df_sub
        elif name == "r/conspiracy (unfiltered)":
            df_con_unf = df_sub
        elif name == "r/politics":
            df_pol = df_sub

    results = []
    subsets = [
        ("r/conspiracy (pure)", "maverick", df_con, "has_maverick"),
        ("r/conspiracy (pure)", "consensus", df_con, "has_consensus_expert"),
        ("r/conspiracy (unfiltered)", "maverick", df_con_unf, "has_maverick"),
        ("r/conspiracy (unfiltered)", "consensus", df_con_unf, "has_consensus_expert"),
        ("r/politics", "maverick", df_pol, "has_maverick"),
        ("r/politics", "consensus", df_pol, "has_consensus_expert"),
    ]

    for subreddit, construct, df_full, has_col in subsets:
        mention_df = df_full[df_full[has_col] == 1].copy()
        
        # Implementation caution: strict cache-presence validation (no placeholders mixed in)
        assert mention_df[f"{construct}_p_hostile"].notna().all(), f"Error: non-mention placeholders mixed in subset {subreddit}/{construct}!"
        
        n_mentions = len(mention_df)
        print(f"\n[{subreddit}/{construct}] mention-only subset N={n_mentions}")
        if n_mentions < 20:
            print(f"  too sparse (N={n_mentions}) -- skipping all 3 specs, no stable coefficient possible.")
            for spec in ["shrinkage", "filtered", "two_covariate"]:
                results.append({
                    "subreddit": subreddit, "construct": construct, "spec": spec,
                    "variable": np.nan, "coef": np.nan, "se": np.nan, "pvalue": np.nan,
                    "n_obs": n_mentions, "note": f"excluded, too sparse (N={n_mentions})",
                })
            continue

        # --- Spec 1: shrinkage (single combined variable, same N as original script) ---
        stance_col = f"{construct}_stance_score"
        formula = f"high_traction ~ {stance_col} + pe_prob + ps_prob + has_link + log_char_length"
        try:
            m = smf.logit(formula, data=mention_df).fit(disp=0, maxiter=100)
            for c in [stance_col, "pe_prob", "ps_prob", "has_link", "log_char_length"]:
                if c in m.params:
                    results.append({
                        "subreddit": subreddit, "construct": construct, "spec": "shrinkage",
                        "variable": c, "coef": m.params[c], "se": m.bse[c],
                        "pvalue": m.pvalues[c], "n_obs": int(m.nobs), "note": "",
                    })
        except Exception as e:
            print(f"  [shrinkage] Model failed: {e}")

        # --- Spec 2: filtered to Stage-1-predicted 'clear' rows, lean only ---
        other_col = f"{construct}_predicted_other"
        clear_df = mention_df[mention_df[other_col] == 0]
        n_excluded = n_mentions - len(clear_df)
        print(f"  [filtered] excluding {n_excluded:,}/{n_mentions:,} ({n_excluded/n_mentions:.1%}) "
              f"predicted 'other' -- N remaining={len(clear_df)}")
        lean_col = f"{construct}_lean"
        formula_filtered = f"high_traction ~ {lean_col} + pe_prob + ps_prob + has_link + log_char_length"
        if len(clear_df) < 20:
            print(f"  [filtered] too sparse after filtering (N={len(clear_df)}) -- skipping.")
            results.append({
                "subreddit": subreddit, "construct": construct, "spec": "filtered",
                "variable": np.nan, "coef": np.nan, "se": np.nan, "pvalue": np.nan,
                "n_obs": len(clear_df), "note": f"excluded, too sparse after filtering (N={len(clear_df)})",
            })
        else:
            try:
                m = smf.logit(formula_filtered, data=clear_df).fit(disp=0, maxiter=100)
                for c in [lean_col, "pe_prob", "ps_prob", "has_link", "log_char_length"]:
                    if c in m.params:
                        results.append({
                            "subreddit": subreddit, "construct": construct, "spec": "filtered",
                            "variable": c, "coef": m.params[c], "se": m.bse[c],
                            "pvalue": m.pvalues[c], "n_obs": int(m.nobs),
                            "note": f"{n_excluded/n_mentions:.1%} of mentions excluded (predicted other)",
                        })
            except Exception as e:
                print(f"  [filtered] Model failed: {e}")

        # --- Spec 3: two covariates (lean + p_evaluative), same N as spec 1 ---
        eval_col = f"{construct}_p_evaluative"
        formula_2cov = f"high_traction ~ {lean_col} + {eval_col} + pe_prob + ps_prob + has_link + log_char_length"
        try:
            m = smf.logit(formula_2cov, data=mention_df).fit(disp=0, maxiter=100)
            for c in [lean_col, eval_col, "pe_prob", "ps_prob", "has_link", "log_char_length"]:
                if c in m.params:
                    results.append({
                        "subreddit": subreddit, "construct": construct, "spec": "two_covariate",
                        "variable": c, "coef": m.params[c], "se": m.bse[c],
                        "pvalue": m.pvalues[c], "n_obs": int(m.nobs), "note": "",
                    })
        except Exception as e:
            print(f"  [two_covariate] Model failed: {e}")

    out_df = pd.DataFrame(results)
    out_df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved results (3 specs x 6 subreddit/construct combos) to {OUT_PATH}")

    print("\n=== Summary: primary stance-direction coefficient per spec (shrinkage=stance_score, filtered/two_covariate=lean) ===")
    primary = out_df[out_df['variable'].astype(str).str.contains('stance_score|_lean', na=False, regex=True)]
    if len(primary):
        print(primary[['subreddit', 'construct', 'spec', 'variable', 'coef', 'pvalue', 'n_obs', 'note']].to_string(index=False))


if __name__ == "__main__":
    main()
