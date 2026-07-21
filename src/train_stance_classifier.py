"""train_stance_classifier.py

Trains a local, deterministic stance classifier on the HITL stance queues,
following the exact same architecture as the existing pe_prob/ps_prob
staged classifiers in staged_pipeline.py (TfidfVectorizer + class_weight-
balanced LogisticRegression) -- no LLM calls, consistent with the rest of
this project's local-classifier pattern.

Purpose: the core regression's has_maverick/has_consensus_expert are
currently pooled "any mention" binaries -- they don't distinguish a
hostile mention ("even the CDC admits...") from an endorsing one ("the
CDC's own study confirms..."). Since the hostile/endorsement mix already
differs sharply by subreddit and construct, pooling could be diluting two
different real effects into one middling coefficient. This classifier
lets has_maverick/has_consensus_expert be split into hostile vs.
endorsement (vs. other) sub-variables for a follow-on regression.

REDESIGNED 2026-07-21: was strictly binary (hostile vs. endorsement,
dropping neutral/ambiguous/wrong_match). A 99-row Jones-specific quality
check found the binary model reads hostile-vs-neutral fine but is bad at
detecting genuine endorsement (38.9% held-out accuracy on the model's own
"confidently endorsing" predictions, worse than chance) -- forcing every
mention onto one axis meant list/link-dumps, sarcastic meme-callback
mockery ("gay frogs"), and genuinely neutral/descriptive mentions all had
to land somewhere on hostile<->endorsement, with no room to say "this
isn't really evaluative." Switched to 3-class (hostile / endorsement /
other), folding the previously-discarded neutral+ambiguous labels (154
rows already sitting in the queues, unused) into `other` -- no new
labeling needed to start. `wrong_match` stays excluded (misidentified
entity, not a real stance instance at all).

--classes 2 (legacy) reproduces the original binary behavior exactly and
writes to the original OUT_PATH, so nothing that depends on the existing
stance_classifier.joblib (rerun_regressions_with_stance.py,
run_integrated_regressions.py -- the core thesis regression numbers)
breaks silently. --classes 3 (new default) writes to a SEPARATE file
(OUT_PATH_3CLASS) rather than overwriting the binary one -- migrating the
production regression scripts to a 3-class stance variable is a design
decision (how does a 3-class categorical enter a traction regression?)
that needs its own sign-off, not a side effect of retraining.

Output: data/processed/stance_classifier.joblib (--classes 2) or
        data/processed/stance_classifier_3class.joblib (--classes 3, default)
"""
import os
import json
import argparse
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import classification_report, cohen_kappa_score, roc_auc_score
import joblib

import sys
sys.path.insert(0, os.path.dirname(__file__))
from stance_window_utils import extract_entity_window, filter_quoted_spans


class EmbeddingVectorizer:
    """Drop-in replacement for TfidfVectorizer's .fit_transform()/.transform()
    interface, backed by a local sentence-transformers model (downloaded once,
    cached locally -- no API calls, same "no LLM calls" constraint as the rest
    of this project; this project has already used this exact model for
    BERTopic in the notebook, and a 92K-row precomputed-embeddings parquet
    exists from that work, though its rows barely overlap this project's
    stance-labeled comments so it can't be reused directly here).

    Added 2026-07-21 (--features embeddings) after error analysis on the
    leak-source-entity misses (Wikileaks/Assange/Snowden/Greenwald) showed
    the remaining errors are almost all rhetorical (sarcasm, quoting an
    opposing claim to mock it, citation-relay sentences with no hostile/
    endorsing vocabulary at all) -- exactly the kind of thing bag-of-words
    TF-IDF structurally cannot represent regardless of how much more
    training data it gets. Embeddings won't solve true sarcasm, but should
    help with paraphrase/semantic-similarity cases TF-IDF misses on exact
    word overlap alone."""

    def __init__(self, model_name='all-MiniLM-L6-v2'):
        from sentence_transformers import SentenceTransformer
        self.model_name = model_name
        self._model = SentenceTransformer(model_name)

    def fit_transform(self, texts):
        return self.transform(texts)

    def transform(self, texts):
        return self._model.encode(list(texts), show_progress_bar=False)

