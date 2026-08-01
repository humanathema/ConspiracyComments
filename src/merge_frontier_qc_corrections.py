"""merge_frontier_qc_corrections.py

Merges rated rows from data/hitl/queue_frontier_disagreement_qc.csv (73
rows flagged where the frontier judge strongly disagreed with the
current label -- 50 AI-silver, 23 human-labeled, entity-safe joined,
see build history in conversation 2026-08-01/02) back into
stance_classifier_training_data.parquet.

Same conventions as the other merge scripts: 5-way -> 3-way collapse
(raw 5-way only ever lives in raw_label), backed up before writing,
matched by (text, label) since this queue's full_text is the WINDOW for
AI-silver rows (not the recovered full text -- that's a display-only
enhancement in hitl_rater.py, never touches what's actually in the
training data or what was actually scored).
"""
import os

import pandas as pd

TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
QUEUE_PATH = "data/hitl/queue_frontier_disagreement_qc.csv"
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
    backup_path = os.path.join(BACKUP_DIR, f"stance_classifier_training_data_pre_frontierqc_merge_{pd.Timestamp.now():%Y%m%d_%H%M%S}.parquet")
    df.to_parquet(backup_path, index=False)
    print(f"Backed up pre-merge training data to {backup_path}")

    n_changed = 0
    n_confirmed = 0
    n_not_found = 0
    n_unmapped = 0
    for _, row in reviewed.iterrows():
        # queue's own "label" column is the ORIGINAL label at the time this
        # row was flagged -- match on (text, original label) to land on the
        # exact right row, same fix as the entity-mismatch bug this queue
        # was already rebuilt once to avoid reintroducing.
        match = (df["text"] == row["full_text"]) & (df["label"] == row["label"])
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
        note = f"frontier_qc source_kind={row.get('source_kind','')} frontier_score={row.get('frontier_score','')}; " + str(row.get("notes", "") or "")
        df.loc[idx, "label_notes"] = note
        if new_label != old_label:
            n_changed += 1
        else:
            n_confirmed += 1

    print(f"\nApplied: {n_changed} label changes, {n_confirmed} confirmations (label unchanged, now marked reviewed)")
    if n_unmapped:
        print(f"WARNING: {n_unmapped} rows had an unrecognized human_stance value -- not applied, check manually")
    if n_not_found:
        print(f"WARNING: {n_not_found} reviewed rows had no exact (text, label) match in the training data -- not applied, check manually")

    df.to_parquet(TRAINING_DATA_PATH, index=False)
    print(f"\nSaved updated training data to {TRAINING_DATA_PATH}")


if __name__ == "__main__":
    main()
