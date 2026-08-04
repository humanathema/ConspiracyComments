import pandas as pd
import numpy as np
from sklearn.metrics import cohen_kappa_score
from itertools import combinations

# Load all 8 predictions
files = [
    'preds_r7v2_baseline.csv', 'preds_r7v2_split.csv',
    'preds_r7v1_baseline.csv', 'preds_r7v1_split.csv',
    'preds_r5v2_baseline.csv', 'preds_r5v2_split.csv',
    'preds_r7v3_baseline.csv', 'preds_r5v3_baseline.csv'
]
preds = {f.replace('preds_', '').replace('.csv', ''): pd.read_csv(f) for f in files}

# Find best ensemble subset
best_kappa = 0
best_subset = None

for r in range(1, 9):
    for combo in combinations(preds.keys(), r):
        votes = np.stack([preds[m]['pred'].values for m in combo], axis=1)
        majority = np.array([np.bincount(row).argmax() for row in votes])
        kappa = cohen_kappa_score(preds[combo[0]]['true'], majority)
        if kappa > best_kappa:
            best_kappa = kappa
            best_subset = combo

print(f"BEST ENSEMBLE: {best_subset}")
print(f"KAPPA: {best_kappa:.4f}")
print(f"N models: {len(best_subset)}")
EOF
