"""rerun_refined_regressions_v2.py

Corrected re-run of src/refine_thesis_models.py, fixing the two issues
found on 2026-07-15 audit of Antigravity's "refined" analysis (see
ANTIGRAVITY_HANDOFF.md):

  1. r/TopMindsOfReddit is NOT a neutral control -- it's a mockery/meta
     community that quotes and ridicules r/conspiracy content (confirmed
     via its AutoModerator "linked threads" rule and sample comment
     content). Replaced with a temporally-stratified r/politics sample
     (see src/build_politics_control_sample.py), which must be pulled
     and scored via src/score_comparisons.py BEFORE this script will run
     (it will exit with an error telling you what's missing).

  2. `consensus_expert` was a contaminated residual catch-all ("everything
     in mainstream_expert_authority that isn't in the hardcoded canon
     list") -- it silently absorbed genuine skeptics/contrarians, academic
     journal names, historical figures, and political/legal figures.
     Replaced with the explicit hand-verified allowlist in
     src/consensus_experts_verified.py.

Everything else (personal-experience / procedural-skepticism scoring
pipeline, has_maverick / has_canonical_expert regex construction, the
r/conspiracy "pure population" query, the regression formula, the
keyness/log-likelihood methodology) is IDENTICAL to
src/refine_thesis_models.py -- copied verbatim, not redesigned, so the
comparison is apples-to-apples with everything upstream of the two fixes.

PREREQUISITES (run in this exact order if not already done):
    python3.12 src/build_politics_control_sample.py
    python3.12 src/score_comparisons.py

TO RUN:
    python3.12 src/rerun_refined_regressions_v2.py

OUTPUTS (new files, does NOT overwrite the original TopMinds-based
results -- both are kept so you can compare):
    data/processed/comparison_politics_staged_scored.parquet
    data/processed/refined_regression_results_v2.csv
    data/processed/refined_semantic_keyness_results_v2.csv
"""
import os
import sys
import math
import numpy as np
import pandas as pd
import joblib
import duckdb
import statsmodels.formula.api as smf
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from refine_thesis_models import (
    CANONICAL_EXPERTS, FICTIONAL_OR_LEAKED,
    pass_personal_experience_filter, pass_procedural_skepticism_filter,
    build_regex, extract_contexts, compute_log_likelihood,
)
from consensus_experts_verified import VERIFIED_CONSENSUS_EXPERTS
from verified_maverick_additions import VERIFIED_MAVERICK_ADDITIONS
from maverick_authority_verified import VERIFIED_MAVERICK_AUTHORITY

MODELS_PATH = 'data/processed/staged_pipeline_models.joblib'
ENTITY_PATH = 'data/processed/entity_final_review.csv'
POLITICS_PATH = 'data/processed/comparison_politics_scored.parquet'
STAGED_PATH = 'data/processed/research_corpus_staged_scores_full21m.parquet'
EMPATH_PATH = 'data/processed/empath_scores_full.parquet'
THREAD_PATH = 'data/processed/thread_quality_metrics.csv'
PRESENCE_PATH = 'data/processed/thread_insider_presence.csv'
BRIGADE_PATH = 'data/processed/comment_brigade_flags.csv'

POLITICS_SCORED_PATH = 'data/processed/comparison_politics_staged_scored.parquet'
REFINED_REG_RESULTS_PATH = 'data/processed/refined_regression_results_v2.csv'
REFINED_KEYNESS_PATH = 'data/processed/refined_semantic_keyness_results_v2.csv'

MAX_SAMPLE = 150000  # matches original TopMinds sample cap; politics sample is
                     # smaller than that so in practice this just means "use it all"


