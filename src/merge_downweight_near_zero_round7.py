"""merge_downweight_near_zero_round7.py

Cheap, fast test of a specific hypothesis before investing Nash's manual
review time in the active-learning correction loop: round6 (kappa=0.4245)
underperformed round2 (kappa=0.4922) despite tripling train data, and
spot-checking round5/6 rows found a real, identifiable failure mode --
near-zero |frontier_score| rows get bucketed into a hard hostile/
endorsement class by the exact-zero threshold convention and trained at
FULL confidence weight (0.75), same as unambiguous |frontier_score|=0.8+
rows, even though a -0.10 score is barely distinguishable from neutral
(confirmed on an actual sampled row: an Assange comment scored -0.10 and
labeled "hostile" reads as neutral/speculative on full-text inspection,
not hostile).

4,174/15,730 (26.5%) of all round5+round6 frontier-labeled rows have
|frontier_score| < 0.15 -- a meaningful fraction to be systematically
overconfident about.

This is the FAST test: just down-weight those near-zero rows (not full
active-learning correction, no new human labels) and retrain. If kappa
recovers toward round2, that confirms the hypothesis is worth Nash's
actual review time (a targeted active-learning queue on exactly this
stratum). If it doesn't move, the problem is elsewhere and manual review
of this particular stratum wouldn't have been the right lever.

NEAR_ZERO_THRESHOLD and NEW_WEIGHT are the tuning knobs.

Output: overwrites data/processed/stance_classifier_training_data.parquet
  (backed up first, same convention as every other merge tonight)
"""
import os
import pandas as pd

TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
BACKUP_DIR = "data/processed/active_learning_backups"
NEAR_ZERO_THRESHOLD = 0.15  # matches the BOUNDARY_WIDTH convention used
# elsewhere tonight (population-proportion estimate)
NEW_WEIGHT = 0.15  # down from 0.75 -- not zeroing out entirely, these rows
# still carry SOME signal (a slight lean is still a slight lean), just
# shouldn't be trained on with the same confidence as a clear-cut case
TARGET_SOURCES = [
    "frontier_boundary_expansion_20260802_round5_exact_zero_threshold",
    "frontier_random_expansion_20260802_round6",
]


def main():
    df = pd.read_parquet(TRAINING_DATA_PATH)

    scores = df["label_notes"].str.extract(r"frontier_score=(-?\d*\.?\d+)")[0].astype(float)
    is_target = df["source_file"].isin(TARGET_SOURCES)
    is_near_zero = is_target & (scores.abs() < NEAR_ZERO_THRESHOLD)

    print(f"{is_target.sum():,} rows from round5/6 frontier expansions", flush=True)
    print(f"{is_near_zero.sum():,} of those have |frontier_score| < {NEAR_ZERO_THRESHOLD} "
          f"({is_near_zero.sum()/is_target.sum()*100:.1f}%)", flush=True)
    print(f"Down-weighting from 0.75 -> {NEW_WEIGHT}", flush=True)

    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_path = os.path.join(BACKUP_DIR, f"stance_classifier_training_data_pre_round7_downweight_{pd.Timestamp.now():%Y%m%d_%H%M%S}.parquet")
    df.to_parquet(backup_path, index=False)
    print(f"Backed up pre-round7 training data to {backup_path}", flush=True)

    df.loc[is_near_zero, "weight"] = NEW_WEIGHT
    df.to_parquet(TRAINING_DATA_PATH, index=False)

    train = df[df["split"] == "train"]
    print(f"\nDone. {len(train):,} train rows unchanged in count, "
          f"{is_near_zero.sum():,} reweighted to {NEW_WEIGHT}.", flush=True)


if __name__ == "__main__":
    main()
