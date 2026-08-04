"""append_requeue_v2_new_rows.py

Handles the 28 rows from queue_active_learning_requeue_v2.csv that
merge_active_learning_requeue_v2.py correctly skipped as "not found" --
confirmed 2026-08-03 these are genuinely NEW candidate rows, not
corrections to existing ones:
  - 25 from source_file="mined_other_candidates_2026-07-30_hitl_reviewed"
    -- prospective "other"-class candidates from the 2026-07-30 mining
    pass that were human-reviewed for inclusion but never actually
    appended to the training parquet as base rows.
  - 3 from source_file="queue_irr_stance_shared.csv" -- rows from the
    99-row human-human IRR sample that also aren't in the training
    parquet (that queue was for measuring inter-rater agreement, not
    originally meant to feed training directly, but Nash's requeue_v2
    review re-confirmed labels for a few of them, so they're included
    here rather than silently dropped).

Appended (not merged) as new rows: is_human=True, weight=1.0 (matching
every other human-labeled row's convention, confirmed by direct query),
split="train" (deliberately not "val" -- the shared val set must stay
exactly what the bigval rebuild fixed, not grow by whatever happens to
land in an active-learning queue).
"""
import os

import pandas as pd

TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
QUEUE_PATH = "data/hitl/queue_active_learning_requeue_v2.csv"
BACKUP_DIR = "data/processed/active_learning_backups"

LABEL_MAP = {
    "endorsement": "endorsement",
    "hostile": "hostile",
    "neutral": "other",
    "ambiguous": "other",
}


def main():
    df = pd.read_parquet(TRAINING_DATA_PATH)
    queue = pd.read_csv(QUEUE_PATH)

    reviewed = queue[queue["human_stance"].notna() & (queue["human_stance"].astype(str).str.strip() != "")].copy()
    new_rows = reviewed[~reviewed["full_text"].isin(df["text"])].copy()

    if new_rows.empty:
        print("No new (not-already-present) reviewed rows found -- nothing to append.")
        return

    print(f"{len(new_rows)} reviewed rows not already in the training data:")
    print(new_rows["source_file"].value_counts().to_string())

    unmapped = new_rows[~new_rows["human_stance"].isin(LABEL_MAP)]
    if not unmapped.empty:
        print(f"\nWARNING: {len(unmapped)} rows have an unrecognized human_stance value, dropping them:")
        print(unmapped[["full_text", "human_stance"]].to_string())
        new_rows = new_rows[new_rows["human_stance"].isin(LABEL_MAP)]

    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_path = os.path.join(BACKUP_DIR, f"stance_classifier_training_data_pre_requeue_v2_append_{pd.Timestamp.now():%Y%m%d_%H%M%S}.parquet")
    df.to_parquet(backup_path, index=False)
    print(f"\nBacked up pre-append training data to {backup_path}")

    to_add = pd.DataFrame({
        "text": new_rows["full_text"].values,
        "label": new_rows["human_stance"].map(LABEL_MAP).values,
        "raw_label": new_rows["human_stance"].values,
        "source_file": new_rows["source_file"].values,
        "target_entity": new_rows["target_entity"].values,
        "entity_spans": new_rows["entity_spans"].values,
        "label_target_std": None,
        "label_agreement_level": None,
        "weight": 1.0,
        "is_human": True,
        "split": "train",
        "label_notes": new_rows["notes"].fillna("").values,
    })

    before = len(df)
    df = pd.concat([df, to_add], ignore_index=True)
    df.to_parquet(TRAINING_DATA_PATH, index=False)

    print(f"\nAppended {len(to_add)} new rows ({before:,} -> {len(df):,}).")
    print(f"Saved updated training data to {TRAINING_DATA_PATH}")


if __name__ == "__main__":
    main()