def load_entities_split_corrected():
    """Same as refine_thesis_models.load_entities_split(), except
    `consensus` is drawn from the explicit VERIFIED_CONSENSUS_EXPERTS
    allowlist instead of an "everything left over" residual catch-all.

    BUG FIXED 2026-07-15 (same day, caught by Nash pushing back on the
    N=18 sparsity result): the first version of this function still
    pre-filtered candidates through
    `df_entity["final_bucket_guess"] == "mainstream_expert_authority"`
    before checking the allowlist -- so entities the automated bucketing
    pipeline never bucketed at all (blank final_bucket_guess), like
    Anthony Fauci (doc_count 975, never bucketed -- see the correction
    note at the top of consensus_experts_verified.py), were silently
    excluded even after being manually added to the allowlist. The
    allowlist is hand-verified and authoritative on its own; it does not
    need to be cross-checked against the (known-unreliable, see §15b)
    automated bucket assignment at all."""
    df_entity = pd.read_csv(ENTITY_PATH)

    # FIXED 2026-07-20: mavericks now comes from the explicit, hand-
    # reviewed VERIFIED_MAVERICK_AUTHORITY allowlist (446 entities, Nash's
    # review of maverick_candidate_entities_scored.csv), replacing the raw
    # `final_bucket_guess == 'maverick_authority'` bucket (418 entities)
    # this used to pull from directly. That bucket was never audited --
    # ~25% of its actual corpus matches were topic-noise ("New World
    # Order", "Deep State", "Conspiracy Theory") rather than any person or
    # organization. See handoff/task_maverick_authority_list_cleanup.md
    # for the full history. VERIFIED_MAVERICK_ADDITIONS (WikiLeaks/Assange/
    # Manning/Snowden/Ellsberg/Kiriakou) is now a subset of the reviewed
    # list but merged in regardless for safety in case of future edits to
    # either list.
    mavericks = list(dict.fromkeys(list(VERIFIED_MAVERICK_AUTHORITY) + VERIFIED_MAVERICK_ADDITIONS))

    # canon still comes from the mainstream_expert_authority-bucketed pool
    # (CANONICAL_EXPERTS matching works fine here, those figures ARE
    # reliably bucketed -- Einstein, Plato etc. have unambiguous categories)
    experts = df_entity[df_entity["final_bucket_guess"] == "mainstream_expert_authority"]["entity"].dropna().astype(str).unique().tolist()
    experts = [e for e in experts if len(e) >= 3]
    canon = [e for e in experts
             if not any(f.lower() in e.lower() for f in FICTIONAL_OR_LEAKED)
             and any(c.lower() in e.lower() for c in CANONICAL_EXPERTS)]

    consensus = list(VERIFIED_CONSENSUS_EXPERTS)

    return mavericks, canon, consensus


def _duckdb_regex_mask(df, pattern_str):
    """Runs the regex through DuckDB's RE2 (C++) engine instead of Python's
    `re` module. Verified against the Python-`re` result on a 30k-row sample
    (486/486 identical matches) -- ~140x faster than pandas .str.contains()
    with the same compiled pattern, because RE2 is compiled C++ rather than
    per-row Python-level re.search() calls. DuckDB regexp_matches() doesn't
    honor Python's re.IGNORECASE flag (it isn't part of the pattern string,
    it's separate state on the compiled object), so it must be re-added as
    an explicit `(?i)` prefix or matches silently undercount on mixed-case text.
    """
    con = duckdb.connect()
    con.register("df_view", df[["id", "text"]])
    res = con.execute(
        "SELECT id, CAST(regexp_matches(text, ?) AS INTEGER) as has_match FROM df_view",
        ["(?i)" + pattern_str],
    ).df()
    con.close()
    return res.set_index("id")["has_match"].reindex(df["id"]).fillna(0).astype(bool).values


