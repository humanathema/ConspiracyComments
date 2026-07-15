"""run_askreddit_control.py

Run the staged hybrid pipeline over the r/AskReddit corpus to compute pe_prob and ps_prob,
evaluate maverick entity mentions, and run regression models (with and without length controls)
to serve as an external baseline comparison.
"""

import os
import re
import time
import numpy as np
import pandas as pd
import joblib
import duckdb
import statsmodels.formula.api as smf

MODELS_PATH = 'data/processed/staged_pipeline_models.joblib'
INPUT_PARQUET = 'data/processed/comparison_askreddit_scored.parquet'
ENTITY_PATH = 'data/processed/entity_final_review.csv'
OUTPUT_PARQUET = 'data/processed/comparison_askreddit_staged_scored.parquet'
OUTPUT_CSV = 'data/processed/askreddit_regression_results.csv'

# Regex patterns for Stage 1 (consistent with score_main_corpus_staged.py)
PRONOUNS = re.compile(r"\b(i|me|my|myself|we|our|us)\b", re.IGNORECASE)
LIFE_ANCHORS = re.compile(
    r"\b(family|career|brother|sister|wife|husband|job|life|school|hospital|mom|dad|mother|father|parents|kid|kids|child|children|grew up|remember|remembered|happened)\b",
    re.IGNORECASE
)
SKEPT_TERMS = re.compile(
    r"\b(evidence|proof|argument|premise|contradict|logical|validity|source|cite|citation|logic|facts|peer|study|studies|data|science|scientific|statistics)\b",
    re.IGNORECASE
)
NEGATIONS = re.compile(
    r"\b(doesn't add up|makes no sense|where is the|flaw|disprove|debunk|falsify|invalid|manipulate|bias|biased|cherry pick|cherry-picked|propaganda)\b",
    re.IGNORECASE
)

def pass_personal_experience_filter(text):
    text_str = str(text)
    return bool(PRONOUNS.search(text_str)) and bool(LIFE_ANCHORS.search(text_str))

def pass_procedural_skepticism_filter(text):
    text_str = str(text)
    return bool(SKEPT_TERMS.search(text_str)) or bool(NEGATIONS.search(text_str))

def build_maverick_regex():
    if not os.path.exists(ENTITY_PATH):
        print(f"Warning: {ENTITY_PATH} not found. Creating empty maverick regex.")
        return r"\b(never_match_this_string_xyz)\b"
    df_entity = pd.read_csv(ENTITY_PATH)
    ents = df_entity[df_entity["final_bucket_guess"] == "maverick_authority"]["entity"].dropna().astype(str).unique()
    if len(ents) == 0:
        return r"\b(never_match_this_string_xyz)\b"
    ents_sorted = sorted(ents, key=len, reverse=True)
    return r"\b(" + "|".join(re.escape(e) for e in ents_sorted) + r")\b"

