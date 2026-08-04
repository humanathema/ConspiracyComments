import pandas as pd
import numpy as np
from sklearn.metrics import cohen_kappa_score
from itertools import combinations
import glob

# Automatically find all prediction files in the folder
files = glob.glob('preds_*.csv')

if not files:
    print("Error: No 'preds_*.csv' files found in this directory.")
    exit()

print(f"Found {len(files)} prediction files...")

preds = {f.replace('preds_', '').replace('.csv', ''): pd.read_csv(f) for f in files}

# Find best ensemble subset
best_kappa = 0
best_subset = None

for r in range(1, len(preds) + 1):
    for combo in combinations(preds.keys(), r):
        votes = np.stack([preds[m]['pred'].values for m in combo], axis=1)
        majority = np.array([np.bincount(row).argmax() for row in votes])
        # Using the 'true' column from the first file in the combo as ground truth
        kappa = cohen_kappa_score(preds[combo[0]]['true'], majority)
        if kappa > best_kappa:
            best_kappa = kappa
            best_subset = combo

print(f"\nBEST ENSEMBLE: {best_subset}")
print(f"KAPPA: {best_kappa:.4f}")
print(f"N models: {len(best_subset)}")
