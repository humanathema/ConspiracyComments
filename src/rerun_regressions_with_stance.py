"""rerun_regressions_with_stance.py

Extends rerun_refined_regressions_v2.py's model with a continuous stance
variable, to test whether the pooled has_maverick/has_consensus_expert
"any mention" coefficients are averaging over two different sub-effects
(hostile vs. endorsement) rather than reflecting one true effect.

Design: rather than a hard hostile/endorsement split (which would bake in
the stance classifier's real misclassification error as attenuation
bias -- see train_stance_classifier.py's honest CV numbers, kappa=0.287
pooled, as low as 0.557 accuracy on the weakest source queue), each
mention gets a continuous *_stance_prob in [0,1] (predicted probability
of endorsement).

FIRST ATTEMPT (kept only in git history, not this version) tried fitting
has_X + X_stance_prob together across the WHOLE population in one model.
That failed: X_stance_prob is exactly 0 for every non-mention row (>99%
of the data), so it and has_X end up correlated at r=0.97 -- severe
collinearity that produced wild, sign-flipping coefficients (log-odds of
+12.6 in one case) that are a numerical artifact, not a real effect.

CURRENT DESIGN: restrict to the mention-positive subset (has_X==1,
constant there, dropped from the formula) and test whether stance_prob
predicts traction WITHIN mentions:

    high_traction ~ stance_prob + pe_prob + ps_prob + has_link + log_char_length

fit separately for each of the four (subreddit, construct) combinations.
If stance_prob's coefficient is ~0 and not significant, stance doesn't
explain traction within mentions (consistent with the HITL chi-square
nulls already found on the small rated samples). If significant, it
means valence matters beyond mere presence -- but read the maverick/
r/conspiracy result with extra caution, since that's the classifier's
weakest domain (56% CV accuracy).

Caveat carried through from the classifier's own honesty check: this is
a first pass with a mediocre classifier (kappa 0.287, worse on the
r/conspiracy maverick queue specifically) -- read this run's results as
provisional, not definitive, until an active-learning round improves the
weak spot (see build_stance_active_learning_queue.py).

Does NOT overwrite refined_regression_results_v2.csv -- separate output,
same as rerun_refined_regressions_v2.py's own relationship to
refine_thesis_models.py.
"""
import os
import sys
import numpy as np
import pandas as pd
import joblib
import duckdb
import statsmodels.formula.api as smf

sys.path.insert(0, os.path.dirname(__file__))
from refine_thesis_models import build_regex
from rerun_refined_regressions_v2 import (
    load_entities_split_corrected, compute_has_maverick, compute_has_consensus_expert,
    _duckdb_regex_mask,
    STAGED_PATH, EMPATH_PATH, THREAD_PATH, PRESENCE_PATH, BRIGADE_PATH,
    POLITICS_SCORED_PATH,
)
from combined_maverick_detector import load_maverick_disambiguation_lookup, VALID_MAVERICK_CANDIDATES, CANDIDATE_TO_BARES as MAVERICK_CANDIDATE_TO_BARES
from consensus_disambiguation_lookup import load_consensus_disambiguation_lookup, VALID_CONSENSUS_CANDIDATES, CANDIDATE_TO_BARES as CONSENSUS_CANDIDATE_TO_BARES
from stance_window_utils import extract_entity_window, compute_spans_for_row

STANCE_MODEL_PATH = 'data/processed/stance_classifier.joblib'
OUT_PATH = 'data/processed/regression_results_with_stance.csv'


def score_stance_prob(df, mask_col, vec, clf, rx, lookup, candidate_to_bares):
    """Returns an array: predicted P(endorsement) for rows where mask_col==1,
    0.0 for rows where mask_col==0 (no mention -> stance not applicable).
    REDESIGNED 2026-07-20: the classifier is now trained on entity-focused
    text windows (stance_window_utils), not whole-comment text -- must
    score the same way here or the vectorizer sees out-of-distribution
    input. Spans are computed per-row (direct regex, falling back to the
    disambiguation lookup for bare ambiguous forms) then windowed."""
    probs = np.zeros(len(df))
    mentioned = df[mask_col] == 1
    if mentioned.sum() > 0:
        sub = df.loc[mentioned]
        windows = [
            extract_entity_window(text, compute_spans_for_row(text, cid, rx, lookup, candidate_to_bares))
            for cid, text in zip(sub['id'].astype(str), sub['text'].fillna(''))
        ]
        X = vec.transform(windows)
        probs[mentioned.values] = clf.predict_proba(X)[:, 1]
    return probs


