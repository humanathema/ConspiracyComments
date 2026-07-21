"""per_entity_stance_over_time.py

Extends per_entity_stance_breakdown.py with a time dimension. Motivated by
Nash's question: the pooled per-entity breakdown shows Alex Jones ~85-86%
hostile overall (see ANTIGRAVITY_HANDOFF.md) -- read as r/conspiracy having
turned on him as a "shill"/"controlled opposition". That pooled number
can't tell us whether hostility has been stable across the corpus's whole
2008-2026 span, or whether there's a TIME REVERSAL -- Jones (and similar
media-personality mavericks) endorsed in the earlier years and only turned
hostile more recently. This script bins the same (comment, entity) stance
scores by year and reports early-vs-late splits so a reversal would show
up directly instead of being averaged away.

Method: identical entity-matching + stance-scoring pipeline as
per_entity_stance_breakdown.py (same regex/disambiguation lookup, same
window classifier), unfiltered r/conspiracy population, but this time
carrying `created_utc` through to the per-(comment, entity) row so mentions
can be aggregated by year.

REDESIGNED 2026-07-21: switched to the 3-class (hostile / endorsement /
other) classifier and stopped hard-excluding list/link-dump mentions --
see per_entity_stance_breakdown.py's module docstring for why. pct_hostile
here now means "share of mentions the model's argmax calls hostile", not
"share with P(endorsement)<0.5" -- same intent, different mechanics, and
the early-vs-late reversal test (50%-line crossing) still applies
directly to this definition.

Output:
  data/processed/per_entity_stance_over_time.csv       -- one row per
    (entity, year) with mention_count + per-class mean prob/pct
  data/processed/per_entity_stance_reversal_summary.csv -- one row per
    entity with early-half vs late-half stats (split at each entity's own
    median comment date, not a fixed calendar year) and a reversal flag
"""
import os
import sys
import argparse
import numpy as np
import pandas as pd
import duckdb
import joblib

sys.path.insert(0, os.path.dirname(__file__))
from refine_thesis_models import build_regex
from rerun_refined_regressions_v2 import load_entities_split_corrected, STAGED_PATH, EMPATH_PATH, THREAD_PATH, BRIGADE_PATH
from combined_maverick_detector import load_maverick_disambiguation_lookup, VALID_MAVERICK_CANDIDATES, CANDIDATE_TO_BARES as MAVERICK_CANDIDATE_TO_BARES
from consensus_disambiguation_lookup import load_consensus_disambiguation_lookup, VALID_CONSENSUS_CANDIDATES, CANDIDATE_TO_BARES as CONSENSUS_CANDIDATE_TO_BARES
from stance_window_utils import extract_entity_window, is_list_or_link_dump_window
from per_entity_stance_breakdown import entity_groups_for_row

STANCE_MODEL_PATH = 'data/processed/stance_classifier_3class.joblib'
YEARLY_OUT_PATH = 'data/processed/per_entity_stance_over_time.csv'
REVERSAL_OUT_PATH = 'data/processed/per_entity_stance_reversal_summary.csv'
MIN_MENTIONS_TO_REPORT_YEAR = 20   # per (entity, year) cell
MIN_TOTAL_MENTIONS = 150            # entity must clear this to get a reversal row at all
MIN_HALF_MENTIONS = 30              # each half (early/late) must clear this too


