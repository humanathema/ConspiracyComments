"""merge_escalation_review_corrections.py

Merges rated rows from data/hitl/queue_escalation_human_review.csv (the
45 aleatoric + 29 no-context rows from the escalation ladder -- boundary-
confidence classifier predictions that either didn't resolve with real
thread context, or had no context available at all, so were routed
straight to Nash for direct review instead of further automated
escalation) back into stance_classifier_training_data.parquet.

Same conventions as merge_active_learning_corrections.py: matched by
exact text (training parquet has no id column), 5-way human_stance
collapsed to the production 3-way scheme (raw 5-way only ever lives in
raw_label), backed up before writing.

Note: this queue's taxonomy has no wrong_match option (these rows came
from already-disambiguated human-labeled training data, not fresh entity
extraction), so LABEL_MAP here only needs the neutral/ambiguous -> other
collapse.
"""
import os

import pandas as pd

TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
QUEUE_PATH = "data/hitl/queue_escalation_human_review.csv"
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
    backup_path = os.path.join(BACKUP_DIR, f"stance_classifier_training_data_pre_escalation_merge_{pd.Timestamp.now():%Y%m%d_%H%M%S}.parquet")
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
        note = f"escalation_review verdict={row.get('verdict', '')}; " + str(row.get("notes", "") or "")
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
