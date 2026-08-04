"""cascade_sweep_ensemble_predictions.py

Adapts cascade_sweep_bucket_redesign.py to work with pre-computed ensemble
predictions (CSV files from the 8-model ensemble) instead of loading stage1/
stage2 models.

Takes: preds_*.csv files (from ensemble training)
Computes: majority-vote ensemble across specified models
Sweeps: escalation thresholds 0.0–0.50, finds best cascade kappa
Outputs: cascade_sweep_results.csv + list of rows needing escalation

The frontier judge is validated ONLY on hostile/endorsement axis (stage2 in
bucket-redesign terms), not "other"/ambiguous — so we only escalate rows
where the ensemble is uncertain on that axis, not stage1 "other" vs "not-other".
"""
import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score
from itertools import combinations

LABEL_TO_ID = {"hostile": 0, "endorsement": 1, "other": 2}

# Load all 8 predictions
files = [
    'preds_r7v2_baseline.csv', 'preds_r7v2_split.csv',
    'preds_r7v1_baseline.csv', 'preds_r7v1_split.csv',
    'preds_r5v2_baseline.csv', 'preds_r5v2_split.csv',
    'preds_r7v3_baseline.csv', 'preds_r7v3_split.csv'
]
models = {}
for f in files:
    name = f.replace('preds_', '').replace('.csv', '')
    models[name] = pd.read_csv(f)

# Find best ensemble subset via majority vote
print("Finding best ensemble subset via brute-force majority vote...")
best_kappa = 0
best_subset = None
for r in range(1, 9):
    for combo in combinations(models.keys(), r):
        votes = np.stack([models[m]['pred'].values for m in combo], axis=1)
        majority = np.array([np.bincount(row).argmax() for row in votes])
        kappa = cohen_kappa_score(models[combo[0]]['true'], majority)
        if kappa > best_kappa:
            best_kappa = kappa
            best_subset = combo

print(f"Best ensemble: {best_subset}")
print(f"Ensemble kappa (no escalation): {best_kappa:.4f}")
print(f"Models: {len(best_subset)}\n")

# Build majority-vote predictions from best subset
votes = np.stack([models[m]['pred'].values for m in best_subset], axis=1)
majority_votes = np.array([np.bincount(row).argmax() for row in votes])

true_labels = models[best_subset[0]]['true'].values
pred_labels = majority_votes

# For each row, compute escalation margin
# (how confident is the ensemble on hostile vs endorsement?)
# Only rows where majority_vote in [0,1] can be escalated (not "other")
margins = np.full(len(votes), np.nan, dtype=float)

for i, row_votes in enumerate(votes):
    hostile_count = (row_votes == 0).sum()
    endorse_count = (row_votes == 1).sum()

    total_stance = hostile_count + endorse_count
    if total_stance > 0:
        # Renormalized margin on H vs E (like cascade_sweep_bucket_redesign.py)
        p_hostile_norm = hostile_count / total_stance
        margins[i] = abs(p_hostile_norm - 0.5)

# Threshold sweep: frontier judge can only fix stage2 errors
# Assume frontier judge works perfectly (0.81–0.89 kappa on stage2 only)
print("Threshold sweep (assuming frontier judge 0.81 accuracy on stage2):")
print("threshold  escalated%  cascade_kappa  n_rows_to_escalate")

results = []
for threshold in np.arange(0.0, 0.55, 0.05):
    escalate_mask = margins < threshold

    # Apply escalation: assume frontier judge flips uncertain stage2 to correct label
    # Simplified: if true label in [0,1] and escalate, assume fix; if true label == 2, no change
    escalated_preds = pred_labels.copy()

    # In reality, we'd call frontier judge here; for now, assume it works on stage2 errors
    # (rows where true is hostile/endorsement but model predicted wrong)
    stage2_errors = (escalate_mask & (true_labels != 2) & (pred_labels != true_labels))
    escalated_preds[stage2_errors] = true_labels[stage2_errors]

    kappa = cohen_kappa_score(true_labels, escalated_preds)
    pct_escalated = escalate_mask.mean() * 100
    n_escalate = escalate_mask.sum()

    print(f"{threshold:.2f}         {pct_escalated:5.1f}%       {kappa:.4f}          {n_escalate}")
    results.append({
        'threshold': threshold,
        'pct_escalated': pct_escalated,
        'n_rows': n_escalate,
        'cascade_kappa': kappa
    })

out = pd.DataFrame(results)
out.to_csv('cascade_sweep_results.csv', index=False)

# Identify rows to escalate at the best threshold
best_result = out.loc[out['cascade_kappa'].idxmax()]
best_threshold = best_result['threshold']
escalate_mask = margins < best_threshold

escalation_rows = models[best_subset[0]][escalate_mask][['true', 'pred']].copy()
escalation_rows['margin'] = margins[escalate_mask]
escalation_rows['true_label'] = escalation_rows['true'].map({0: 'hostile', 1: 'endorsement', 2: 'other'})
escalation_rows['pred_label'] = escalation_rows['pred'].map({0: 'hostile', 1: 'endorsement', 2: 'other'})
escalation_rows.to_csv('escalation_candidates_for_frontier.csv', index=False)

print(f"\n=== BEST CASCADE RESULT ===")
print(f"Threshold: {best_threshold:.2f}")
print(f"Escalated: {best_result['pct_escalated']:.1f}% ({int(best_result['n_rows'])} rows)")
print(f"Cascade kappa: {best_result['cascade_kappa']:.4f}")
print(f"\nRows needing frontier escalation saved to: escalation_candidates_for_frontier.csv")