QUEUES = [
    'data/hitl/queue_consensus_stance.csv',
    'data/hitl/queue_maverick_stance.csv',
    'data/hitl/queue_consensus_stance_politics.csv',
    'data/hitl/queue_maverick_stance_politics.csv',
    'data/hitl/queue_maverick_stance_round2.csv',  # active-learning round 2, 2026-07-20
    'data/hitl/queue_maverick_stance_round3.csv',  # active-learning round 3, 2026-07-20
    'data/hitl/queue_maverick_stance_round4.csv',  # active-learning round 4 (multi-entity split), 2026-07-20
    'data/hitl/queue_maverick_stance_round5.csv',  # active-learning round 5 (windowed scoring), 2026-07-20
    'data/hitl/queue_maverick_stance_round6.csv',  # active-learning round 6 (high-endorse-confidence targeted), 2026-07-21
    'data/hitl/queue_maverick_stance_round7.csv',  # active-learning round 7 (high-other-confidence targeted), 2026-07-21
    'data/hitl/queue_wikileaks_stance_quality_check.csv',  # entity quality-check, folded into training 2026-07-21 --
    'data/hitl/queue_assange_stance_quality_check.csv',    # leak-source/org entities scored near-random (kappa 0.09/0.03)
                                                            # despite good overall accuracy -- training data had almost no
                                                            # organization-style mentions, these add real diverse examples.
    'data/hitl/queue_snowden_stance_quality_check.csv',    # same pattern, kappa=-0.045 (worse than chance) before folding in
    'data/hitl/queue_greenwald_stance_quality_check.csv',  # same pattern again, kappa=0.076 before folding in
    'data/hitl/queue_jones_short_stance_quality_check.csv',  # short-comment (<=100 char) population check,
                                                              # 2026-07-22 -- kappa=0.167 held-out, worse than the
                                                              # long-comment Jones check (0.243) and errors spread
                                                              # across all 3 classes, not just endorsement.
]
OUT_PATH = 'data/processed/stance_classifier.joblib'
OUT_PATH_3CLASS = 'data/processed/stance_classifier_3class.joblib'
OUT_SUMMARY_PATH = 'data/processed/stance_classifier_summary.csv'
OUT_ROUND_PATH = 'data/processed/stance_classifier_round_progression.csv'

# Cumulative rounds for the active-learning progression curve: round 1 is
# the four base queues, rounds 2-5 add one active-learning queue each.
# (round 6 -- queue_maverick_stance_round6.csv -- is built but not yet
# labeled, not included here.)
ROUNDS = [
    ('round1_base', QUEUES[:4]),
    ('round2', QUEUES[:4] + QUEUES[4:5]),
    ('round3', QUEUES[:4] + QUEUES[4:6]),
    ('round4', QUEUES[:4] + QUEUES[4:7]),
    ('round5', QUEUES[:4] + QUEUES[4:8]),
    ('round6', QUEUES[:4] + QUEUES[4:9]),
    ('round7', QUEUES[:4] + QUEUES[4:10]),
    ('round8_wikileaks_assange', QUEUES[:4] + QUEUES[4:12]),
    ('round9_snowden', QUEUES[:4] + QUEUES[4:13]),
    ('round10_greenwald', QUEUES[:4] + QUEUES[4:14]),
    ('round11_jones_short', QUEUES[:4] + QUEUES[4:15]),
]

LABEL_MAP_3CLASS = {
    'hostile': 'hostile',
    'endorsement': 'endorsement',
    'neutral': 'other',
    'ambiguous': 'other',
}


