"""augment_training_data_with_mined_other.py

Arm-2 data prep: adds the 200 hand-reviewed mined-"other"-candidate rows
(data-source: mine_other_candidates2.py's Kaggle run, 2026-07-30 --
only ~100-200 of an original 110,271-candidate pool survived a
lost-output-pool bug, see context-repo session_update_2026-07-30_regression_and_other_mining)
on top of the entity-fixed stance_classifier_training_data.parquet, as
its own separate augmented file -- NOT merged into the base file, and
NOT combined with the entity-conditioning ablation, so a kappa change
has one attributable cause (see build_stance_classifier_training_data.py
and the two-stage kernel's docstring for why this project insists on
one change at a time).

Added rows go into the TRAIN split only, never val -- the existing
297-row val set stays exactly as it was for arm 1 (entity-conditioning),
so this arm's result is paired-bootstrap-comparable against the same
baseline predictions rather than a different benchmark.

Input: data/processed/stance_classifier_training_data.parquet (already
  entity-fixed)
       /Users/nash/Downloads/other_candidates_entity_linked.csv (200
  rows, human_stance already hand-labeled: 127 other / 52 hostile / 21
  endorse)
Output: data/processed/stance_classifier_training_data_plus_mined_other.parquet
"""
import pandas as pd

BASE_PATH = "data/processed/stance_classifier_training_data.parquet"
MINED_PATH = "/Users/nash/Downloads/other_candidates_entity_linked.csv"
OUT_PATH = "data/processed/stance_classifier_training_data_plus_mined_other.parquet"

LABEL_MAP = {"other": "other", "hostile": "hostile", "endorse": "endorsement"}


def main():
    base = pd.read_parquet(BASE_PATH)
    mined = pd.read_csv(MINED_PATH)

    before = len(mined)
    overlap = mined["text"].isin(set(base["text"]))
    if overlap.any():
        print(f"Dropping {overlap.sum()} mined rows whose text already exists in base training data.")
        mined = mined[~overlap]
    print(f"Mined rows after overlap check: {len(mined)} / {before}")

    mapped_label = mined["human_stance"].map(LABEL_MAP)
    added = pd.DataFrame({
        "text": mined["text"],
        "label": mapped_label,
        # No neutral/ambiguous sub-distinction in the mined-candidate review
        # (human_stance here is already the 3-way scheme) -- raw_label just
        # mirrors label so arm-3's redesigned-buckets kernel (which reads
        # raw_label) doesn't silently drop these rows if it's ever combined
        # with this arm later; not used by this arm's own kernel.
        "raw_label": mapped_label,
        "source_file": "mined_other_candidates_2026-07-30_hitl_reviewed",
        "target_entity": mined["entity_key"],
        "entity_spans": None,
        "weight": 1.0,
        "is_human": True,
        "split": "train",  # deliberately never val -- see module docstring
    })

    n_unmapped = added["label"].isna().sum()
    if n_unmapped:
        raise ValueError(f"{n_unmapped} mined rows had an unmapped human_stance value -- fix LABEL_MAP")

    combined = pd.concat([base, added], ignore_index=True)
    combined.to_parquet(OUT_PATH, index=False)

    print(f"\nBase: {len(base):,} rows -> Augmented: {len(combined):,} rows (+{len(added)})")
    print("Added-row label distribution:")
    print(added["label"].value_counts())
    print(f"\nSaved to {OUT_PATH}")
    print(f"Train: {(combined['split']=='train').sum():,} | Val: {(combined['split']=='val').sum():,} (unchanged from base)")


if __name__ == "__main__":
    main()
