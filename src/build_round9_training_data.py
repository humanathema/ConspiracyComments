"""build_round9_training_data.py

Combines:
  - round 9 high-confidence silver labels (ensemble margin >= 0.45) — weight 0.75
  - round 9 epistemic-context frontier-scored rows — weight 0.9
  - previous cumulative training data (round 8 combined) — weight as-is

Outputs stance_classifier_training_data_round9_new.parquet  (new rows only)
     and stance_classifier_training_data_round9_combined.parquet (full cumulative set)

Run locally after pulling results back from VM.

Usage:
  python3 src/build_round9_training_data.py \
    --scores data/processed/round9/batch_ensemble_scores_round9.parquet \
    --frontier data/processed/escalation_cascade_frontier_scored_round9.csv \
    --context_rerun data/processed/round9/escalation_context_rerun_round9.parquet \
    --prev_combined data/processed/stance_classifier_training_data_round8_combined.parquet \
    --out_new data/processed/stance_classifier_training_data_round9_new.parquet \
    --out_combined data/processed/stance_classifier_training_data_round9_combined.parquet
"""

import argparse
import pandas as pd
import numpy as np
from pathlib import Path

LABEL_MAP = {0: "hostile", 1: "endorsement", 2: "other"}
FRONTIER_LABEL_MAP = {
    "hostile": "hostile", "endorsement": "endorsement",
    "neutral": "other", "other": "other"
}
MARGIN_THR = 0.45
VAL_SIZE   = 680
RANDOM_STATE = 42


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores",       required=True)
    ap.add_argument("--frontier",     required=True)
    ap.add_argument("--context_rerun",required=True)
    ap.add_argument("--prev_combined",required=True)
    ap.add_argument("--out_new",      required=True)
    ap.add_argument("--out_combined", required=True)
    args = ap.parse_args()

    # --- Round 9 high-confidence silver rows ---
    scores = pd.read_parquet(args.scores)
    context_rerun = pd.read_parquet(args.context_rerun)

    # Rows that were NOT escalated (confident from the start)
    confident = scores[scores["margin"] >= MARGIN_THR].copy()
    confident["label"]    = confident["pred_label"]
    confident["raw_label"] = confident["label"]
    confident["weight"]   = 0.75
    confident["source_file"] = "round9_ensemble"
    print(f"Confident silver rows: {len(confident):,}")

    # Epistemic context-resolved rows (were uncertain, context resolved them)
    # These will be overridden by frontier-scored labels below if available
    epistemic = context_rerun[context_rerun["resolved"]].copy()
    print(f"Epistemic context-resolved: {len(epistemic):,}")

    # --- Frontier-scored rows ---
    frontier = pd.read_csv(args.frontier)
    frontier["label"]     = frontier["frontier_label"].map(FRONTIER_LABEL_MAP)
    frontier["raw_label"] = frontier["label"]
    frontier["weight"]    = 0.9
    frontier["source_file"] = "round9_epistemic_context"
    frontier = frontier[frontier["label"].notna() & (frontier["label"] != "")]
    # Merge text back from scores
    frontier = frontier.merge(scores[["id", "text", "target_entity"]], on="id", how="left")
    print(f"Frontier-scored rows: {len(frontier):,}")

    # Combine new rows
    keep_cols = ["id", "text", "target_entity", "label", "raw_label", "weight", "source_file"]
    new_rows = pd.concat([
        confident[keep_cols],
        frontier[keep_cols],
    ], ignore_index=True).drop_duplicates(subset=["id"])

    print(f"Total new rows for round 9: {len(new_rows):,}")
    print(new_rows["label"].value_counts())

    # Fill missing columns for compatibility
    for col in ["entity_spans", "label_target_std", "label_agreement_level",
                "is_human", "label_notes", "label_target_score"]:
        new_rows[col] = None

    new_rows["split"] = "train"  # will be re-split in combined
    new_rows.to_parquet(args.out_new, index=False)
    print(f"\nSaved round9_new: {args.out_new}")

    # --- Combine with previous ---
    prev = pd.read_parquet(args.prev_combined).drop(columns=["split"])
    new_base = new_rows.drop(columns=["split"])

    all_cols = list(prev.columns)
    for col in all_cols:
        if col not in new_base.columns:
            new_base[col] = None

    combined = pd.concat([prev, new_base[all_cols]], ignore_index=True)

    # Freeze the same 680 human-only val rows from prev_combined.
    # Never re-stratify from the full combined pool — that would contaminate
    # the val set with AI-silver rows and make kappa measurement circular.
    prev_with_split = pd.read_parquet(args.prev_combined, columns=["id", "split"])
    frozen_val_ids = set(prev_with_split.loc[prev_with_split["split"] == "val", "id"].astype(str))
    if len(frozen_val_ids) != VAL_SIZE:
        raise RuntimeError(
            f"Expected {VAL_SIZE} val rows in prev_combined, got {len(frozen_val_ids)}. "
            "Check that prev_combined has a frozen human-only val split."
        )
    combined["split"] = "train"
    combined.loc[combined["id"].astype(str).isin(frozen_val_ids), "split"] = "val"
    actual_val = (combined["split"] == "val").sum()
    if actual_val != VAL_SIZE:
        raise RuntimeError(
            f"After freezing val IDs, got {actual_val} val rows instead of {VAL_SIZE}. "
            "Some frozen val IDs may be missing from combined — check for deduplication."
        )

    print(f"\nCombined: {len(combined):,} rows "
          f"(train={(combined['split']=='train').sum():,}, val={(combined['split']=='val').sum():,})")
    combined.to_parquet(args.out_combined, index=False)
    print(f"Saved round9_combined: {args.out_combined}")


if __name__ == "__main__":
    main()
