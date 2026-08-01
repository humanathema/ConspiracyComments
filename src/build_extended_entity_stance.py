"""build_extended_entity_stance.py

Extends stance detection beyond the maverick/consensus constructs to
every other named-entity list the project has already built but never
ran through the stance classifier:

  - CANONICAL_EXPERTS (src/refine_thesis_models.py) -- historical/
    scientific figures used for the has_canonical_expert regression flag.
    Previously mention-counts-only, see build_canonical_entity_mentions.py.
  - The "other" buckets from entity_final_review.csv (villain,
    mainstream_figure_not_source, mainstream_source, alternative_source)
    -- previously mention-counts-only, see build_other_entities_mentions.py.
    Reuses that script's exact filtered entity list
    (data/processed/other_entities_mentions.csv) rather than re-deriving
    it, so the ambiguity/junk exclusions already applied there carry over
    unchanged.

Uses the SAME trained two-stage cascade classifier and windowing
convention as the maverick/consensus pipeline
(stance_classifier_2stage_pooled.joblib, stance_window_utils.py) --
no new labeling, no new judgment calls about entity identity, purely a
mechanical extension of an already-validated pipeline to a wider entity
set. One entity ("Nikola Tesla") already exists in the maverick/consensus
lists and is skipped here to avoid double-counting.

Memory-safe by construction: the entity-match regex is applied INSIDE the
DuckDB WHERE clause, so only matching rows' text is ever materialized
into pandas -- never the full 21M-row / 19M-row unfiltered population
(see ANTIGRAVITY_HANDOFF.md machine-constraints guidance).

Outputs:
  data/processed/entity_mentions_cache_extended.parquet
    comment_id | entity_key | construct | p_hostile | p_endorsement |
    p_other | predicted_label | is_list_dump
  data/processed/per_entity_stance_breakdown_extended.csv
    entity | mention_count | mean_p_hostile | mean_p_endorsement |
    mean_p_other | pct_predicted_hostile | pct_predicted_endorsement |
    pct_predicted_other | pct_list_dump | pct_hostile | construct
"""
import os
import re
import sys
import csv

import numpy as np
import pandas as pd
import joblib
import duckdb

sys.path.insert(0, os.path.dirname(__file__))
from refine_thesis_models import CANONICAL_EXPERTS, build_regex
from rerun_refined_regressions_v2 import (
    load_entities_split_corrected,
    STAGED_PATH, EMPATH_PATH, THREAD_PATH, BRIGADE_PATH, POLITICS_SCORED_PATH,
)
from stance_window_utils import extract_entity_window, is_list_or_link_dump_window, filter_quoted_spans
from per_entity_stance_breakdown import summarize

STANCE_MODEL_PATH = 'data/processed/stance_classifier_2stage_pooled.joblib'
OTHER_ENTITIES_PATH = 'data/processed/other_entities_mentions.csv'
UNREVIEWED_ENTITIES_PATH = 'data/processed/missing_entity_candidates.csv'
OUT_PARQUET = 'data/processed/entity_mentions_cache_extended.parquet'
OUT_BREAKDOWN = 'data/processed/per_entity_stance_breakdown_extended.csv'
MIN_MENTIONS_TO_REPORT = 20


def score_windows_cascade(windows, vec, clf_stage1, clf_stage2):
    X = vec.transform(windows)

    s1_classes = list(clf_stage1.classes_)
    p_stage1 = clf_stage1.predict_proba(X)
    p_other = p_stage1[:, s1_classes.index('other')]
    p_clear = 1.0 - p_other
    pred_stage1 = clf_stage1.predict(X)

    s2_classes = list(clf_stage2.classes_)
    p_stage2 = clf_stage2.predict_proba(X)
    p_hostile_given_clear = p_stage2[:, s2_classes.index('hostile')]
    p_endorsement_given_clear = p_stage2[:, s2_classes.index('endorsement')]

    p_hostile = p_clear * p_hostile_given_clear
    p_endorsement = p_clear * p_endorsement_given_clear

    predicted_label = np.where(
        pred_stage1 == 'other', 'other',
        np.where(p_hostile_given_clear >= p_endorsement_given_clear, 'hostile', 'endorsement'),
    )
    return predicted_label, {'hostile': p_hostile, 'endorsement': p_endorsement, 'other': p_other}


def entity_groups_for_row(text, rx):
    """Direct-regex-only grouping (no disambiguation-lookup fallback --
    none exists for these entities, same as build_canonical_entity_mentions.py
    / build_other_entities_mentions.py's mention-counting)."""
    spans = [{"start": m.start(), "end": m.end(), "text": m.group(0)} for m in rx.finditer(str(text))]
    spans = filter_quoted_spans(text, spans)
    groups = {}
    for s in spans:
        groups.setdefault(s["text"].lower(), []).append(s)
    return groups


