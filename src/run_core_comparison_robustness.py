"""run_core_comparison_robustness.py

Task: Harden the r/conspiracy vs r/politics comparison.
This script performs two robustness checks:
  1. Sub-task A: A formal pooled interaction logit test to determine if the
     engagement effects of epistemic constructs genuinely differ by subreddit.
  2. Sub-task B: An author-overlap-excluded sensitivity rerun of the r/politics
     logit, checking if r/politics findings are driven by commenters who are also
     established r/conspiracy participants.
"""
import os
import sys
import numpy as np
import pandas as pd
import duckdb
import statsmodels.formula.api as smf

# Add src/ to Python path for imports
sys.path.insert(0, os.path.dirname(__file__))

from rerun_refined_regressions_v2 import load_entities_split_corrected, build_regex
from rerun_refined_regressions_v2 import (
    STAGED_PATH, EMPATH_PATH, THREAD_PATH, PRESENCE_PATH, BRIGADE_PATH, POLITICS_SCORED_PATH
)

FOOTPRINTS_PATH = 'data/processed/author_subreddit_footprints_async.csv'
INTERACTION_OUT_PATH = 'data/processed/subreddit_interaction_results.csv'
OVERLAP_OUT_PATH = 'data/processed/politics_overlap_excluded_comparison.csv'