def _load_queues(queue_paths, n_classes):
    frames = []
    for q in queue_paths:
        df = pd.read_csv(q)
        df['source_queue'] = os.path.basename(q).replace('queue_', '').replace('.csv', '')
        if 'entity_spans' not in df.columns:
            df['entity_spans'] = '[]'
        frames.append(df[['id', 'full_text', 'entity_spans', 'human_stance', 'source_queue']])
    all_df = pd.concat(frames, ignore_index=True)

    if n_classes == 2:
        usable = all_df[all_df['human_stance'].isin(['hostile', 'endorsement'])].copy()
        usable['y'] = usable['human_stance']
    else:
        usable = all_df[all_df['human_stance'].isin(LABEL_MAP_3CLASS.keys())].copy()
        usable['y'] = usable['human_stance'].map(LABEL_MAP_3CLASS)

    def _parse_spans(raw):
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return []
        return raw or []

    parsed_spans = usable['entity_spans'].apply(_parse_spans)
    filtered_spans = [filter_quoted_spans(t, s) for t, s in zip(usable['full_text'], parsed_spans)]
    # A row is "quote-only" if it HAD spans before filtering but none survive --
    # the labeled entity mention was purely someone else's quoted text, so the
    # window would otherwise silently fall back to the whole comment (including
    # the quote) rather than reflect what the label was actually about.
    quote_only = [len(orig) > 0 and len(kept) == 0 for orig, kept in zip(parsed_spans, filtered_spans)]
    usable['filtered_spans'] = filtered_spans
    n_dropped = sum(quote_only)
    if n_dropped:
        print(f"  Dropping {n_dropped} row(s) whose only entity mention(s) were inside a quoted line")
    usable = usable.loc[[not q for q in quote_only]].copy()
    usable['text_window'] = usable.apply(
        lambda r: extract_entity_window(r['full_text'], r['filtered_spans']), axis=1)
    return usable


def load_training_data(n_classes):
    return _load_queues(QUEUES, n_classes)


def make_vectorizer(features):
    if features == 'embeddings':
        return EmbeddingVectorizer()
    return TfidfVectorizer(max_features=5000, ngram_range=(1, 1), sublinear_tf=True, stop_words='english')


def cv_kappa_auc(df, n_classes, features='tfidf'):
    X_text = df['text_window'].fillna('')
    y = df['y'].values
    vec = make_vectorizer(features)
    X = vec.fit_transform(X_text)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    clf_cv = LogisticRegression(class_weight='balanced', C=1.0, random_state=42, max_iter=1000)
    y_pred = cross_val_predict(clf_cv, X, y, cv=cv)
    y_proba = cross_val_predict(clf_cv, X, y, cv=cv, method='predict_proba')
    kappa = cohen_kappa_score(y, y_pred)
    if n_classes == 2:
        # column order from cross_val_predict follows sorted(np.unique(y)) --
        # 'endorsement' < 'hostile' alphabetically, so column 1 = hostile's
        # probability, NOT endorsement's. Use column matching 'endorsement'
        # explicitly rather than assuming index 1, to avoid a silent flip.
        classes_sorted = sorted(np.unique(y))
        auc = roc_auc_score(y, y_proba[:, classes_sorted.index('endorsement')])
    else:
        auc = roc_auc_score(y, y_proba, multi_class='ovr', average='macro')
    return kappa, auc, len(df)


