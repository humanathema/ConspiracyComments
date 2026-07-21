"""per_entity_stance_breakdown.py

Breaks the pooled has_maverick/has_consensus_expert stance results down by
INDIVIDUAL entity (Alex Jones, Edward Snowden, Anthony Fauci, ...) instead
of treating "maverick" and "consensus expert" as single lumped buckets.
Motivated by Nash's observation that r/conspiracy comments about Alex
Jones, Snowden, and Assange often accuse them of being "controlled
opposition" or replaced doubles -- a pattern that would predict hostility
concentrated in the most PROMINENT mavericks specifically, not mavericks
as a category. A pooled has_maverick coefficient can't distinguish "no one
cares about stance" from "half the entities are loved, half are hated,
and it averages to noise" -- which is exactly the kind of thing that
could explain the maverick sign-flip/null-result instability found in
the pooled analysis.

Method: for every has_maverick==1 / has_consensus_expert==1 comment in the
r/conspiracy Unfiltered population (same as run_integrated_regressions.py's
Unfiltered tier -- chosen over the "pure" population for statistical power,
since splitting into dozens of entities eats into per-entity sample size
fast), identify which SPECIFIC entity each mention refers to (direct-regex
matched text, or the disambiguation-lookup-resolved candidate name for
ambiguous bare forms), score stance with the entity-focused window
classifier (same one used everywhere else this session), and produce one
row per (comment, entity) -- so a comment mentioning two different
mavericks contributes to both entities' distributions separately.

Stage 1: descriptive only (mention count + stance_prob distribution per
entity) -- no regression fitting here. That's deliberate: most of the
~570 possible entities have too few mentions for a stable coefficient,
and jumping straight to per-entity regressions on thin data would just
manufacture noise. Full traction regressions for the highest-volume
entities are a planned follow-on, not this script.

Output: data/processed/per_entity_stance_breakdown.csv
"""
import os
import re
import sys
import json
import argparse
import numpy as np
import pandas as pd
import duckdb
import joblib

sys.path.insert(0, os.path.dirname(__file__))
from refine_thesis_models import build_regex
from rerun_refined_regressions_v2 import load_entities_split_corrected, STAGED_PATH, EMPATH_PATH, THREAD_PATH, BRIGADE_PATH, PRESENCE_PATH
from combined_maverick_detector import load_maverick_disambiguation_lookup, VALID_MAVERICK_CANDIDATES, CANDIDATE_TO_BARES as MAVERICK_CANDIDATE_TO_BARES
from consensus_disambiguation_lookup import load_consensus_disambiguation_lookup, VALID_CONSENSUS_CANDIDATES, CANDIDATE_TO_BARES as CONSENSUS_CANDIDATE_TO_BARES
from stance_window_utils import extract_entity_window

STANCE_MODEL_PATH = 'data/processed/stance_classifier.joblib'
OUT_PATH = 'data/processed/per_entity_stance_breakdown.csv'
MIN_MENTIONS_TO_REPORT = 20  # below this, distribution stats are too noisy to be meaningful


def entity_groups_for_row(text, cid, rx, lookup, candidate_to_bares):
    """Same grouping logic as build_stance_active_learning_queue.py's
    multi-entity split -- returns {entity_key: [span, ...]}. entity_key is
    the lowercased matched text for direct regex hits (a rough per-surface-
    form identity, not a fully canonicalized one -- see module docstring),
    or the resolved candidate name for lookup-fallback hits."""
    text = str(text)
    direct_spans = [{"start": m.start(), "end": m.end(), "text": m.group(0)} for m in rx.finditer(text)]
    groups = {}
    for s in direct_spans:
        groups.setdefault(s["text"].lower(), []).append(s)
    if not groups:
        resolved = lookup.get(str(cid))
        bares = candidate_to_bares.get(resolved, [])
        fallback_spans = []
        for bare in bares:
            bare_rx = re.compile(r'\b' + re.escape(bare) + r'\b', re.IGNORECASE)
            fallback_spans.extend({"start": m.start(), "end": m.end(), "text": m.group(0)} for m in bare_rx.finditer(text))
        if fallback_spans:
            # FIX: lowercase here too, matching direct-match keys above --
            # otherwise e.g. "Stephen Hawking" (lookup-resolved, title
            # case) and "stephen hawking" (direct full-name match,
            # lowercased) end up as two separate rows for the same entity.
            groups[resolved.lower()] = fallback_spans
    return groups