def compute_has_maverick(df, rx_mav, lookup):
    """DuckDB-accelerated replacement for the original df.iterrows() version
    (2026-07-20, perf fix -- the row-by-row Python loop + per-row dict lookup
    over ~2M rows was the dominant cost in this script's ~2.5hr runtime).
    Output is identical: a row is has_maverick=1 if the regex matches OR its
    disambiguation-resolved id maps to a name in VALID_MAVERICK_CANDIDATES.
    """
    from combined_maverick_detector import VALID_MAVERICK_CANDIDATES
    has_regex = _duckdb_regex_mask(df, rx_mav.pattern)
    resolved = df["id"].astype(str).map(lookup)
    has_lookup = resolved.isin(VALID_MAVERICK_CANDIDATES).values
    return (has_regex | has_lookup).astype(int).tolist()


def compute_has_consensus_expert(df, rx_con, lookup):
    """Same pattern as compute_has_maverick (DuckDB regex mask OR
    disambiguation-lookup fallback), applied to the consensus side.
    Added 2026-07-20 alongside removing bare "Hawking" from
    VERIFIED_CONSENSUS_EXPERTS (it caught the verb "hawking" as often as
    the physicist) -- see consensus_disambiguation_lookup.py for the
    Stage B/C resolution this now falls back to."""
    from consensus_disambiguation_lookup import VALID_CONSENSUS_CANDIDATES
    has_regex = _duckdb_regex_mask(df, rx_con.pattern)
    resolved = df["id"].astype(str).map(lookup)
    has_lookup = resolved.isin(VALID_CONSENSUS_CANDIDATES).values
    return (has_regex | has_lookup).astype(int).tolist()


def extract_contexts_fast(df, entities, window_size=15):
    """DuckDB-accelerated prefilter wrapper around the imported extract_contexts()
    (2026-07-20, perf fix). extract_contexts() itself is left untouched in
    refine_thesis_models.py so the original script's behavior/output stays
    byte-identical -- this just skips calling it on the ~99%+ of rows that
    can't possibly match (entity mentions are rare, a few thousand hits out
    of ~2M rows), via one DuckDB RE2 regex scan instead of df.iterrows()
    re-scanning every row with Python's `re` inside extract_contexts() itself.
    """
    pattern = build_regex(entities)
    mask = _duckdb_regex_mask(df, pattern.pattern)
    return extract_contexts(df[mask], entities, window_size=window_size)



