import os
import re
import sys
import duckdb
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

# Configuration and Paths
CANDIDATE_PATH = "data/processed/candidate_topic_split_terms.csv"
STAGED_PATH = "data/processed/research_corpus_staged_scores_full21m.parquet"
EMPATH_PATH = "data/processed/empath_scores_full.parquet"
THREAD_PATH = "data/processed/thread_quality_metrics.csv"
PRESENCE_PATH = "data/processed/thread_insider_presence.csv"
BRIGADE_PATH = "data/processed/comment_brigade_flags.csv"
OUT_PATH = "data/processed/trump_vs_classical_regression_results.csv"

# Add script directory to system path to import local utilities
sys.path.insert(0, os.path.dirname(__file__))
from rerun_refined_regressions_v2 import load_entities_split_corrected

# Timestamp for r/The_Donald ban date: 2020-06-29 00:00:00 UTC
BAN_TIMESTAMP = 1593388800

def load_lexicons():
    """Load and process confirmed candidate terms from candidate CSV."""
    if not os.path.exists(CANDIDATE_PATH):
        raise FileNotFoundError(f"Candidate file not found at {CANDIDATE_PATH}. Run src/generate_trump_vs_classical_candidates.py first.")
        
    df = pd.read_csv(CANDIDATE_PATH)

    # BUG FIXED 2026-07-20: this previously EXCLUDED only terms marked
    # 'no'/'exclude'/etc., meaning a blank `confirmed` cell (the actual
    # state of every row -- nobody had reviewed the list) passed through
    # as if approved. That defeated the entire point of the review
    # checkpoint (see handoff/task_trump_vs_classical_topic_split.md) --
    # the corpus got tagged and regressed on an unreviewed list,
    # including several terms far too generic for this construct
    # (bare "trump", "biden", "fake news" -- confirmed 2026-07-20 to
    # account for 70% of the trump_era-matching population with no
    # Trump-conspiracy-specific term present at all). Now requires an
    # explicit affirmative mark; blank/anything else is excluded.
    df['confirmed_clean'] = df['confirmed'].astype(str).str.strip().str.lower()
    included_vals = {'yes', 'y', 'confirm', 'confirmed', 'true', '1'}
    df_confirmed = df[df['confirmed_clean'].isin(included_vals)]
    
    trump_terms = df_confirmed[df_confirmed['proposed_bucket'] == 'trump_era']['term'].dropna().astype(str).unique().tolist()
    classical_terms = df_confirmed[df_confirmed['proposed_bucket'] == 'classical']['term'].dropna().astype(str).unique().tolist()
    
    # Sort terms by length in descending order to avoid matching short prefixes before long phrases
    trump_terms = sorted(trump_terms, key=len, reverse=True)
    classical_terms = sorted(classical_terms, key=len, reverse=True)
    
    # Construct regular expressions
    trump_pattern = r"\b(" + "|".join(re.escape(t) for t in trump_terms) + r")\b"
    classical_pattern = r"\b(" + "|".join(re.escape(t) for t in classical_terms) + r")\b"
    
    print(f"Loaded {len(trump_terms)} Trump-era terms and {len(classical_terms)} Classical-conspiracy terms.")
    return trump_pattern, classical_pattern

