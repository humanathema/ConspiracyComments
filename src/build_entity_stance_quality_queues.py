"""build_entity_stance_quality_queues.py

Generalizes build_jones_stance_quality_queue.py to build quality-check queues
for other key mavericks/whistleblowers under the 3-class stance classifier:
- WikiLeaks
- Julian Assange
- Edward Snowden
- Glenn Greenwald

For each target entity concept, this script groups all key surface forms and 
lookup-resolved entity keys (e.g., combining 'assange' and 'julian assange' 
to ensure comprehensive coverage). It draws a stratified random sample of 
mentions across the 3-class classifier's predicted labels: hostile, endorsement, and other.

To preserve blind labeling, predictions are saved separately.

Output files per entity:
  data/hitl/queue_{entity}_stance_quality_check.csv
  data/processed/{entity}_stance_quality_check_predictions.csv
"""
import os
import sys
import json
import argparse
import numpy as np
import pandas as pd
import duckdb
import joblib

sys.path.insert(0, os.path.dirname(__file__))
from refine_thesis_models import build_regex
from rerun_refined_regressions_v2 import load_entities_split_corrected, STAGED_PATH, EMPATH_PATH, THREAD_PATH, BRIGADE_PATH
from combined_maverick_detector import load_maverick_disambiguation_lookup, VALID_MAVERICK_CANDIDATES, CANDIDATE_TO_BARES
from stance_window_utils import extract_entity_window
from per_entity_stance_breakdown import entity_groups_for_row

STANCE_MODEL_PATH = 'data/processed/stance_classifier_3class.joblib'
RANDOM_SEED = 42
N_PER_BUCKET = 33

# Mapping from target entity concept to its matching lowercased entity_keys.
# We combine these surface forms explicitly so that we check all variants of the
# same real-world entity, ensuring maximum coverage and statistical validity.
ENTITY_CONCEPT_KEYS = {
    'wikileaks': ['wikileaks', 'wikileaks.org', '@wikileaks'],
    'assange': ['assange', 'julian assange', 'assanges', "julian assange's", "julian assange’s", 'jullian assange', 'whereisassange'],
    'snowden': ['snowden', 'edward snowden', 'snowdens', 'ed snowden', "edward snowden's", "edward snowden’s"],
    'greenwald': ['greenwald', 'glenn greenwald']
}


def build_queue_for_entity(entity, df, rx_mav, lookup, text_lookup, meta_lookup, vec, clf, classes):
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
    probs = clf.predict_proba(X)  # columns ordered per clf.classes_
    
    # Store probability for each class
    for i, c in enumerate(classes):
        entity_df[f'p_{c}'] = probs[:, i]
        
    pred_idx = probs.argmax(axis=1)
    entity_df['predicted_label'] = [classes[i] for i in pred_idx]

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--entity', default='all', choices=['all', 'wikileaks', 'assange', 'snowden', 'greenwald'],
                        help="Build quality check queue for a specific entity or all of them.")
    args = parser.parse_args()

    print("=== Building generalized entity stance quality-check queues ===")

    print("Loading 3-class stance classifier...")
    if not os.path.exists(STANCE_MODEL_PATH):
        print(f"Error: Model not found at {STANCE_MODEL_PATH}")
        sys.exit(1)
        
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec, clf = stance_model['vec'], stance_model['clf']
    classes = list(clf.classes_)
    print(f"  classes={classes}, cv_kappa={stance_model['cv_kappa']:.3f}, cv_auc={stance_model['cv_auc']:.3f}, n_train={stance_model['n_train']}")

    print("Loading verified entity lists...")
    mavericks, canon, consensus = load_entities_split_corrected()
    rx_mav = build_regex(mavericks)
    lookup = load_maverick_disambiguation_lookup()

    con = duckdb.connect()
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
        build_queue_for_entity(entity, df, rx_mav, lookup, text_lookup, meta_lookup, vec, clf, classes)


if __name__ == "__main__":
    main()
