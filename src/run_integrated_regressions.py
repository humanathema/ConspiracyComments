"""run_integrated_regressions.py

Run OLS and Logit regressions to synthesize our constructs across the distribution
of thread elasticity (upvotes-per-comment ratio) and varying thresholds of author 
insider status.

Saves coefficient grids to data/processed/synthesis_regression_results.csv.
"""
import os
import re
import time
import numpy as np
import pandas as pd
import duckdb
import statsmodels.api as sm
import statsmodels.formula.api as smf

STAGED_PATH = "data/processed/research_corpus_staged_scores_full21m.parquet"
EMPATH_PATH = "data/processed/empath_scores_full.parquet"
INSIDER_PATH = "data/processed/author_insider_metrics.csv"
THREAD_PATH = "data/processed/thread_quality_metrics.csv"
ENTITY_PATH = "data/processed/entity_final_review.csv"
BRIGADE_PATH = "data/processed/comment_brigade_flags.csv"
# Keep the entity-regex-fixed-but-not-virality-filtered result
# (synthesis_regression_results.csv) intact for comparison -- this run adds
# the crosspost/brigading exclusion on top, written separately so both are
# auditable side by side rather than one silently overwriting the other.
OUT_PATH = "data/processed/synthesis_regression_results_filtered.csv"
INTERACTION_OUT_PATH = "data/processed/synthesis_interaction_results.csv"


def build_expert_regex():
    print("Loading maverick_authority entities from review CSV...")
    if not os.path.exists(ENTITY_PATH):
        raise FileNotFoundError(f"Entities review file not found at {ENTITY_PATH}")

    df_entity = pd.read_csv(ENTITY_PATH)
    # BUG FIX (2026-07-14): the original filter used has_expert_credential OR
    # has_institutional_insider alone, WITHOUT requiring final_bucket_guess ==
    # 'maverick_authority'. Those two flags are deliberately cross-cutting --
    # they're also set on mainstream_expert_authority entities (Einstein,
    # Plato) and mainstream_figure_not_source entities (Hillary Clinton,
    # Nixon, Kissinger -- tagged institutional_insider for being government
    # officials, not for being cited as alternative/fringe authorities). So
    # "has_maverick" was actually measuring "mentions ANY credentialed-or-
    # institutional entity, maverick or mainstream", not appeals to
    # maverick/alternative authority specifically -- which plausibly explains
    # the confusing, direction-flipping pattern across strata: the variable
    # wasn't holding the construct being tested constant.
    expert_ents = df_entity[
        df_entity["final_bucket_guess"] == "maverick_authority"
    ]["entity"].dropna().astype(str).unique()

    print(f"Loaded {len(expert_ents):,} distinct maverick_authority entities "
          f"(strictly final_bucket_guess == 'maverick_authority', fixed from "
          f"the earlier cross-cutting-flag version).")
    
    # Sort by length descending to match multi-word phrases first
    expert_ents_sorted = sorted(expert_ents, key=len, reverse=True)
    pattern_str = r"\b(" + "|".join(re.escape(e) for e in expert_ents_sorted) + r")\b"
    return pattern_str


def load_integrated_dataset(pattern_str):
    print("Connecting to DuckDB and executing the full integrated dataset query...")
    start_time = time.time()

    con = duckdb.connect()

    # Ingest comments in main posts, join construct scores, author insider_score, and thread elasticity
    # Incorporate the fast regexp_matches over text directly in SQL (utilizing RE2 engine in C++)
    # FIX (2026-07-14): now joins the brigade-flags table and actually
    # excludes is_high_crosspost / brigade-flagged rows, instead of pulling
    # is_crossposted into the query and never filtering on it.
    query = f"""
        SELECT
            s.id,
            s.pe_prob,
            s.ps_prob,
            e.upvotes,
            e.controversiality,
            CAST(e.has_link AS INTEGER) as has_link,
            CAST(regexp_matches(e.text, $1) AS INTEGER) as has_maverick,
            a.insider_score,
            t.elasticity_ratio,
            t.is_crossposted,
            t.is_high_crosspost
        FROM '{STAGED_PATH}' s
        JOIN '{EMPATH_PATH}' e ON s.id = e.id
        JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
        LEFT JOIN '{INSIDER_PATH}' a ON e.author = a.author
        LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
        WHERE t.is_high_crosspost = 0
          AND COALESCE(b.brigade_upvote_flag, 0) = 0
          AND COALESCE(b.brigade_downvote_flag, 0) = 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
    """

    df = con.execute(query, [pattern_str]).df()
    elapsed = time.time() - start_time
    print(f"Dataset successfully ingested in {elapsed:.2f} seconds. Row count: {len(df):,}")
    return df


