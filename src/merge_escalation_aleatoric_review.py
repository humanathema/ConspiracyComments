"""merge_escalation_aleatoric_review.py

Merges rated rows from data/hitl/queue_escalation_aleatoric_review.csv
(the 39 aleatoric + 29 no-context rows built 2026-08-03 -- boundary-
confidence predictions where thread context either didn't help or
wasn't available, so they went straight to direct human review per the
original escalation-ladder design, never further automated) into
stance_classifier_training_data.parquet.

NOT the same file as merge_escalation_review_corrections.py, which
targets the older, already-merged queue_escalation_human_review.csv
(74 rows, 2026-08-01 batch, confirmed already applied -- see the
matching stance_classifier_training_data_pre_escalation_merge_20260801_231201.parquet
backup). That queue's schema (comment_id, dist_to_boundary, p_has_stance,
context_text, ...) is also different from this one's
(current_label/predicted_label/parent_text) -- confirmed by direct
column comparison, 2026-08-03, not assumed. Same merge conventions
otherwise: exact-text match, 5-way->3-way label collapse, backup before
write.
"""
import os

import pandas as pd

TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
QUEUE_PATH = "data/hitl/queue_escalation_aleatoric_review.csv"
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
    backup_path = os.path.join(BACKUP_DIR, f"stance_classifier_training_data_pre_aleatoric_merge_{pd.Timestamp.now():%Y%m%d_%H%M%S}.parquet")
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
        note = f"escalation_aleatoric verdict={row.get('verdict', '')}; " + str(row.get("notes", "") or "")
        df.loc[idx, "label_notes"] = note
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
