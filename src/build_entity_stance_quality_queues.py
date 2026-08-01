"""build_entity_stance_quality_queues.py

Generalizes the queue builder to support both Reddit and AboveTopSecret (ATS):
- Reddit (default): Draws stratified random samples across predictions for mavericks
  and consensus entities in r/conspiracy and r/politics comments.
- ATS (--platform ats): Draws a multi-era, multi-entity stratified sample of 99 comments,
  balanced across early (1998-2011) and late (2012-2026) eras, covering Julian Assange,
  Edward Snowden, WikiLeaks, and Alex Jones.

Predictions are saved separately to preserve blind rating discipline.

Outputs:
  data/hitl/queue_{platform}_stance_quality_check.csv
  data/processed/{platform}_stance_quality_check_predictions.csv
"""
import os
import sys
import json
import argparse
import re
import numpy as np
import pandas as pd
import duckdb
import joblib

sys.path.insert(0, os.path.dirname(__file__))
from refine_thesis_models import build_regex
from rerun_refined_regressions_v2 import load_entities_split_corrected, STAGED_PATH, EMPATH_PATH, THREAD_PATH, BRIGADE_PATH
from combined_maverick_detector import load_maverick_disambiguation_lookup, VALID_MAVERICK_CANDIDATES, CANDIDATE_TO_BARES
from stance_window_utils import extract_entity_window, filter_quoted_spans
from build_entity_mentions_cache import entity_groups_for_row

STANCE_MODEL_PATH = 'data/processed/stance_classifier_2stage_pooled.joblib'
ATS_SCORED_PATH = 'data/processed/ats_entity_examples_stance.parquet'
ATS_COMMENTS_PATH = 'data/processed/ats_comments_final.parquet'

RANDOM_SEED = 42
N_PER_BUCKET = 33

ENTITY_CONCEPT_KEYS = {
    'wikileaks': ['wikileaks', 'wikileaks.org', '@wikileaks'],
    'assange': ['assange', 'julian assange', 'assanges', "julian assange's", "julian assange’s", 'jullian assange', 'whereisassange'],
    'snowden': ['snowden', 'edward snowden', 'snowdens', 'ed snowden', "edward snowden's", "edward snowden’s"],
    'greenwald': ['greenwald', 'glenn greenwald']
}


def build_queue_for_entity(entity, df, rx_mav, lookup, text_lookup, meta_lookup, vec, clf_stage1, clf_stage2, classes):
    print(f"\n--- Processing target entity concept: '{entity}' ---")
    target_keys = ENTITY_CONCEPT_KEYS[entity]
    print(f"Matching keys: {target_keys}")

    rows = []
    for cid in df['id']:
        text = text_lookup.get(cid)
        if text is None:
            continue
        
        groups = entity_groups_for_row(text, cid, rx_mav, lookup, CANDIDATE_TO_BARES)
        
        # Collect and combine spans for any of the target concept keys
        spans = []
        for key in target_keys:
            if key in groups:
                spans.extend(groups[key])
                
        if not spans:
            continue
            
        # Deduplicate spans by start/end boundaries and sort them by start position
        seen_spans = set()
        unique_spans = []
        for span in spans:
            boundary = (span['start'], span['end'])
            if boundary not in seen_spans:
                seen_spans.add(boundary)
                unique_spans.append(span)
        spans = sorted(unique_spans, key=lambda s: s['start'])

        window = extract_entity_window(text, spans)
        parent_id, link_id = meta_lookup.get(cid, (None, None))
        rows.append({
            "id": cid, "full_text": text, "entity_spans": spans,
            "parent_id": parent_id, "link_id": link_id, "text_window": window,
        })
        
    print(f"  Found {len(rows):,} mentions (post quote-stripping).")
    if not rows:
        print(f"  Skipping '{entity}' as no mentions were found.")
        return

    entity_df = pd.DataFrame(rows)
    X = vec.transform(entity_df['text_window'])
    
    # Run cascade model
    s1_classes = list(clf_stage1.classes_)
    p_stage1 = clf_stage1.predict_proba(X)
    p_other = p_stage1[:, s1_classes.index('other')]
    p_clear = 1.0 - p_other
    pred_stage1 = clf_stage1.predict(X)

    s2_classes = list(clf_stage2.classes_)
    p_stage2 = clf_stage2.predict_proba(X)
    p_hostile_given_clear = p_stage2[:, s2_classes.index('hostile')]
    p_endorsement_given_clear = p_stage2[:, s2_classes.index('endorsement')]

    entity_df['p_hostile'] = p_clear * p_hostile_given_clear
    entity_df['p_endorsement'] = p_clear * p_endorsement_given_clear
    entity_df['p_other'] = p_other

    entity_df['predicted_label'] = np.where(
        pred_stage1 == 'other', 'other',
        np.where(p_hostile_given_clear >= p_endorsement_given_clear, 'hostile', 'endorsement'),
    )

    print("\nPredicted label distribution (all mentions):")
    print(entity_df['predicted_label'].value_counts())

    rng = np.random.RandomState(RANDOM_SEED)
    sampled_parts = []
    for bucket in classes:
        pool = entity_df[entity_df['predicted_label'] == bucket]
        n = min(N_PER_BUCKET, len(pool))
        if n < N_PER_BUCKET:
            print(f"  WARNING: only {len(pool)} available in '{bucket}' bucket, sampling all of them.")
        if len(pool) > 0:
            sampled_parts.append(pool.sample(n=n, random_state=rng))
            
    if not sampled_parts:
        print("  WARNING: No comments sampled.")
        return
        
    sample = pd.concat(sampled_parts, ignore_index=True).sample(frac=1, random_state=rng).reset_index(drop=True)

    # Format queue for hand labeling
    queue = sample[['id', 'full_text', 'parent_id', 'link_id', 'entity_spans']].copy()
    queue['human_stance'] = ''
    queue['notes'] = ''
    queue['entity_spans'] = queue['entity_spans'].apply(json.dumps)
    queue = queue[['id', 'full_text', 'human_stance', 'notes', 'entity_spans', 'parent_id', 'link_id']]
    
    queue_out_path = f'data/hitl/queue_{entity}_stance_quality_check.csv'
    pred_out_path = f'data/processed/{entity}_stance_quality_check_predictions.csv'
    
    os.makedirs('data/hitl', exist_ok=True)
    os.makedirs('data/processed', exist_ok=True)
    
    queue.to_csv(queue_out_path, index=False)
    print(f"Saved {len(queue)}-row labeling queue to {queue_out_path}")
    
    # Format and save predictions separately to preserve blind rating discipline
    pred_cols = ['id', 'predicted_label'] + [f'p_{c}' for c in classes]
    preds = sample[pred_cols]
    preds.to_csv(pred_out_path, index=False)
    print(f"Saved model predictions (separate for blind labeling) to {pred_out_path}")


