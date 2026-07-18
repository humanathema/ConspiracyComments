"""Run rank-based upvote and controversiality regressions on scored constructs.

Groups the 21.4M scored comments into deciles based on continuous pe_prob and ps_prob,
calculates robust engagement metrics (median, mean, controversiality rate, and high traction rate),
and runs regressions to measure the strength and direction of community feedback.

Output: data/processed/engagement_regression_results.csv
"""
import duckdb
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGED_PATH = str(REPO_ROOT / "data/processed/research_corpus_staged_scores_full21m.parquet")
EMPATH_PATH = str(REPO_ROOT / "data/processed/empath_scores_full.parquet")
OUT_PATH = str(REPO_ROOT / "data/processed/engagement_regression_results.csv")


def run_regressions_for_construct(df, prob_col, name):
    print(f"\nAnalyzing engagement for {name} ({prob_col})...")
    
    # 1. Create deciles
    # qcut is highly efficient but since we have 21.4M rows, we do it carefully
    df['decile'] = pd.qcut(df[prob_col], 10, labels=False, duplicates='drop')
    
    # 2. Group by decile and calculate metrics
    # Reddit upvotes can occasionally be negative, so handle carefully
    min_upvotes = df['upvotes'].min()
    df['log_upvotes'] = np.log(df['upvotes'] - min_upvotes + 1)
    df['high_traction'] = (df['upvotes'] >= 5).astype(int)
    
    decile_stats = df.groupby('decile').agg(
        mean_upvotes=('upvotes', 'mean'),
        median_upvotes=('upvotes', 'median'),
        controversiality_rate=('controversiality', 'mean'),
        high_traction_rate=('high_traction', 'mean'),
        min_score=(prob_col, 'min'),
        max_score=(prob_col, 'max'),
        count=('id', 'count')
    ).reset_index()
    
    decile_stats['construct'] = name
    
    # 3. Fit models
    # OLS of log_upvotes ~ prob_col
    print("  Fitting OLS regression on log-upvotes...")
    ols_model = smf.ols(f'log_upvotes ~ {prob_col}', data=df).fit()
    ols_coef = ols_model.params[prob_col]
    ols_p = ols_model.pvalues[prob_col]
    
    # Logistic of controversiality ~ prob_col
    print("  Fitting Logistic regression on controversiality...")
    logit_model = smf.logit(f'controversiality ~ {prob_col}', data=df).fit()
    logit_coef = logit_model.params[prob_col]
    logit_p = logit_model.pvalues[prob_col]
    
    # Logistic of high_traction ~ prob_col
    print("  Fitting Logistic regression on high traction...")
    traction_model = smf.logit(f'high_traction ~ {prob_col}', data=df).fit()
    traction_coef = traction_model.params[prob_col]
    traction_p = traction_model.pvalues[prob_col]
    
    print(f"  {name} Regression Results:")
    print(f"    OLS log(upvotes) Coef: {ols_coef:.4f} (p-value: {ols_p:.3e})")
    print(f"    Logit Controversiality Coef: {logit_coef:.4f} (p-value: {logit_p:.3e})")
    print(f"    Logit High-Traction Coef: {traction_coef:.4f} (p-value: {traction_p:.3e})")
    
    # Attach regression stats to decile table
    decile_stats['ols_log_upvotes_coef'] = ols_coef
    decile_stats['ols_log_upvotes_p'] = ols_p
    decile_stats['logit_controversiality_coef'] = logit_coef
    decile_stats['logit_controversiality_p'] = logit_p
    decile_stats['logit_high_traction_coef'] = traction_coef
    decile_stats['logit_high_traction_p'] = traction_p
    
    return decile_stats


def main():
    print("Connecting to DuckDB and loading score/engagement metrics...")
    start = time.time()
    
    con = duckdb.connect()
    
    # Query pe_prob, ps_prob, upvotes, and controversiality
    query = f"""
        SELECT 
            s.id,
            s.pe_prob,
            s.ps_prob,
            e.upvotes,
            CAST(e.controversiality AS INTEGER) as controversiality
        FROM '{STAGED_PATH}' s
        JOIN '{EMPATH_PATH}' e
        ON s.id = e.id
        WHERE e.upvotes IS NOT NULL AND e.controversiality IS NOT NULL
    """
    
    df = con.query(query).df()
    elapsed_query = time.time() - start
    print(f"Data loaded in {elapsed_query:.1f} seconds. Row count: {len(df):,}")
    
    # Run regressions
    pe_stats = run_regressions_for_construct(df, 'pe_prob', 'Personal Experience')
    ps_stats = run_regressions_for_construct(df, 'ps_prob', 'Procedural Skepticism')
    
    # Combine and save
    combined = pd.concat([pe_stats, ps_stats], ignore_index=True)
    combined.to_csv(OUT_PATH, index=False)
    
    # Display summary tables
    pd.set_option('display.float_format', lambda x: '%.4f' % x)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    
    for name in ['Personal Experience', 'Procedural Skepticism']:
        print("\n" + "="*80)
        print(f"              {name.upper()} DECILE ENGAGEMENT SUMMARY")
        print("="*80)
        sub = combined[combined['construct'] == name][
            ['decile', 'min_score', 'max_score', 'median_upvotes', 'mean_upvotes', 'controversiality_rate', 'high_traction_rate', 'count']
        ]
        print(sub.to_string(index=False))
        print("="*80)
        
    print(f"\nSaved regression statistics table to {OUT_PATH}")


if __name__ == "__main__":
    main()
