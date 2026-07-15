"""run_pure_population_analysis.py

Reframing of the Stage 4 analysis per Nash's correction (2026-07-14): the
insider/elasticity filtering isn't there to set up a significance test
between "insider" and "other" strata -- that comparison was never the
actual research question, and the earlier interaction-term test showed
`has_maverick` doesn't differ significantly across elasticity strata
anyway. The filtering exists as QUALITY CONTROL: isolating a population we
have real reason to trust reflects genuine community judgment (not
brigaded, not viral/tourist-inflated, actually insider-commented), so that
whatever effect we find WITHIN that population can be taken at face value
as a real subreddit phenomenon rather than noise. The finding is the
direct coefficient + its own significance in that clean population -- not
a between-group contrast.

This adds a second, independent quality signal beyond elasticity: thread-
level insider PRESENCE (what fraction of a thread's distinct commenters
are insider-classified), computed in this session and confirmed only
weakly correlated with elasticity (r=-0.06) -- i.e. genuinely
complementary information, not redundant with the upvotes-per-comment
ratio.

"Genuine insider environment" population = ALL of:
  - Low-elasticity tercile (established direction: low ratio = more
    discussion per upvote = insider signal)
  - insider_presence_ratio >= INSIDER_PRESENCE_THRESHOLD (majority-plus of
    distinct commenters are insider-classified)
  - not flagged is_high_crosspost (complete num_crossposts signal)
  - not flagged brigade_upvote_flag / brigade_downvote_flag (cell-76 definition)

Reports direct OLS/Logit coefficients + p-values for that population,
alongside the same regression on the unfiltered population for descriptive
context (NOT as a formal difference test -- see above).

**Still missing, flagged not built here**: an external control/baseline
(r/AskReddit or similar) to test whether any of these relationships are
r/conspiracy-specific or just generic Reddit upvote dynamics. This is the
right kind of "control" per Nash's own framing, not an insider-vs-other
contrast within r/conspiracy. Already a known gap, see
ANTIGRAVITY_HANDOFF.md §7.

Output: data/processed/pure_population_regression_results.csv
"""
import os
import re
import time

import duckdb
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

STAGED_PATH = "data/processed/research_corpus_staged_scores_full21m.parquet"
EMPATH_PATH = "data/processed/empath_scores_full.parquet"
INSIDER_PATH = "data/processed/author_insider_metrics.csv"
THREAD_PATH = "data/processed/thread_quality_metrics.csv"
PRESENCE_PATH = "data/processed/thread_insider_presence.csv"
ENTITY_PATH = "data/processed/entity_final_review.csv"
BRIGADE_PATH = "data/processed/comment_brigade_flags.csv"
OUT_PATH = "data/processed/pure_population_regression_results.csv"

INSIDER_PRESENCE_THRESHOLD = 0.75  # majority-plus of commenters are insiders; matches observed median


def build_maverick_regex():
    df_entity = pd.read_csv(ENTITY_PATH)
    ents = df_entity[df_entity["final_bucket_guess"] == "maverick_authority"]["entity"].dropna().astype(str).unique()
    ents_sorted = sorted(ents, key=len, reverse=True)
    return r"\b(" + "|".join(re.escape(e) for e in ents_sorted) + r")\b"


def load_dataset(pattern_str):
    con = duckdb.connect()
    query = f"""
        SELECT
            s.id,
            s.pe_prob,
            s.ps_prob,
            e.upvotes,
            CAST(e.has_link AS INTEGER) as has_link,
            CAST(regexp_matches(e.text, $1) AS INTEGER) as has_maverick,
            t.elasticity_ratio,
            t.is_high_crosspost,
            p.insider_presence_ratio
        FROM '{STAGED_PATH}' s
        JOIN '{EMPATH_PATH}' e ON s.id = e.id
        JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
        LEFT JOIN '{PRESENCE_PATH}' p ON SUBSTR(e.link_id, 4) = p.post_id
        LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
        WHERE COALESCE(b.brigade_upvote_flag, 0) = 0
          AND COALESCE(b.brigade_downvote_flag, 0) = 0
    """
    return con.execute(query, [pattern_str]).df()


def run_regression(df, formula, model_type):
    if len(df) < 30:
        return None
    try:
        if model_type == "OLS":
            m = smf.ols(formula, data=df).fit()
        else:
            m = smf.logit(formula, data=df).fit(disp=0, maxiter=100)
        return m
    except Exception as e:
        print(f"  regression failed: {e}")
        return None


def report(df, label, constructs, formulas):
    print(f"\n--- {label} (N={len(df):,}) ---")
    records = []
    for model_name, formula, model_type in formulas:
        m = run_regression(df, formula, model_type)
        if m is None:
            print(f"  {model_name}: failed or insufficient N")
            continue
        for c in constructs:
            if c in m.params:
                sig = "*" if m.pvalues[c] < 0.05 else " "
                print(f"  {model_name:20s} {c:15s} coef={m.params[c]:+.4f}{sig} p={m.pvalues[c]:.2e}")
                records.append({
                    "population": label, "model": model_name, "construct": c,
                    "coef": m.params[c], "se": m.bse[c], "pvalue": m.pvalues[c],
                    "n_obs": int(m.nobs),
                })
    return records


