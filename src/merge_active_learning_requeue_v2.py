"""merge_active_learning_requeue_v2.py

Merges rated rows from data/hitl/queue_active_learning_requeue_v2.csv
back into the real training data (stance_classifier_training_data.parquet).
Adapted from merge_active_learning_corrections.py (same conventions:
exact-text match, 5-way->3-way label collapse, backup before write) --
a separate script rather than reparameterizing the original, matching
this project's established per-round pattern (merge_boundary_expansion_
round{3,4,5}.py, merge_random_expansion_round6.py, etc.).

Why a new file instead of pointing the original at the new queue: v2 was
rebuilt against the current models (round5-bigval) with a different tier
structure (tier1/tier2/tier3-boundary, see build_active_learning_requeue.py)
and 22/150 rows never got an `id` recovered via text-match against the
raw corpus (confirmed 2026-08-03) -- those rows are left with human_stance
still blank (structurally unratable, not skipped), so they're excluded by
the same notna() filter as any other not-yet-reviewed row, no special
handling needed here.

No `wrong_match` values observed in this queue's human_stance column
(checked directly, 2026-08-03) -- LABEL_MAP omits the drop-row branch
the v1 script has, since it's not needed here. If a future rerun of this
queue-builder ever produces one, this script will just warn on an
unrecognized value rather than silently dropping it -- safer default.
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
    if reviewed.empty:
        print("No reviewed rows in the queue yet -- nothing to merge.")
        return

    print(f"{len(reviewed)} / {len(queue)} queue rows have been reviewed.")

    if "label_notes" not in df.columns:
        df["label_notes"] = None

    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_path = os.path.join(BACKUP_DIR, f"stance_classifier_training_data_pre_requeue_v2_merge_{pd.Timestamp.now():%Y%m%d_%H%M%S}.parquet")
    df.to_parquet(backup_path, index=False)
    print(f"Backed up pre-merge training data to {backup_path}")

    n_changed = 0
    n_confirmed = 0
    n_not_found = 0
    n_unmapped = 0
    for _, row in reviewed.iterrows():
        match = df["text"] == row["full_text"]
        if not match.any():
            n_not_found += 1
            continue
        idx = df[match].index
        raw_new = row["human_stance"]

        if raw_new not in LABEL_MAP:
            n_unmapped += 1
            print(f"  WARNING: unrecognized human_stance value {raw_new!r}, skipping row (not applied)")
            continue

        old_label = df.loc[idx, "label"].iloc[0]
        new_label = LABEL_MAP[raw_new]
        df.loc[idx, "label"] = new_label
        df.loc[idx, "raw_label"] = raw_new
        df.loc[idx, "label_notes"] = row.get("notes", "")
        if new_label != old_label:
            n_changed += 1
        else:
            n_confirmed += 1

    print(f"\nApplied: {n_changed} label changes, {n_confirmed} confirmations (label unchanged, now marked reviewed)")
    if n_unmapped:
        print(f"WARNING: {n_unmapped} rows had an unrecognized human_stance value -- not applied, check manually")
    if n_not_found:
        print(f"WARNING: {n_not_found} reviewed rows had no exact text match in the training data -- not applied, check manually")

    df.to_parquet(TRAINING_DATA_PATH, index=False)
    print(f"\nSaved updated training data to {TRAINING_DATA_PATH}")


if __name__ == "__main__":
    main()