def main():
    print("=== RUNNING ASKREDDIT EXTERNAL CONTROL BASELINE ===")
    
    # 1. Load models
    if not os.path.exists(MODELS_PATH):
        raise FileNotFoundError(f"Staged pipeline models not found at {MODELS_PATH}")
    print(f"Loading Stage 2 models from {MODELS_PATH}...")
    models = joblib.load(MODELS_PATH)
    pe_vec = models['personal_experience']['vec']
    pe_clf = models['personal_experience']['clf']
    ps_vec = models['procedural_skepticism']['vec']
    ps_clf = models['procedural_skepticism']['clf']
    
    # 2. Load AskReddit scored dataset
    if not os.path.exists(INPUT_PARQUET):
        raise FileNotFoundError(f"AskReddit scored dataset not found at {INPUT_PARQUET}")
    print(f"Loading AskReddit dataset from {INPUT_PARQUET}...")
    df = pd.read_parquet(INPUT_PARQUET)
    print(f"Loaded {len(df):,} rows")
    
    # 3. Apply Staged Pipeline for Personal Experience & Procedural Skepticism
    print("Scoring Personal Experience...")
    df['pe_pass_s1'] = df['text'].apply(pass_personal_experience_filter)
    df['pe_prob'] = 0.0
    passed_pe = df[df['pe_pass_s1']].index
    if len(passed_pe) > 0:
        X_pe = pe_vec.transform(df.loc[passed_pe, 'text'].fillna(''))
        df.loc[passed_pe, 'pe_prob'] = pe_clf.predict_proba(X_pe)[:, 1]
    
    print("Scoring Procedural Skepticism...")
    df['ps_pass_s1'] = df['text'].apply(pass_procedural_skepticism_filter)
    df['ps_prob'] = 0.0
    passed_ps = df[df['ps_pass_s1']].index
    if len(passed_ps) > 0:
        X_ps = ps_vec.transform(df.loc[passed_ps, 'text'].fillna(''))
        df.loc[passed_ps, 'ps_prob'] = ps_clf.predict_proba(X_ps)[:, 1]
        
    # 4. Score Maverick Entity Mentions
    print("Scoring Maverick Entity mentions...")
    maverick_rx = re.compile(build_maverick_regex(), re.IGNORECASE)
    df['has_maverick'] = df['text'].apply(lambda x: 1 if bool(maverick_rx.search(str(x))) else 0)
    
    # 5. Add length controls and target transformations
    df['log_char_length'] = np.log(df['char_length'] + 1)
    df['log_upvotes'] = np.log(df['upvotes'] - df['upvotes'].min() + 1)
    df['high_traction'] = (df['upvotes'] >= 5).astype(int)
    
    # Save scored dataset
    df.to_parquet(OUTPUT_PARQUET, index=False)
    print(f"Saved scored AskReddit dataset to {OUTPUT_PARQUET}")
    
    # 6. Run regressions
    print("\n--- Running Regressions on AskReddit Baseline ---")
    
    results = []
    
    specs = [
        ("OLS_log_upvotes_no_len", "log_upvotes ~ pe_prob + ps_prob + has_link + has_maverick", "OLS"),
        ("OLS_log_upvotes_with_len", "log_upvotes ~ pe_prob + ps_prob + has_link + has_maverick + log_char_length", "OLS"),
        ("Logit_high_traction_no_len", "high_traction ~ pe_prob + ps_prob + has_link + has_maverick", "Logit"),
        ("Logit_high_traction_with_len", "high_traction ~ pe_prob + ps_prob + has_link + has_maverick + log_char_length", "Logit")
    ]
    
    for name, formula, model_type in specs:
        print(f"\nRunning {name}...")
        try:
            if model_type == "OLS":
                m = smf.ols(formula, data=df).fit()
            else:
                m = smf.logit(formula, data=df).fit(disp=0, maxiter=100)
            
            print(m.summary().tables[1])
            
            # Record coefficients
            for c in ["pe_prob", "ps_prob", "has_link", "has_maverick", "log_char_length"]:
                if c in m.params:
                    results.append({
                        "model": name,
                        "type": model_type,
                        "variable": c,
                        "coef": m.params[c],
                        "se": m.bse[c],
                        "pvalue": m.pvalues[c],
                        "n_obs": int(m.nobs)
                    })
        except Exception as e:
            print(f"Regression {name} failed: {e}")
            
    pd.DataFrame(results).to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved regression results to {OUTPUT_CSV}")
    
    # 7. Compare with Conspiracy "Unfiltered" Results
    print("\n" + "=" * 80)
    print("  COMPARISON: r/AskReddit VS r/conspiracy (Unfiltered)")
    print("=" * 80)
    
    conspiracy_path = "data/processed/pure_population_regression_results.csv"
    if os.path.exists(conspiracy_path):
        df_con = pd.read_csv(conspiracy_path)
        # Filter to Conspiracy Unfiltered descriptive baseline
        df_con_unfilt = df_con[df_con["population"] == "Unfiltered (descriptive context only)"]
        
        print("\n[Logit High Traction Comparison]")
        print(f"{'Variable':15s} | {'r/conspiracy Coef':18s} | {'r/conspiracy p':14s} | {'r/AskReddit Coef':16s} | {'r/AskReddit p':12s}")
        print("-" * 80)
        
        # Pull AskReddit Logit (no len) for direct baseline comparison
        df_ar_logit = pd.DataFrame(results)
        df_ar_logit = df_ar_logit[df_ar_logit["model"] == "Logit_high_traction_no_len"]
        
        for c in ["pe_prob", "ps_prob", "has_link", "has_maverick"]:
            con_row = df_con_unfilt[(df_con_unfilt["model"] == "Logit_high_traction") & (df_con_unfilt["construct"] == c)]
            ar_row = df_ar_logit[df_ar_logit["variable"] == c]
            
            con_coef = f"{con_row['coef'].values[0]:+.4f}" if len(con_row) > 0 else "N/A"
            con_p = f"{con_row['pvalue'].values[0]:.2e}" if len(con_row) > 0 else "N/A"
            ar_coef = f"{ar_row['coef'].values[0]:+.4f}" if len(ar_row) > 0 else "N/A"
            ar_p = f"{ar_row['pvalue'].values[0]:.2e}" if len(ar_row) > 0 else "N/A"
            
            print(f"{c:15s} | {con_coef:>17s} | {con_p:>13s} | {ar_coef:>15s} | {ar_p:>11s}")
            
    else:
        print("Note: pure_population_regression_results.csv not found to run automatic comparison.")

if __name__ == "__main__":
    main()
