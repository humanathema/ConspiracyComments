"""score_authority_appeal_full.py

Validates and scores the dormant source_citation/appeal_to_authority
constructs (found sitting unused in the methods provenance audit --
trained local TF-IDF+LogisticRegression classifiers exist in
train_and_score_comparisons.py, on genuinely human-labeled ground truth
in labeled_2k_with_scores.csv, but were only ever scored against the
comparison control corpora, never the main r/conspiracy population).

Purpose: entity-based has_maverick/has_consensus_expert only capture
authority appeals tied to a NAMED figure in our curated lists.
appeal_to_authority/source_citation are entity-agnostic -- they should
catch citation of institutional authority (court decisions, government
reports, credentials) independent of whether a specific listed entity is
named. The interesting population for the "credentials problem" question
is comments that score high on these but match NEITHER entity list --
that's the "credentialed-sounding but not one of our named figures"
population that pure entity-matching structurally can't see.

IMPORTANT ASYMMETRY, confirmed by rerunning src/validation.py before this
script: source_citation's ground-truth labels agree strongly with
genuine human judgment (kappa=0.869 vs the human_1 subset) -- solid.
appeal_to_authority's labels are much weaker (kappa=0.323) -- the ground
truth itself is noisy, which caps whatever gets built on it. Both are
validated here via proper 5-fold CV (not just trusting validation.py's
LLM-label-vs-human number, which measures something different from this
script's own from-scratch-trained local classifier), and both results
are reported honestly -- expect appeal_to_authority to come back
provisional at best.

Uses research_corpus_enriched.parquet (4.78M rows) as the scoring
population -- this is the Stage-1 pre-filter this project already built
specifically for source_citation/appeal_to_authority (evidence_count>0 OR
has_link=1 OR alt_authority_count>0 OR quantitative_count>0), documented
in score_main_corpus_staged.py's own comment as the correct corpus for
these two dimensions specifically (as opposed to the full 21M corpus used
for personal_experience/procedural_skepticism).
"""
import os
import sys
import numpy as np
import pandas as pd
import duckdb
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import classification_report, cohen_kappa_score, roc_auc_score

sys.path.insert(0, os.path.dirname(__file__))
from rerun_refined_regressions_v2 import load_entities_split_corrected, compute_has_maverick, compute_has_consensus_expert
from refine_thesis_models import build_regex
from combined_maverick_detector import load_maverick_disambiguation_lookup
from consensus_disambiguation_lookup import load_consensus_disambiguation_lookup

L2K = 'data/processed/labeled_2k_with_scores.csv'
ENRICHED_PATH = 'data/processed/research_corpus_enriched.parquet'
OUT_MODELS_PATH = 'data/processed/authority_appeal_classifiers.joblib'
OUT_SCORED_PATH = 'data/processed/authority_appeal_scored.parquet'
OUT_SUMMARY_PATH = 'data/processed/authority_appeal_summary.csv'

DIMS = ['source_citation', 'appeal_to_authority']


def as_binary(s):
    if s.dtype == object:
        return s.astype(str).str.lower().isin(['1', '1.0', 'true', 'yes']).astype(int)
    return (s.fillna(0) > 0.5).astype(int)


def train_and_validate(dim):
    df = pd.read_csv(L2K)
    human = df[df[f'{dim}_source'] == 'human_1'].dropna(subset=['text'])
    X_text = human['text'].fillna('')
    y = as_binary(human[f'{dim}_score']).values
    print(f"\n=== {dim}: training on {len(human)} human-labeled rows (base rate {y.mean():.3f}) ===")

    vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 1), sublinear_tf=True, stop_words='english')
    X = vec.fit_transform(X_text)

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    clf_cv = LogisticRegression(class_weight='balanced', C=1.0, random_state=42)
    y_pred = cross_val_predict(clf_cv, X, y, cv=cv)
    y_proba = cross_val_predict(clf_cv, X, y, cv=cv, method='predict_proba')[:, 1]

    print(classification_report(y, y_pred, target_names=['negative', dim], zero_division=0))
    kappa = cohen_kappa_score(y, y_pred)
    auc = roc_auc_score(y, y_proba)
    print(f"5-fold CV Cohen's Kappa: {kappa:.3f}, ROC AUC: {auc:.3f}")

    clf = LogisticRegression(class_weight='balanced', C=1.0, random_state=42)
    clf.fit(X, y)
    return {'vec': vec, 'clf': clf, 'cv_kappa': kappa, 'cv_auc': auc, 'n_train': len(human)}


def main():
    print("=== Validating and scoring source_citation / appeal_to_authority ===")
    models = {}
    for dim in DIMS:
        models[dim] = train_and_validate(dim)
    joblib.dump(models, OUT_MODELS_PATH)
    print(f"\nSaved classifiers to {OUT_MODELS_PATH}")

    print(f"\nLoading enriched corpus ({ENRICHED_PATH})...")
    df = pd.read_parquet(ENRICHED_PATH, columns=['id', 'text'])
    print(f"  Loaded {len(df):,} rows.")

    for dim in DIMS:
        vec, clf = models[dim]['vec'], models[dim]['clf']
        X = vec.transform(df['text'].fillna(''))
        df[f'{dim}_prob'] = clf.predict_proba(X)[:, 1]
        print(f"  Scored {dim}: mean={df[f'{dim}_prob'].mean():.3f}, "
              f">0.5 count={int((df[f'{dim}_prob']>0.5).sum()):,}")

    print("\nFlagging entity mentions (has_maverick / has_consensus_expert) on the same corpus...")
    mavericks, canon, consensus = load_entities_split_corrected()
    rx_mav = build_regex(mavericks)
    rx_con = build_regex(consensus)
    lookup = load_maverick_disambiguation_lookup()
    consensus_lookup = load_consensus_disambiguation_lookup()
    df['has_maverick'] = compute_has_maverick(df, rx_mav, lookup)
    df['has_consensus_expert'] = compute_has_consensus_expert(df, rx_con, consensus_lookup)
    df['has_any_entity'] = ((df['has_maverick'] == 1) | (df['has_consensus_expert'] == 1)).astype(int)

    df.drop(columns=['text']).to_parquet(OUT_SCORED_PATH, index=False)
    print(f"Saved scored corpus (no text, small) to {OUT_SCORED_PATH}")

    print("\n=== The population this was actually for: high authority-appeal, NO named entity ===")
    summary_rows = []
    for dim in DIMS:
        high = df[df[f'{dim}_prob'] > 0.5]
        no_entity = high[high['has_any_entity'] == 0]
        pct_no_entity = len(no_entity) / max(len(high), 1) * 100
        print(f"\n{dim}: {len(high):,} high-scoring comments total, "
              f"{len(no_entity):,} ({pct_no_entity:.1f}%) match NO entity in either list")
        summary_rows.append({
            'construct': dim,
            'n_train': models[dim]['n_train'],
            'cv_kappa': models[dim]['cv_kappa'],
            'cv_auc': models[dim]['cv_auc'],
            'n_high_scoring': len(high),
            'n_no_entity_match': len(no_entity),
            'pct_no_entity_match': pct_no_entity,
        })

    pd.DataFrame(summary_rows).to_csv(OUT_SUMMARY_PATH, index=False)
    print(f"\nSaved summary to {OUT_SUMMARY_PATH}")
    print("\nDone.")


if __name__ == "__main__":
    main()
