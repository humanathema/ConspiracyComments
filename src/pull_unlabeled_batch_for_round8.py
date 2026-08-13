"""pull_unlabeled_batch_for_round8.py

Pull ~25,000 unlabeled rows from the corpus that mention target entities.
These rows have NO existing stance label and will be scored by the ensemble,
then escalated to frontier judge for hard cases only.

Input: Full corpus (parquet files)
       Target entities list
Output: unlabeled_batch_round8_raw.parquet
"""
import pandas as pd
import numpy as np
from pathlib import Path
import duckdb

# Target entities to search for
TARGET_ENTITIES = [
    'assange', 'snowden', 'greenwald', 'swartz', 'wikileaks',  # whistleblowers
    'fauci', 'gates', 'cdc', 'who', 'biden',  # consensus experts
    'jones', 'carlson', 'stone', 'gaetz', 'trump'  # mavericks/media
]

# Load the corpus
corpus_path = Path('data/processed/research_corpus_enriched.parquet')
if not corpus_path.exists():
    print(f"Corpus file not found: {corpus_path}")
    exit(1)

print("Loading corpus...")
corpus = pd.read_parquet(corpus_path)
print(f"Total rows: {len(corpus)}")

# Filter to rows with NO existing stance label (unlabeled)
unlabeled = corpus[corpus['stance_label'].isna() | (corpus['stance_label'] == 'unknown')].copy()
print(f"Unlabeled rows: {len(unlabeled)}")

# Further filter to rows mentioning at least one target entity
def mentions_target(text, entities=TARGET_ENTITIES):
    if pd.isna(text):
        return False
    text_lower = str(text).lower()
    return any(entity in text_lower for entity in entities)

print("Filtering to rows mentioning target entities...")
with_targets = unlabeled[unlabeled['text'].apply(mentions_target)].copy()
print(f"Unlabeled rows with target entities: {len(with_targets)}")

# Sample up to 25,000
if len(with_targets) > 25000:
    batch = with_targets.sample(n=25000, random_state=42)
    print(f"Sampled 25,000 rows")
else:
    batch = with_targets
    print(f"Using all {len(batch)} available rows")

# Keep only necessary columns for ensemble scoring
batch = batch[['id', 'text', 'target_entity', 'subreddit', 'score', 'created_utc']].copy()

# Save
output_path = 'data/processed/unlabeled_batch_round8_raw.parquet'
batch.to_parquet(output_path, index=False)
print(f"\nSaved {len(batch)} rows to {output_path}")
print(f"\nBatch summary:")
print(f"  Rows: {len(batch)}")
print(f"  Unique entities: {batch['target_entity'].nunique()}")
print(f"  Subreddits: {batch['subreddit'].nunique()}")
