#!/usr/bin/env python3
"""build_irr_stance_queue.py

Constructs the small shared IRR stance queue (queue_irr_stance_shared.csv)
containing exactly 99 items (33 endorsement, 33 hostile, 33 other/neutral/ambiguous)
stratified across predicted class probabilities.

Excludes any comments that are already in any of the existing rated/active-learning queues.
"""
import os
import sys
import json as jsonlib
import numpy as np
import pandas as pd
import duckdb
import joblib
import re

# Resolve root path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from refine_thesis_models import build_regex
from rerun_refined_regressions_v2 import (
    load_entities_split_corrected, compute_has_maverick, compute_has_consensus_expert,
    STAGED_PATH, EMPATH_PATH, THREAD_PATH, PRESENCE_PATH, BRIGADE_PATH,
)
from combined_maverick_detector import load_maverick_disambiguation_lookup, CANDIDATE_TO_BARES as MAVERICK_CANDIDATE_TO_BARES
from consensus_disambiguation_lookup import load_consensus_disambiguation_lookup, CANDIDATE_TO_BARES as CONSENSUS_CANDIDATE_TO_BARES
from stance_window_utils import extract_entity_window, compute_spans_for_row

STANCE_MODEL_PATH = os.path.join(REPO_ROOT, 'data/processed/stance_classifier_3class.joblib')
OUTPUT_QUEUE_PATH = os.path.join(REPO_ROOT, 'data/hitl/queue_irr_stance_shared.csv')

EXISTING_QUEUES = [
    'data/hitl/queue_consensus_stance.csv',
    'data/hitl/queue_maverick_stance.csv',
    'data/hitl/queue_consensus_stance_politics.csv',
    'data/hitl/queue_maverick_stance_politics.csv',
    'data/hitl/queue_maverick_stance_round2.csv',
    'data/hitl/queue_maverick_stance_round3.csv',
    'data/hitl/queue_maverick_stance_round4.csv',
    'data/hitl/queue_maverick_stance_round5.csv',
    'data/hitl/queue_maverick_stance_round6.csv',
    'data/hitl/queue_maverick_stance_round7.csv',
    'data/hitl/queue_wikileaks_stance_quality_check.csv',
    'data/hitl/queue_assange_stance_quality_check.csv',
    'data/hitl/queue_snowden_stance_quality_check.csv',
    'data/hitl/queue_greenwald_stance_quality_check.csv',
    'data/hitl/queue_jones_short_stance_quality_check.csv',
]


def load_all_existing_ids():
    ids = set()
    for q in EXISTING_QUEUES:
        p = os.path.join(REPO_ROOT, q)
        if os.path.exists(p):
            try:
                df = pd.read_csv(p)
                col = 'comment_id' if 'comment_id' in df.columns else 'id'
                # Extract clean IDs (removing multi-entity suffixes like "__jones")
                for cid in df[col].astype(str):
                    clean_id = cid.split('__')[0]
                    ids.add(clean_id)
            except Exception as e:
                print(f"Warning: could not read {q}: {e}")
    return ids


def load_candidate_pool(existing_ids):
    print("Connecting to DuckDB...")
    con = duckdb.connect()
    
    # Query for comments with moderate lengths (100 to 500 chars) for high readability,
    # and filter for high-quality threads per project guidelines.
    print("Loading candidate population from staging & empath...")
    query = f"""
        SELECT s.id, e.text, e.parent_id, e.link_id
        FROM '{os.path.join(REPO_ROOT, STAGED_PATH)}' s
        JOIN '{os.path.join(REPO_ROOT, EMPATH_PATH)}' e ON s.id = e.id
        JOIN '{os.path.join(REPO_ROOT, THREAD_PATH)}' t ON SUBSTR(e.link_id, 4) = t.post_id
        LEFT JOIN '{os.path.join(REPO_ROOT, PRESENCE_PATH)}' p ON SUBSTR(e.link_id, 4) = p.post_id
        LEFT JOIN '{os.path.join(REPO_ROOT, BRIGADE_PATH)}' b ON s.id = b.comment_id
        WHERE LENGTH(e.text) BETWEEN 100 AND 500
          AND t.elasticity_ratio <= (SELECT quantile(elasticity_ratio, 0.33) FROM '{os.path.join(REPO_ROOT, THREAD_PATH)}')
          AND t.is_high_crosspost = 0
          AND p.insider_presence_ratio >= 0.75
          AND COALESCE(b.brigade_upvote_flag, 0) = 0
          AND COALESCE(b.brigade_downvote_flag, 0) = 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
    """
    df = con.execute(query).df()
    print(f"  Loaded {len(df):,} candidates.")
    
    # Exclude already-rated items
    df['clean_id'] = df['id'].astype(str)
    df = df[~df['clean_id'].isin(existing_ids)].copy()
    print(f"  After excluding previously queued comments: {len(df):,}")
    return df


