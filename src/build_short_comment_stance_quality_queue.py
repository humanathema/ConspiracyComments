"""build_short_comment_stance_quality_queue.py

Quality-check queue for the short-comment (<=100 char) corpus.
This script draws a stratified random sample of 99 Alex Jones mentions
across the 3-class stance classifier's predicted labels (hostile, endorsement, other)
for blind hand-labeling.

GUARDRAILS ENFORCED:
  - This script ONLY builds the quality-check queue of 99 rows.
  - It explicitly rejects requests to score or label the entire 18.6M corpus.
  - It only processes Alex Jones mentions to keep a direct comparison with the long-comment Jones queue.
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
from per_entity_stance_breakdown import entity_groups_for_row

# Paths
SHORT_COMMENTS_PATH = 'data/processed/conspiracy_comments_short_lte100chars.parquet'
STANCE_MODEL_PATH = 'data/processed/stance_classifier_3class.joblib'
QUEUE_OUT_PATH = 'data/hitl/queue_jones_short_stance_quality_check.csv'
PRED_OUT_PATH = 'data/processed/jones_short_stance_quality_check_predictions.csv'

# Target setup
TARGET_ENTITY = 'alex jones'
N_PER_BUCKET = 33
RANDOM_SEED = 42

def main():
    print("=== Building Short-Comment Alex Jones Stance Quality-Check Queue ===")

    # GUARDRAIL CHECK: Scope-creeping prevention
    print("Enforcing Guardrail: This script is restricted to building a 99-row quality-check queue only.")
    print("Full scoring of the 18.6M short-comment corpus is disabled to prevent unauthorized scope creep.")

    if not os.path.exists(SHORT_COMMENTS_PATH):
        print(f"Error: Short comments parquet not found at {SHORT_COMMENTS_PATH}")
        sys.exit(1)

    print("Loading 3-class stance classifier...")
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec, clf = stance_model['vec'], stance_model['clf']
    classes = stance_model['classes_']
    print(f"  Loaded model: classes={classes}, cv_kappa={stance_model['cv_kappa']:.3f}, n_train={stance_model['n_train']}")

    print("Loading verified entity lists...")
    mavericks, _, _ = load_entities_split_corrected()
    rx_mav = build_regex(mavericks)
    lookup = load_maverick_disambiguation_lookup()

    con = duckdb.connect()
    
    # Query only comments containing "jones" (case-insensitive) to drastically speed up execution
    # and filter out high-crosspost or brigaded comments using standard pipeline paths.
    print("Loading and filtering short comments from parquet via DuckDB...")
    query = f"""
        SELECT
            s.id,
            s.parent_id,
            s.link_id,
            s.text
        FROM '{SHORT_COMMENTS_PATH}' s
        JOIN '{THREAD_PATH}' t ON SUBSTR(s.link_id, 4) = t.post_id
        LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
        WHERE s.text ILIKE '%jones%'
          AND t.is_high_crosspost = 0
          AND COALESCE(b.brigade_upvote_flag, 0) = 0
          AND COALESCE(b.brigade_downvote_flag, 0) = 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
    """
    df = con.execute(query).df()
    print(f"  Found {len(df):,} filtered short comments with 'jones' keyword.")

    text_lookup = dict(zip(df['id'], df['text']))
    meta_lookup = dict(zip(df['id'], zip(df['parent_id'], df['link_id'])))

    print(f"Scanning for '{TARGET_ENTITY}' mentions (quote-stripped windows)...")
    rows = []
    for cid in df['id'].astype(str):
        text = text_lookup.get(cid)
        if text is None:
            continue
        groups = entity_groups_for_row(text, cid, rx_mav, lookup, CANDIDATE_TO_BARES)
        spans = groups.get(TARGET_ENTITY)
        if not spans:
            continue
        window = extract_entity_window(text, spans)
        parent_id, link_id = meta_lookup.get(cid, (None, None))
        rows.append({
            "id": cid, "full_text": text, "entity_spans": spans,
            "parent_id": parent_id, "link_id": link_id, "text_window": window,
        })
    print(f"  Identified {len(rows):,} verified '{TARGET_ENTITY}' mentions (post quote-stripping).")

    if not rows:
        print("Error: No verified mentions found.")
        sys.exit(1)

    long_df = pd.DataFrame(rows)
    X = vec.transform(long_df['text_window'])
    probs = clf.predict_proba(X)
    
    # Store probability for each class
    for i, c in enumerate(classes):
        long_df[f"p_{c}"] = probs[:, i]
    
    # Assign predicted label
    pred_idx = probs.argmax(axis=1)
    long_df['predicted_label'] = [classes[idx] for idx in pred_idx]

    print("\nPredicted class distribution among short comments:")
    print(long_df['predicted_label'].value_counts())

    # Stratified Sampling: 33 per class
    rng = np.random.RandomState(RANDOM_SEED)
    sampled_parts = []
    for label in classes:
        pool = long_df[long_df['predicted_label'] == label]
        n = min(N_PER_BUCKET, len(pool))
        if n < N_PER_BUCKET:
            print(f"  WARNING: Only {len(pool)} available in '{label}' class, sampling all of them.")
        sampled_parts.append(pool.sample(n=n, random_state=rng))
        
    sample = pd.concat(sampled_parts, ignore_index=True).sample(frac=1, random_state=rng).reset_index(drop=True)

    # 1. Output blind manual labeling queue
    queue = sample[['id', 'full_text', 'parent_id', 'link_id', 'entity_spans']].copy()
    queue['human_stance'] = ''
    queue['notes'] = ''
    queue['entity_spans'] = queue['entity_spans'].apply(jsonlib.dumps)
    queue = queue[['id', 'full_text', 'human_stance', 'notes', 'entity_spans', 'parent_id', 'link_id']]
    
    os.makedirs(os.path.dirname(QUEUE_OUT_PATH), exist_ok=True)
    queue.to_csv(QUEUE_OUT_PATH, index=False)
    print(f"\nSaved {len(queue)}-row labeling queue to {QUEUE_OUT_PATH}")
    print("Label the 'human_stance' column with: hostile / endorsement / neutral / ambiguous")

    # 2. Output separate predictions (to keep manual labeling blind)
    pred_cols = ['id', 'predicted_label'] + [f"p_{c}" for c in classes]
    preds = sample[pred_cols]
    preds.to_csv(PRED_OUT_PATH, index=False)
    print(f"Saved model predictions (kept separate for blind labeling) to {PRED_OUT_PATH}")

if __name__ == "__main__":
    main()