def build_long_table(df, has_col, rx, lookup, candidate_to_bares, vec, clf, text_lookup):
    mask = df[has_col] == 1
    ids = df.loc[mask, 'id'].astype(str)
    print(f"  Processing {len(ids):,} {has_col} mentions...")

    rows = []
    windows_to_score = []
    row_meta = []
    for cid in ids:
        text = text_lookup.get(cid)
        if text is None:
            continue
        groups = entity_groups_for_row(text, cid, rx, lookup, candidate_to_bares)
        for entity_key, spans in groups.items():
            if entity_key is None:
                continue
            window = extract_entity_window(text, spans)
            windows_to_score.append(window)
            row_meta.append({"comment_id": cid, "entity": entity_key})

    if not windows_to_score:
        return pd.DataFrame(columns=["comment_id", "entity", "stance_prob"])

    print(f"  Scoring {len(windows_to_score):,} (comment, entity) windows...")
    X = vec.transform(windows_to_score)
    probs = clf.predict_proba(X)[:, 1]
    for r, p in zip(row_meta, probs):
        r["stance_prob"] = p
    return pd.DataFrame(row_meta)


def summarize(long_df, construct_label):
    if long_df.empty:
        return pd.DataFrame()
    g = long_df.groupby('entity')['stance_prob']
    summary = g.agg(
        mention_count='count',
        mean_stance_prob='mean',
        median_stance_prob='median',
        p25_stance_prob=lambda x: x.quantile(0.25),
        p75_stance_prob=lambda x: x.quantile(0.75),
    ).reset_index()
    summary['pct_hostile'] = g.apply(lambda x: (x < 0.5).mean()).values
    summary['pct_strongly_hostile_lt_0.3'] = g.apply(lambda x: (x < 0.3).mean()).values
    summary['pct_lean_hostile_0.3_0.5'] = g.apply(lambda x: ((x >= 0.3) & (x < 0.5)).mean()).values
    summary['pct_lean_endorse_0.5_0.7'] = g.apply(lambda x: ((x >= 0.5) & (x < 0.7)).mean()).values
    summary['pct_strongly_endorse_gte_0.7'] = g.apply(lambda x: (x >= 0.7).mean()).values
    summary['construct'] = construct_label
    return summary.sort_values('mention_count', ascending=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--population', default='unfiltered', choices=['unfiltered', 'pure'],
                         help="'unfiltered' = crosspost/brigade-excluded only (default); "
                              "'pure' = also elasticity<=33rd percentile + insider-presence>=0.75, "
                              "the curated core-community population used elsewhere in this project.")
    args = parser.parse_args()
    global OUT_PATH
    OUT_PATH = f'data/processed/per_entity_stance_breakdown_{args.population}.csv'

    print(f"=== Per-entity stance breakdown (r/conspiracy, {args.population} population) ===")

    print("Loading stance classifier...")
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec, clf = stance_model['vec'], stance_model['clf']
    print(f"  cv_kappa={stance_model['cv_kappa']:.3f}, cv_auc={stance_model['cv_auc']:.3f}")

    print("Loading verified entity lists...")
    mavericks, canon, consensus = load_entities_split_corrected()
    rx_mav = build_regex(mavericks)
    rx_con = build_regex(consensus)
    lookup = load_maverick_disambiguation_lookup()
    consensus_lookup = load_consensus_disambiguation_lookup()

    con = duckdb.connect()
    print(f"Loading r/conspiracy {args.population} population (entity flags only, no full text)...")
    if args.population == 'pure':
        query = f"""
            SELECT
                s.id,
                CAST(regexp_matches(e.text, $1) AS INTEGER) as has_maverick_regex,
                CAST(regexp_matches(e.text, $2) AS INTEGER) as has_consensus_expert_regex
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
    else:
        query = f"""
            SELECT
                s.id,
                CAST(regexp_matches(e.text, $1) AS INTEGER) as has_maverick_regex,
                CAST(regexp_matches(e.text, $2) AS INTEGER) as has_consensus_expert_regex
            FROM '{STAGED_PATH}' s
            JOIN '{EMPATH_PATH}' e ON s.id = e.id
            JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
            LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
            WHERE t.is_high_crosspost = 0
              AND COALESCE(b.brigade_upvote_flag, 0) = 0
              AND COALESCE(b.brigade_downvote_flag, 0) = 0
            QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
        """
    df = con.execute(query, ["(?i)" + rx_mav.pattern, "(?i)" + rx_con.pattern]).df()
    print(f"  Loaded {len(df):,} rows.")

    resolved_mav = df["id"].astype(str).map(lookup)
    df["has_maverick"] = (df["has_maverick_regex"].astype(bool) | resolved_mav.isin(VALID_MAVERICK_CANDIDATES)).astype(int)
    resolved_con = df["id"].astype(str).map(consensus_lookup)
    df["has_consensus_expert"] = (df["has_consensus_expert_regex"].astype(bool) | resolved_con.isin(VALID_CONSENSUS_CANDIDATES)).astype(int)
    df = df.drop(columns=["has_maverick_regex", "has_consensus_expert_regex"])

    mention_mask = (df['has_maverick'] == 1) | (df['has_consensus_expert'] == 1)
    mention_ids_df = df.loc[mention_mask, ['id']].copy()
    print(f"Fetching text for {len(mention_ids_df):,} mentions...")
    con.register("mention_ids_view", mention_ids_df)
    text_df = con.execute(f"""
        SELECT e.id, e.text FROM '{EMPATH_PATH}' e JOIN mention_ids_view n ON e.id = n.id
    """).df()
    text_lookup = dict(zip(text_df['id'], text_df['text']))
    print(f"  Fetched {len(text_lookup):,} texts.")

    print("\nBuilding per-entity long table (maverick)...")
    long_mav = build_long_table(df, 'has_maverick', rx_mav, lookup, MAVERICK_CANDIDATE_TO_BARES, vec, clf, text_lookup)
    print("Building per-entity long table (consensus)...")
    long_con = build_long_table(df, 'has_consensus_expert', rx_con, consensus_lookup, CONSENSUS_CANDIDATE_TO_BARES, vec, clf, text_lookup)

    summary_mav = summarize(long_mav, 'maverick')
    summary_con = summarize(long_con, 'consensus')
    summary = pd.concat([summary_mav, summary_con], ignore_index=True)
    summary.to_csv(OUT_PATH, index=False)
    print(f"\nSaved full per-entity breakdown to {OUT_PATH}")

    print(f"\n=== Top 30 mavericks by mention count (min {MIN_MENTIONS_TO_REPORT} mentions) ===")
    top_mav = summary_mav[summary_mav['mention_count'] >= MIN_MENTIONS_TO_REPORT].head(30)
    print(top_mav[['entity', 'mention_count', 'mean_stance_prob', 'pct_hostile']].to_string(index=False))

    print(f"\n=== Top 30 consensus figures by mention count (min {MIN_MENTIONS_TO_REPORT} mentions) ===")
    top_con = summary_con[summary_con['mention_count'] >= MIN_MENTIONS_TO_REPORT].head(30)
    print(top_con[['entity', 'mention_count', 'mean_stance_prob', 'pct_hostile']].to_string(index=False))

    # Direct test of the "prominence predicts hostility" hypothesis
    for label, s in [("maverick", summary_mav), ("consensus", summary_con)]:
        s_filtered = s[s['mention_count'] >= MIN_MENTIONS_TO_REPORT]
        if len(s_filtered) >= 5:
            corr = s_filtered['mention_count'].corr(s_filtered['pct_hostile'], method='spearman')
            print(f"\nSpearman correlation (mention_count vs pct_hostile), {label}: {corr:.3f} "
                  f"(n={len(s_filtered)} entities)")

    print("\nDone.")


if __name__ == "__main__":
    main()