def main():
    print("=== RE-RUN v2: CORRECTED CONSENSUS LIST + r/politics CONTROL ===")

    if not os.path.exists(POLITICS_PATH):
        print(f"\nMISSING: {POLITICS_PATH}")
        print("Run these first, in order:")
        print("  python3.12 src/build_politics_control_sample.py")
        print("  python3.12 src/score_comparisons.py")
        sys.exit(1)

    print("Splitting entities (corrected consensus allowlist)...")
    mavericks, canon, consensus = load_entities_split_corrected()
    print(f"Splits complete: {len(mavericks)} Mavericks, {len(canon)} Canonical Experts, "
          f"{len(consensus)} Consensus Experts (verified allowlist, was 147 contaminated -> now {len(consensus)}).")
    print(f"Consensus entities used: {sorted(consensus)}")

    rx_mav = build_regex(mavericks)
    rx_can = build_regex(canon)
    rx_con = build_regex(consensus)

    from combined_maverick_detector import load_maverick_disambiguation_lookup
    lookup = load_maverick_disambiguation_lookup()
    print(f"Loaded {len(lookup)} resolved bare-form entries from disambiguation lookup.")

    from consensus_disambiguation_lookup import load_consensus_disambiguation_lookup
    consensus_lookup = load_consensus_disambiguation_lookup()
    print(f"Loaded {len(consensus_lookup)} resolved bare-form entries from consensus disambiguation lookup.")

    con = duckdb.connect()
    print("\nLoading r/conspiracy pure comments...")
    query = f"""
        SELECT s.id, e.text, e.upvotes, e.char_length, s.pe_prob, s.ps_prob, e.has_link, e.author, SUBSTR(e.link_id, 4) as post_id
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
    df_con['has_maverick'] = compute_has_maverick(df_con, rx_mav, lookup)
    df_con['has_canonical_expert'] = df_con['text'].apply(lambda x: 1 if bool(rx_can.search(str(x))) else 0)
    df_con['has_consensus_expert'] = compute_has_consensus_expert(df_con, rx_con, consensus_lookup)
    df_con['log_char_length'] = np.log(df_con['char_length'] + 1)
    df_con['log_upvotes'] = np.log(df_con['upvotes'] - df_con['upvotes'].min() + 1)
    df_con['high_traction'] = (df_con['upvotes'] >= 5).astype(int)

    print("\nProcessing r/politics control sample...")
    if os.path.exists(POLITICS_SCORED_PATH):
        print(f"Loading pre-scored r/politics dataset from {POLITICS_SCORED_PATH}...")
        df_pol = pd.read_parquet(POLITICS_SCORED_PATH)
    else:
        print(f"Loading raw politics dataset from {POLITICS_PATH}...")
        df_pol_raw = pd.read_parquet(POLITICS_PATH)
        n_sample = min(MAX_SAMPLE, len(df_pol_raw))
        print(f"Sampling {n_sample:,} representative comments from {len(df_pol_raw):,} total comments...")
        df_pol = df_pol_raw.sample(n=n_sample, random_state=42).copy()

        print(f"Loading Staged Classifiers from {MODELS_PATH}...")
        models = joblib.load(MODELS_PATH)
        pe_vec = models['personal_experience']['vec']
        pe_clf = models['personal_experience']['clf']
        ps_vec = models['procedural_skepticism']['vec']
        ps_clf = models['procedural_skepticism']['clf']

        print("Scoring Personal Experience on r/politics...")
        df_pol['pe_pass_s1'] = df_pol['text'].apply(pass_personal_experience_filter)
        df_pol['pe_prob'] = 0.0
        passed_pe = df_pol[df_pol['pe_pass_s1']].index
        if len(passed_pe) > 0:
            X_pe = pe_vec.transform(df_pol.loc[passed_pe, 'text'].fillna(''))
            df_pol.loc[passed_pe, 'pe_prob'] = pe_clf.predict_proba(X_pe)[:, 1]

        print("Scoring Procedural Skepticism on r/politics...")
        df_pol['ps_pass_s1'] = df_pol['text'].apply(pass_procedural_skepticism_filter)
        df_pol['ps_prob'] = 0.0
        passed_ps = df_pol[df_pol['ps_pass_s1']].index
        if len(passed_ps) > 0:
            X_ps = ps_vec.transform(df_pol.loc[passed_ps, 'text'].fillna(''))
            df_pol.loc[passed_ps, 'ps_prob'] = ps_clf.predict_proba(X_ps)[:, 1]

        df_pol.to_parquet(POLITICS_SCORED_PATH, index=False)
        print(f"Saved scored r/politics sample to {POLITICS_SCORED_PATH}")

    print("Flagging entity mentions in r/politics...")
    df_pol['post_id'] = df_pol['link_id'].apply(lambda x: x[3:] if pd.notna(x) and len(str(x)) > 3 else str(x))
    df_pol['has_maverick'] = compute_has_maverick(df_pol, rx_mav, lookup)
    df_pol['has_canonical_expert'] = df_pol['text'].apply(lambda x: 1 if bool(rx_can.search(str(x))) else 0)
    df_pol['has_consensus_expert'] = compute_has_consensus_expert(df_pol, rx_con, consensus_lookup)
    df_pol['log_char_length'] = np.log(df_pol['char_length'] + 1)
    df_pol['log_upvotes'] = np.log(df_pol['upvotes'] - df_pol['upvotes'].min() + 1)
    df_pol['high_traction'] = (df_pol['upvotes'] >= 5).astype(int)

    print("\n--- Running Regressions ---")
    results = []
    clustered_results = []
    specs = [
        ("r/conspiracy", df_con),
        ("r/politics", df_pol),
    ]
    formula = "high_traction ~ pe_prob + ps_prob + has_link + has_maverick + has_canonical_expert + has_consensus_expert + log_char_length"

    for name, df_sub in specs:
        n_consensus = int(df_sub["has_consensus_expert"].sum())
        print(f"\n[{name}] has_consensus_expert positive cases: {n_consensus} / {len(df_sub):,}")
        if n_consensus > 0:
            ct = pd.crosstab(df_sub["has_consensus_expert"], df_sub["high_traction"])
            print(ct)

        use_formula = formula
        dropped_consensus = False
        if n_consensus < 20 or (n_consensus > 0 and (ct.values == 0).any()):
            use_formula = formula.replace(" + has_consensus_expert", "")
            dropped_consensus = True
            print(f"[{name}] has_consensus_expert too sparse for a stable coefficient "
                  f"(N={n_consensus}) -- refitting without it. See raw contingency table above.")

        # 1. Standard run (Naive) to preserve original outputs
        print(f"\nRunning Naive Logit Model for {name}...")
        try:
            m = smf.logit(use_formula, data=df_sub).fit(disp=0, maxiter=100)
            print(m.summary().tables[1])
            for c in ["pe_prob", "ps_prob", "has_link", "has_maverick", "has_canonical_expert", "has_consensus_expert", "log_char_length"]:
                if c in m.params:
                    results.append({
                        "subreddit": name, "variable": c,
                        "coef": m.params[c], "se": m.bse[c],
                        "pvalue": m.pvalues[c], "n_obs": int(m.nobs),
                    })
            if dropped_consensus:
                results.append({
                    "subreddit": name, "variable": "has_consensus_expert",
                    "coef": np.nan, "se": np.nan, "pvalue": np.nan,
                    "n_obs": int(m.nobs),
                    "note": f"excluded from model, too sparse (N_positive={n_consensus}); see contingency table in log",
                })
        except Exception as e:
            print(f"Naive Model failed for {name}: {e}")

        # 2. Clustered Runs for comparison
        cov_types = [
            ("naive", None),
            ("thread", "post_id"),
            ("author", "author")
        ]
        for cov_name, group_col in cov_types:
            print(f"\nRunning Logit Model for {name} with covariance clustered by {cov_name}...")
            try:
                if cov_name == "naive":
                    m_clust = smf.logit(use_formula, data=df_sub).fit(disp=0, maxiter=100)
                else:
                    df_fit = df_sub.dropna(subset=[group_col])
                    m_clust = smf.logit(use_formula, data=df_fit).fit(cov_type='cluster', cov_kwds={'groups': df_fit[group_col].astype(str)}, disp=0, maxiter=100)
                
                for c in ["pe_prob", "ps_prob", "has_link", "has_maverick", "has_canonical_expert", "has_consensus_expert", "log_char_length"]:
                    if c in m_clust.params:
                        clustered_results.append({
                            "subreddit": name, "variable": c, "cov_type": cov_name,
                            "coef": m_clust.params[c], "se": m_clust.bse[c],
                            "pvalue": m_clust.pvalues[c], "n_obs": int(m_clust.nobs),
                        })
                if dropped_consensus:
                    clustered_results.append({
                        "subreddit": name, "variable": "has_consensus_expert", "cov_type": cov_name,
                        "coef": np.nan, "se": np.nan, "pvalue": np.nan,
                        "n_obs": int(m_clust.nobs),
                        "note": f"excluded from model, too sparse (N_positive={n_consensus})",
                    })
            except Exception as e:
                print(f"Clustered Model ({cov_name}) failed for {name}: {e}")

    pd.DataFrame(results).to_csv(REFINED_REG_RESULTS_PATH, index=False)
    print(f"\nSaved naive regression results to {REFINED_REG_RESULTS_PATH}")

    REFINED_REG_RESULTS_CLUSTERED_PATH = 'data/processed/refined_regression_results_v2_clustered.csv'
    pd.DataFrame(clustered_results).to_csv(REFINED_REG_RESULTS_CLUSTERED_PATH, index=False)
    print(f"Saved comparative clustered regression results to {REFINED_REG_RESULTS_CLUSTERED_PATH}")

    print("\n--- Running Refined Semantic Keyness ---")
    print("Extracting contexts for r/conspiracy...")
    con_mav_words = [w for ctx in extract_contexts_fast(df_con, mavericks) for w in ctx]
    con_can_words = [w for ctx in extract_contexts_fast(df_con, canon) for w in ctx]
    con_con_words = [w for ctx in extract_contexts_fast(df_con, consensus) for w in ctx]
    print(f"con_mav: {len(con_mav_words):,}, con_can: {len(con_can_words):,}, con_con: {len(con_con_words):,}")

    print("Extracting contexts for r/politics...")
    pol_can_words = [w for ctx in extract_contexts_fast(df_pol, canon) for w in ctx]
    pol_con_words = [w for ctx in extract_contexts_fast(df_pol, consensus) for w in ctx]
    print(f"pol_can: {len(pol_can_words):,}, pol_con: {len(pol_con_words):,}")

    print("\nComparing Canonical Experts vs. Consensus Experts in r/conspiracy...")
    df_con_canon_vs_cons = compute_log_likelihood(con_can_words, con_con_words)
    df_con_canon_vs_cons["comparison"] = "canonical_vs_consensus"
    df_con_canon_vs_cons["subreddit"] = "r/conspiracy"

    print("Comparing Mavericks vs. Consensus Experts in r/conspiracy...")
    df_con_mav_vs_cons = compute_log_likelihood(con_mav_words, con_con_words)
    df_con_mav_vs_cons["comparison"] = "maverick_vs_consensus"
    df_con_mav_vs_cons["subreddit"] = "r/conspiracy"

    print("Comparing Canonical Experts vs. Consensus Experts in r/politics...")
    df_pol_canon_vs_cons = compute_log_likelihood(pol_can_words, pol_con_words)
    df_pol_canon_vs_cons["comparison"] = "canonical_vs_consensus"
    df_pol_canon_vs_cons["subreddit"] = "r/politics"

    df_keyness = pd.concat([df_con_canon_vs_cons, df_con_mav_vs_cons, df_pol_canon_vs_cons])
    df_keyness.to_csv(REFINED_KEYNESS_PATH, index=False)
    print(f"Saved refined keyness metrics to {REFINED_KEYNESS_PATH}")

    print("\n" + "=" * 80)
    print("  REFINED KEYNESS v2: CANONICAL (Positive LL) vs. CONSENSUS (Negative LL) inside r/conspiracy")
    print("=" * 80)
    if not df_con_canon_vs_cons.empty:
        print("\n--- Overrepresented in CANONICAL contexts ---")
        for _, row in df_con_canon_vs_cons[(df_con_canon_vs_cons["log_likelihood"] > 0) & (df_con_canon_vs_cons["freq_c1"] >= 3)].head(15).iterrows():
            print(f"  {row['word']:18s} | LL = {row['log_likelihood']:+8.2f} | Canon: {row['freq_c1']:3d} ({row['pct_c1']:.3f}%) vs Consensus: {row['freq_c2']:3d} ({row['pct_c2']:.3f}%)")
        print("\n--- Overrepresented in CONSENSUS contexts ---")
        for _, row in df_con_canon_vs_cons[(df_con_canon_vs_cons["log_likelihood"] < 0) & (df_con_canon_vs_cons["freq_c2"] >= 3)].sort_values("log_likelihood").head(15).iterrows():
            print(f"  {row['word']:18s} | LL = {row['log_likelihood']:+8.2f} | Canon: {row['freq_c1']:3d} ({row['pct_c1']:.3f}%) vs Consensus: {row['freq_c2']:3d} ({row['pct_c2']:.3f}%)")


if __name__ == "__main__":
    main()
