"""build_frontier_targets_dataset.py

Merges the frontier judge's continuous stance-strength scores
(score_frontier_continuous_targets.py) into the training data as a new
frontier_score column, for the ordinal-v2 ablation (genuine continuous
training targets instead of forced -1/+1).

Output: data/processed/stance_classifier_training_data_frontier_targets.parquet
  Same rows/columns as stance_classifier_training_data.parquet, plus
  frontier_score (NaN for "other"-labeled rows and val rows not scored --
  only stage2-eligible TRAIN rows were scored, val keeps its existing
  discrete label for ground truth).
"""
import pandas as pd

BASE_PATH = "data/processed/stance_classifier_training_data.parquet"
SCORES_PATH = "data/processed/stance_frontier_continuous_targets.parquet"
OUT_PATH = "data/processed/stance_classifier_training_data_frontier_targets.parquet"


def main():
    base = pd.read_parquet(BASE_PATH)
    scores = pd.read_parquet(SCORES_PATH)

    print(f"Base: {len(base)} rows. Scores: {len(scores)} rows.")
    dupe_texts = scores["text"].duplicated().sum()
    if dupe_texts:
        print(f"WARNING: {dupe_texts} duplicate texts in scores file, keeping first occurrence")
        scores = scores.drop_duplicates(subset="text", keep="first")

    merged = base.merge(scores[["text", "frontier_score", "frontier_reason"]], on="text", how="left")
    assert len(merged) == len(base), "merge changed row count -- duplicate text collision somewhere"

    n_train_hs = ((merged["split"] == "train") & (merged["label"] != "other")).sum()
    n_scored = ((merged["split"] == "train") & (merged["label"] != "other") & merged["frontier_score"].notna()).sum()
    print(f"\nStage2-eligible train rows: {n_train_hs}, with a frontier_score: {n_scored}")
    if n_scored < n_train_hs:
        print(f"WARNING: {n_train_hs - n_scored} stage2-eligible train rows have no frontier_score -- "
              "run score_frontier_continuous_targets.py to completion first")

    merged.to_parquet(OUT_PATH, index=False)
    print(f"\nSaved to {OUT_PATH}")

    valid = merged[merged["frontier_score"].notna()]
    print("\nMean frontier_score by label (sanity check):")
    print(valid.groupby("label")["frontier_score"].agg(["mean", "median", "std", "count"]))


if __name__ == "__main__":
    main()
