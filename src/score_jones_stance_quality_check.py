"""score_jones_stance_quality_check.py

Scores data/hitl/queue_jones_stance_quality_check.csv (99 hand-labeled Jones
mentions, stratified by predicted stance_prob bucket -- see
build_jones_stance_quality_queue.py) against the classifier's blind
predictions in data/processed/jones_stance_quality_check_predictions.csv.

Nash's labels are freeform (e.g. "lean hostile", "neutral/list", "unclear,
lean hostile?") rather than strictly the four codebook categories, so this
script normalizes them into {hostile, endorsement, neutral, ambiguous}
before scoring, and separately flags rows Nash tagged as list/link-dump
mentions (a hypothesized failure mode: enumerated names with no real
evaluative content, which the model may score as confidently endorsing
purely for lack of hostile-coded vocabulary).

Accuracy/kappa is computed only on the hostile/endorsement subset (same
convention as training -- neutral/ambiguous were never something this
binary classifier was asked to predict), reported overall and broken down
by the predicted_bucket stratum the row was originally sampled from.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score, confusion_matrix, classification_report

QUEUE_PATH = 'data/hitl/queue_jones_stance_quality_check.csv'
PRED_PATH = 'data/processed/jones_stance_quality_check_predictions.csv'
REVIEW_OUT_PATH = 'data/hitl/queue_jones_stance_quality_check_REVIEW.csv'


def normalize_label(raw):
    s = str(raw).strip().lower()
    is_list = 'list' in s
    if s.startswith('hostile') or s == 'lean hostile' or 'lean hostile' in s:
        return 'hostile', is_list
    if s.startswith('endorse'):
        return 'endorsement', is_list
    if s.startswith('neutral'):
        return 'neutral', is_list
    if s.startswith('ambiguous') or s.startswith('unclear'):
        return 'ambiguous', is_list
    return 'other', is_list


def main():
    q = pd.read_csv(QUEUE_PATH)
    p = pd.read_csv(PRED_PATH)
    df = q.merge(p, on='id', how='inner')
    assert len(df) == len(q), "queue/predictions id mismatch"

    normalized = df['human_stance'].apply(normalize_label)
    df['human_norm'] = normalized.apply(lambda t: t[0])
    df['is_list_mention'] = normalized.apply(lambda t: t[1])

    print("=== Raw label distribution ===")
    print(df['human_stance'].value_counts())
    print("\n=== Normalized label distribution ===")
    print(df['human_norm'].value_counts())
    print(f"\nList/link-dump flagged mentions: {df['is_list_mention'].sum()} / {len(df)}")

    print(f"\nNeutral+ambiguous share: {(df['human_norm'].isin(['neutral','ambiguous'])).mean():.1%} "
          "of sampled mentions -- the classifier was never trained to have an opinion on these; "
          "high neutral/ambiguous share is itself a construct-validity signal, separate from accuracy below.")

    binary = df[df['human_norm'].isin(['hostile', 'endorsement'])].copy()
    binary['y_true'] = (binary['human_norm'] == 'endorsement').astype(int)
    binary['y_pred'] = (binary['stance_prob'] >= 0.5).astype(int)

    print(f"\n=== Binary hostile-vs-endorsement scoring (n={len(binary)}, excludes neutral/ambiguous) ===")
    print(classification_report(binary['y_true'], binary['y_pred'], target_names=['hostile', 'endorsement']))
    kappa = cohen_kappa_score(binary['y_true'], binary['y_pred'])
    acc = (binary['y_true'] == binary['y_pred']).mean()
    print(f"Accuracy: {acc:.3f}")
    print(f"Cohen's Kappa (vs. training CV kappa=0.352 for context): {kappa:.3f}")
    print("\nConfusion matrix (rows=true, cols=predicted; 0=hostile, 1=endorsement):")
    print(confusion_matrix(binary['y_true'], binary['y_pred']))

    print("\n=== Accuracy by predicted_bucket stratum ===")
    for bucket in ['hostile', 'borderline', 'endorsing']:
        sub = binary[binary['predicted_bucket'] == bucket]
        if len(sub) == 0:
            continue
        acc_b = (sub['y_true'] == sub['y_pred']).mean()
        print(f"  {bucket}: n={len(sub)}, accuracy={acc_b:.3f}, "
              f"human hostile={sum(sub['y_true']==0)}, human endorse={sum(sub['y_true']==1)}")

    print("\n=== List/link-dump mentions (hypothesized failure mode) ===")
    list_rows = df[df['is_list_mention']]
    if len(list_rows):
        print(list_rows[['id', 'human_stance', 'stance_prob', 'predicted_bucket']].to_string(index=False))
    else:
        print("  None flagged.")

    print("\n=== Worst misses: model far from human label ===")
    binary['error'] = (binary['stance_prob'] - (1 - binary['y_true'])).abs()
    # y_true=0 (hostile) -> model should be near 0; y_true=1 (endorsement) -> near 1
    binary['expected'] = binary['y_true']
    binary['miss'] = (binary['stance_prob'] - binary['expected']).abs()
    worst = binary.sort_values('miss', ascending=False).head(10)
    print(worst[['id', 'human_norm', 'stance_prob', 'predicted_bucket']].to_string(index=False))

    # --- Reviewable file: every row, human-readable, worst misses first ---
    # model_predicted_label mirrors the same >=0.5 threshold used everywhere
    # else in this project (per_entity_stance_breakdown.py etc), so "wrong"
    # here means "wrong under the threshold actually used downstream", not
    # just "far from 0/1".
    df['model_predicted_label'] = np.where(df['stance_prob'] >= 0.5, 'endorsement', 'hostile')
    df['correct'] = np.where(
        df['human_norm'].isin(['hostile', 'endorsement']),
        df['model_predicted_label'] == df['human_norm'],
        np.nan,
    )
    df['miss_magnitude'] = np.where(
        df['human_norm'] == 'hostile', df['stance_prob'],
        np.where(df['human_norm'] == 'endorsement', 1 - df['stance_prob'], np.nan),
    )
    review = df.sort_values('miss_magnitude', ascending=False, na_position='last')[
        ['id', 'full_text', 'human_stance', 'human_norm', 'is_list_mention',
         'stance_prob', 'predicted_bucket', 'model_predicted_label', 'correct', 'notes']
    ]
    review.to_csv(REVIEW_OUT_PATH, index=False)
    print(f"\nSaved full reviewable file (worst misses first) to {REVIEW_OUT_PATH}")
    print(f"  {int((review['correct'] == False).sum())} wrong, {int((review['correct'] == True).sum())} correct, "
          f"{int(review['correct'].isna().sum())} not scored (neutral/ambiguous)")


if __name__ == "__main__":
    main()