def load_conspiracy_dataset(rx_mav, rx_can, rx_con):
    con = duckdb.connect()
    print("Loading r/conspiracy pure comments via DuckDB...")
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
        QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
    """
    df_con = con.execute(query).df()
    print(f"Loaded {len(df_con):,} pure r/conspiracy comments.")

    print("Flagging entity mentions in r/conspiracy...")
    df_con['has_maverick'] = df_con['text'].apply(lambda x: 1 if bool(rx_mav.search(str(x))) else 0)
    df_con['has_canonical_expert'] = df_con['text'].apply(lambda x: 1 if bool(rx_can.search(str(x))) else 0)
    df_con['has_consensus_expert'] = df_con['text'].apply(lambda x: 1 if bool(rx_con.search(str(x))) else 0)
    df_con['log_char_length'] = np.log(df_con['char_length'] + 1)
    df_con['high_traction'] = (df_con['upvotes'] >= 5).astype(int)
    return df_con


def load_politics_dataset(rx_mav, rx_can, rx_con):
    print(f"Loading pre-scored r/politics dataset from {POLITICS_SCORED_PATH}...")
    df_pol = pd.read_parquet(POLITICS_SCORED_PATH)

    print("Flagging entity mentions in r/politics...")
    df_pol['has_maverick'] = df_pol['text'].apply(lambda x: 1 if bool(rx_mav.search(str(x))) else 0)
    df_pol['has_canonical_expert'] = df_pol['text'].apply(lambda x: 1 if bool(rx_can.search(str(x))) else 0)
    df_pol['has_consensus_expert'] = df_pol['text'].apply(lambda x: 1 if bool(rx_con.search(str(x))) else 0)
    df_pol['log_char_length'] = np.log(df_pol['char_length'] + 1)
    df_pol['high_traction'] = (df_pol['upvotes'] >= 5).astype(int)
    return df_pol


def run_subtask_a(df_con, df_pol):
    print("\n=== SUB-TASK A: FORMAL POOLED INTERACTION LOGIT TEST ===")
    
    # Label and pool the datasets
    df_con = df_con.copy()
    df_pol = df_pol.copy()
    df_con['subreddit'] = 'r/conspiracy'
    df_pol['subreddit'] = 'r/politics'

    cols = [
        'subreddit', 'high_traction', 'pe_prob', 'ps_prob', 'has_link',
        'has_maverick', 'has_canonical_expert', 'has_consensus_expert', 'log_char_length'
    ]
    df_pooled = pd.concat([df_con[cols], df_pol[cols]], ignore_index=True)
    # Set r/conspiracy as reference
    df_pooled['subreddit'] = pd.Categorical(df_pooled['subreddit'], categories=['r/conspiracy', 'r/politics'])

    formula = (
        "high_traction ~ (pe_prob + ps_prob + has_link + has_maverick + "
        "has_canonical_expert + has_consensus_expert + log_char_length) * C(subreddit)"
    )

    print(f"Fitting Logit model on N = {len(df_pooled):,} pooled observations...")
    try:
        model = smf.logit(formula, data=df_pooled).fit(disp=0, maxiter=100)
        print(model.summary().tables[1])
        
        # Save complete results
        results = []
        for term in model.params.index:
            results.append({
                "term": term,
                "coef": model.params[term],
                "se": model.bse[term],
                "pvalue": model.pvalues[term],
                "z_val": model.tvalues[term],
                "lower_ci": model.conf_int().loc[term, 0],
                "upper_ci": model.conf_int().loc[term, 1],
                "n_obs": int(model.nobs)
            })
        df_results = pd.DataFrame(results)
        df_results.to_csv(INTERACTION_OUT_PATH, index=False)
        print(f"Saved formal interaction results to {INTERACTION_OUT_PATH}")

        # Highlight the interaction terms specifically
        print("\n--- Interaction Terms: Subreddit Contrast (Reference: r/conspiracy) ---")
        interaction_df = df_results[df_results["term"].str.contains("C\(subreddit\)")]
        for _, row in interaction_df.iterrows():
            sig = "*" if row["pvalue"] < 0.05 else " "
            sig_strong = "**" if row["pvalue"] < 0.001 else ""
            print(f"  {row['term']:60s} | Coef: {row['coef']:+.4f} | SE: {row['se']:.4f} | p: {row['pvalue']:.4e} {sig}{sig_strong}")
            
    except Exception as e:
        print(f"Model fitting failed: {e}")
        print("Retrying without has_consensus_expert interaction due to quasi-complete separation...")
        formula_fallback = (
            "high_traction ~ (pe_prob + ps_prob + has_link + has_maverick + "
            "has_canonical_expert + log_char_length) * C(subreddit) + has_consensus_expert"
        )
        try:
            model = smf.logit(formula_fallback, data=df_pooled).fit(disp=0, maxiter=100)
            print(model.summary().tables[1])
            
            results = []
            for term in model.params.index:
                results.append({
                    "term": term,
                    "coef": model.params[term],
                    "se": model.bse[term],
                    "pvalue": model.pvalues[term],
                    "z_val": model.tvalues[term],
                    "lower_ci": model.conf_int().loc[term, 0],
                    "upper_ci": model.conf_int().loc[term, 1],
                    "n_obs": int(model.nobs)
                })
            df_results = pd.DataFrame(results)
            df_results.to_csv(INTERACTION_OUT_PATH, index=False)
            print(f"Saved fallback interaction results (with has_consensus_expert excluded from interaction) to {INTERACTION_OUT_PATH}")
        except Exception as e_fallback:
            print(f"Fallback model also failed: {e_fallback}")


def run_subtask_b(df_pol, rx_mav, rx_can, rx_con):
    print("\n=== SUB-TASK B: AUTHOR-OVERLAP-EXCLUDED RERUN ===")
    
    if not os.path.exists(FOOTPRINTS_PATH):
        print(f"Error: Author footprints file not found at {FOOTPRINTS_PATH}")
        return

    # Load author footprints
    print(f"Loading author footprints from {FOOTPRINTS_PATH}...")
    df_foot = pd.read_csv(FOOTPRINTS_PATH)

    # Overlap definition: authors in r/politics control sample with >= 5 comments in r/conspiracy
    con_authors = set(df_foot[(df_foot['subreddit'] == 'conspiracy') & (df_foot['comment_count'] >= 5)]['author'].dropna().unique())
    pol_authors = set(df_pol['author'].dropna().unique())
    overlap_authors = pol_authors.intersection(con_authors)
    print(f"Identified {len(overlap_authors):,} overlap authors (with >=5 comments in r/conspiracy) "
          f"out of {len(pol_authors):,} total r/politics authors.")

    df_pol_excluded = df_pol[~df_pol['author'].isin(overlap_authors)].copy()
    n_removed_comments = len(df_pol) - len(df_pol_excluded)
    print(f"Excluding {n_removed_comments:,} comments from overlap authors. "
          f"Politics sample size: {len(df_pol):,} -> {len(df_pol_excluded):,}")

    # Logits on Full vs. Excluded
    specs = [
        ("Full r/politics Sample", df_pol, "full"),
        ("Overlap-Excluded r/politics Sample", df_pol_excluded, "excluded")
    ]
    
    model_coefs = {}
    
    for name, df_sub, key in specs:
        n_consensus = int(df_sub["has_consensus_expert"].sum())
        print(f"\n[{name}] has_consensus_expert positive cases: {n_consensus} / {len(df_sub):,}")
        ct = pd.crosstab(df_sub["has_consensus_expert"], df_sub["high_traction"])
        print(ct)

        formula = "high_traction ~ pe_prob + ps_prob + has_link + has_maverick + has_canonical_expert + has_consensus_expert + log_char_length"
        
        # If has_consensus_expert is too sparse, remove it from the formula to avoid complete separation
        if n_consensus < 20 or (n_consensus > 0 and (ct.values == 0).any()):
            formula_run = formula.replace(" + has_consensus_expert", "")
            print(f"[{name}] has_consensus_expert too sparse (N={n_consensus}) or separation observed. Refitting without it.")
        else:
            formula_run = formula

        try:
            model = smf.logit(formula_run, data=df_sub).fit(disp=0, maxiter=100)
            print(model.summary().tables[1])
            
            # BUG FIXED 2026-07-20: these dict keys didn't vary by `var`
            # inside the loop, so each variable's stats overwrote the
            # previous one -- the saved output ended up with every row
            # showing log_char_length's coefficient (the last variable in
            # the list), not each variable's own. Confirmed against
            # data/processed/politics_overlap_excluded_comparison.csv:
            # every row was identically -0.08127464568213258, matching
            # log_char_length's known r/politics coefficient exactly.
            coefs = {}
            for var in ["Intercept", "pe_prob", "ps_prob", "has_link", "has_maverick", "has_canonical_expert", "has_consensus_expert", "log_char_length"]:
                if var in model.params:
                    coefs[f"coef_{var}_{key}"] = model.params[var]
                    coefs[f"se_{var}_{key}"] = model.bse[var]
                    coefs[f"pvalue_{var}_{key}"] = model.pvalues[var]
                else:
                    coefs[f"coef_{var}_{key}"] = np.nan
                    coefs[f"se_{var}_{key}"] = np.nan
                    coefs[f"pvalue_{var}_{key}"] = np.nan
            coefs[f"n_obs_{key}"] = int(model.nobs)
            model_coefs[key] = coefs
        except Exception as e:
            print(f"[{name}] Model failed: {e}")
            model_coefs[key] = None

    # Merge results side-by-side
    comparison_records = []
    variables = ["Intercept", "pe_prob", "ps_prob", "has_link", "has_maverick", "has_canonical_expert", "has_consensus_expert", "log_char_length"]
    
    for var in variables:
        record = {"variable": var}
        if model_coefs.get("full") is not None:
            record["coef_full"] = model_coefs["full"].get(f"coef_{var}_full")
            record["se_full"] = model_coefs["full"].get(f"se_{var}_full")
            record["pvalue_full"] = model_coefs["full"].get(f"pvalue_{var}_full")
            record["n_obs_full"] = model_coefs["full"].get("n_obs_full")
        else:
            record["coef_full"] = np.nan
            record["se_full"] = np.nan
            record["pvalue_full"] = np.nan
            record["n_obs_full"] = np.nan

        if model_coefs.get("excluded") is not None:
            record["coef_excluded"] = model_coefs["excluded"].get(f"coef_{var}_excluded")
            record["se_excluded"] = model_coefs["excluded"].get(f"se_{var}_excluded")
            record["pvalue_excluded"] = model_coefs["excluded"].get(f"pvalue_{var}_excluded")
            record["n_obs_excluded"] = model_coefs["excluded"].get("n_obs_excluded")
        else:
            record["coef_excluded"] = np.nan
            record["se_excluded"] = np.nan
            record["pvalue_excluded"] = np.nan
            record["n_obs_excluded"] = np.nan
            
        comparison_records.append(record)

    df_comp = pd.DataFrame(comparison_records)
    df_comp.to_csv(OVERLAP_OUT_PATH, index=False)
    print(f"\nSaved side-by-side overlap-excluded comparison to {OVERLAP_OUT_PATH}")


def main():
    print("================================================================================")
    # Load corrected entity lists and compile regexes
    print("Splitting entities (corrected consensus allowlist)...")
    mavericks, canon, consensus = load_entities_split_corrected()
    
    rx_mav = build_regex(mavericks)
    rx_can = build_regex(canon)
    rx_con = build_regex(consensus)

    # Ingest conspiracy pure sample
    df_con = load_conspiracy_dataset(rx_mav, rx_can, rx_con)

    # Ingest politics control sample
    df_pol = load_politics_dataset(rx_mav, rx_can, rx_con)

    # Run Sub-task A
    run_subtask_a(df_con, df_pol)

    # Run Sub-task B
    run_subtask_b(df_pol, rx_mav, rx_can, rx_con)
    print("================================================================================")


if __name__ == "__main__":
    main()
