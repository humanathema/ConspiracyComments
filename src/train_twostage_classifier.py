"""train_twostage_classifier.py

Tests a two-stage cascade as an alternative to the flat 3-class stance
classifier (train_stance_classifier.py / train_jones_classifier.py):
  Stage 1: binary "clear stance" (hostile or endorsement) vs. "other"
  Stage 2: binary hostile vs. endorsement, trained/applied only on rows
           Stage 1 called "clear"

Nash's question (2026-07-22): does splitting "is there a stance at all"
from "which stance" outperform predicting all 3 classes directly? The
flat model has to place `other` on the same decision surface as the
hostile/endorsement distinction; a cascade lets Stage 2 learn a cleaner
boundary since it never sees `other` examples at all. The risk is
compounding error (a Stage 1 miss is unrecoverable) plus less data per
stage.

Evaluated with a single 5-fold CV over the whole pipeline (not two
separately-honest CVs) so the reported kappa reflects the ACTUAL
end-to-end 3-class outcome a downstream user would get -- directly
comparable to the flat models' CV kappa (pooled: 0.331, Jones-only:
0.288, both from the same eval convention: vec fit once on the full
data upfront, honesty check is on the classifier's fold-holdout, per the
existing project convention in train_stance_classifier.py).

--scope pooled: same QUEUES list as train_stance_classifier.py (2026-07-22
    revision, includes jones_short).
--scope jones: same two Jones queues as train_jones_classifier.py (long +
    short, freeform labels normalized the same way).

Output: data/processed/stance_classifier_2stage_{scope}.joblib
"""
import os
import sys
import argparse
import json
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import classification_report, cohen_kappa_score, confusion_matrix
import joblib

sys.path.insert(0, os.path.dirname(__file__))
from stance_window_utils import extract_entity_window, filter_quoted_spans
from score_entity_stance_quality_checks import normalize_label
from train_stance_classifier import QUEUES as POOLED_QUEUES

JONES_QUEUES = [
    'data/hitl/queue_jones_stance_quality_check.csv',
    'data/hitl/queue_jones_short_stance_quality_check.csv',
]


def load_data(queue_paths):
    frames = []
    for q in queue_paths:
        df = pd.read_csv(q)
        df['source_queue'] = os.path.basename(q).replace('queue_', '').replace('.csv', '')
        if 'entity_spans' not in df.columns:
            df['entity_spans'] = '[]'
        frames.append(df[['id', 'full_text', 'entity_spans', 'human_stance', 'source_queue']])
    all_df = pd.concat(frames, ignore_index=True)

    normalized = all_df['human_stance'].apply(normalize_label)
    all_df['y'] = normalized.apply(lambda t: t[0])

    def _parse_spans(raw):
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (ValueError, TypeError):
                return []
        return raw or []

    parsed_spans = all_df['entity_spans'].apply(_parse_spans)
    filtered_spans = [filter_quoted_spans(t, s) for t, s in zip(all_df['full_text'], parsed_spans)]
    quote_only = [len(orig) > 0 and len(kept) == 0 for orig, kept in zip(parsed_spans, filtered_spans)]
    n_dropped = sum(quote_only)
    if n_dropped:
        print(f"  Dropping {n_dropped} row(s) whose only entity mention(s) were inside a quoted line")
    all_df['filtered_spans'] = filtered_spans
    all_df = all_df.loc[[not q for q in quote_only]].copy()
    all_df['text_window'] = all_df.apply(
        lambda r: extract_entity_window(r['full_text'], r['filtered_spans']), axis=1)
    return all_df


