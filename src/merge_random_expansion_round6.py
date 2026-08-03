"""merge_random_expansion_round6.py

Merges the 9,663 valid frontier-scored random-expansion rows
(select_random_expansion_sample.py + score_random_expansion_vertex.py)
into stance_classifier_training_data.parquet, diluting the boundary-
expansion rows' dominance (currently 4,998/7,485 = 66.8% of train).
These rows were selected RANDOMLY, not by classifier uncertainty --
the point is balance, not more hard cases (Nash's direction 2026-08-02).

Same exact-zero 3-way threshold as round5 (the better-performing of the
two round4/5 variants -- other-recall matched round2's 55% with better
precision than round4's wider deadzone, which overcorrected and hurt
endorsement/hostile recall).

Input: data/processed/random_expansion_candidates_frontier_scored.parquet
Output: overwrites data/processed/stance_classifier_training_data.parquet
  (backed up first, same convention as every other merge tonight)
"""
import os
import pandas as pd

SCORED_PATH = "data/processed/random_expansion_candidates_frontier_scored.parquet"
TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
BACKUP_DIR = "data/processed/active_learning_backups"
NEW_WEIGHT = 0.75


def label_from_score(s):
    if s == 0.0:
        return "other"
    return "endorsement" if s > 0.0 else "hostile"


def main():
    df = pd.read_parquet(TRAINING_DATA_PATH)
    scored = pd.read_parquet(SCORED_PATH)
    valid = scored[scored["frontier_score"].notna()].copy()
    print(f"{len(valid)}/{len(scored)} random-expansion rows have a valid frontier score", flush=True)

    existing_texts = set(df["text"])
    valid = valid[~valid["text"].isin(existing_texts)]
    print(f"{len(valid)} rows are genuinely new (not already in training data)", flush=True)

    valid["label"] = valid["frontier_score"].apply(label_from_score)
    print(f"Label distribution: {valid['label'].value_counts().to_dict()}", flush=True)

    new_rows = pd.DataFrame({
        "text": valid["text"],
        "label": valid["label"],
        "raw_label": valid["label"],
        "source_file": "frontier_random_expansion_20260802_round6",
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
    backup_path = os.path.join(BACKUP_DIR, f"stance_classifier_training_data_pre_round6_merge_{pd.Timestamp.now():%Y%m%d_%H%M%S}.parquet")
    df.to_parquet(backup_path, index=False)
    print(f"Backed up pre-round6 training data to {backup_path}", flush=True)

    out = pd.concat([df, new_rows], ignore_index=True)
    out.to_parquet(TRAINING_DATA_PATH, index=False)

    train = out[out["split"] == "train"]
    boundary_mask = train["source_file"].astype(str).str.contains("round5_exact_zero", na=False)
    print(f"\nBefore: {len(df):,} rows ({(df.split=='train').sum():,} train / {(df.split=='val').sum():,} val)", flush=True)
    print(f"After:  {len(out):,} rows ({(out.split=='train').sum():,} train / {(out.split=='val').sum():,} val)", flush=True)
    print(f"Added {len(new_rows):,} new train rows: {new_rows['label'].value_counts().to_dict()}", flush=True)
    print(f"Boundary-expansion (round5) share of train set: {boundary_mask.sum():,}/{len(train):,} "
          f"({boundary_mask.sum()/len(train)*100:.1f}%)", flush=True)


if __name__ == "__main__":
    main()
