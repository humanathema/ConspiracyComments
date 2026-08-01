"""merge_boundary_expansion_round3.py

Merges the 4,998 frontier-scored boundary-confidence rows
(score_boundary_candidates_vertex.py, gemini-3.5-flash via Vertex AI,
round2-model-targeted selection) into stance_classifier_training_data.parquet
as new TRAIN-only rows -- val stays untouched so round 3's kappa is a
clean, directly comparable number against round2 (0.4922).

Labels are thresholded from the continuous frontier_score at 0.0
(>=0 -> endorsement, <0 -> hostile), same convention as every other
frontier-judge-to-label conversion tonight. Text is the real full
comment (these rows came from a genuine corpus join, not a windowed
snippet -- unlike the existing AI-silver rows), so these are closer in
kind to human-labeled rows than to the windowed AI-silver ones.

Weight: 0.75, a deliberate middle ground -- higher than the existing
AI-silver weight (0.5, that source's judge had only 33-36% agreement
with the classifier) since the frontier judge scored kappa=0.8266 on
truly held-out val tonight, but not full human weight (1.0) since it's
still a single automated pass, not multi-rater-verified. A judgment
call, not a principled derivation -- flagged here rather than silently
picked.

Input: data/processed/boundary_candidates_frontier_scored.parquet
Output: overwrites data/processed/stance_classifier_training_data.parquet
  (backed up first, same convention as every other merge tonight)
"""
import os

import pandas as pd

TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
SCORED_PATH = "data/processed/boundary_candidates_frontier_scored.parquet"
BACKUP_DIR = "data/processed/active_learning_backups"
NEW_WEIGHT = 0.75


def main():
    df = pd.read_parquet(TRAINING_DATA_PATH)
    scored = pd.read_parquet(SCORED_PATH)
    valid = scored[scored["frontier_score"].notna()].copy()
    print(f"{len(valid)}/{len(scored)} boundary rows have a valid frontier score", flush=True)

    # skip anything whose exact text is already in the training set (shouldn't
    # happen given these were selected as UNLABELED candidates, but check
    # anyway -- cheap insurance against accidental duplication)
    existing_texts = set(df["text"])
    valid = valid[~valid["text"].isin(existing_texts)]
    print(f"{len(valid)} rows are genuinely new (not already in training data)", flush=True)

    valid["label"] = valid["frontier_score"].apply(lambda s: "endorsement" if s >= 0 else "hostile")

    new_rows = pd.DataFrame({
        "text": valid["text"],
        "label": valid["label"],
        "raw_label": valid["label"],
        "source_file": "frontier_boundary_expansion_20260802",
        "target_entity": valid["entity_key"],
        "entity_spans": None,
        "label_target_std": None,
        "label_agreement_level": None,
        "weight": NEW_WEIGHT,
        "is_human": False,
        "split": "train",
        "label_notes": valid["frontier_score"].apply(lambda s: f"frontier_score={s:.2f}"),
    })

    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_path = os.path.join(BACKUP_DIR, f"stance_classifier_training_data_pre_round3_merge_{pd.Timestamp.now():%Y%m%d_%H%M%S}.parquet")
    df.to_parquet(backup_path, index=False)
    print(f"Backed up pre-merge training data to {backup_path}", flush=True)

    out = pd.concat([df, new_rows], ignore_index=True)
    out.to_parquet(TRAINING_DATA_PATH, index=False)

    print(f"\nBefore: {len(df):,} rows ({(df.split=='train').sum():,} train / {(df.split=='val').sum():,} val)", flush=True)
    print(f"After:  {len(out):,} rows ({(out.split=='train').sum():,} train / {(out.split=='val').sum():,} val)", flush=True)
    print(f"Added {len(new_rows):,} new train rows: {new_rows['label'].value_counts().to_dict()}", flush=True)


if __name__ == "__main__":
    main()
