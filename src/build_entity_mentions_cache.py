"""build_entity_mentions_cache.py

Performs one full, consolidated corpus scan over both r/conspiracy unfiltered
and r/politics populations to extract, score, and materialize all entity
mentions (at individual-entity, merged-construct, and merged-subgroup granularities).

Outputs a centralized long-format cache:
  - data/processed/entity_mentions_cache_2stage_pooled.parquet
  - data/processed/entity_mentions_cache_2stage_pooled.csv

Columns:
  comment_id | entity_key | construct | p_hostile | p_endorsement | p_other | predicted_label | is_list_dump
"""
import os
import re
import sys
import numpy as np
import pandas as pd
import joblib
import duckdb

sys.path.insert(0, os.path.dirname(__file__))
from refine_thesis_models import build_regex
from rerun_refined_regressions_v2 import (
    load_entities_split_corrected, compute_has_maverick, compute_has_consensus_expert,
    STAGED_PATH, EMPATH_PATH, THREAD_PATH, PRESENCE_PATH, BRIGADE_PATH,
    POLITICS_SCORED_PATH, VERIFIED_MAVERICK_ADDITIONS,
)
from combined_maverick_detector import load_maverick_disambiguation_lookup, VALID_MAVERICK_CANDIDATES, CANDIDATE_TO_BARES as MAVERICK_CANDIDATE_TO_BARES
from consensus_disambiguation_lookup import load_consensus_disambiguation_lookup, VALID_CONSENSUS_CANDIDATES, CANDIDATE_TO_BARES as CONSENSUS_CANDIDATE_TO_BARES
from stance_window_utils import extract_entity_window, compute_spans_for_row, is_list_or_link_dump_window, filter_quoted_spans

STANCE_MODEL_PATH = 'data/processed/stance_classifier_2stage_pooled.joblib'
LOOKUP_PATH = 'data/processed/entity_categories_lookup.csv'
OUT_PARQUET = 'data/processed/entity_mentions_cache_2stage_pooled.parquet'
OUT_CSV = 'data/processed/entity_mentions_cache_2stage_pooled.csv'


def entity_groups_for_row(text, cid, rx, lookup, candidate_to_bares):
    """Same grouping logic as original per_entity_stance_breakdown.py --
    returns {entity_key: [span, ...]}. filters out quoted spans."""
    text = str(text)
    direct_spans = [{"start": m.start(), "end": m.end(), "text": m.group(0)} for m in rx.finditer(text)]
    direct_spans = filter_quoted_spans(text, direct_spans)
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
        fallback_spans = filter_quoted_spans(text, fallback_spans)
        if fallback_spans:
            groups[resolved.lower()] = fallback_spans
    return groups


def score_windows_cascade(windows, vec, clf_stage1, clf_stage2):
    """Scores text windows with the two-stage cascade: Stage 1 (clear vs. other)
    gates Stage 2 (hostile vs. endorsement). Returns predicted_label plus a
    combined 3-way probability vector."""
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


def load_whistleblower_names_uncorrected():
    """Scrapes the '# whistleblower (124)' block directly to replicate the original
    split script's parsing bug (missing UNAMBIGUOUS_MAVERICK_ALIASES)."""
    path = os.path.join(os.path.dirname(__file__), 'maverick_authority_verified.py')
    with open(path) as f:
        text = f.read()
    start = text.index('# whistleblower (124)')
    end = text.index('# credentialed_advocacy_org', start)
    section = text[start:end]
    names = re.findall(r'"((?:[^"\\]|\\.)*)"', section)
    all_names = list(dict.fromkeys(names + VERIFIED_MAVERICK_ADDITIONS))
    return set(n.lower() for n in all_names)


