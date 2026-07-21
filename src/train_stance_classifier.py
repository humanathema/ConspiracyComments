"""train_stance_classifier.py

Trains a local, deterministic stance classifier (hostile vs. endorsement)
on the four completed HITL stance queues, following the exact same
architecture as the existing pe_prob/ps_prob staged classifiers in
staged_pipeline.py (TfidfVectorizer + class_weight-balanced
LogisticRegression) -- no LLM calls, consistent with the rest of this
project's local-classifier pattern.

Purpose: the core regression's has_maverick/has_consensus_expert are
currently pooled "any mention" binaries -- they don't distinguish a
hostile mention ("even the CDC admits...") from an endorsing one ("the
CDC's own study confirms..."). Since the hostile/endorsement mix already
differs sharply by subreddit and construct (r/conspiracy consensus-expert
mentions are 68% hostile; r/politics maverick mentions are 55% hostile --
close to the mirror image), pooling could be diluting two different real
effects into one middling coefficient, the same mechanism that diluted
has_maverick before the Brand/Hawking/Ventura/Hancock/Kory entity-list
fix. This classifier lets has_maverick/has_consensus_expert be split into
hostile vs. endorsement sub-variables for a follow-on regression.

Training data: the four queues, filtered to human_stance in
{hostile, endorsement} only (drops neutral/ambiguous/wrong_match --
wrong_match rows are misidentified entities, not a real stance instance
at all; neutral/ambiguous are excluded from THIS binary classifier the
same way pe_prob/ps_prob's source queues only had two classes).
Pooled across all four queues (not four separate models) to get enough
training data (666 usable rows) -- source_queue is not used as a feature,
so the classifier reflects general hostile-vs-endorsement language, not
subreddit-specific vocabulary quirks.

Honesty check included: 5-fold stratified cross-validation is reported
BEFORE the final fit-on-everything model is saved, since this is a new
construct with less precedent than pe_prob/ps_prob and 666 rows is not
a lot of training data -- see the printed report before trusting scored
output downstream.

REDESIGNED 2026-07-20: switched from whole-comment-text TF-IDF to
entity-focused text windows (stance_window_utils.extract_entity_window,
+-15 words around each target-entity span, same convention as
stage_b_consolidated_corpus_pass.py's disambiguation windowing). The
whole-text version broke down on multi-entity comments split into
per-entity rows (build_stance_active_learning_queue.py's round 4): two
rows sharing identical full_text but opposite stance labels (e.g. comment
l8q1uwu -- "David Icke" rated endorsement, "Icke", the same person, rated
hostile) is a direct contradiction for a model that only sees the whole
text. Windowing around each row's actual target entity fixes this at the
root -- every row's input is now specific to what it's a label for, so
split rows no longer need to be excluded from training (they were,
briefly, as a stopgap; that exclusion is removed now that windowing
handles it properly).

Output: data/processed/stance_classifier.joblib
"""
import os
import json
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import classification_report, cohen_kappa_score, roc_auc_score
import joblib

import sys
sys.path.insert(0, os.path.dirname(__file__))
from stance_window_utils import extract_entity_window

QUEUES = [
    'data/hitl/queue_consensus_stance.csv',
    'data/hitl/queue_maverick_stance.csv',
    'data/hitl/queue_consensus_stance_politics.csv',
    'data/hitl/queue_maverick_stance_politics.csv',
    'data/hitl/queue_maverick_stance_round2.csv',  # active-learning round 2, 2026-07-20
    'data/hitl/queue_maverick_stance_round3.csv',  # active-learning round 3, 2026-07-20
    'data/hitl/queue_maverick_stance_round4.csv',  # active-learning round 4 (multi-entity split), 2026-07-20
    'data/hitl/queue_maverick_stance_round5.csv',  # active-learning round 5 (windowed scoring), 2026-07-20
]
OUT_PATH = 'data/processed/stance_classifier.joblib'
OUT_SUMMARY_PATH = 'data/processed/stance_classifier_summary.csv'
OUT_ROUND_PATH = 'data/processed/stance_classifier_round_progression.csv'

# Cumulative rounds for the active-learning progression curve: round 1 is
# the four base queues, rounds 2-5 add one active-learning queue each.
ROUNDS = [
    ('round1_base', QUEUES[:4]),
    ('round2', QUEUES[:4] + QUEUES[4:5]),
    ('round3', QUEUES[:4] + QUEUES[4:6]),
    ('round4', QUEUES[:4] + QUEUES[4:7]),
    ('round5', QUEUES[:4] + QUEUES[4:8]),
]


