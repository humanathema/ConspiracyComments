"""score_entity_stance_quality_checks.py

Scores the hand-labeled quality check queues (Reddit or AboveTopSecret)
against the two-stage cascade stance classifier's separate predictions.

For AboveTopSecret (--platform ats), it implements a 4-way label normalization scheme:
  - hostile / endorsement / neutral / ambiguous
And computes binary Cohen's Kappa & Accuracy strictly on the hostile/endorsement subset.
It also reports a temporal drift audit (Early Era <= 2011 vs Late Era >= 2012).

Outputs:
  data/hitl/queue_{entity_or_platform}_stance_quality_check_REVIEW.csv
"""
import os
import sys
import argparse
import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score, confusion_matrix, classification_report

CLASSES = ['hostile', 'endorsement', 'other']


def normalize_label(raw):
    if pd.isna(raw):
        return 'other', False
    s = str(raw).strip().lower()
    is_list = 'list' in s
    if s.startswith('hostile') or s == 'lean hostile' or 'lean hostile' in s:
        return 'hostile', is_list
    if s.startswith('endorse') or 'endorse' in s:
        return 'endorsement', is_list
    if s.startswith('neutral') or 'neutral' in s:
        return 'neutral', is_list
    if s.startswith('ambiguous') or s.startswith('unclear') or 'ambiguous' in s or 'unclear' in s:
        return 'ambiguous', is_list
    return 'other', is_list


def score_for_entity(entity):
    print(f"\n=================================================================")
    print(f"=== Scoring Stance Quality Check for Entity Concept: '{entity}' ===")
    print(f"=================================================================")

    queue_path = f'data/hitl/queue_{entity}_stance_quality_check.csv'
    pred_path = f'data/processed/{entity}_stance_quality_check_predictions.csv'
    review_out_path = f'data/hitl/queue_{entity}_stance_quality_check_REVIEW.csv'

    if not os.path.exists(queue_path):
        print(f"Error: Queue file not found at {queue_path}")
        return
    if not os.path.exists(pred_path):
        print(f"Error: Prediction file not found at {pred_path}")
        return

    q = pd.read_csv(queue_path)
    p = pd.read_csv(pred_path)
    df = q.merge(p, on='id', how='inner')
    assert len(df) == len(q), f"Queue/predictions ID mismatch! Check for duplicate IDs or missing predictions."

    # Filter for labeled comments
    labeled_df = df[df['human_stance'].notna() & (df['human_stance'].astype(str).str.strip() != '')].copy()
    print(f"Loaded {len(df)} total comments in queue. Labeled: {len(labeled_df)}")
    
    if len(labeled_df) == 0:
        print("No human labels found yet. Please open the queue file and label the 'human_stance' column.")
        return

    normalized = labeled_df['human_stance'].apply(normalize_label)
    # Map back to 3-class for standard evaluation (neutral/ambiguous mapped to 'other')
    labeled_df['human_norm'] = normalized.apply(lambda t: 'other' if t[0] in ['neutral', 'ambiguous', 'other'] else t[0])
    labeled_df['is_list_mention'] = normalized.apply(lambda t: t[1])

    print("\n=== Raw human label distribution ===")
    print(labeled_df['human_stance'].value_counts())
    print("\n=== Normalized 3-class human label distribution ===")
    print(labeled_df['human_norm'].value_counts())
    print(f"\nList/link-dump flagged mentions: {labeled_df['is_list_mention'].sum()} / {len(labeled_df)} ({labeled_df['is_list_mention'].mean():.1%})")

    # Overall 3-class evaluation
    y_true = labeled_df['human_norm']
    y_pred = labeled_df['predicted_label']

    print("\n=== 3-Class Classification Report (hostile / endorsement / other) ===")
    print(classification_report(y_true, y_pred, labels=CLASSES, target_names=CLASSES, zero_division=0))

    kappa = cohen_kappa_score(y_true, y_pred, labels=CLASSES)
    acc = (y_true == y_pred).mean()
    print(f"Overall Accuracy: {acc:.3f}")
    print(f"Cohen's Kappa (multi-class): {kappa:.3f}")

    print("\nConfusion matrix (rows=true, cols=predicted):")
    cm = confusion_matrix(y_true, y_pred, labels=CLASSES)
    cm_df = pd.DataFrame(cm, index=[f"true_{c}" for c in CLASSES], columns=[f"pred_{c}" for c in CLASSES])
    print(cm_df)

    print("\n=== Accuracy by predicted label stratum ===")
    for bucket in CLASSES:
        sub = labeled_df[labeled_df['predicted_label'] == bucket]
        if len(sub) == 0:
            continue
        acc_b = (sub['human_norm'] == sub['predicted_label']).mean()
        print(f"  predicted='{bucket}': n={len(sub)}, accuracy={acc_b:.3f}")
        for c in CLASSES:
            count = sum(sub['human_norm'] == c)
            print(f"    human_norm='{c}': {count}")

    # Miss magnitude check
    def get_miss_magnitude(row):
        true_cls = row['human_norm']
        prob_col = f'p_{true_cls}'
        if prob_col in row:
            return 1.0 - row[prob_col]
        return np.nan

    labeled_df['miss_magnitude'] = labeled_df.apply(get_miss_magnitude, axis=1)
    labeled_df['correct'] = labeled_df['human_norm'] == labeled_df['predicted_label']

    print("\n=== Top 10 worst misses: model highly confident in wrong label ===")
    worst = labeled_df.sort_values('miss_magnitude', ascending=False).head(10)
    print(worst[['id', 'human_norm', 'predicted_label', 'miss_magnitude']].to_string(index=False))

    # Save full review file
    unlabeled_df = df[~(df['id'].isin(labeled_df['id']))].copy()
    unlabeled_df['human_norm'] = np.nan
    unlabeled_df['is_list_mention'] = np.nan
    unlabeled_df['correct'] = np.nan
    unlabeled_df['miss_magnitude'] = np.nan

    review_df = pd.concat([
        labeled_df.sort_values('miss_magnitude', ascending=False),
        unlabeled_df
    ], ignore_index=True)

    review_cols = [
        'id', 'full_text', 'human_stance', 'human_norm', 'is_list_mention',
        'predicted_label', 'correct', 'miss_magnitude'
    ] + [f'p_{c}' for c in CLASSES] + ['notes']
    
    review_df = review_df[review_cols]
    review_df.to_csv(review_out_path, index=False)
    print(f"\nSaved full reviewable results to {review_out_path}")