def main():
    print("=== Regression with continuous stance probability ===")

    if not os.path.exists(STANCE_MODEL_PATH):
        print(f"MISSING: {STANCE_MODEL_PATH}. Run src/train_stance_classifier.py first.")
        sys.exit(1)
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec, clf = stance_model['vec'], stance_model['clf']
    print(f"Loaded stance classifier (cv_kappa={stance_model['cv_kappa']:.3f}, "
          f"cv_auc={stance_model['cv_auc']:.3f}, n_train={stance_model['n_train']}) -- "
          "treat results below as provisional given this quality, see module docstring.")

    print("Splitting entities (corrected consensus allowlist)...")
    mavericks, canon, consensus = load_entities_split_corrected()
    rx_mav = build_regex(mavericks)
    rx_can = build_regex(canon)
    rx_con = build_regex(consensus)

    lookup = load_maverick_disambiguation_lookup()
    consensus_lookup = load_consensus_disambiguation_lookup()

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
    df_con['high_traction'] = (df_con['upvotes'] >= 5).astype(int)

    # ADDED (Nash's request, 2026-07-21): r/politics has NEVER had an
    # elasticity/insider-presence pre-filter -- it's always used the raw
    # scored sample, so it's effectively been "Unfiltered" this whole
    # time. That means r/conspiracy's PURE population (elasticity <=33rd
    # percentile, insider-presence >=0.75) was never actually apples-to-
    # apples with r/politics -- an asymmetry that existed in every
    # r/conspiracy-vs-r/politics comparison up to now. Fixed by ALSO
    # pulling r/conspiracy's Unfiltered population (same exclusions as
    # run_integrated_regressions.py's "Unfiltered" tier: crosspost/
    # brigade-excluded only, no elasticity/insider-presence filter) here,
    # scored with the EXACT same formula as r/politics, for a genuinely
    # matched comparison. The elasticity-tier drill-down INSIDE
    # r/conspiracy (Low/Medium/High) already exists separately in
    # data/processed/synthesis_stance_submodels.csv (a different formula,
    # since that's an internal-only comparison, not one that needs to
    # match r/politics) -- not reproduced here.
    # MEMORY NOTE: this population is ~16.7M rows (same order as the OOM
    # hit in run_integrated_regressions.py) -- unlike the ~2M-row "pure"
    # query above, we do NOT select e.text directly here. Entity flags are
    # computed via inline SQL regexp_matches (same as
    # run_integrated_regressions.py's load_integrated_dataset), and text
    # is fetched afterward only for the much smaller maverick/consensus
    # mention subset that the stance scoring actually needs.
    print("\nLoading r/conspiracy UNFILTERED comments (no elasticity/insider-presence filter)...")
    query_unfiltered = f"""
        SELECT
            s.id, e.upvotes, e.char_length, s.pe_prob, s.ps_prob, e.has_link, e.author,
            SUBSTR(e.link_id, 4) as post_id,
            CAST(regexp_matches(e.text, $1) AS INTEGER) as has_maverick_regex,
            CAST(regexp_matches(e.text, $2) AS INTEGER) as has_canonical_expert,
            CAST(regexp_matches(e.text, $3) AS INTEGER) as has_consensus_expert_regex
        FROM '{STAGED_PATH}' s
        JOIN '{EMPATH_PATH}' e ON s.id = e.id
        JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
        LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
        WHERE t.is_high_crosspost = 0
          AND COALESCE(b.brigade_upvote_flag, 0) = 0
          AND COALESCE(b.brigade_downvote_flag, 0) = 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
    """
    df_con_unf = con.execute(query_unfiltered, ["(?i)" + rx_mav.pattern, "(?i)" + rx_can.pattern, "(?i)" + rx_con.pattern]).df()
    print(f"Loaded {len(df_con_unf):,} unfiltered r/conspiracy comments.")

    print("Applying disambiguation-lookup fallback for r/conspiracy (unfiltered)...")
    resolved_mav = df_con_unf["id"].astype(str).map(lookup)
    df_con_unf["has_maverick"] = (df_con_unf["has_maverick_regex"].astype(bool) | resolved_mav.isin(VALID_MAVERICK_CANDIDATES)).astype(int)
    resolved_con = df_con_unf["id"].astype(str).map(consensus_lookup)
    df_con_unf["has_consensus_expert"] = (df_con_unf["has_consensus_expert_regex"].astype(bool) | resolved_con.isin(VALID_CONSENSUS_CANDIDATES)).astype(int)
    df_con_unf = df_con_unf.drop(columns=["has_maverick_regex", "has_consensus_expert_regex"])
    df_con_unf['log_char_length'] = np.log(df_con_unf['char_length'] + 1)
    df_con_unf['high_traction'] = (df_con_unf['upvotes'] >= 5).astype(int)

    mention_mask = (df_con_unf['has_maverick'] == 1) | (df_con_unf['has_consensus_expert'] == 1)
    mention_ids_df = df_con_unf.loc[mention_mask, ['id']].copy()
    print(f"Fetching text for {len(mention_ids_df):,} maverick/consensus mentions (unfiltered pop)...")
    con.register("con_unf_mention_ids", mention_ids_df)
    mention_text = con.execute(f"""
        SELECT e.id, e.text
        FROM '{EMPATH_PATH}' e
        JOIN con_unf_mention_ids n ON e.id = n.id
    """).df()
    text_lookup_unf = dict(zip(mention_text['id'], mention_text['text']))
    df_con_unf['text'] = df_con_unf['id'].map(text_lookup_unf)

    print("Loading r/politics scored sample...")
    df_pol = pd.read_parquet(POLITICS_SCORED_PATH)
    print(f"Loaded {len(df_pol):,} r/politics comments.")
    df_pol['has_maverick'] = compute_has_maverick(df_pol, rx_mav, lookup)
    df_pol['has_canonical_expert'] = df_pol['text'].apply(lambda x: 1 if bool(rx_can.search(str(x))) else 0)
    df_pol['has_consensus_expert'] = compute_has_consensus_expert(df_pol, rx_con, consensus_lookup)
    df_pol['log_char_length'] = np.log(df_pol['char_length'] + 1)
    df_pol['high_traction'] = (df_pol['upvotes'] >= 5).astype(int)

    print("\nScoring continuous stance probability for mentions...")
    for name, df_sub in [("r/conspiracy (pure)", df_con), ("r/conspiracy (unfiltered)", df_con_unf), ("r/politics", df_pol)]:
        df_sub['maverick_stance_prob'] = score_stance_prob(
            df_sub, 'has_maverick', vec, clf, rx_mav, lookup, MAVERICK_CANDIDATE_TO_BARES)
        df_sub['consensus_stance_prob'] = score_stance_prob(
            df_sub, 'has_consensus_expert', vec, clf, rx_con, consensus_lookup, CONSENSUS_CANDIDATE_TO_BARES)
        print(f"[{name}] maverick_stance_prob mean (mentions only): "
              f"{df_sub.loc[df_sub['has_maverick']==1, 'maverick_stance_prob'].mean():.3f} "
              f"(n={int(df_sub['has_maverick'].sum())})")
        print(f"[{name}] consensus_stance_prob mean (mentions only): "
              f"{df_sub.loc[df_sub['has_consensus_expert']==1, 'consensus_stance_prob'].mean():.3f} "
              f"(n={int(df_sub['has_consensus_expert'].sum())})")

    # DESIGN NOTE (fixed after first attempt): originally tried one pooled
    # model per subreddit with has_X + X_stance_prob as separate terms
    # across the WHOLE population. That failed badly -- X_stance_prob is
    # exactly 0 for every non-mention row (>99% of the data) and only
    # varies in a narrow band within the tiny mention subgroup, so it and
    # has_X end up correlated at r=0.97. That collinearity produced wild,
    # sign-flipping coefficients (e.g. log-odds of +12.6) that are a
    # numerical artifact, not a real effect -- confirmed by checking the
    # correlation directly after the first run looked implausible.
    # Fixed design: restrict to the mention-positive subset (has_X==1,
    # constant, dropped from the formula) and test whether stance_prob
    # predicts traction WITHIN mentions. Smaller N, but numerically sound.
    results = []
    subsets = [
        ("r/conspiracy (pure)", "maverick", df_con[df_con['has_maverick'] == 1]),
        ("r/conspiracy (pure)", "consensus", df_con[df_con['has_consensus_expert'] == 1]),
        ("r/conspiracy (unfiltered)", "maverick", df_con_unf[df_con_unf['has_maverick'] == 1]),
        ("r/conspiracy (unfiltered)", "consensus", df_con_unf[df_con_unf['has_consensus_expert'] == 1]),
        ("r/politics", "maverick", df_pol[df_pol['has_maverick'] == 1]),
        ("r/politics", "consensus", df_pol[df_pol['has_consensus_expert'] == 1]),
    ]
    for subreddit, construct, df_sub in subsets:
        stance_col = f"{construct}_stance_prob"
        n = len(df_sub)
        print(f"\n[{subreddit}/{construct}] mention-only subset N={n}")
        if n < 20:
            print(f"  too sparse (N={n}) -- skipping, no stable coefficient possible.")
            results.append({
                "subreddit": subreddit, "construct": construct, "variable": stance_col,
                "coef": np.nan, "se": np.nan, "pvalue": np.nan, "n_obs": n,
                "note": f"excluded, too sparse (N={n})",
            })
            continue
        formula = f"high_traction ~ {stance_col} + pe_prob + ps_prob + has_link + log_char_length"
        try:
            m = smf.logit(formula, data=df_sub).fit(disp=0, maxiter=100)
            print(m.summary().tables[1])
            for c in [stance_col, "pe_prob", "ps_prob", "has_link", "log_char_length"]:
                if c in m.params:
                    results.append({
                        "subreddit": subreddit, "construct": construct, "variable": c,
                        "coef": m.params[c], "se": m.bse[c],
                        "pvalue": m.pvalues[c], "n_obs": int(m.nobs),
                    })
        except Exception as e:
            print(f"  Model failed for {subreddit}/{construct}: {e}")

    pd.DataFrame(results).to_csv(OUT_PATH, index=False)
    print(f"\nSaved results to {OUT_PATH}")


if __name__ == "__main__":
    main()
