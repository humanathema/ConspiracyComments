"""pull_unlabeled_batch_r8_clean.py

Clean Round 8 unlabeled batch pull — text-based entity matching on empath_scores.

Fixes the missing target_entity column from the earlier broken pull.

Strategy:
1. Scan empath_scores_full_mapped (21M rows, local) for text mentions of each
   target entity. Assign canonical target_entity per row (longest match wins).
2. Dedup against stance_classifier_training_data (text-based).
3. Sample 25k balanced across entities.
4. Save with id, text, target_entity columns.

Avoids CDC/WHO because both are ambiguous pronouns ('who', 'cdc' as abbrev).
Runs locally with DuckDB (~20s scan on the 3.4GB file).
"""

import duckdb
import pandas as pd
import numpy as np
from pathlib import Path

EMPATH  = 'data/processed/empath_scores_full_mapped.parquet'
TRAIN   = 'data/processed/stance_classifier_training_data.parquet'
OUTPUT  = 'data/processed/unlabeled_batch_r8_clean.parquet'

TARGET_SIZE  = 25_000
RANDOM_STATE = 42

# Entity patterns: (canonical_name, sql_condition_using_text_lower)
# Order: most specific first (avoids assigning 'Bill Gates' when text says 'Julian Assange gates prison')
ENTITIES = [
    ('Julian Assange',   "lower(text) LIKE '%assange%'"),
    ('Edward Snowden',   "lower(text) LIKE '%snowden%'"),
    ('Glenn Greenwald',  "lower(text) LIKE '%greenwald%'"),
    ('Aaron Swartz',     "lower(text) LIKE '%swartz%' AND lower(text) NOT LIKE '%swartz %' OR lower(text) LIKE '%aaron swartz%'"),
    ('WikiLeaks',        "lower(text) LIKE '%wikileaks%'"),
    ('Anthony Fauci',    "lower(text) LIKE '%fauci%'"),
    ('Bill Gates',       "lower(text) LIKE '%bill gates%'"),
    ('Alex Jones',       "lower(text) LIKE '%alex jones%' OR lower(text) LIKE '%infowars%'"),
    ('Tucker Carlson',   "lower(text) LIKE '%tucker carlson%'"),
    ('Roger Stone',      "lower(text) LIKE '%roger stone%'"),
    ('Matt Gaetz',       "lower(text) LIKE '%matt gaetz%' OR lower(text) LIKE '%gaetz%'"),
]

print("=== Round 8 Clean Batch Pull ===\n")
print(f"Source: {EMPATH}")

con = duckdb.connect()

# ── Step 1: Extract entity-matched rows via SQL ────────────────────────────
print("\nScanning empath_scores for entity mentions...")
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
    print(f"  {entity_name}: {len(df):,} rows")
    frames.append(df)

all_matches = pd.concat(frames, ignore_index=True)
print(f"\nTotal rows before dedup: {len(all_matches):,}")

# Keep only one entity per comment_id (first entity in ENTITIES list wins,
# so more-specific entities take priority over general ones)
all_matches = all_matches.drop_duplicates('id', keep='first').reset_index(drop=True)
print(f"After per-id dedup: {len(all_matches):,} unique comments")

# ── Step 2: Text-based dedup against training data ─────────────────────────
print("\nDeduplicating against training data...")
train = pd.read_parquet(TRAIN, columns=['text'])
train_texts = set(train['text'].dropna().str.strip())
print(f"  Training texts: {len(train_texts):,}")

pre = len(all_matches)
all_matches = all_matches[~all_matches['text'].str.strip().isin(train_texts)].copy()
print(f"  Removed {pre - len(all_matches):,} overlap rows")
print(f"  Remaining: {len(all_matches):,}")

print("\nCandidate pool entity distribution:")
print(all_matches['target_entity'].value_counts().to_string())

# ── Step 3: Stratified sample (cap per entity, total 25k) ─────────────────
print(f"\nSampling {TARGET_SIZE:,} rows...")
entity_counts = all_matches['target_entity'].value_counts()
n_entities = len(entity_counts)
# Start with equal share; boost smaller entities up to their count
per_entity_cap = max(TARGET_SIZE // n_entities, 500)

sampled = []
for entity, count in entity_counts.items():
    n = min(count, per_entity_cap)
    sub = all_matches[all_matches['target_entity'] == entity].sample(
        n=n, random_state=RANDOM_STATE)
    sampled.append(sub)

batch = pd.concat(sampled, ignore_index=True)

# If under target, fill remainder randomly from leftover
if len(batch) < TARGET_SIZE:
    already = set(batch['id'])
    leftover = all_matches[~all_matches['id'].isin(already)]
    need = TARGET_SIZE - len(batch)
    if len(leftover) >= need:
        extra = leftover.sample(n=need, random_state=RANDOM_STATE)
        batch = pd.concat([batch, extra], ignore_index=True)

# Final shuffle
batch = batch.sample(frac=1, random_state=RANDOM_STATE).reset_index(drop=True)

print(f"\nFinal batch: {len(batch):,} rows")
print("\nFinal entity distribution:")
print(batch['target_entity'].value_counts().to_string())

# ── Step 4: Save ───────────────────────────────────────────────────────────
batch = batch[['id', 'text', 'target_entity']].copy()
batch.to_parquet(OUTPUT, index=False)
print(f"\n✓ Saved to {OUTPUT}")
print("\nNext step: score with ensemble (src/score_batch_with_ensemble_round8.py)")
print("          or push to Kaggle for GPU scoring")
