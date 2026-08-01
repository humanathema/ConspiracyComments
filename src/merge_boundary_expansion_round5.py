"""merge_boundary_expansion_round5.py

Same fix as round4 (merge_boundary_expansion_round4.py) -- re-merges the
existing frontier-judge scores with a proper 3-way threshold instead of
round3's binary one -- but tests a tighter, more principled cut: exact
frontier_score == 0.0 counts as "other", instead of round4's +/-0.15
deadzone.

Why test this separately: the frontier_score distribution isn't smooth --
it clusters at discrete values (looks like the judge rounds to ~0.05
increments), and 0.0 is a real spike: 968/4,998 rows (19.4%) landed on
EXACTLY 0.0, versus only 93 at -0.10 and 110 at 0.10. That's a much
bigger jump than a smooth continuum would produce, suggesting 0.0 is the
judge's dedicated "no real stance" answer in a lot of cases, not an
incidental midpoint. Round4's wider deadzone also sweeps in hedged-but-
real-stance rows (the val diagnostic showed true endorsement/hostile
rows scoring as low as 0.00/as high as 0.85), which may hurt precision
on the recovered "other" class. Exact-zero should be a purer (if
smaller) "other" set: 968 rows vs round4's 1,171.

No new frontier-judge calls needed -- same existing scored data as
round3/round4. Starts from the same PRE-round3-merge backup as round4
(not round4's output -- both round4 and round5 are independent re-merges
of the same clean base, so they're a clean ablation of ONLY the
threshold choice, not stacked on each other).

Input: data/processed/boundary_candidates_frontier_scored.parquet
       data/processed/active_learning_backups/stance_classifier_training_data_pre_round3_merge_20260802_081242.parquet
Output: overwrites data/processed/stance_classifier_training_data.parquet
  (backed up first, same convention as every other merge tonight)
"""
import os

import pandas as pd

PRE_ROUND3_BACKUP = "data/processed/active_learning_backups/stance_classifier_training_data_pre_round3_merge_20260802_081242.parquet"
TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
SCORED_PATH = "data/processed/boundary_candidates_frontier_scored.parquet"
BACKUP_DIR = "data/processed/active_learning_backups"
NEW_WEIGHT = 0.75


def label_from_score(s):
    if s == 0.0:
        return "other"
    return "endorsement" if s > 0.0 else "hostile"


def main():
    df = pd.read_parquet(PRE_ROUND3_BACKUP)
    scored = pd.read_parquet(SCORED_PATH)
    valid = scored[scored["frontier_score"].notna()].copy()
    print(f"{len(valid)}/{len(scored)} boundary rows have a valid frontier score", flush=True)

    existing_texts = set(df["text"])
    valid = valid[~valid["text"].isin(existing_texts)]
    print(f"{len(valid)} rows are genuinely new (not already in pre-round3 training data)", flush=True)

    valid["label"] = valid["frontier_score"].apply(label_from_score)
    print(f"Label distribution with exact-zero threshold: {valid['label'].value_counts().to_dict()}", flush=True)

    new_rows = pd.DataFrame({
        "text": valid["text"],
        "label": valid["label"],
        "raw_label": valid["label"],
        "source_file": "frontier_boundary_expansion_20260802_round5_exact_zero_threshold",
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
    if os.path.exists(TRAINING_DATA_PATH):
        backup_path = os.path.join(BACKUP_DIR, f"stance_classifier_training_data_pre_round5_merge_{pd.Timestamp.now():%Y%m%d_%H%M%S}.parquet")
        pd.read_parquet(TRAINING_DATA_PATH).to_parquet(backup_path, index=False)
        print(f"Backed up pre-round5 (round4) training data to {backup_path}", flush=True)

    out = pd.concat([df, new_rows], ignore_index=True)
    out.to_parquet(TRAINING_DATA_PATH, index=False)

    print(f"\nBefore (pre-round3 base): {len(df):,} rows ({(df.split=='train').sum():,} train / {(df.split=='val').sum():,} val)", flush=True)
    print(f"After (round5):           {len(out):,} rows ({(out.split=='train').sum():,} train / {(out.split=='val').sum():,} val)", flush=True)
    print(f"Added {len(new_rows):,} new train rows: {new_rows['label'].value_counts().to_dict()}", flush=True)


if __name__ == "__main__":
    main()
