"""merge_boundary_expansion_round4.py

Re-does round3's merge with a fixed 3-way label threshold. Round3
(merge_boundary_expansion_round3.py) thresholded frontier_score with NO
"other"/no-stance bucket at all (>=0 -> endorsement, <0 -> hostile),
despite the frontier judge's own prompt defining 0.0 as "no real stance,
or perfectly balanced/mixed" (score_boundary_candidates_vertex.py's
PROMPT_TEMPLATE). Confirmed real damage from this, not just theoretical:
median frontier_score across the 4,998 rows was exactly 0.0, and 25.3%
scored within +/-0.15 of zero -- all force-labeled into a stance category
anyway. Round3's stage1 (has_stance vs other) recall on the true "other"
class collapsed to 32% (confusion matrix: 56/82 true "other" val rows
misclassified as hostile/endorsement), and this mislabeling is the
direct, mechanical explanation -- not just the separate class-imbalance
problem (0 of 4,998 added rows were even eligible to be labeled "other"
under round3's threshold, regardless of what the judge actually said).

No new frontier-judge calls needed -- reuses the same
boundary_candidates_frontier_scored.parquet scores, just fixes the label
mapping. Starts from the PRE-round3-merge backup (clean base, since
round3's mislabeled rows need to be replaced, not added on top of).

DEADZONE = 0.15 (matches the width used to estimate ~1,262 recoverable
"other" rows during diagnosis) -- a judgment call, not derived; the
judge's own scale treats 0.0 as the center of "no real stance" but gives
no explicit width for that band.

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
DEADZONE = 0.15


def label_from_score(s, deadzone=DEADZONE):
    if abs(s) < deadzone:
        return "other"
    return "endorsement" if s >= deadzone else "hostile"


def main():
    df = pd.read_parquet(PRE_ROUND3_BACKUP)
    scored = pd.read_parquet(SCORED_PATH)
    valid = scored[scored["frontier_score"].notna()].copy()
    print(f"{len(valid)}/{len(scored)} boundary rows have a valid frontier score", flush=True)

    existing_texts = set(df["text"])
    valid = valid[~valid["text"].isin(existing_texts)]
    print(f"{len(valid)} rows are genuinely new (not already in pre-round3 training data)", flush=True)

    valid["label"] = valid["frontier_score"].apply(label_from_score)
    print(f"Label distribution with deadzone={DEADZONE}: {valid['label'].value_counts().to_dict()}", flush=True)

    new_rows = pd.DataFrame({
        "text": valid["text"],
        "label": valid["label"],
        "raw_label": valid["label"],
        "source_file": "frontier_boundary_expansion_20260802_round4_fixed_threshold",
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
        backup_path = os.path.join(BACKUP_DIR, f"stance_classifier_training_data_pre_round4_merge_{pd.Timestamp.now():%Y%m%d_%H%M%S}.parquet")
        pd.read_parquet(TRAINING_DATA_PATH).to_parquet(backup_path, index=False)
        print(f"Backed up pre-round4 (round3) training data to {backup_path}", flush=True)

    out = pd.concat([df, new_rows], ignore_index=True)
    out.to_parquet(TRAINING_DATA_PATH, index=False)

    print(f"\nBefore (pre-round3 base): {len(df):,} rows ({(df.split=='train').sum():,} train / {(df.split=='val').sum():,} val)", flush=True)
    print(f"After (round4):           {len(out):,} rows ({(out.split=='train').sum():,} train / {(out.split=='val').sum():,} val)", flush=True)
    print(f"Added {len(new_rows):,} new train rows: {new_rows['label'].value_counts().to_dict()}", flush=True)


if __name__ == "__main__":
    main()
