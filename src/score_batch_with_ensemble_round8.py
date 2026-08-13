"""score_batch_with_ensemble_round8.py

Score unlabeled batch with 0.5773 ensemble (5-model majority vote).
Filter to uncertain rows (margin < 0.45) for frontier escalation.

This is Step 2 of the progressive distillation cascade:
- Load unlabeled batch (from pull_unlabeled_batch_round8.py)
- Load the 5 ModernBERT models used in the 0.5773 ensemble
- Score each model, compute majority vote + margin
- Filter uncertain rows (margin < 0.45)
- Save for frontier escalation

Input: unlabeled_batch_round8.parquet (~25k rows)
       preds_r7v2_split.csv, preds_r7v1_baseline.csv, etc. (validation predictions)
Output: batch_ensemble_scores_round8.parquet (~25k rows with scores + margins)
        batch_escalation_candidates_round8.csv (~2.5-5k uncertain rows)
"""
import pandas as pd
import numpy as np
from pathlib import Path

print("=== Step 2: Score Batch with 0.5773 Ensemble ===\n")

# Load unlabeled batch
batch_path = Path('data/processed/unlabeled_batch_round8.parquet')
if not batch_path.exists():
    print(f"Error: {batch_path} not found")
    print("Run pull_unlabeled_batch_round8.py first")
    exit(1)

print("Loading unlabeled batch...")
batch = pd.read_parquet(batch_path)
print(f"  Loaded {len(batch):,} rows")

# The 5-model ensemble from validation is:
# r7v2_split, r7v1_baseline, r5v2_baseline, r5v2_split, r7v3_baseline
# But we need to train these models on the full training data, not just validation

print("\nNote: This step requires training the 5 models on full training data")
print("(not using validation predictions from preds_*.csv)")
print("\nFor now, placeholder: assuming models are trained and predictions are available")
print("\nTODO: Train 5-model ensemble on stance_classifier_training_data.parquet")
print("      Then score batch with trained models")

# Once models are trained, the process would be:
# 1. Load trained models
# 2. Score batch rows
# 3. Compute majority vote for each row
# 4. Calculate margin (distance from 50/50 split on top-2 predictions)
# 5. Filter rows with margin < 0.45
# 6. Save escalation set

print("\n⚠️  Next step depends on trained Round 8 models")
print("   See Round 8 full pipeline docs for model training details")