def compute_round_progression(n_classes):
    print("\n--- Round-over-round active-learning progression (honesty check) ---")
    rows = []
    for label, queue_paths in ROUNDS:
        df = _load_queues(queue_paths, n_classes)
        kappa, auc, n = cv_kappa_auc(df, n_classes)
        print(f"  {label}: n={n}, kappa={kappa:.3f}, auc={auc:.3f}")
        rows.append({'round': label, 'n_train': n, 'cv_kappa': kappa, 'cv_auc': auc})
    out = pd.DataFrame(rows)
    out_path = OUT_ROUND_PATH if n_classes == 2 else OUT_ROUND_PATH.replace('.csv', '_3class.csv')
    out.to_csv(out_path, index=False)
    print(f"Saved round progression to {out_path}")
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--classes', type=int, default=3, choices=[2, 3],
                         help="2: legacy hostile-vs-endorsement binary, writes to the original "
                              "stance_classifier.joblib (what rerun_regressions_with_stance.py / "
                              "run_integrated_regressions.py currently load -- untouched either way). "
                              "3 (default): hostile/endorsement/other, folding the previously-discarded "
                              "neutral+ambiguous labels into 'other'. Writes to a SEPARATE file "
                              "(stance_classifier_3class.joblib) so switching the default here can't "
                              "silently break anything already depending on the binary model.")
    parser.add_argument('--features', default='tfidf', choices=['tfidf', 'embeddings'],
                         help="'tfidf' (default): the existing bag-of-words representation. "
                              "'embeddings': local sentence-transformers embeddings instead (see "
                              "EmbeddingVectorizer docstring) -- experimental, writes to a separate "
                              "file, skips the round-progression curve (slow to re-encode repeatedly "
                              "and not comparable to the tfidf-based historical rounds anyway).")
    args = parser.parse_args()
    n_classes = args.classes
    features = args.features
    suffix = '_3class' if n_classes == 3 else ''
    if features == 'embeddings':
        suffix += '_embeddings'
    out_path = f'data/processed/stance_classifier{suffix}.joblib'
    out_summary_path = f'data/processed/stance_classifier_summary{suffix}.csv'

    label_desc = "hostile=0, endorsement=1" if n_classes == 2 else "hostile / endorsement / other"
    print(f"=== Training Stance Classifier ({n_classes}-class: {label_desc}) ===")
    df = load_training_data(n_classes)
    print(f"Training rows: {len(df)}")
    print(df.groupby(['source_queue', 'human_stance']).size())
    print("\nClass distribution (post quote-filtering):")
    print(df['y'].value_counts())

    X_text = df['text_window'].fillna('')
    y = df['y'].values

    vec = make_vectorizer(features)
    X = vec.fit_transform(X_text)

    print("\n--- 5-fold stratified cross-validation (honesty check) ---")
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    clf_cv = LogisticRegression(class_weight='balanced', C=1.0, random_state=42, max_iter=1000)
    y_pred = cross_val_predict(clf_cv, X, y, cv=cv)
    y_proba = cross_val_predict(clf_cv, X, y, cv=cv, method='predict_proba')

    classes_sorted = sorted(np.unique(y))
    print(classification_report(y, y_pred, labels=classes_sorted, target_names=classes_sorted))
    kappa = cohen_kappa_score(y, y_pred)
    if n_classes == 2:
        auc = roc_auc_score(y, y_proba[:, classes_sorted.index('endorsement')])
        auc_label = "ROC AUC"
    else:
        auc = roc_auc_score(y, y_proba, multi_class='ovr', average='macro')
        auc_label = "Macro ROC AUC (one-vs-rest)"
    print(f"Cohen's Kappa: {kappa:.3f}")
    print(f"{auc_label}: {auc:.3f}")

    print("\n--- Per-source-queue held-out accuracy AND kappa (from the same CV predictions) ---")
    print("(accuracy alone is misleading on imbalanced per-entity samples -- e.g. a queue that's "
          "66% endorsement gets 66% accuracy for free by always guessing endorsement; kappa is the "
          "chance-corrected number that actually says whether the model is discriminating anything.)")
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
        'n_classes': n_classes, 'classes_': list(clf.classes_), 'features': features,
    }, out_path)
    print(f"\nSaved stance classifier to {out_path}")

    per_queue.reset_index().rename(columns={'accuracy': 'cv_accuracy', 'kappa': 'cv_kappa_per_queue'}).assign(
        overall_kappa=kappa, overall_auc=auc, overall_n_train=len(df)
    ).to_csv(out_summary_path, index=False)
    print(f"Saved summary to {out_summary_path}")

    if features == 'embeddings':
        print("\n(Skipping round-progression curve for embeddings mode -- slow to re-encode "
              "repeatedly, and not comparable to the tfidf-based historical rounds anyway.)")
    else:
        compute_round_progression(n_classes)


if __name__ == "__main__":
    main()