def sweep_insider_presence_threshold(df_base, constructs):
    """Sweep INSIDER_PRESENCE_THRESHOLD across the actual distribution
    (within the already-quality-filtered low-elasticity/non-viral
    population) rather than committing to one fixed cutoff -- shows
    whether/where an effect emerges or strengthens as the population gets
    purer, instead of asserting a single arbitrary threshold is "the"
    right one."""
    print("\n" + "=" * 95)
    print("  SWEEP: has_maverick coefficient across the insider_presence_ratio distribution")
    print("=" * 95)
    quantiles = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    thresholds = sorted(set(
        [0.0] + [round(df_base["insider_presence_ratio"].quantile(q), 3) for q in quantiles] + [1.0]
    ))
    print(f"Thresholds (from the data's own quantiles): {thresholds}")

    formula_ols = "log_upvotes ~ pe_prob + ps_prob + has_link + has_maverick"
    formula_logit = "high_traction ~ pe_prob + ps_prob + has_link + has_maverick"

    records = []
    print(f"\n{'Threshold':>10s} | {'N':>8s} | {'OLS coef':>10s} | {'OLS p':>10s} | {'Logit coef':>10s} | {'Logit p':>10s}")
    print("-" * 95)
    for t in thresholds:
        sub = df_base[df_base["insider_presence_ratio"] >= t]
        m_ols = run_regression(sub, formula_ols, "OLS")
        m_logit = run_regression(sub, formula_logit, "Logit")
        ols_coef = m_ols.params.get("has_maverick", np.nan) if m_ols else np.nan
        ols_p = m_ols.pvalues.get("has_maverick", np.nan) if m_ols else np.nan
        logit_coef = m_logit.params.get("has_maverick", np.nan) if m_logit else np.nan
        logit_p = m_logit.pvalues.get("has_maverick", np.nan) if m_logit else np.nan
        sig_ols = "*" if not np.isnan(ols_p) and ols_p < 0.05 else " "
        sig_logit = "*" if not np.isnan(logit_p) and logit_p < 0.05 else " "
        print(f"{t:>10.3f} | {len(sub):>8,} | {ols_coef:>+9.4f}{sig_ols} | {ols_p:>10.2e} | "
              f"{logit_coef:>+9.4f}{sig_logit} | {logit_p:>10.2e}")
        records.append({
            "insider_presence_threshold": t, "n_obs": len(sub),
            "ols_coef": ols_coef, "ols_pvalue": ols_p,
            "logit_coef": logit_coef, "logit_pvalue": logit_p,
        })
    print("-" * 95)
    print("Note: * indicates p<0.05")
    return records


def main():
    print("=== PURE-POPULATION DIRECT-EFFECT ANALYSIS ===")
    pattern_str = build_maverick_regex()
    df = load_dataset(pattern_str)
    print(f"Loaded {len(df):,} rows")

    df["log_upvotes"] = np.log(df["upvotes"] - df["upvotes"].min() + 1)
    df["high_traction"] = (df["upvotes"] >= 5).astype(int)
    df["elasticity_bin"] = pd.qcut(df["elasticity_ratio"], 3, labels=["Low", "Medium", "High"])

    constructs = ["pe_prob", "ps_prob", "has_link", "has_maverick"]
    formulas = [
        ("OLS_log_upvotes", "log_upvotes ~ pe_prob + ps_prob + has_link + has_maverick", "OLS"),
        ("Logit_high_traction", "high_traction ~ pe_prob + ps_prob + has_link + has_maverick", "Logit"),
    ]

    all_records = []

    # Descriptive baseline: unfiltered, for context only (not a difference test)
    all_records += report(df, "Unfiltered (descriptive context only)", constructs, formulas)

    # Elasticity alone (as before)
    df_low_elastic = df[(df["elasticity_bin"] == "Low") & (df["is_high_crosspost"] == 0)]
    all_records += report(df_low_elastic, "Low elasticity + non-viral only", constructs, formulas)

    # THE actual target population: elasticity + insider presence + quality filters combined
    df_pure = df[
        (df["elasticity_bin"] == "Low")
        & (df["is_high_crosspost"] == 0)
        & (df["insider_presence_ratio"] >= INSIDER_PRESENCE_THRESHOLD)
    ]
    all_records += report(
        df_pure,
        f"GENUINE INSIDER ENVIRONMENT (low elasticity + non-viral + "
        f"insider_presence>={INSIDER_PRESENCE_THRESHOLD} + non-brigaded)",
        constructs, formulas,
    )

    pd.DataFrame(all_records).to_csv(OUT_PATH, index=False)
    print(f"\nSaved all results to {OUT_PATH}")

    # Threshold sweep across the actual insider_presence_ratio distribution,
    # within the same low-elasticity + non-viral quality-filtered base --
    # per Nash's follow-up: don't commit to one arbitrary cutoff, look at
    # the whole distribution and see where (if anywhere) it matters.
    sweep_records = sweep_insider_presence_threshold(df_low_elastic, constructs)
    pd.DataFrame(sweep_records).to_csv("data/processed/insider_presence_threshold_sweep.csv", index=False)
    print("Saved sweep results to data/processed/insider_presence_threshold_sweep.csv")


if __name__ == "__main__":
    main()