def build_long_table_with_time(df, has_col, rx, lookup, candidate_to_bares, vec, clf, classes, text_lookup, time_lookup):
    mask = df[has_col] == 1
    ids = df.loc[mask, 'id'].astype(str)
    print(f"  Processing {len(ids):,} {has_col} mentions...")

    windows_to_score = []
    row_meta = []
    n_list_dump = 0
    for cid in ids:
        text = text_lookup.get(cid)
        if text is None:
            continue
        groups = entity_groups_for_row(text, cid, rx, lookup, candidate_to_bares)
        for entity_key, spans in groups.items():
            if entity_key is None:
                continue
            window = extract_entity_window(text, spans)
            is_dump = is_list_or_link_dump_window(window)
            n_list_dump += is_dump
            windows_to_score.append(window)
            row_meta.append({"comment_id": cid, "entity": entity_key, "is_list_dump": is_dump,
                              "created_utc": time_lookup.get(cid)})

    if n_list_dump:
        print(f"  {n_list_dump:,} mention(s) flagged as list/link-dump -- scored normally, not excluded.")

    if not windows_to_score:
        return pd.DataFrame(columns=["comment_id", "entity", "is_list_dump", "created_utc", "predicted_label"] + [f"p_{c}" for c in classes])

    print(f"  Scoring {len(windows_to_score):,} (comment, entity) windows...")
    X = vec.transform(windows_to_score)
    probs = clf.predict_proba(X)
    pred_idx = probs.argmax(axis=1)
    out = pd.DataFrame(row_meta)
    for i, c in enumerate(classes):
        out[f"p_{c}"] = probs[:, i]
    out["predicted_label"] = [classes[i] for i in pred_idx]
    out["year"] = pd.to_datetime(out["created_utc"], unit="s").dt.year
    return out


def yearly_summary(long_df, construct_label, classes):
    if long_df.empty:
        return pd.DataFrame()
    g = long_df.groupby(['entity', 'year'])
    summary = g.size().rename('mention_count').reset_index()
    for c in classes:
        summary[f'mean_p_{c}'] = g[f'p_{c}'].mean().values
        summary[f'pct_predicted_{c}'] = g.apply(lambda x, c=c: (x['predicted_label'] == c).mean()).values
    summary['pct_hostile'] = summary['pct_predicted_hostile']
    summary['construct'] = construct_label
    return summary


