"""build_short_comment_stance_quality_queues.py

Quality-check queues for other key entities (WikiLeaks, Julian Assange, Edward Snowden, Glenn Greenwald)
on the short-comment population. Draws a stratified random sample of 99 mentions per entity.
"""

import os
import sys
import json as jsonlib
import numpy as np
import pandas as pd
import duckdb
import joblib

sys.path.insert(0, os.path.dirname(__file__))
from refine_thesis_models import build_regex
from rerun_refined_regressions_v2 import load_entities_split_corrected, THREAD_PATH, BRIGADE_PATH
from combined_maverick_detector import load_maverick_disambiguation_lookup, CANDIDATE_TO_BARES
from stance_window_utils import extract_entity_window
from build_entity_mentions_cache import entity_groups_for_row

# Paths
SHORT_COMMENTS_PATH = 'data/processed/conspiracy_comments_short_lte100chars.parquet'
STANCE_MODEL_PATH = 'data/processed/stance_classifier_3class.joblib'
N_PER_BUCKET = 33
RANDOM_SEED = 42

ENTITY_CONCEPT_KEYS = {
    'wikileaks': ['wikileaks', 'wikileaks.org', '@wikileaks'],
    'assange': ['assange', 'julian assange', 'assanges', "julian assange's", "julian assange’s", 'jullian assange', 'whereisassange'],
    'snowden': ['snowden', 'edward snowden', 'snowdens', 'ed snowden', "edward snowden's", "edward snowden’s"],
    'greenwald': ['greenwald', 'glenn greenwald']
}


def build_queue_for_entity(entity, df, rx_mav, lookup, text_lookup, meta_lookup, vec, clf, classes):
    print(f"\n--- Processing target entity concept: '{entity}' (short comments) ---")
    target_keys = ENTITY_CONCEPT_KEYS[entity]
    print(f"Matching keys: {target_keys}")

    rows = []
    for cid in df['id'].astype(str):
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
    probs = clf.predict_proba(X)
    
    # Store probability for each class
    for i, c in enumerate(classes):
        entity_df[f'p_{c}'] = probs[:, i]
        
    pred_idx = probs.argmax(axis=1)
    entity_df['predicted_label'] = [classes[i] for i in pred_idx]

    print("Predicted label distribution (all mentions):")
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
    queue['entity_spans'] = queue['entity_spans'].apply(jsonlib.dumps)
    queue = queue[['id', 'full_text', 'human_stance', 'notes', 'entity_spans', 'parent_id', 'link_id']]
    
    queue_out_path = f'data/hitl/queue_short_{entity}_stance_quality_check.csv'
    pred_out_path = f'data/processed/short_{entity}_stance_quality_check_predictions.csv'
    
    os.makedirs('data/hitl', exist_ok=True)
    os.makedirs('data/processed', exist_ok=True)
    
    queue.to_csv(queue_out_path, index=False)
    print(f"Saved {len(queue)}-row labeling queue to {queue_out_path}")
    
    # Format and save predictions separately to preserve blind rating discipline
    pred_cols = ['id', 'predicted_label'] + [f'p_{c}' for c in classes]
    preds = sample[pred_cols]
    preds.to_csv(pred_out_path, index=False)
    print(f"Saved model predictions (separate for blind labeling) to {pred_out_path}")


def main():
    print("=== Building Short-Comment Multi-Entity Stance Quality Queues ===")

    if not os.path.exists(SHORT_COMMENTS_PATH):
        print(f"Error: Short comments parquet not found at {SHORT_COMMENTS_PATH}")
        sys.exit(1)

    print("Loading 3-class stance classifier...")
    if not os.path.exists(STANCE_MODEL_PATH):
        print(f"Error: Model not found at {STANCE_MODEL_PATH}")
        sys.exit(1)
        
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec, clf = stance_model['vec'], stance_model['clf']
    classes = stance_model['classes_']
    print(f"  classes={classes}, cv_kappa={stance_model['cv_kappa']:.3f}, n_train={stance_model['n_train']}")

    print("Loading verified entity lists...")
    mavericks, _, _ = load_entities_split_corrected()
    rx_mav = build_regex(mavericks)
    lookup = load_maverick_disambiguation_lookup()

    con = duckdb.connect()
    
    # Build keyword filter to speed up queries
    keyword_terms = []
    for concept, keys in ENTITY_CONCEPT_KEYS.items():
        for key in keys:
            if not key.startswith('@'):
                keyword_terms.append(key)
    
    def escape_term(t):
        return t.replace("'", "''")
    filter_clause = " OR ".join([f"s.text ILIKE '%{escape_term(term)}%'" for term in keyword_terms])

    print("Loading and filtering short comments via DuckDB...")
    query = f"""
        SELECT
            s.id,
            s.parent_id,
            s.link_id,
            s.text
        FROM '{SHORT_COMMENTS_PATH}' s
        JOIN '{THREAD_PATH}' t ON SUBSTR(s.link_id, 4) = t.post_id
        LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
        WHERE ({filter_clause})
          AND t.is_high_crosspost = 0
          AND COALESCE(b.brigade_upvote_flag, 0) = 0
          AND COALESCE(b.brigade_downvote_flag, 0) = 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
    """
    df = con.execute(query).df()
    print(f"  Found {len(df):,} filtered short comments with relevant keywords.")

    if df.empty:
        print("No matching comments found in short comments. Exiting.")
        return

    text_lookup = dict(zip(df['id'], df['text']))
    meta_lookup = dict(zip(df['id'], zip(df['parent_id'], df['link_id'])))

    for entity in ENTITY_CONCEPT_KEYS.keys():
        build_queue_for_entity(entity, df, rx_mav, lookup, text_lookup, meta_lookup, vec, clf, classes)


if __name__ == "__main__":
    main()