def run_cv(df):
    X_text = df['text_window'].fillna('')
    y = df['y'].values
    is_clear = np.where(y == 'other', 'other', 'clear')

    vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 1), sublinear_tf=True, stop_words='english')
    X = vec.fit_transform(X_text)

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    y_final_pred = np.empty(len(df), dtype=object)
    stage1_pred_all = np.empty(len(df), dtype=object)

    for train_idx, test_idx in cv.split(X, y):
        clf1 = LogisticRegression(class_weight='balanced', C=1.0, random_state=42, max_iter=1000)
        clf1.fit(X[train_idx], is_clear[train_idx])
        pred1 = clf1.predict(X[test_idx])
        stage1_pred_all[test_idx] = pred1

        y_final_pred[test_idx] = 'other'
        train_clear_mask = is_clear[train_idx] == 'clear'
        clf2 = LogisticRegression(class_weight='balanced', C=1.0, random_state=42, max_iter=1000)
        clf2.fit(X[train_idx][train_clear_mask], y[train_idx][train_clear_mask])

        test_clear_mask = pred1 == 'clear'
        if test_clear_mask.sum() > 0:
            test_idx_arr = np.array(test_idx)
            clear_positions = test_idx_arr[test_clear_mask]
            pred2 = clf2.predict(X[clear_positions])
            y_final_pred[clear_positions] = pred2

    print("\n=== Stage 1 alone: clear-stance vs. other (held-out) ===")
    print(classification_report(is_clear, stage1_pred_all, labels=['clear', 'other'], zero_division=0))
    stage1_kappa = cohen_kappa_score(is_clear, stage1_pred_all)
    print(f"Stage 1 Kappa: {stage1_kappa:.3f}")

    print("\n=== Stage 2 alone: hostile vs endorsement, evaluated ONLY on rows truly clear "
          "(upper bound if Stage 1 were perfect) ===")
    true_clear_mask = is_clear == 'clear'
    print(classification_report(y[true_clear_mask], y_final_pred[true_clear_mask],
                                 labels=['hostile', 'endorsement', 'other'], zero_division=0))

    print("\n=== End-to-end cascade: full 3-class outcome (comparable to flat-model kappa) ===")
    classes_sorted = ['endorsement', 'hostile', 'other']
    print(classification_report(y, y_final_pred, labels=classes_sorted, target_names=classes_sorted, zero_division=0))
    kappa = cohen_kappa_score(y, y_final_pred)
    acc = (y == y_final_pred).mean()
    print(f"End-to-end Accuracy: {acc:.3f}")
    print(f"End-to-end Cohen's Kappa: {kappa:.3f}")
    print("\nConfusion matrix (rows=true, cols=predicted):")
    cm = confusion_matrix(y, y_final_pred, labels=classes_sorted)
    print(pd.DataFrame(cm, index=[f"true_{c}" for c in classes_sorted], columns=[f"pred_{c}" for c in classes_sorted]))

    return vec, X, y, is_clear, kappa, stage1_kappa


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scope', choices=['pooled', 'jones'], default='pooled')
    args = parser.parse_args()

    queues = POOLED_QUEUES if args.scope == 'pooled' else JONES_QUEUES
    print(f"=== Two-stage cascade classifier (scope={args.scope}) ===")
    df = load_data(queues)
    print(f"Training rows: {len(df)}")
    print(df.groupby(['source_queue', 'y']).size())

    vec, X, y, is_clear, kappa, stage1_kappa = run_cv(df)

    print("\nFitting final stage 1 + stage 2 models on all usable rows...")
    clf1_final = LogisticRegression(class_weight='balanced', C=1.0, random_state=42, max_iter=1000)
    clf1_final.fit(X, is_clear)
    clear_mask = is_clear == 'clear'
    clf2_final = LogisticRegression(class_weight='balanced', C=1.0, random_state=42, max_iter=1000)
    clf2_final.fit(X[clear_mask], y[clear_mask])

    out_path = f'data/processed/stance_classifier_2stage_{args.scope}.joblib'
    os.makedirs('data/processed', exist_ok=True)
    joblib.dump({
        'vec': vec, 'clf_stage1': clf1_final, 'clf_stage2': clf2_final,
        'cv_kappa_end_to_end': kappa, 'cv_kappa_stage1': stage1_kappa,
        'n_train': len(df), 'scope': args.scope,
    }, out_path)
    print(f"Saved two-stage cascade classifier to {out_path}")


if __name__ == "__main__":
    main()
