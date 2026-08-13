"""pull_unlabeled_batch_round9.py

Pull next ~50k unlabeled batch for round 9 expansion.
Excludes all rows already in any training parquet under data/processed/.
Uses same entity list as round 8.
"""

import duckdb
import pandas as pd
import numpy as np
from pathlib import Path

EMPATH  = 'data/processed/empath_scores_full_mapped.parquet'
OUTPUT  = 'data/processed/unlabeled_batch_round9.parquet'
TARGET_SIZE  = 50_000
RANDOM_STATE = 43

# All training parquets to dedup against
TRAIN_FILES = list(Path('data/processed').glob('stance_classifier_training_data*.parquet'))

ENTITIES = [
    ('Julian Assange',   "lower(text) LIKE '%assange%'"),
    ('Edward Snowden',   "lower(text) LIKE '%snowden%'"),
    ('Glenn Greenwald',  "lower(text) LIKE '%greenwald%'"),
    ('Aaron Swartz',     "lower(text) LIKE '%swartz%'"),
    ('WikiLeaks',        "lower(text) LIKE '%wikileaks%'"),
    ('Anthony Fauci',    "lower(text) LIKE '%fauci%'"),
    ('Bill Gates',       "lower(text) LIKE '%bill gates%'"),
    ('Alex Jones',       "lower(text) LIKE '%alex jones%' OR lower(text) LIKE '%infowars%'"),
    ('Tucker Carlson',   "lower(text) LIKE '%tucker carlson%'"),
    ('Roger Stone',      "lower(text) LIKE '%roger stone%'"),
    ('Matt Gaetz',       "lower(text) LIKE '%matt gaetz%' OR lower(text) LIKE '%gaetz%'"),
]

print("=== Round 9 Batch Pull ===\n")

con = duckdb.connect()

# Collect all already-trained IDs
trained_ids = set()
for tf in TRAIN_FILES:
    df = pd.read_parquet(tf, columns=['id'])
    trained_ids.update(df['id'].astype(str).tolist())
print(f"Already-trained IDs to exclude: {len(trained_ids):,}")

frames = []
for entity_name, condition in ENTITIES:
    q = f"""
        SELECT id, text, '{entity_name.replace("'", "''")}' AS target_entity
        FROM read_parquet('{EMPATH}')
        WHERE ({condition})
          AND text IS NOT NULL
          AND length(trim(text)) > 30
    """
    df = con.execute(q).df()
    df = df[~df['id'].astype(str).isin(trained_ids)]
    frames.append(df)
    print(f"  {entity_name}: {len(df):,} remaining")

pool = pd.concat(frames, ignore_index=True)
pool = pool.drop_duplicates(subset=['id'])
print(f"\nTotal pool (deduped): {len(pool):,}")

if len(pool) <= TARGET_SIZE:
    batch = pool
    print(f"Pool smaller than target — using all {len(batch):,} rows")
else:
    # Sample balanced across entities
    per_entity = TARGET_SIZE // len(ENTITIES)
    sampled = []
    for entity_name, _ in ENTITIES:
        ent_pool = pool[pool['target_entity'] == entity_name]
        n = min(len(ent_pool), per_entity)
        sampled.append(ent_pool.sample(n=n, random_state=RANDOM_STATE))
    batch = pd.concat(sampled, ignore_index=True)
    # Top up to TARGET_SIZE from remaining if any entity was short
    if len(batch) < TARGET_SIZE:
        used_ids = set(batch['id'])
        remainder = pool[~pool['id'].isin(used_ids)]
        topup = remainder.sample(n=min(TARGET_SIZE - len(batch), len(remainder)), random_state=RANDOM_STATE)
        batch = pd.concat([batch, topup], ignore_index=True)

print(f"\nFinal batch: {len(batch):,} rows")
print(batch['target_entity'].value_counts().to_string())

batch.to_parquet(OUTPUT, index=False)
print(f"\nSaved to {OUTPUT}")