def score_ats():
    print(f"\n=================================================================")
    print(f"=== Scoring Stance Quality Check for AboveTopSecret (ATS) ===")
    print(f"=================================================================")

    queue_path = 'data/hitl/queue_ats_stance_quality_check.csv'
    pred_path = 'data/processed/ats_stance_quality_check_predictions.csv'
    review_out_path = 'data/hitl/queue_ats_stance_quality_check_REVIEW.csv'

    if not os.path.exists(queue_path):
        print(f"Error: Queue file not found at {queue_path}")
        return
    if not os.path.exists(pred_path):
        print(f"Error: Prediction file not found at {pred_path}")
        return

    q = pd.read_csv(queue_path)
    p = pd.read_csv(pred_path)
    df = q.merge(p, on=['id', 'entity_key'], how='inner')
    assert len(df) == len(q), "Queue/predictions ID/entity_key mismatch!"

    # Filter for labeled comments
    labeled_df = df[df['human_stance'].notna() & (df['human_stance'].astype(str).str.strip() != '')].copy()
    print(f"Loaded {len(df)} total comments in queue. Labeled: {len(labeled_df)}")
    
    if len(labeled_df) == 0:
        print("\nNo human labels found yet. Please open the queue file and label the 'human_stance' column:")
        print(f"  {queue_path}")
        print("\nValid labels (case-insensitive):")
        print("  - hostile / lean hostile")
        print("  - endorsement / endorse / lean endorsement")
        print("  - neutral")
        print("  - ambiguous / unclear")
        print("\nYou can append 'list' to any label (e.g. 'hostile list') to flag list-dumps.")
        return

    normalized = labeled_df['human_stance'].apply(normalize_label)
    labeled_df['human_norm'] = normalized.apply(lambda t: t[0])
    labeled_df['is_list_mention'] = normalized.apply(lambda t: t[1])

    print("\n=== Raw human label distribution ===")
    print(labeled_df['human_stance'].value_counts())
    print("\n=== Normalized 4-class human label distribution ===")
    print(labeled_df['human_norm'].value_counts())
    print(f"\nList/link-dump flagged mentions: {labeled_df['is_list_mention'].sum()} / {len(labeled_df)} ({labeled_df['is_list_mention'].mean():.1%})")

    neutral_ambig_mask = labeled_df['human_norm'].isin(['neutral', 'ambiguous', 'other'])
    print(f"\nNeutral/ambiguous/other share: {neutral_ambig_mask.mean():.1%}")
    print("  (The classifier was never trained to have an opinion on these; a high share")
    print("  is a construct-validity signal separate from classification accuracy below.)")

    # Binary hostile-vs-endorsement stance scoring
    binary = labeled_df[labeled_df['human_norm'].isin(['hostile', 'endorsement'])].copy()
    if len(binary) == 0:
        print("\nWARNING: No clear stance labels ('hostile' or 'endorsement') found in labeled subset. Cannot run binary scoring.")
        return

    # Use max prob between hostile and endorsement as binary classification
    binary['y_true'] = binary['human_norm']
    binary['y_pred'] = np.where(binary['p_endorsement'] >= binary['p_hostile'], 'endorsement', 'hostile')

    print(f"\n=== Binary Stance Scoring (n={len(binary)}, excludes neutral/ambiguous/other) ===")
    print(classification_report(binary['y_true'], binary['y_pred'], labels=['hostile', 'endorsement']))

    kappa = cohen_kappa_score(binary['y_true'], binary['y_pred'], labels=['hostile', 'endorsement'])
    acc = (binary['y_true'] == binary['y_pred']).mean()
    print(f"Stance Accuracy: {acc:.3f}")
    print(f"Cohen's Kappa (vs. Reddit CV kappa=0.370 for context): {kappa:.3f}")

    # Per-era breakdown to audit temporal drift
    if 'year' in binary.columns:
        binary['era'] = np.where(binary['year'] <= 2011, 'early (pre-2012)', 'late (post-2011)')
        print("\n=== Temporal Drift Analysis (Accuracy & Kappa by Era) ===")
        for era in sorted(binary['era'].unique()):
            era_sub = binary[binary['era'] == era]
            if len(era_sub) == 0:
                continue
            era_acc = (era_sub['y_true'] == era_sub['y_pred']).mean()
            # Cohen's Kappa requires at least one prediction and one true label of each class
            if len(era_sub['y_true'].unique()) > 1:
                era_kappa = cohen_kappa_score(era_sub['y_true'], era_sub['y_pred'], labels=['hostile', 'endorsement'])
                era_kappa_str = f"{era_kappa:.3f}"
            else:
                era_kappa_str = "N/A (monoclass)"
            print(f"  * {era}: n={len(era_sub)}, accuracy={era_acc:.3f}, kappa={era_kappa_str}")

    print("\nConfusion matrix (rows=true, cols=predicted; hostile vs. endorsement):")
    print(confusion_matrix(binary['y_true'], binary['y_pred'], labels=['hostile', 'endorsement']))

    # Write review file
    labeled_df['correct'] = labeled_df['human_norm'] == labeled_df['predicted_label']
    unlabeled_df = df[~(df['id'].isin(labeled_df['id']))].copy()
    unlabeled_df['human_norm'] = np.nan
    unlabeled_df['is_list_mention'] = np.nan
    unlabeled_df['correct'] = np.nan

    review_df = pd.concat([labeled_df, unlabeled_df], ignore_index=True)
    review_df.to_csv(review_out_path, index=False)
    print(f"\nSaved full reviewable results to {review_out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', default='reddit', choices=['reddit', 'ats'],
                        help="Platform target: 'reddit' or 'ats'.")
    parser.add_argument('--entity', default='all',
                        choices=['all', 'wikileaks', 'assange', 'snowden', 'greenwald', 'jones_short'],
                        help="Score quality check queue for a specific entity or all of them (Reddit-only).")
    args = parser.parse_args()

    if args.platform == 'ats':
        score_ats()
    else:
        entities = ['wikileaks', 'assange', 'snowden', 'greenwald'] if args.entity == 'all' else [args.entity]
        for entity in entities:
            score_for_entity(entity)


if __name__ == "__main__":
    main()
