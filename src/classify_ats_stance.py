"""src/classify_ats_stance.py

Applies the two-stage cascade stance classifier (stance_classifier_2stage_pooled.joblib)
to AboveTopSecret (ATS) entity mentions in data/processed/ats_entity_examples.parquet.

It extracts text windows (+-15 words around target entities), filters out quotes
and link-dumps, and runs the cascade model:
  Stage 1 (clear vs other): splits other from hostile/endorsement
  Stage 2 (hostile vs endorsement): learns clean boundaries of stance
"""
import os
import sys
import re
import pandas as pd
import numpy as np
import joblib

sys.path.insert(0, os.path.dirname(__file__))
from stance_window_utils import extract_entity_window, filter_quoted_spans, is_list_or_link_dump_window

STANCE_MODEL_PATH = 'data/processed/stance_classifier_2stage_pooled.joblib'
INPUT_PARQUET = 'data/processed/ats_entity_examples.parquet'
OUTPUT_PARQUET = 'data/processed/ats_entity_examples_stance.parquet'


def find_spans_for_key(text, entity_key):
    """Robust 100% matched span-finding logic for resolved keys."""
    text_str = str(text)
    ek_str = str(entity_key)
    
    # 1. Try full word boundary
    rx_full = re.compile(r'\b' + re.escape(ek_str) + r'\b', re.IGNORECASE)
    spans = [{'start': m.start(), 'end': m.end(), 'text': m.group(0)} for m in rx_full.finditer(text_str)]
    if spans:
        return spans
        
    # 2. Try individual words (longest first, skipping short words)
    words = [w.strip() for w in re.split(r'\W+', ek_str) if w.strip()]
    if words:
        words_sorted = sorted(words, key=len, reverse=True)
        for word in words_sorted:
            if len(word) < 3 and len(words_sorted) > 1:
                continue
            rx_word = re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE)
            spans = [{'start': m.start(), 'end': m.end(), 'text': m.group(0)} for m in rx_word.finditer(text_str)]
            if spans:
                return spans
                
    # 3. Fall back to case-insensitive substring
    rx_sub = re.compile(re.escape(ek_str), re.IGNORECASE)
    spans = [{'start': m.start(), 'end': m.end(), 'text': m.group(0)} for m in rx_sub.finditer(text_str)]
    return spans


def score_windows_cascade(windows, vec, clf_stage1, clf_stage2):
    print(f"  Vectorizing {len(windows):,} windows...")
    X = vec.transform(windows)

    print("  Running Stage 1 (clear vs. other)...")
    s1_classes = list(clf_stage1.classes_)
    p_stage1 = clf_stage1.predict_proba(X)
    p_other = p_stage1[:, s1_classes.index('other')]
    p_clear = 1.0 - p_other
    pred_stage1 = clf_stage1.predict(X)

    print("  Running Stage 2 (hostile vs. endorsement)...")
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


def main():
    print("=== Applying ATS Two-Stage Stance Classifier ===")
    
    if not os.path.exists(STANCE_MODEL_PATH):
        print(f"Error: Model not found at {STANCE_MODEL_PATH}. Train it first.")
        sys.exit(1)
        
    if not os.path.exists(INPUT_PARQUET):
        print(f"Error: Input parquet not found at {INPUT_PARQUET}.")
        sys.exit(1)
        
    print(f"Loading cascade model from {STANCE_MODEL_PATH}...")
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec = stance_model['vec']
    clf_stage1 = stance_model['clf_stage1']
    clf_stage2 = stance_model['clf_stage2']
    print("Model loaded successfully.")
    
    print(f"Loading input entity mentions from {INPUT_PARQUET}...")
    df = pd.read_parquet(INPUT_PARQUET)
    print(f"Loaded {len(df):,} mentions.")
    
    print("Extracting mention windows and filtering quotes...")
    windows = []
    is_list_dumps = []
    
    for row in df.itertuples():
        text = str(row.text)
        ek = str(row.entity_key)
        
        # 1. Find spans
        spans = find_spans_for_key(text, ek)
        
        # 2. Filter quotes
        spans = filter_quoted_spans(text, spans)
        
        # 3. Extract window
        win_text = extract_entity_window(text, spans)
        windows.append(win_text)
        
        # 4. Flag list dumps
        is_list_dumps.append(is_list_or_link_dump_window(win_text))
        
    df['text_window'] = windows
    df['is_list_dump'] = is_list_dumps
    
    print("\nScoring all extracted windows...")
    predicted_labels, p_by_class = score_windows_cascade(windows, vec, clf_stage1, clf_stage2)
    
    # Update columns in dataframe
    df['predicted_label'] = predicted_labels
    df['p_hostile'] = p_by_class['hostile']
    df['p_endorsement'] = p_by_class['endorsement']
    df['p_other'] = p_by_class['other']
    
    print("\nPrediction distribution:")
    print(df['predicted_label'].value_counts())
    print(f"List-dump flagged windows: {sum(df['is_list_dump']):,} ({df['is_list_dump'].mean():.1%})")
    
    print(f"\nSaving stance-classified results to {OUTPUT_PARQUET}...")
    df.to_parquet(OUTPUT_PARQUET, index=False)
    print("Stance classification complete!")


if __name__ == '__main__':
    main()