def reversal_summary(long_df, construct_label):
    if long_df.empty:
        return pd.DataFrame()
    rows = []
    for entity, sub in long_df.groupby('entity'):
        if len(sub) < MIN_TOTAL_MENTIONS:
            continue
        sub = sub.sort_values('created_utc')
        median_time = sub['created_utc'].median()
        early = sub[sub['created_utc'] <= median_time]
        late = sub[sub['created_utc'] > median_time]
        if len(early) < MIN_HALF_MENTIONS or len(late) < MIN_HALF_MENTIONS:
            continue
        early_hostile = (early['predicted_label'] == 'hostile').mean()
        late_hostile = (late['predicted_label'] == 'hostile').mean()
        early_endorse = (early['predicted_label'] == 'endorsement').mean()
        late_endorse = (late['predicted_label'] == 'endorsement').mean()
        early_other = (early['predicted_label'] == 'other').mean()
        late_other = (late['predicted_label'] == 'other').mean()
        # crude nonparametric trend check at the row level: does P(endorsement)
        # correlate with time within this entity's own mentions? (same
        # semantics as the old binary stance_prob's role here)
        time_corr = sub['p_endorsement'].corr(sub['created_utc'].rank(), method='spearman')
        reversed_hostile_to_endorse = early_hostile >= 0.5 and late_hostile < 0.5
        reversed_endorse_to_hostile = early_hostile < 0.5 and late_hostile >= 0.5
        rows.append({
            'entity': entity,
            'construct': construct_label,
            'total_mentions': len(sub),
            'early_n': len(early),
            'late_n': len(late),
            'early_period': f"{pd.to_datetime(early['created_utc'].min(), unit='s').year}-{pd.to_datetime(early['created_utc'].max(), unit='s').year}",
            'late_period': f"{pd.to_datetime(late['created_utc'].min(), unit='s').year}-{pd.to_datetime(late['created_utc'].max(), unit='s').year}",
            'early_pct_hostile': early_hostile,
            'late_pct_hostile': late_hostile,
            'delta_pct_hostile': late_hostile - early_hostile,
            'early_pct_endorsement': early_endorse,
            'late_pct_endorsement': late_endorse,
            'early_pct_other': early_other,
            'late_pct_other': late_other,
            'spearman_time_vs_endorsement_prob': time_corr,
            'reversed_endorse_to_hostile': reversed_endorse_to_hostile,
            'reversed_hostile_to_endorse': reversed_hostile_to_endorse,
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values('delta_pct_hostile', ascending=False)
    return out


def main():
    global MIN_TOTAL_MENTIONS
    parser = argparse.ArgumentParser()
    parser.add_argument('--min-total-mentions', type=int, default=MIN_TOTAL_MENTIONS)
    args = parser.parse_args()
    MIN_TOTAL_MENTIONS = args.min_total_mentions

    print("=== Per-entity stance over time (r/conspiracy, unfiltered population) ===")

    print("Loading stance classifier...")
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec, clf = stance_model['vec'], stance_model['clf']
    classes = list(clf.classes_)
    print(f"  classes={classes}, cv_kappa={stance_model['cv_kappa']:.3f}, cv_auc={stance_model['cv_auc']:.3f}")

    print("Loading verified entity lists...")
    mavericks, canon, consensus = load_entities_split_corrected()
    rx_mav = build_regex(mavericks)
    rx_con = build_regex(consensus)
    lookup = load_maverick_disambiguation_lookup()
    consensus_lookup = load_consensus_disambiguation_lookup()

    con = duckdb.connect()
    print("Loading r/conspiracy unfiltered population (entity flags + created_utc)...")
    query = f"""
        SELECT
            s.id,
            e.created_utc,
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
    time_lookup = dict(zip(df['id'], df['created_utc']))
    print(f"  Fetched {len(text_lookup):,} texts.")

    print("\nBuilding per-entity long table with time (maverick)...")
    long_mav = build_long_table_with_time(df, 'has_maverick', rx_mav, lookup, MAVERICK_CANDIDATE_TO_BARES, vec, clf, classes, text_lookup, time_lookup)
    print("Building per-entity long table with time (consensus)...")
    long_con = build_long_table_with_time(df, 'has_consensus_expert', rx_con, consensus_lookup, CONSENSUS_CANDIDATE_TO_BARES, vec, clf, classes, text_lookup, time_lookup)

    yearly_mav = yearly_summary(long_mav, 'maverick', classes)
    yearly_con = yearly_summary(long_con, 'consensus', classes)
    yearly = pd.concat([yearly_mav, yearly_con], ignore_index=True)
    yearly.to_csv(YEARLY_OUT_PATH, index=False)
    print(f"\nSaved yearly breakdown to {YEARLY_OUT_PATH}")

    rev_mav = reversal_summary(long_mav, 'maverick')
    rev_con = reversal_summary(long_con, 'consensus')
    reversal = pd.concat([rev_mav, rev_con], ignore_index=True)
    reversal.to_csv(REVERSAL_OUT_PATH, index=False)
    print(f"Saved early-vs-late reversal summary to {REVERSAL_OUT_PATH}")

    print(f"\n=== Alex Jones, year by year (min {MIN_MENTIONS_TO_REPORT_YEAR} mentions/year) ===")
    jones_years = yearly_mav[(yearly_mav['entity'] == 'alex jones') & (yearly_mav['mention_count'] >= MIN_MENTIONS_TO_REPORT_YEAR)]
    print(jones_years.sort_values('year')[['year', 'mention_count', 'pct_predicted_hostile', 'pct_predicted_endorsement', 'pct_predicted_other']].to_string(index=False))

    print("\n=== Entities with a possible time reversal (min "
          f"{MIN_TOTAL_MENTIONS} total mentions, {MIN_HALF_MENTIONS}/half) ===")
    if not reversal.empty:
        flagged = reversal[reversal['reversed_endorse_to_hostile'] | reversal['reversed_hostile_to_endorse']]
        cols = ['entity', 'construct', 'total_mentions', 'early_period', 'late_period',
                'early_pct_hostile', 'late_pct_hostile', 'delta_pct_hostile', 'spearman_time_vs_endorsement_prob']
        if flagged.empty:
            print("  None flagged (no entity crossed the 50% hostile line between halves).")
        else:
            print(flagged[cols].to_string(index=False))
        print("\n=== Full early-vs-late table, sorted by |delta_pct_hostile| ===")
        reversal['abs_delta'] = reversal['delta_pct_hostile'].abs()
        print(reversal.sort_values('abs_delta', ascending=False).head(30)[cols].to_string(index=False))
    else:
        print("  No entity cleared the mention thresholds.")

    print("\nDone.")


if __name__ == "__main__":
    main()