def run_single_regression(df, formula, model_type):
    """Fits a single regression model and returns stats."""
    n_obs = len(df)
    if n_obs < 30: # Need sufficient observations to run
        return None
        
    try:
        if model_type == "OLS":
            model = smf.ols(formula, data=df).fit()
            params = model.params
            bse = model.bse
            pvalues = model.pvalues
            tvalues = model.tvalues
            r2 = model.rsquared
            f_p = model.f_pvalue
            return params, bse, pvalues, tvalues, r2, f_p
        elif model_type == "Logit":
            # Set disp=0 to suppress convergence messages
            model = smf.logit(formula, data=df).fit(disp=0, maxiter=100)
            params = model.params
            bse = model.bse
            pvalues = model.pvalues
            tvalues = model.tvalues # really z-values
            r2 = model.prsquared
            f_p = model.llr_pvalue
            return params, bse, pvalues, tvalues, r2, f_p
    except Exception as e:
        # Gracefully skip if separation occurs or model fails to converge
        return None
    return None


def main():
    print("=== STARTING THE GRAND SYNTHESIS INTEGRATED REGRESSIONS ===")
    
    # 1. Build regex
    pattern_str = build_expert_regex()
    
    # 2. Ingest data
    df = load_integrated_dataset(pattern_str)
    
    # 3. Compute scaled metrics
    print("Preprocessing variables...")
    min_upvotes = df['upvotes'].min()
    df['log_upvotes'] = np.log(df['upvotes'] - min_upvotes + 1)
    df['high_traction'] = (df['upvotes'] >= 5).astype(int)
    
    # 4. Bin elasticity continuously into terciles
    df['elasticity_bin'] = pd.qcut(df['elasticity_ratio'], 3, labels=['Low', 'Medium', 'High'])
    print("Elasticity tercile thresholds:")
    for bin_name in ['Low', 'Medium', 'High']:
        subset_ratio = df[df['elasticity_bin'] == bin_name]['elasticity_ratio']
        print(f"  {bin_name:6s} Elasticity: min={subset_ratio.min():.4f}, max={subset_ratio.max():.4f}, N={len(subset_ratio):,}")
        
    # Define design factors
    elasticity_strata = ['Unfiltered', 'Low', 'Medium', 'High']
    insider_thresholds = [None, -0.5, 0.0, 0.5, 1.0, 1.5]
    constructs = ['pe_prob', 'ps_prob', 'has_link', 'has_maverick']
    
    formula_ols = "log_upvotes ~ pe_prob + ps_prob + has_link + has_maverick"
    formula_contro = "controversiality ~ pe_prob + ps_prob + has_link + has_maverick"
    formula_traction = "high_traction ~ pe_prob + ps_prob + has_link + has_maverick"
    
    models_config = [
        ("OLS_log_upvotes", formula_ols, "OLS"),
        ("Logit_controversiality", formula_contro, "Logit"),
        ("Logit_high_traction", formula_traction, "Logit")
    ]
    
    results_records = []
    
    print("\nRunning regressions across parameter grids...")
    start_fits = time.time()
    fit_count = 0
    
    for strata in elasticity_strata:
        # Filter by elasticity strata
        if strata == 'Unfiltered':
            df_strata = df
        else:
            df_strata = df[df['elasticity_bin'] == strata]
            
        for threshold in insider_thresholds:
            # Filter by insider threshold
            if threshold is None:
                df_subset = df_strata
                threshold_label = "None"
            else:
                df_subset = df_strata[df_strata['insider_score'] > threshold]
                threshold_label = f"> {threshold}"
                
            n_obs = len(df_subset)
            
            for model_name, formula, m_type in models_config:
                fit_count += 1
                fit_res = run_single_regression(df_subset, formula, m_type)
                
                record = {
                    "elasticity_strata": strata,
                    "insider_threshold": threshold_label,
                    "model_name": model_name,
                    "n_obs": n_obs,
                    "r2_or_pseudo_r2": np.nan,
                    "model_sig_pvalue": np.nan
                }
                
                # Initialize constructs with NaN
                for c in constructs:
                    record[f"{c}_coef"] = np.nan
                    record[f"{c}_se"] = np.nan
                    record[f"{c}_pvalue"] = np.nan
                    record[f"{c}_tstat"] = np.nan
                    
                if fit_res is not None:
                    params, bse, pvalues, tvalues, r2, f_p = fit_res
                    record["r2_or_pseudo_r2"] = r2
                    record["model_sig_pvalue"] = f_p
                    
                    for c in constructs:
                        if c in params:
                            record[f"{c}_coef"] = params[c]
                            record[f"{c}_se"] = bse[c]
                            record[f"{c}_pvalue"] = pvalues[c]
                            record[f"{c}_tstat"] = tvalues[c]
                            
                results_records.append(record)
                
    elapsed_fits = time.time() - start_fits
    print(f"Finished {fit_count} regression fits in {elapsed_fits:.2f} seconds.")
    
    # 5. Save results to CSV
    df_results = pd.DataFrame(results_records)
    df_results.to_csv(OUT_PATH, index=False)
    print(f"Saved complete synthesis regression results table to {OUT_PATH}")
    
    # 6. Output Gorgeous Summary Trajectories
    pd.set_option('display.float_format', lambda x: '%.4f' % x)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    
    print("\n" + "="*95)
    print("            GRAND SYNTHESIS: CONSTRUCT COEFFICIENT TRAJECTORIES ACROSS ELASTICITY")
    print("="*95)
    print("Comparing how continuous constructs relate to Engagement under different elasticity environments")
    print("Values shown are for OLS Log-Upvotes and Logit High-Traction models (Insider score cutoff: None)")
    print("-"*95)
    
    for construct in constructs:
        print(f"\nConstruct: {construct.upper()}")
        print(f"{'Elasticity Bin':15s} | {'OLS Log-Upvotes Coef (p-val)':30s} | {'Logit High-Traction Coef (p-val)':30s} | {'Obs Count':10s}")
        print("-"*95)
        for strata in ['Unfiltered', 'Low', 'Medium', 'High']:
            ols_row = df_results[(df_results['elasticity_strata'] == strata) & 
                                 (df_results['insider_threshold'] == 'None') & 
                                 (df_results['model_name'] == 'OLS_log_upvotes')].iloc[0]
            logit_row = df_results[(df_results['elasticity_strata'] == strata) & 
                                   (df_results['insider_threshold'] == 'None') & 
                                   (df_results['model_name'] == 'Logit_high_traction')].iloc[0]
            
            ols_coef = ols_row[f"{construct}_coef"]
            ols_p = ols_row[f"{construct}_pvalue"]
            logit_coef = logit_row[f"{construct}_coef"]
            logit_p = logit_row[f"{construct}_pvalue"]
            
            ols_str = f"{ols_coef:+.4f} (p={ols_p:.2e})" if not np.isnan(ols_coef) else "N/A"
            logit_str = f"{logit_coef:+.4f} (p={logit_p:.2e})" if not np.isnan(logit_coef) else "N/A"
            
            print(f"{strata:15s} | {ols_str:30s} | {logit_str:30s} | {ols_row['n_obs']:,}")
        print("-"*95)
        
    print("\n" + "="*95)
    print("        SENSITIVITY ANALYSIS: COEFFICIENT SHIFTS ACROSS AUTHOR INSIDER THRESHOLDS")
    print("="*95)
    print("Demonstrates how coefficients shift as we narrow the population to purer insider communities")
    print("Values shown are for OLS Log-Upvotes in the Low Elasticity Stratum (Organic discussion trenches)")
    print("-"*95)
    
    print(f"{'Insider Threshold':18s} | " + " | ".join(f"{c[:12]:12s}" for c in constructs) + " | Obs Count")
    print("-"*95)
    for threshold in ['None', '> -0.5', '> 0.0', '> 0.5', '> 1.0', '> 1.5']:
        row = df_results[(df_results['elasticity_strata'] == 'Low') & 
                         (df_results['insider_threshold'] == threshold) & 
                         (df_results['model_name'] == 'OLS_log_upvotes')].iloc[0]
        
        coefs_str = []
        for c in constructs:
            coef = row[f"{c}_coef"]
            p_val = row[f"{c}_pvalue"]
            if np.isnan(coef):
                coefs_str.append(f"{'N/A':12s}")
            else:
                # Put an asterisk next to significant findings
                sig_star = "*" if p_val < 0.05 else " "
                coefs_str.append(f"{coef:+.4f}{sig_star:1s}")
                
        print(f"{threshold:18s} | " + " | ".join(coefs_str) + f" | {row['n_obs']:,}")
    print("-"*95)
    print("Note: * indicates p-value < 0.05")
    print("="*95)
    
    # 7. Formal interaction-term test (FIX 2026-07-14): the strata comparison
    # above compares four SEPARATE regressions by eye -- a coefficient losing
    # significance in a smaller/noisier subsample doesn't prove the true
    # effect differs. Run ONE pooled model with explicit construct x
    # elasticity_bin interaction terms and read off THEIR p-values as the
    # actual test of "does this construct's effect on engagement genuinely
    # differ across elasticity strata".
    run_interaction_regressions(df)

    print("\nGrand Synthesis Complete!")