def main():
    print("=== Materializing Centralized Long-Format Entity-Mentions Cache ===")
    
    if not os.path.exists(STANCE_MODEL_PATH):
        print(f"MISSING STANCE MODEL: {STANCE_MODEL_PATH}. Train it first.")
        sys.exit(1)
        
    print("Loading two-stage cascade model...")
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec = stance_model['vec']
    clf_stage1, clf_stage2 = stance_model['clf_stage1'], stance_model['clf_stage2']
    print(f"Loaded model successfully (CV kappa={stance_model['cv_kappa_end_to_end']:.3f})")

    print("Loading verified entity lists...")
    mavericks, canon, consensus = load_entities_split_corrected()
    rx_mav = build_regex(mavericks)
    rx_con = build_regex(consensus)

    lookup = load_maverick_disambiguation_lookup()
    consensus_lookup = load_consensus_disambiguation_lookup()

    # Load categories and add misspelling fix for 'taibi'
    print("Loading entity category lookup mappings...")
    lookup_df = pd.read_csv(LOOKUP_PATH)
    entity_to_cat = dict(zip(lookup_df['entity_key'], lookup_df['category']))
    entity_to_cat['taibi'] = 'whistleblower'
    
    # Save the 'taibi' fix back to CSV for permanent consistency
    if 'taibi' not in lookup_df['entity_key'].values:
        new_row = pd.DataFrame([{'entity_key': 'taibi', 'category': 'whistleblower', 'construct': 'maverick'}])
        lookup_df = pd.concat([lookup_df, new_row], ignore_index=True)
        lookup_df.to_csv(LOOKUP_PATH, index=False)

    whistleblower_set_uncorrected = load_whistleblower_names_uncorrected()

    con = duckdb.connect()
    print("\n[Population 1/2] Loading r/conspiracy unfiltered...")
    query_unfiltered = f"""
        SELECT
            s.id, e.text,
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
    df_con_unf = con.execute(query_unfiltered, ["(?i)" + rx_mav.pattern, "(?i)" + rx_con.pattern]).df()
    print(f"  Loaded {len(df_con_unf):,} rows.")

    print("  Applying fallback disambiguation lookup...")
    resolved_mav = df_con_unf["id"].astype(str).map(lookup)
    df_con_unf["has_maverick"] = (df_con_unf["has_maverick_regex"].astype(bool) | resolved_mav.isin(VALID_MAVERICK_CANDIDATES)).astype(int)
    resolved_con = df_con_unf["id"].astype(str).map(consensus_lookup)
    df_con_unf["has_consensus_expert"] = (df_con_unf["has_consensus_expert_regex"].astype(bool) | resolved_con.isin(VALID_CONSENSUS_CANDIDATES)).astype(int)
    df_con_unf = df_con_unf.drop(columns=["has_maverick_regex", "has_consensus_expert_regex"])

    # Keep only comments with at least one mention of interest
    con_mentions = df_con_unf[(df_con_unf['has_maverick'] == 1) | (df_con_unf['has_consensus_expert'] == 1)].copy()
    print(f"  Found {len(con_mentions):,} comments with mentions in r/conspiracy.")

    print("\n[Population 2/2] Loading r/politics...")
    df_pol = pd.read_parquet(POLITICS_SCORED_PATH)
    print(f"  Loaded {len(df_pol):,} rows.")
    
    print("  Flagging entity mentions in r/politics...")
    df_pol['has_maverick'] = compute_has_maverick(df_pol, rx_mav, lookup)
    df_pol['has_consensus_expert'] = compute_has_consensus_expert(df_pol, rx_con, consensus_lookup)
    
    # Keep only comments with at least one mention of interest
    pol_mentions = df_pol[(df_pol['has_maverick'] == 1) | (df_pol['has_consensus_expert'] == 1)].copy()
    print(f"  Found {len(pol_mentions):,} comments with mentions in r/politics.")

    # Combine into a single text-lookup base for processing
    print("\nCombining comment text lookups...")
    con_mentions['id'] = con_mentions['id'].astype(str)
    pol_mentions['id'] = pol_mentions['id'].astype(str)
    
    combined_mentions = pd.concat([
        con_mentions[['id', 'text', 'has_maverick', 'has_consensus_expert']],
        pol_mentions[['id', 'text', 'has_maverick', 'has_consensus_expert']]
    ], ignore_index=True).drop_duplicates(subset=['id'])
    
    print(f"Total unique comments to process: {len(combined_mentions):,}")

    rows_to_score = []
    
    print("\nExtracting windows across all granularities...")
    for idx, row in combined_mentions.iterrows():
        cid = row['id']
        text = str(row['text'])
        
        # --- MAVERICK CONSTRUCT ---
        if row['has_maverick'] == 1:
            # 1. Granularity A: Per-Entity Windows
            groups = entity_groups_for_row(text, cid, rx_mav, lookup, MAVERICK_CANDIDATE_TO_BARES)
            for entity_key, spans in groups.items():
                if entity_key is not None:
                    win = extract_entity_window(text, spans)
                    rows_to_score.append({
                        'comment_id': cid,
                        'entity_key': entity_key,
                        'construct': 'maverick',
                        'window_text': win
                    })
            
            # 2. Granularity B: Merged-Construct Window
            merged_spans = compute_spans_for_row(text, cid, rx_mav, lookup, MAVERICK_CANDIDATE_TO_BARES)
            win_merged = extract_entity_window(text, merged_spans)
            rows_to_score.append({
                'comment_id': cid,
                'entity_key': 'merged_maverick',
                'construct': 'maverick',
                'window_text': win_merged
            })

            # 3. Granularity C: Corrected Merged-Subgroups
            corrected_subgroups = {}
            for entity_key, spans in groups.items():
                if entity_key is not None:
                    cat = entity_to_cat.get(entity_key, 'conspiracy_general')
                    sub = 'whistleblower' if cat == 'whistleblower' else 'other_maverick'
                    corrected_subgroups.setdefault(sub, []).extend(spans)
                    
            for sub, spans in corrected_subgroups.items():
                win_sub = extract_entity_window(text, spans)
                rows_to_score.append({
                    'comment_id': cid,
                    'entity_key': f'merged_{sub}',
                    'construct': 'maverick',
                    'window_text': win_sub
                })

            # 4. Granularity D: Uncorrected Merged-Subgroups (Scraped Bug Mode)
            uncorrected_subgroups = {}
            for entity_key, spans in groups.items():
                if entity_key is not None:
                    sub = 'whistleblower' if entity_key in whistleblower_set_uncorrected else 'other_maverick'
                    uncorrected_subgroups.setdefault(sub, []).extend(spans)
                    
            for sub, spans in uncorrected_subgroups.items():
                win_sub = extract_entity_window(text, spans)
                rows_to_score.append({
                    'comment_id': cid,
                    'entity_key': f'merged_{sub}_uncorrected',
                    'construct': 'maverick',
                    'window_text': win_sub
                })

        # --- CONSENSUS CONSTRUCT ---
        if row['has_consensus_expert'] == 1:
            # 1. Granularity A: Per-Entity Windows
            groups = entity_groups_for_row(text, cid, rx_con, consensus_lookup, CONSENSUS_CANDIDATE_TO_BARES)
            for entity_key, spans in groups.items():
                if entity_key is not None:
                    win = extract_entity_window(text, spans)
                    rows_to_score.append({
                        'comment_id': cid,
                        'entity_key': entity_key,
                        'construct': 'consensus',
                        'window_text': win
                    })
            
            # 2. Granularity B: Merged-Construct Window
            merged_spans = compute_spans_for_row(text, cid, rx_con, consensus_lookup, CONSENSUS_CANDIDATE_TO_BARES)
            win_merged = extract_entity_window(text, merged_spans)
            rows_to_score.append({
                'comment_id': cid,
                'entity_key': 'merged_consensus',
                'construct': 'consensus',
                'window_text': win_merged
            })

    df_scored = pd.DataFrame(rows_to_score)
    print(f"Extracted {len(df_scored):,} total windows across all granularities.")
    
    if df_scored.empty:
        print("No windows found. Exiting.")
        return

    print("\nScoring all windows using two-stage cascade classifier...")
    windows = df_scored['window_text'].fillna('').tolist()
    predicted_label, p_by_class = score_windows_cascade(windows, vec, clf_stage1, clf_stage2)

    df_scored['p_hostile'] = p_by_class['hostile']
    df_scored['p_endorsement'] = p_by_class['endorsement']
    df_scored['p_other'] = p_by_class['other']
    df_scored['predicted_label'] = predicted_label
    df_scored['is_list_dump'] = df_scored['window_text'].apply(is_list_or_link_dump_window).astype(int)

    # Drop temporary window_text column before saving
    df_cache = df_scored.drop(columns=['window_text'])

    print(f"\nSaving centralized cache to:")
    print(f"  Parquet: {OUT_PARQUET}")
    print(f"  CSV:     {OUT_CSV}")
    
    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    df_cache.to_parquet(OUT_PARQUET, index=False)
    df_cache.to_csv(OUT_CSV, index=False)
    
    print("\nCache materialized successfully!")
    print(f"Total rows cached: {len(df_cache):,}")
    print(f"  Per-Entity rows: {len(df_cache[~df_cache['entity_key'].str.contains('merged_')]):,}")
    print(f"  Subgroup/Construct-Merged rows: {len(df_cache[df_cache['entity_key'].str.contains('merged_')]):,}")


if __name__ == '__main__':
    main()
