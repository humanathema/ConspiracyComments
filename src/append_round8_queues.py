"""append_round8_queues.py

Appends the two round8 HITL queues (maverick_stance_round8.csv,
consensus_stance_round8.csv) as new rows in stance_classifier_training_data.parquet.
Neither had ever been ingested -- confirmed via direct query (zero rows
in the training parquet mention "round8" in source_file) -- and neither
is picked up by re-running build_stance_classifier_training_data.py from
scratch, since that would discard every AI-silver round merged in since
(rounds 3-7, mined-other, etc.). This is an append, matching
append_requeue_v2_new_rows.py's pattern, not a rebuild.

Real news for the neutral-class-starvation problem found 2026-08-04:
these two queues add 19 more genuine human "neutral" labels (12 from
maverick_stance_round8, 7 from consensus_stance_round8) -- a real ~15%
boost to the previously-fixed 123-row neutral pool, from Nash directly
rating more of these during this session.
"""
import os

import pandas as pd

TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
QUEUES = [
    "data/hitl/queue_maverick_stance_round8.csv",
    "data/hitl/queue_consensus_stance_round8.csv",
]
BACKUP_DIR = "data/processed/active_learning_backups"

LABEL_MAP = {
    "endorsement": "endorsement",
    "hostile": "hostile",
    "neutral": "other",
    "ambiguous": "other",
}


def main():
    df = pd.read_parquet(TRAINING_DATA_PATH)

    all_new = []
    for path in QUEUES:
        queue = pd.read_csv(path)
        reviewed = queue[queue["human_stance"].notna() & (queue["human_stance"].astype(str).str.strip() != "")].copy()
        already_present = reviewed["full_text"].isin(df["text"])
        new_rows = reviewed[~already_present]
        print(f"{path}: {len(reviewed)}/{len(queue)} reviewed, {len(new_rows)} not already in training data")

        unmapped = new_rows[~new_rows["human_stance"].isin(LABEL_MAP)]
        if not unmapped.empty:
            print(f"  WARNING: {len(unmapped)} unrecognized human_stance values, dropping:")
            print(unmapped[["full_text", "human_stance"]].to_string())
            new_rows = new_rows[new_rows["human_stance"].isin(LABEL_MAP)]

        new_rows = new_rows.copy()
        new_rows["source_file"] = os.path.basename(path)
        all_new.append(new_rows)

    combined_new = pd.concat(all_new, ignore_index=True)
    if combined_new.empty:
        print("\nNothing new to append.")
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_path = os.path.join(BACKUP_DIR, f"stance_classifier_training_data_pre_round8_append_{pd.Timestamp.now():%Y%m%d_%H%M%S}.parquet")
    df.to_parquet(backup_path, index=False)
    print(f"\nBacked up pre-append training data to {backup_path}")

    to_add = pd.DataFrame({
        "text": combined_new["full_text"].values,
        "label": combined_new["human_stance"].map(LABEL_MAP).values,
        "raw_label": combined_new["human_stance"].values,
        "source_file": combined_new["source_file"].values,
        "target_entity": combined_new["target_entity"].values if "target_entity" in combined_new.columns else None,
        "entity_spans": combined_new["entity_spans"].values if "entity_spans" in combined_new.columns else None,
        "label_target_std": None,
        "label_agreement_level": None,
        "weight": 1.0,
        "is_human": True,
        "split": "train",
        "label_notes": combined_new["notes"].fillna("").values if "notes" in combined_new.columns else "",
    })

    before = len(df)
    df = pd.concat([df, to_add], ignore_index=True)
    df.to_parquet(TRAINING_DATA_PATH, index=False)

    print(f"\nAppended {len(to_add)} new rows ({before:,} -> {len(df):,}).")
    print("New raw_label distribution among appended rows:")
    print(to_add["raw_label"].value_counts().to_string())
    print(f"Saved updated training data to {TRAINING_DATA_PATH}")


if __name__ == "__main__":
    main()