def run_interaction_regressions(df):
    print("\n" + "="*95)
    print("   FORMAL INTERACTION-TERM TEST: does each construct's effect genuinely differ by stratum?")
    print("="*95)
    print("Pooled model with construct*elasticity_bin interactions -- reference category is 'Medium'.")
    print("A significant interaction term means that construct's effect on engagement really is")
    print("different in that stratum vs. the reference, not just 'lost significance in a smaller sample'.")
    print("-"*95)

    df = df.copy()
    df['elasticity_bin'] = df['elasticity_bin'].astype(str)
    # Medium as reference so both Low and High show as explicit contrasts
    df['elasticity_bin'] = pd.Categorical(df['elasticity_bin'], categories=['Medium', 'Low', 'High'])

    formula = ("log_upvotes ~ (pe_prob + ps_prob + has_link + has_maverick) * C(elasticity_bin)")

    interaction_records = []
    try:
        model = smf.ols(formula, data=df).fit()
        print(model.summary())
        for term, coef in model.params.items():
            interaction_records.append({
                "term": term,
                "coef": coef,
                "se": model.bse[term],
                "pvalue": model.pvalues[term],
                "tstat": model.tvalues[term],
                "n_obs": int(model.nobs),
                "r2": model.rsquared,
            })
    except Exception as e:
        print(f"Interaction model failed: {e}")

    if interaction_records:
        pd.DataFrame(interaction_records).to_csv(INTERACTION_OUT_PATH, index=False)
        print(f"\nSaved interaction-term results to {INTERACTION_OUT_PATH}")

        print("\n--- Interaction terms specifically (the actual 'does it differ by stratum' test) ---")
        for r in interaction_records:
            if ":" in r["term"]:
                sig = "*" if r["pvalue"] < 0.05 else " "
                print(f"  {r['term']:55s} coef={r['coef']:+.4f}{sig} p={r['pvalue']:.2e}")


if __name__ == "__main__":
    main()
