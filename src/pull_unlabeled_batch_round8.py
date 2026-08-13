"""pull_unlabeled_batch_round8.py

Pull ~25k unlabeled rows from canonical corpus (research_corpus_staged_scores_full21m
+ empath_scores_full_mapped) that mention target entities, deduped against existing
training data.

This is Step 1 of the progressive distillation cascade:
- Pull raw unlabeled batch mentioning target entities
- Deduplicate against stance_classifier_training_data.parquet
- Score with 0.5773 ensemble (Step 2)
- Escalate uncertain rows to frontier judge (Step 3)
- Merge frontier labels + retrain Round 8 (Step 4)

Input: research_corpus_staged_scores_full21m.parquet (Kaggle)
       empath_scores_full_mapped.parquet (Kaggle)
       stance_classifier_training_data.parquet (local, for dedup)
Output: unlabeled_batch_round8.parquet (~25k rows, no overlap with training data)
"""
import pandas as pd
import numpy as np
import duckdb
from pathlib import Path

# Target entities
TARGET_ENTITIES = [
    'assange', 'snowden', 'greenwald', 'swartz', 'wikileaks',  # whistleblowers
    'fauci', 'gates', 'cdc', 'who',  # consensus experts
    'jones', 'carlson', 'stone', 'gaetz'  # mavericks
]

print("=== Round 8 Expansion: Pull Unlabeled Batch ===\n")

# Load existing training data to get IDs to skip
train_path = Path('data/processed/stance_classifier_training_data.parquet')
if train_path.exists():
    print("Loading training data for dedup...")
    train_data = pd.read_parquet(train_path, columns=['text'])
    train_ids = set(train_data.index)  # or whatever ID column it uses
    print(f"  Training data: {len(train_data)} rows")
else:
    train_ids = set()
    print("  Training data not found, proceeding without dedup")

# The canonical corpus files are on Kaggle, so we need to check if they're available locally
staged_path = Path('data/processed/research_corpus_staged_scores_full21m.parquet')
empath_path = Path('data/processed/empath_scores_full_mapped.parquet')

if not staged_path.exists() or not empath_path.exists():
    print("\n⚠️  Canonical corpus files not found locally:")
    print(f"   - research_corpus_staged_scores_full21m.parquet: {staged_path.exists()}")
    print(f"   - empath_scores_full_mapped.parquet: {empath_path.exists()}")
    print("\nThese files live on Kaggle in tobiasnashws/conspiracycomments-derived-tier2")
    print("Pull them with:")
    print("  kaggle datasets download tobiasnashws/conspiracycomments-derived-tier2 \\")
    print("    -f research_corpus_staged_scores_full21m.parquet -p data/processed/")
    print("  kaggle datasets download tobiasnashws/conspiracycomments-derived-tier2 \\")
    print("    -f empath_scores_full_mapped.parquet -p data/processed/")
    exit(1)

print("Loading canonical corpus files...")
staged = pd.read_parquet(staged_path)
empath = pd.read_parquet(empath_path)
print(f"  Staged scores: {len(staged)} rows")
print(f"  Empath (text): {len(empath)} rows")

# Join on id
print("\nJoining staged + empath on id...")
corpus = staged.merge(empath[['id', 'text']], on='id', how='inner')
print(f"  Joined: {len(corpus)} rows")

# Filter to rows mentioning target entities
print(f"\nFiltering to rows mentioning target entities: {', '.join(TARGET_ENTITIES)}")

def mentions_target(text, entities=TARGET_ENTITIES):
    if pd.isna(text):
        return False
    text_lower = str(text).lower()
    return any(entity in text_lower for entity in entities)

corpus['mentions_target'] = corpus['text'].apply(mentions_target)
with_targets = corpus[corpus['mentions_target']].copy()
print(f"  Rows mentioning targets: {len(with_targets):,}")

# Deduplicate against training data
# Assuming 'id' column exists in both
if 'id' in with_targets.columns and len(train_ids) > 0:
    print(f"\nDeduplicating against training data ({len(train_ids)} rows)...")
    unlabeled = with_targets[~with_targets['id'].isin(train_ids)].copy()
    removed = len(with_targets) - len(unlabeled)
    print(f"  Removed {removed} rows already in training data")
    print(f"  Remaining: {len(unlabeled):,} unlabeled rows")
else:
    unlabeled = with_targets.copy()
    print("\nNo dedup (id column or training data not available)")

# Sample up to 25k
if len(unlabeled) > 25000:
    batch = unlabeled.sample(n=25000, random_state=42)
    print(f"\nSampled 25,000 rows from {len(unlabeled):,}")
else:
    batch = unlabeled
    print(f"\nUsing all {len(batch):,} available rows (less than 25k)")

# Keep minimal columns for ensemble scoring
batch = batch[['id', 'text', 'target_entity' if 'target_entity' in batch.columns else 'id']].copy()
if 'target_entity' not in batch.columns:
    batch['target_entity'] = batch['text'].apply(
        lambda x: next((e for e in TARGET_ENTITIES if e in str(x).lower()), None)
    )

# Save
output_path = 'data/processed/unlabeled_batch_round8.parquet'
batch.to_parquet(output_path, index=False)

print(f"\n✓ Saved {len(batch):,} rows to {output_path}")
print(f"\nNext step: src/score_batch_with_ensemble_round8.py")