def load_and_tag_corpus(trump_pattern, classical_pattern):
    """Load 1.98M pure unbrigaded population and tag with topic_era_cluster inside DuckDB."""
    print("\n--- Phase 1: Sourcing and Tagging the 1.98M Pure Population via DuckDB ---")
    con = duckdb.connect()
    
    # Load entity lists for the standard regression controls
    print("Loading entity list splits (corrected consensus)...")
    mavericks, canon, consensus = load_entities_split_corrected()
    
    # Sort and construct regex strings for entities
    mavericks_sorted = sorted(mavericks, key=len, reverse=True)
    canon_sorted = sorted(canon, key=len, reverse=True)
    consensus_sorted = sorted(consensus, key=len, reverse=True)
    
    mav_pattern = r"\b(" + "|".join(re.escape(m) for m in mavericks_sorted) + r")\b"
    can_pattern = r"\b(" + "|".join(re.escape(c) for c in canon_sorted) + r")\b"
    con_pattern = r"\b(" + "|".join(re.escape(co) for co in consensus_sorted) + r")\b"
    
    # Build complete query with fast DuckDB regex tagging
    print("Executing DuckDB query to retrieve and tag comments...")
    query = f"""
        SELECT
            s.id,
            e.author,
            e.created_utc,
            e.upvotes,
            CAST(e.has_link AS INTEGER) as has_link,
            CAST(regexp_matches(e.text, $1) AS INTEGER) as has_trump,
            CAST(regexp_matches(e.text, $2) AS INTEGER) as has_classical,
            CAST(regexp_matches(e.text, $3) AS INTEGER) as has_maverick,
            CAST(regexp_matches(e.text, $4) AS INTEGER) as has_canonical_expert,
            CAST(regexp_matches(e.text, $5) AS INTEGER) as has_consensus_expert,
            s.pe_prob,
            s.ps_prob,
            e.char_length
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
    
    df = con.execute(query, [trump_pattern, classical_pattern, mav_pattern, can_pattern, con_pattern]).df()
    print(f"Retrieved {len(df):,} pure comments.")
    
    # Classify comments into clusters
    print("Classifying comments into mutual exclusive clusters...")
    conditions = [
        (df['has_trump'] == 1) & (df['has_classical'] == 0),
        (df['has_classical'] == 1) & (df['has_trump'] == 0)
    ]
    choices = ['trump_era', 'classical']
    df['topic_era_cluster'] = np.select(conditions, choices, default='other')
    
    # Calculate coverage
    counts = df['topic_era_cluster'].value_counts()
    for cat, count in counts.items():
        pct = (count / len(df)) * 100
        print(f"  Cluster '{cat}': {count:,} ({pct:.3f}%)")
        
    return df

def run_robust_regression(formula, df_sub, stratum_label):
    """Run OLS and Logit models safely checking for sparsity issues."""
    res_list = []
    
    # Check for has_consensus_expert sparsity
    n_consensus = int(df_sub["has_consensus_expert"].sum())
    use_formula = formula
    dropped_consensus = False
    
    if n_consensus < 15:
        use_formula = formula.replace(" + has_consensus_expert", "")
        dropped_consensus = True
        
    variables = ["pe_prob", "ps_prob", "has_link", "has_maverick", "has_canonical_expert", "has_consensus_expert", "log_char_length"]
    
    # 1. Logit Model (High Traction)
    try:
        m_logit = smf.logit(use_formula, data=df_sub).fit(disp=0, maxiter=100)
        for var in variables:
            if var in m_logit.params:
                res_list.append({
                    "stratum": stratum_label,
                    "model_type": "Logit (High Traction)",
                    "variable": var,
                    "coef": m_logit.params[var],
                    "se": m_logit.bse[var],
                    "pvalue": m_logit.pvalues[var],
                    "n_obs": int(m_logit.nobs)
                })
        if dropped_consensus:
            res_list.append({
                "stratum": stratum_label, "model_type": "Logit (High Traction)", "variable": "has_consensus_expert",
                "coef": np.nan, "se": np.nan, "pvalue": np.nan, "n_obs": len(df_sub),
                "note": "Dropped due to sparsity (<15 cases)"
            })
    except Exception as e:
        print(f"  Logit failed for {stratum_label}: {e}")
        
    # 2. OLS Model (Log Upvotes)
    try:
        ols_formula = use_formula.replace("high_traction", "log_upvotes")
        m_ols = smf.ols(ols_formula, data=df_sub).fit()
        for var in variables:
            if var in m_ols.params:
                res_list.append({
                    "stratum": stratum_label,
                    "model_type": "OLS (Log Upvotes)",
                    "variable": var,
                    "coef": m_ols.params[var],
                    "se": m_ols.bse[var],
                    "pvalue": m_ols.pvalues[var],
                    "n_obs": int(m_ols.nobs)
                })
        if dropped_consensus:
            res_list.append({
                "stratum": stratum_label, "model_type": "OLS (Log Upvotes)", "variable": "has_consensus_expert",
                "coef": np.nan, "se": np.nan, "pvalue": np.nan, "n_obs": len(df_sub),
                "note": "Dropped due to sparsity (<15 cases)"
            })
    except Exception as e:
        print(f"  OLS failed for {stratum_label}: {e}")
        
    return res_list

def main():
    print("=== TRUMP-ERA VS. CLASSICAL-CONSPIRACY REGRESSION ===")
    
    # 1. Load Lexicons
    trump_pattern, classical_pattern = load_lexicons()
    
    # 2. Sourcing and Tagging
    df = load_and_tag_corpus(trump_pattern, classical_pattern)
    
    # 3. Prep controls and outcomes
    print("\nPreparing variables and regression outcomes...")
    df['log_char_length'] = np.log(df['char_length'] + 1)
    df['log_upvotes'] = np.log(df['upvotes'] - df['upvotes'].min() + 1)
    
    # Set high_traction as upvotes >= 5 (standard threshold in pure population script)
    df['high_traction'] = (df['upvotes'] >= 5).astype(int)
    
    df['pe_prob'] = df['pe_prob'].fillna(0.0)
    df['ps_prob'] = df['ps_prob'].fillna(0.0)
    
    # 4. Stratified Regressions
    formula = "high_traction ~ pe_prob + ps_prob + has_link + has_maverick + has_canonical_expert + has_consensus_expert + log_char_length"
    results = []
    
    # A. Classical conspiracy stratum
    df_classical = df[df['topic_era_cluster'] == 'classical']
    print(f"\nRunning regression for Classical conspiracy cluster (N={len(df_classical):,})...")
    if len(df_classical) >= 200:
        results.extend(run_robust_regression(formula, df_classical, "Classical Conspiracy"))
        
    # B. Trump-era stratum
    df_trump = df[df['topic_era_cluster'] == 'trump_era']
    print(f"\nRunning regression for Trump-era cluster (N={len(df_trump):,})...")
    if len(df_trump) >= 200:
        results.extend(run_robust_regression(formula, df_trump, "Trump-era Conspiracy (Pooled)"))
        
    # C. Trump-era pre-ban cut (< 2020-06-29)
    df_trump_pre = df_trump[df_trump['created_utc'] < BAN_TIMESTAMP]
    print(f"\nRunning regression for Trump-era pre-ban cluster (N={len(df_trump_pre):,})...")
    if len(df_trump_pre) >= 200:
        results.extend(run_robust_regression(formula, df_trump_pre, "Trump-era Pre-Ban"))
        
    # D. Trump-era post-ban cut (>= 2020-06-29)
    df_trump_post = df_trump[df_trump['created_utc'] >= BAN_TIMESTAMP]
    print(f"\nRunning regression for Trump-era post-ban cluster (N={len(df_trump_post):,})...")
    if len(df_trump_post) >= 200:
        results.extend(run_robust_regression(formula, df_trump_post, "Trump-era Post-Ban"))
        
    # Compile and apply Bonferroni correction
    df_results = pd.DataFrame(results)
    
    # Calculate Bonferroni alpha across all OLS tests
    ols_tests = df_results[df_results['model_type'] == 'OLS (Log Upvotes)'].dropna(subset=['pvalue'])
    n_ols_tests = len(ols_tests)
    bonferroni_threshold = 0.05 / n_ols_tests if n_ols_tests > 0 else 0.05
    
    print(f"\nCalculated Bonferroni correction threshold for OLS (alpha = 0.05 / {n_ols_tests} tests) = {bonferroni_threshold:.2e}")
    
    df_results['bonferroni_significant'] = df_results.apply(
        lambda r: (r['pvalue'] < bonferroni_threshold) if pd.notna(r['pvalue']) and r['model_type'] == 'OLS (Log Upvotes)' else False,
        axis=1
    )
    
    # Save results to CSV
    df_results.to_csv(OUT_PATH, index=False)
    print(f"Saved regression results to {OUT_PATH}")
    
    # Print clean results table
    print("\n" + "="*110)
    print(f"{'Stratum':<30} | {'Model':<22} | {'Variable':<22} | {'Coef':<9} | {'P-Value':<9} | {'Sig (Bonf)'}")
    print("="*110)
    for idx, row in df_results.iterrows():
        coef_str = f"{row['coef']:+.4f}" if pd.notna(row['coef']) else "N/A"
        pval_str = f"{row['pvalue']:.2e}" if pd.notna(row['pvalue']) else "N/A"
        sig_str = "YES" if row.get('bonferroni_significant', False) else "yes" if (pd.notna(row['pvalue']) and row['pvalue'] < 0.05) else ""
        print(f"{row['stratum']:<30} | {row['model_type']:<22} | {row['variable']:<22} | {coef_str:<9} | {pval_str:<9} | {sig_str}")
    print("="*110)
    print("Note: 'YES' (uppercase) indicates Bonferroni-corrected significance. 'yes' (lowercase) indicates naive p < 0.05.")

if __name__ == "__main__":
    main()
