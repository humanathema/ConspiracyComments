"""merge_frontier_scores_and_measure_cascade.py

Merges frontier scores into ensemble predictions and measures final cascaded kappa.

Steps:
1. Load ensemble predictions and frontier scores
2. For rows that were escalated (margin < 0.35), replace ensemble label with frontier score
3. Measure final kappa with merged labels
4. Compare to baseline (0.5311) and prior single-model best (0.4840)

Input: preds_*.csv, escalation_candidates_for_frontier.csv, escalation_cascade_frontier_scored.csv
Output: Final kappa metrics
"""
import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

# Load ensemble predictions (best 5-model subset)
models = {}
file_names = [
    'preds_r7v2_split.csv', 'preds_r7v1_baseline.csv',
    'preds_r5v2_baseline.csv', 'preds_r5v2_split.csv', 'preds_r7v3_baseline.csv'
]
model_names = []
for f in file_names:
    name = f.replace('preds_', '').replace('.csv', '')
    models[name] = pd.read_csv(f)
    model_names.append(name)

# Build majority-vote ensemble from best 5-model subset
votes = np.stack([models[name]['pred'].values for name in model_names], axis=1)
majority_votes = np.array([np.bincount(row).argmax() for row in votes])

true_labels = models[model_names[0]]['true'].values

# Load escalation candidates and frontier scores
candidates = pd.read_csv('escalation_candidates_for_frontier.csv')
frontier_scores = pd.read_csv('escalation_cascade_frontier_scored.csv')

print(f"Ensemble baseline kappa: {cohen_kappa_score(true_labels, majority_votes):.4f}")
print(f"Frontier scores retrieved: {len(frontier_scores)}")
print(f"Escalation candidates: {len(candidates)}")
print()

# Convert frontier scores (-1 to +1) to labels
# Assume frontier judge returns -1 or lower for hostile, +1 or higher for endorsement, 0 for balanced/other
def frontier_score_to_label(score):
    if pd.isna(score):
        return 2  # other (no score)
    if score < -0.5:
        return 0  # hostile
    elif score > 0.5:
        return 1  # endorsement
    else:
        return 2  # other/balanced

frontier_labels = frontier_scores['frontier_score'].map(frontier_score_to_label)

# Merge frontier scores into ensemble predictions
# For escalated rows (those in the frontier_scores), replace ensemble label with frontier label
merged_preds = majority_votes.copy()
frontier_row_idxs = frontier_scores['row_idx'].values

for i, row_idx in enumerate(frontier_row_idxs):
    if i < len(frontier_labels):
        merged_preds[int(row_idx)] = frontier_labels.iloc[i]

# Measure cascaded kappa
cascaded_kappa = cohen_kappa_score(true_labels, merged_preds)

# Compare corrections
corrected_rows = merged_preds != majority_votes
n_corrected = corrected_rows.sum()

print(f"Frontier-corrected rows: {n_corrected}/{len(cascaded_kappa.shape) if hasattr(cascaded_kappa, 'shape') else len(merged_preds)}")
print()
print("=== FINAL RESULTS ===")
print(f"Ensemble baseline (no escalation): {cohen_kappa_score(true_labels, majority_votes):.4f}")
print(f"Ensemble + frontier cascade:       {cascaded_kappa:.4f}")
print(f"Improvement:                       {cascaded_kappa - cohen_kappa_score(true_labels, majority_votes):+.4f}")
print()

# Show label distribution before/after
print("Label distribution changes:")
ensemble_dist = np.bincount(majority_votes, minlength=3)
cascaded_dist = np.bincount(merged_preds, minlength=3)
labels_str = ["hostile", "endorsement", "other"]
for i, label in enumerate(labels_str):
    print(f"  {label}: {ensemble_dist[i]} → {cascaded_dist[i]} ({cascaded_dist[i]-ensemble_dist[i]:+d})")