def load_entity_list():
    print("Loading verified maverick/consensus lists (to exclude overlap)...")
    mavericks, _canon, consensus = load_entities_split_corrected()
    covered = set(m.lower() for m in mavericks) | set(c.lower() for c in consensus)

    entities = []  # (entity_string, construct)
    for name in CANONICAL_EXPERTS:
        if name.lower() in covered:
            print(f"  Skipping '{name}' -- already covered by maverick/consensus lists.")
            continue
        entities.append((name, 'canonical'))

    with open(OTHER_ENTITIES_PATH, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            name = row['entity']
            if name.lower() in covered:
                continue
            entities.append((name, row['bucket']))

    # Nash, 2026-07-26: extend stance coverage to the "unreviewed" list too --
    # these have no construct/bucket decision yet, but stance classification
    # doesn't depend on knowing the bucket first, and it's the same validated
    # classifier, no new judgment calls. Tagged construct='unreviewed' so the
    # explorer can show real stance numbers without pretending a bucket
    # decision has been made.
    already = set(name.lower() for name, _ in entities)
    with open(UNREVIEWED_ENTITIES_PATH, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            name = row['entity'].strip()
            if not name or name.lower() in covered or name.lower() in already:
                continue
            entities.append((name, 'unreviewed'))
            already.add(name.lower())

    print(f"Loaded {len(entities)} entities across {len(set(c for _, c in entities))} constructs.")
    return entities


def main():
    print("=== Extended entity-mentions cache: stance beyond maverick/consensus ===")

    if not os.path.exists(STANCE_MODEL_PATH):
        print(f"MISSING STANCE MODEL: {STANCE_MODEL_PATH}. Train it first.")
        sys.exit(1)

    print("Loading two-stage cascade model...")
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec = stance_model['vec']
    clf_stage1, clf_stage2 = stance_model['clf_stage1'], stance_model['clf_stage2']
    print(f"Loaded model successfully (CV kappa={stance_model['cv_kappa_end_to_end']:.3f})")

    entities = load_entity_list()
    entity_to_construct = {name.lower(): construct for name, construct in entities}
    rx = build_regex([name for name, _ in entities])

    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='4GB'")

    print("\n[Population 1/2] Scanning r/conspiracy unfiltered (regex applied in-SQL, "
          "only matching rows' text is materialized)...")
    query_unfiltered = f"""
        SELECT s.id, e.text
        FROM '{STAGED_PATH}' s
        JOIN '{EMPATH_PATH}' e ON s.id = e.id
        JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
        LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
        WHERE t.is_high_crosspost = 0
          AND COALESCE(b.brigade_upvote_flag, 0) = 0
          AND COALESCE(b.brigade_downvote_flag, 0) = 0
          AND regexp_matches(e.text, $1)
        QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
    """
    df_con = con.execute(query_unfiltered, ["(?i)" + rx.pattern]).df()
    df_con['id'] = df_con['id'].astype(str)
    print(f"  Found {len(df_con):,} matching comments in r/conspiracy.")

    print("\n[Population 2/2] Scanning r/politics...")
    df_pol_full = pd.read_parquet(POLITICS_SCORED_PATH, columns=['id', 'text'])
    pol_mask = df_pol_full['text'].astype(str).str.contains(rx, regex=True, na=False)
    df_pol = df_pol_full[pol_mask].copy()
    df_pol['id'] = df_pol['id'].astype(str)
    del df_pol_full
    print(f"  Found {len(df_pol):,} matching comments in r/politics.")

    combined = pd.concat([df_con[['id', 'text']], df_pol[['id', 'text']]], ignore_index=True)
    combined = combined.drop_duplicates(subset=['id'])
    del df_con, df_pol
    print(f"\nTotal unique matching comments to process: {len(combined):,}")

    rows_to_score = []
    print("\nExtracting per-entity windows...")
    for row in combined.itertuples(index=False):
        cid, text = row.id, row.text
        groups = entity_groups_for_row(text, rx)
        for entity_key, spans in groups.items():
            construct = entity_to_construct.get(entity_key)
            if construct is None:
                continue
            win = extract_entity_window(text, spans)
            rows_to_score.append({
                'comment_id': cid,
                'entity_key': entity_key,
                'construct': construct,
                'window_text': win,
            })
    del combined

    df_scored = pd.DataFrame(rows_to_score)
    print(f"Extracted {len(df_scored):,} total entity-mention windows.")
    if df_scored.empty:
        print("No windows found. Exiting.")
        return

    print("\nScoring all windows using the two-stage cascade classifier...")
    windows = df_scored['window_text'].fillna('').tolist()
    predicted_label, p_by_class = score_windows_cascade(windows, vec, clf_stage1, clf_stage2)

    df_scored['p_hostile'] = p_by_class['hostile']
    df_scored['p_endorsement'] = p_by_class['endorsement']
    df_scored['p_other'] = p_by_class['other']
    df_scored['predicted_label'] = predicted_label
    df_scored['is_list_dump'] = df_scored['window_text'].apply(is_list_or_link_dump_window).astype(int)

    df_cache = df_scored.drop(columns=['window_text'])
    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    df_cache.to_parquet(OUT_PARQUET, index=False)
    print(f"\nSaved extended entity-mentions cache to {OUT_PARQUET} ({len(df_cache):,} rows).")

    print("\nBuilding per-entity breakdown...")
    df_named = df_cache.rename(columns={'entity_key': 'entity'})
    breakdowns = []
    for construct in sorted(df_named['construct'].unique()):
        sub = df_named[df_named['construct'] == construct]
        breakdowns.append(summarize(sub, construct, ['hostile', 'endorsement', 'other']))
    breakdown = pd.concat(breakdowns, ignore_index=True)
    breakdown.to_csv(OUT_BREAKDOWN, index=False)
    print(f"Saved per-entity breakdown to {OUT_BREAKDOWN}")

    print(f"\n=== Top 30 by mention count (min {MIN_MENTIONS_TO_REPORT} mentions) ===")
    top = breakdown[breakdown['mention_count'] >= MIN_MENTIONS_TO_REPORT].sort_values('mention_count', ascending=False).head(30)
    print(top[['entity', 'construct', 'mention_count', 'pct_predicted_hostile', 'pct_predicted_endorsement', 'pct_predicted_other']].to_string(index=False))

    print("\nDone.")


if __name__ == '__main__':
    main()