def _load_queues(queue_paths):
    frames = []
    for q in queue_paths:
        df = pd.read_csv(q)
        df['source_queue'] = os.path.basename(q).replace('queue_', '').replace('.csv', '')
        if 'entity_spans' not in df.columns:
            df['entity_spans'] = '[]'
        frames.append(df[['id', 'full_text', 'entity_spans', 'human_stance', 'source_queue']])
    all_df = pd.concat(frames, ignore_index=True)
    usable = all_df[all_df['human_stance'].isin(['hostile', 'endorsement'])].copy()
    usable['y'] = (usable['human_stance'] == 'endorsement').astype(int)
    usable['text_window'] = usable.apply(
        lambda r: extract_entity_window(r['full_text'], r['entity_spans']), axis=1)
    return usable


def load_training_data():
    return _load_queues(QUEUES)


def cv_kappa_auc(df):
    X_text = df['text_window'].fillna('')
    y = df['y'].values
    vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 1), sublinear_tf=True, stop_words='english')
    X = vec.fit_transform(X_text)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    clf_cv = LogisticRegression(class_weight='balanced', C=1.0, random_state=42)
    y_pred = cross_val_predict(clf_cv, X, y, cv=cv)
    y_proba = cross_val_predict(clf_cv, X, y, cv=cv, method='predict_proba')[:, 1]
    return cohen_kappa_score(y, y_pred), roc_auc_score(y, y_proba), len(df)


def compute_round_progression():
    print("\n--- Round-over-round active-learning progression (honesty check) ---")
    rows = []
    for label, queue_paths in ROUNDS:
        df = _load_queues(queue_paths)
        kappa, auc, n = cv_kappa_auc(df)
        print(f"  {label}: n={n}, kappa={kappa:.3f}, auc={auc:.3f}")
        rows.append({'round': label, 'n_train': n, 'cv_kappa': kappa, 'cv_auc': auc})
    out = pd.DataFrame(rows)
    out.to_csv(OUT_ROUND_PATH, index=False)
    print(f"Saved round progression to {OUT_ROUND_PATH}")
    return out


def main():
    print("=== Training Stance Classifier (hostile=0, endorsement=1) ===")
    df = load_training_data()
    print(f"Training rows: {len(df)}")
    print(df.groupby(['source_queue', 'human_stance']).size())

    X_text = df['text_window'].fillna('')
    y = df['y'].values

    vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 1), sublinear_tf=True, stop_words='english')
    X = vec.fit_transform(X_text)

    print("\n--- 5-fold stratified cross-validation (honesty check) ---")
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    clf_cv = LogisticRegression(class_weight='balanced', C=1.0, random_state=42)
    y_pred = cross_val_predict(clf_cv, X, y, cv=cv)
    y_proba = cross_val_predict(clf_cv, X, y, cv=cv, method='predict_proba')[:, 1]

    print(classification_report(y, y_pred, target_names=['hostile', 'endorsement']))
    kappa = cohen_kappa_score(y, y_pred)
    auc = roc_auc_score(y, y_proba)
    print(f"Cohen's Kappa: {kappa:.3f}")
    print(f"ROC AUC: {auc:.3f}")

    print("\n--- Per-source-queue held-out accuracy (from the same CV predictions) ---")
    df['cv_pred'] = y_pred
    df['cv_correct'] = (df['cv_pred'] == df['y']).astype(int)
    per_queue = df.groupby('source_queue')['cv_correct'].mean()
    print(per_queue)

    print("\nFitting final model on all usable rows...")
    clf = LogisticRegression(class_weight='balanced', C=1.0, random_state=42)
    clf.fit(X, y)

    os.makedirs('data/processed', exist_ok=True)
    joblib.dump({'vec': vec, 'clf': clf, 'cv_kappa': kappa, 'cv_auc': auc, 'n_train': len(df)}, OUT_PATH)
    print(f"\nSaved stance classifier to {OUT_PATH}")

    per_queue.reset_index().rename(columns={'cv_correct': 'cv_accuracy'}).assign(
        overall_kappa=kappa, overall_auc=auc, overall_n_train=len(df)
    ).to_csv(OUT_SUMMARY_PATH, index=False)
    print(f"Saved summary to {OUT_SUMMARY_PATH}")

    compute_round_progression()


if __name__ == "__main__":
    main()