def build_ats_queue(con, classes):
    print("\n--- Building Stance Quality-Check Queue for AboveTopSecret (ATS) ---")
    
    if not os.path.exists(ATS_SCORED_PATH):
        print(f"Error: Classified ATS parquet not found at {ATS_SCORED_PATH}. Run classify_ats_stance.py first.")
        sys.exit(1)
        
    # Join ATS entity mentions with raw timestamps using DuckDB
    print("Loading ATS entity mentions and joining with raw timestamps...")
    df_with_time = con.execute(f"""
        SELECT 
            e.comment_id AS id,
            e.entity_key,
            e.text AS full_text,
            e.text_window,
            e.predicted_label,
            e.p_hostile,
            e.p_endorsement,
            e.p_other,
            e.is_list_dump,
            c.raw_timestamp
        FROM read_parquet('{ATS_SCORED_PATH}') e
        JOIN read_parquet('{ATS_COMMENTS_PATH}') c ON e.comment_id = c.post_id
    """).df()
    
    print(f"Loaded {len(df_with_time):,} scored ATS mentions with threading timestamps.")
    
    # Parse years and map to era (Early Era: <= 2011, Late Era: >= 2012)
    years = []
    for t in df_with_time['raw_timestamp']:
        m = re.search(r'\b(19\d{2}|20\d{2})\b', str(t))
        years.append(int(m.group(1)) if m else 2012)  # default fallback to median
    df_with_time['year'] = years
    df_with_time['era'] = np.where(df_with_time['year'] <= 2011, 'early', 'late')
    
    # Filter for target audit concepts with sufficient volume on ATS
    audit_keys = ['alex jones', 'edward snowden', 'julian assange', 'wikileaks']
    df_with_time['entity_key_lower'] = df_with_time['entity_key'].astype(str).str.lower()
    
    # Create mask for any target key containment
    mask = df_with_time['entity_key_lower'].apply(lambda val: any(ak in val for ak in audit_keys))
    pool_df = df_with_time[mask].copy()
    print(f"Audit pool contains {len(pool_df):,} target mentions of Alex Jones, Julian Assange, Snowden, and WikiLeaks.")
    
    # Draw stratified random sample: 33 hostile, 33 endorsement, 33 other (total 99 comments).
    # Within each of the 3 classes, we want to balance Early Era vs Late Era (approx 16-17 each).
    sampled_parts = []
    rng = np.random.RandomState(RANDOM_SEED)
    
    for bucket in classes:
        bucket_pool = pool_df[pool_df['predicted_label'] == bucket]
        
        # Balance early vs late
        early_pool = bucket_pool[bucket_pool['era'] == 'early']
        late_pool = bucket_pool[bucket_pool['era'] == 'late']
        
        n_early = min(17, len(early_pool))
        n_late = min(33 - n_early, len(late_pool))
        
        # If one era is deficient, take more from the other era
        if n_late < 33 - n_early and len(early_pool) > n_early:
            n_early = min(33 - n_late, len(early_pool))
            
        print(f"  Bucket '{bucket}': sampling {n_early} early era (pre-2012) and {n_late} late era (post-2011) comments.")
        
        if n_early > 0:
            sampled_parts.append(early_pool.sample(n=n_early, random_state=rng))
        if n_late > 0:
            sampled_parts.append(late_pool.sample(n=n_late, random_state=rng))
            
    if not sampled_parts:
        print("Error: No comments sampled for ATS queue.")
        return
        
    sample = pd.concat(sampled_parts, ignore_index=True).sample(frac=1, random_state=rng).reset_index(drop=True)
    
    # Format queue for hand labeling
    queue = sample[['id', 'full_text', 'text_window', 'entity_key', 'year']].copy()
    queue['human_stance'] = ''
    queue['notes'] = ''
    
    queue_out_path = 'data/hitl/queue_ats_stance_quality_check.csv'
    pred_out_path = 'data/processed/ats_stance_quality_check_predictions.csv'
    
    os.makedirs('data/hitl', exist_ok=True)
    os.makedirs('data/processed', exist_ok=True)
    
    queue.to_csv(queue_out_path, index=False)
    print(f"Saved {len(queue)}-row blind ATS labeling queue to {queue_out_path}")
    
    # Format and save predictions separately for blind labeling
    pred_cols = ['id', 'entity_key', 'predicted_label', 'p_hostile', 'p_endorsement', 'p_other', 'is_list_dump']
    preds = sample[pred_cols]
    preds.to_csv(pred_out_path, index=False)
    print(f"Saved ATS predictions (separate for blind rating) to {pred_out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', default='reddit', choices=['reddit', 'ats'],
                        help="Platform target: 'reddit' or 'ats'.")
    parser.add_argument('--entity', default='all', choices=['all', 'wikileaks', 'assange', 'snowden', 'greenwald'],
                        help="Build quality check queue for a specific entity or all of them (Reddit-only).")
    args = parser.parse_args()

    print(f"=== Building Generalized Stance Quality-Check Queue [Platform: {args.platform.upper()}] ===")

    print("Loading Two-Stage Cascade Stance Classifier...")
    if not os.path.exists(STANCE_MODEL_PATH):
        print(f"Error: Model not found at {STANCE_MODEL_PATH}")
        sys.exit(1)
        
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec = stance_model['vec']
    clf_stage1 = stance_model['clf_stage1']
    clf_stage2 = stance_model['clf_stage2']
    classes = ['hostile', 'endorsement', 'other']
    print(f"  classes={classes}, cv_kappa={stance_model.get('cv_kappa_end_to_end', 0.0):.3f}")

    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='4GB'")

    if args.platform == 'ats':
        build_ats_queue(con, classes)
    else:
        # Standard Reddit builder
        print("Loading verified entity lists...")
        mavericks, canon, consensus = load_entities_split_corrected()
        rx_mav = build_regex(mavericks)
        lookup = load_maverick_disambiguation_lookup()

        import shutil
        temp_dir = f"data/processed/.duckdb_temp_{os.getpid()}"
        os.makedirs(temp_dir, exist_ok=True)
        con.execute(f"PRAGMA temp_directory='{temp_dir}'")

        print("Loading r/conspiracy unfiltered population (has_maverick flag only)...")
        query = f"""
            SELECT
                s.id,
                e.parent_id,
                e.link_id,
                CAST(regexp_matches(e.text, $1) AS INTEGER) as has_maverick_regex
            FROM '{STAGED_PATH}' s
            JOIN '{EMPATH_PATH}' e ON s.id = e.id
            JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
            LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
            WHERE t.is_high_crosspost = 0
              AND COALESCE(b.brigade_upvote_flag, 0) = 0
              AND COALESCE(b.brigade_downvote_flag, 0) = 0
            QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
        """
        df = con.execute(query, ["(?i)" + rx_mav.pattern]).df()
        resolved_mav = df["id"].astype(str).map(lookup)
        df["has_maverick"] = (df["has_maverick_regex"].astype(bool) | resolved_mav.isin(VALID_MAVERICK_CANDIDATES)).astype(int)
        df = df[df["has_maverick"] == 1].drop(columns=["has_maverick_regex"])
        print(f"  {len(df):,} maverick-mention rows to scan.")

        # Load text for the maverick-mention rows
        con.register("mention_ids_view", df[['id']])
        text_df = con.execute(f"""
            SELECT e.id, e.text FROM '{EMPATH_PATH}' e JOIN mention_ids_view n ON e.id = n.id
        """).df()
        text_lookup = dict(zip(text_df['id'], text_df['text']))
        meta_lookup = dict(zip(df['id'], zip(df['parent_id'], df['link_id'])))

        # Determine which entities to run
        if args.entity == 'all':
            entities = list(ENTITY_CONCEPT_KEYS.keys())
        else:
            entities = [args.entity]

        for entity in entities:
            build_queue_for_entity(entity, df, rx_mav, lookup, text_lookup, meta_lookup, vec, clf_stage1, clf_stage2, classes)

        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
