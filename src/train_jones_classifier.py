"""train_jones_classifier.py

Trains a Jones-only 3-class stance classifier (hostile/endorsement/other),
combining both hand-labeled Jones queues instead of pooling across all
entities the way train_stance_classifier.py does:
- data/hitl/queue_jones_stance_quality_check.csv (long comments, freeform
  labels -- "endorse", "lean hostile", "unclear/list" etc., never folded
  into the pooled trainer because its labels don't match that script's
  strict LABEL_MAP_3CLASS equality check)
- data/hitl/queue_jones_short_stance_quality_check.csv (<=100 char
  comments, already-clean 3-class labels)

Reuses normalize_label() from score_entity_stance_quality_checks.py (same
freeform-tolerant normalization already used to score both queues) so the
freeform long-queue labels are handled the same way they were when scored,
not silently dropped.

Purpose: test whether an entity-specific model, trained only on Jones
examples, out-discriminates the pooled cross-entity model
(stance_classifier_3class.joblib, CV kappa=0.331 as of the round11 retrain)
on Jones data specifically -- at the cost of a much smaller training set
(~190 rows here vs. 1708 pooled). Small-n caveat: per-queue kappa in the
pooled model's own held-out breakdown ranged from 0.132 (wikileaks) to
0.412 (n=10 round5), so single-digit-percent swings in a ~190-row CV
number below should not be over-read.

Output: data/processed/jones_stance_classifier_3class.joblib
"""
import os
import sys
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import classification_report, cohen_kappa_score, roc_auc_score
import joblib

sys.path.insert(0, os.path.dirname(__file__))
from stance_window_utils import extract_entity_window, filter_quoted_spans
from score_entity_stance_quality_checks import normalize_label

QUEUES = [
    'data/hitl/queue_jones_stance_quality_check.csv',
    'data/hitl/queue_jones_short_stance_quality_check.csv',
]
OUT_PATH = 'data/processed/jones_stance_classifier_3class.joblib'
OUT_SUMMARY_PATH = 'data/processed/jones_stance_classifier_summary_3class.csv'


def load_jones_training_data():
    frames = []
    for q in QUEUES:
        df = pd.read_csv(q)
        df['source_queue'] = os.path.basename(q).replace('queue_', '').replace('.csv', '')
        frames.append(df[['id', 'full_text', 'entity_spans', 'human_stance', 'source_queue']])
    all_df = pd.concat(frames, ignore_index=True)

    normalized = all_df['human_stance'].apply(normalize_label)
    all_df['y'] = normalized.apply(lambda t: t[0])
    all_df['is_list_mention'] = normalized.apply(lambda t: t[1])
    # normalize_label maps everything not hostile/endorsement to 'other'
    # (it has no concept of "unusable" -- unlike train_stance_classifier.py's
    # LABEL_MAP_3CLASS which only recognizes 4 exact input values). Since
    # every row here has a real human_stance value (queues are fully
    # labeled), nothing needs to be dropped as unlabeled.
    usable = all_df.copy()

    def _parse_spans(raw):
        if isinstance(raw, str):
            try:
                import json
                return json.loads(raw)
            except (ValueError, TypeError):
                return []
        return raw or []

    parsed_spans = usable['entity_spans'].apply(_parse_spans)
    filtered_spans = [filter_quoted_spans(t, s) for t, s in zip(usable['full_text'], parsed_spans)]
    quote_only = [len(orig) > 0 and len(kept) == 0 for orig, kept in zip(parsed_spans, filtered_spans)]
    usable['filtered_spans'] = filtered_spans
    n_dropped = sum(quote_only)
    if n_dropped:
        print(f"  Dropping {n_dropped} row(s) whose only entity mention(s) were inside a quoted line")
    usable = usable.loc[[not q for q in quote_only]].copy()
    usable['text_window'] = usable.apply(
        lambda r: extract_entity_window(r['full_text'], r['filtered_spans']), axis=1)
    return usable


def main():
    print("=== Training Jones-only Stance Classifier (3-class: hostile / endorsement / other) ===")
    df = load_jones_training_data()
    print(f"Training rows: {len(df)}")
    print(df.groupby(['source_queue', 'y']).size())

    X_text = df['text_window'].fillna('')
    y = df['y'].values

    vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 1), sublinear_tf=True, stop_words='english')
    X = vec.fit_transform(X_text)

    print("\n--- 5-fold stratified cross-validation (honesty check) ---")
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    clf_cv = LogisticRegression(class_weight='balanced', C=1.0, random_state=42, max_iter=1000)
    y_pred = cross_val_predict(clf_cv, X, y, cv=cv)
    y_proba = cross_val_predict(clf_cv, X, y, cv=cv, method='predict_proba')

    classes_sorted = sorted(np.unique(y))
    print(classification_report(y, y_pred, labels=classes_sorted, target_names=classes_sorted, zero_division=0))
    kappa = cohen_kappa_score(y, y_pred)
    auc = roc_auc_score(y, y_proba, multi_class='ovr', average='macro')
    print(f"Cohen's Kappa: {kappa:.3f}")
    print(f"Macro ROC AUC (one-vs-rest): {auc:.3f}")

    print("\n--- Per-source-queue held-out accuracy AND kappa ---")
    df['cv_pred'] = y_pred
    df['cv_correct'] = (df['cv_pred'] == df['y']).astype(int)
    per_queue_rows = []
    for name, sub in df.groupby('source_queue'):
        maj_baseline = sub['y'].value_counts(normalize=True).max()
        try:
            q_kappa = cohen_kappa_score(sub['y'], sub['cv_pred'])
        except ValueError:
            q_kappa = float('nan')
        per_queue_rows.append({
            'source_queue': name, 'n': len(sub), 'accuracy': sub['cv_correct'].mean(),
            'majority_baseline': maj_baseline, 'kappa': q_kappa,
        })
    per_queue = pd.DataFrame(per_queue_rows).set_index('source_queue')
    print(per_queue.to_string(float_format=lambda x: f'{x:.3f}'))

    print("\nFitting final model on all usable rows...")
    clf = LogisticRegression(class_weight='balanced', C=1.0, random_state=42, max_iter=1000)
    clf.fit(X, y)

    os.makedirs('data/processed', exist_ok=True)
    joblib.dump({
        'vec': vec, 'clf': clf, 'cv_kappa': kappa, 'cv_auc': auc, 'n_train': len(df),
        'n_classes': 3, 'classes_': list(clf.classes_), 'features': 'tfidf',
    }, OUT_PATH)
    print(f"\nSaved Jones-only stance classifier to {OUT_PATH}")

    per_queue.reset_index().rename(columns={'accuracy': 'cv_accuracy', 'kappa': 'cv_kappa_per_queue'}).assign(
        overall_kappa=kappa, overall_auc=auc, overall_n_train=len(df)
    ).to_csv(OUT_SUMMARY_PATH, index=False)
    print(f"Saved summary to {OUT_SUMMARY_PATH}")


if __name__ == "__main__":
    main()