def main():
    print("=== Building Unified IRR Shared Stance Queue ===")
    
    existing_ids = load_all_existing_ids()
    print(f"Loaded {len(existing_ids)} existing comment IDs to exclude.")
    
    candidates = load_candidate_pool(existing_ids)
    if candidates.empty:
        print("Error: No candidate comments loaded.")
        sys.exit(1)
        
    print("Loading stance model...")
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec, clf = stance_model['vec'], stance_model['clf']
    classes = stance_model['classes_'] # ['endorsement', 'hostile', 'other']
    print(f"  Model classes: {classes}")
    
    print("Splitting entities...")
    mavericks, canon, consensus = load_entities_split_corrected()
    rx_mav = build_regex(mavericks)
    rx_con = build_regex(consensus)
    lookup_mav = load_maverick_disambiguation_lookup()
    lookup_con = load_consensus_disambiguation_lookup()
    
    print("Identifying positive construct matches...")
    candidates['has_maverick'] = compute_has_maverick(candidates, rx_mav, lookup_mav)
    candidates['has_consensus'] = compute_has_consensus_expert(candidates, rx_con, lookup_con)
    
    pop = candidates[(candidates['has_maverick'] == 1) | (candidates['has_consensus'] == 1)].copy()
    print(f"  Positive construct population (maverick OR consensus): {len(pop):,}")
    
    if len(pop) < 500:
        print("Warning: small candidate pool, falling back to full length pool.")
        
    print("Deduplicating by text...")
    pop = pop.drop_duplicates(subset='text', keep='first').copy()
    print(f"  Unique text pool: {len(pop):,}")
    
    print("Computing text windows for classifier predictions...")
    windows = []
    rows_valid = []
    
    for idx_row, row in pop.iterrows():
        cid = str(row['id'])
        text = str(row['text'])
        
        is_mav = row['has_maverick'] == 1
        rx = rx_mav if is_mav else rx_con
        active_lookup = lookup_mav if is_mav else lookup_con
        candidate_to_bares = MAVERICK_CANDIDATE_TO_BARES if is_mav else CONSENSUS_CANDIDATE_TO_BARES
        
        direct_spans = [{"start": m.start(), "end": m.end(), "text": m.group(0)} for m in rx.finditer(text)]
        entity_groups = {}
        for s in direct_spans:
            entity_groups.setdefault(s["text"].lower(), []).append(s)
            
        if not entity_groups:
            resolved = active_lookup.get(cid)
            if resolved:
                bares = candidate_to_bares.get(resolved, [])
                fallback_spans = []
                for bare in bares:
                    bare_rx = re.compile(r'\b' + re.escape(bare) + r'\b', re.IGNORECASE)
                    fallback_spans.extend({"start": m.start(), "end": m.end(), "text": m.group(0)} for m in bare_rx.finditer(text))
                if fallback_spans:
                    entity_groups[resolved] = fallback_spans
                    
        if not entity_groups:
            entity_groups = {None: []}
            
        all_spans = []
        for spans in entity_groups.values():
            all_spans.extend(spans)
            
        try:
            window = extract_entity_window(text, all_spans)
        except Exception:
            window = text
            
        windows.append(window)
        
        rows_valid.append({
            'id': cid,
            'full_text': text,
            'parent_id': row['parent_id'],
            'link_id': row['link_id'],
            'entity_groups': entity_groups,
            'text_window': window
        })
        
    df_valid = pd.DataFrame(rows_valid)
    print(f"  Valid rows with windows: {len(df_valid)}")
    
    print("Scoring candidates with stance classifier...")
    X = vec.transform(df_valid['text_window'])
    probs = clf.predict_proba(X)
    
    for i, c in enumerate(classes):
        df_valid[f'p_{c}'] = probs[:, i]
        
    df_valid['predicted_label'] = [classes[idx] for idx in probs.argmax(axis=1)]
    
    print("Predicted label distribution in pool:")
    print(df_valid['predicted_label'].value_counts())
    
    rng = np.random.RandomState(42)
    sampled_pools = []
    
    for cls in classes:
        cls_pool = df_valid[df_valid['predicted_label'] == cls]
        if len(cls_pool) < 33:
            print(f"Warning: Only {len(cls_pool)} available for class '{cls}'. Sampling all.")
            sampled_pools.append(cls_pool)
        else:
            sampled_pools.append(cls_pool.sample(n=33, random_state=rng))
            
    df_sampled = pd.concat(sampled_pools, ignore_index=True)
    df_shuffled = df_sampled.sample(frac=1, random_state=42).reset_index(drop=True)
    print(f"Final sampled shared set: {len(df_shuffled)} rows.")
    
    queue_rows = []
    for _, row in df_shuffled.iterrows():
        cid = str(row['id'])
        text = str(row['full_text'])
        entity_groups = row['entity_groups']
        
        for entity_key, spans in entity_groups.items():
            suffix = "" if len(entity_groups) == 1 else f"__{re.sub(r'[^a-z0-9]+', '_', str(entity_key).lower())}"
            queue_rows.append({
                'id': cid + suffix,
                'comment_id': cid,
                'target_entity': entity_key if len(entity_groups) > 1 else "",
                'full_text': text,
                'human_stance': '',
                'notes': '',
                'entity_spans': jsonlib.dumps(spans),
                'parent_id': row['parent_id'],
                'link_id': row['link_id'],
            })
            
    df_queue = pd.DataFrame(queue_rows)
    print(f"Constructed {len(df_queue)} queue rows (including {len(df_queue) - len(df_shuffled)} splits).")
    
    if len(df_queue) > 99:
        print(f"Truncating queue from {len(df_queue)} to exactly 99 rows to meet size guidelines.")
        df_queue = df_queue.head(99)
        
    os.makedirs(os.path.dirname(OUTPUT_QUEUE_PATH), exist_ok=True)
    
    cols = ['id', 'full_text', 'human_stance', 'notes', 'entity_spans', 'parent_id', 'link_id', 'target_entity']
    df_queue = df_queue[cols]
    df_queue.to_csv(OUTPUT_QUEUE_PATH, index=False)
    print(f"Successfully saved shared IRR stance queue to {OUTPUT_QUEUE_PATH}")


if __name__ == "__main__":
    main()
