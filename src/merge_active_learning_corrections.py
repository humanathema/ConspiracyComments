"""merge_active_learning_corrections.py

Merges rated rows from data/hitl/queue_active_learning_requeue.csv back
into the real training data (data/processed/stance_classifier_training_data.parquet),
then regenerates the requeue against whatever model is current so the
next batch reflects what's actually still uncertain.

Matched by exact text (the training parquet has no id column -- see
build_stance_classifier_training_data.py's own docstring on why; text is
unique per row in practice, same matching convention already used by
augment_training_data_with_mined_other.py).

A row only counts as "rated" if human_stance is non-empty AND differs
from the model's flagged current_label OR the rater left a note -- an
empty/unedited row (rater hasn't gotten to it yet, or agreed with the
current label and skipped it) is left untouched.

Confirming-the-current-label counts as a real decision too, not just
changing it -- so this script treats any row where human_stance is
filled in as reviewed, whether or not the value changed. That's the
"reviewed and confirmed" case, distinct from "not yet looked at."

Notes handling: captured and carried into label_notes for every reviewed
row (blank if none given). Not yet used to set a real ordinal
target_score -- deliberately left as a simple placeholder column for
now (see conversation 2026-08-01: "wire it up... to whatever extent we
find useful, as we go, or later"), not a forced mapping.
"""
import os

import pandas as pd

TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
QUEUE_PATH = "data/hitl/queue_active_learning_requeue.csv"
BACKUP_DIR = "data/processed/active_learning_backups"

# Same 5-way -> 3-way collapse as build_stance_classifier_training_data.py --
# label must stay 3-way (hostile/endorsement/other), raw 5-way only ever
# lives in raw_label. FIX 2026-08-01: this script previously wrote
# human_stance straight into BOTH label and raw_label unmapped, which is
# exactly the label-column corruption already found and hand-fixed once
# this session (see ANTIGRAVITY_HANDOFF.md "known gaps") -- fixed at the
# source here so it can't recur on the next merge.
LABEL_MAP = {
    "endorsement": "endorsement",
    "hostile": "hostile",
    "neutral": "other",
    "ambiguous": "other",
    # wrong_match dropped entirely, handled below -- means the entity
    # mention itself was spurious/misidentified, not a hard stance call.
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
    backup_path = os.path.join(BACKUP_DIR, f"stance_classifier_training_data_pre_merge_{pd.Timestamp.now():%Y%m%d_%H%M%S}.parquet")
    df.to_parquet(backup_path, index=False)
    print(f"Backed up pre-merge training data to {backup_path}")

    n_changed = 0
    n_confirmed = 0
    n_not_found = 0
    n_dropped = 0
    n_unmapped = 0
    drop_idx = []
    for _, row in reviewed.iterrows():
        match = df["text"] == row["full_text"]
        if not match.any():
            n_not_found += 1
            continue
        idx = df[match].index
        raw_new = row["human_stance"]

        if raw_new == "wrong_match":
            drop_idx.extend(idx)
            n_dropped += len(idx)
            continue

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

    if drop_idx:
        df = df.drop(index=drop_idx)

    print(f"\nApplied: {n_changed} label changes, {n_confirmed} confirmations (label unchanged, now marked reviewed)")
    print(f"Dropped: {n_dropped} wrong_match rows (spurious entity mention, not a stance correction)")
    if n_unmapped:
        print(f"WARNING: {n_unmapped} rows had an unrecognized human_stance value -- not applied, check manually")
    if n_not_found:
        print(f"WARNING: {n_not_found} reviewed rows had no exact text match in the training data -- not applied, check manually")

    df.to_parquet(TRAINING_DATA_PATH, index=False)
    print(f"\nSaved updated training data to {TRAINING_DATA_PATH}")
    print("Run build_active_learning_requeue.py again (after retraining, if you want the next queue to reflect an updated model) to refresh the queue.")


if __name__ == "__main__":
    main()
