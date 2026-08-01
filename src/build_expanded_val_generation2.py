"""build_expanded_val_generation2.py

Grows the val set using the two new row-sets found tonight (199 mined-
other-candidate rows, 94 recovered IRR rows -- confirmed zero overlap
between them), instead of leaving val frozen at 297 rows forever while
train keeps growing. Motivation (Nash, 2026-08-01): a bigger val set
directly addresses the run-to-run kappa noise problem observed across
tonight's five ablation arms (baseline kappa ranged 0.30-0.41 on
identical architecture, just from unfixed random seeds interacting with
a small val set).

Design, chosen specifically to NOT invalidate tonight's five already-run
results: the ORIGINAL 297 val rows are never reshuffled or touched --
only the 293 NET-NEW rows get split 85/15 (same ratio, same stratify-by-
label convention as the original build script) and added to their
respective splits. This means the original 297-row val set is a strict
subset of the new, larger one -- tonight's results remain valid as
"measured against the original core val," while this expanded set
becomes the new reference point for whatever runs next.

This does NOT include entity-conditioning (that's a text-transform
applied at training time, not a data change) or bucket-redesign (that
reads raw_label, already present on both new row-sets).

Output: data/processed/stance_classifier_training_data_gen2.parquet
IMPORTANT: this is a new reference generation -- a fresh baseline MUST
be re-verified against it before trusting any comparison run against
this file. Do not assume tonight's 0.3444-0.4128 baseline numbers
(measured on the old, smaller val) carry over unchanged.
"""
import numpy as np
import pandas as pd

BASE_PATH = "data/processed/stance_classifier_training_data.parquet"
MINED_AUG_PATH = "data/processed/stance_classifier_training_data_plus_mined_other.parquet"
IRR_AUG_PATH = "data/processed/stance_classifier_training_data_with_irr.parquet"
OUT_PATH = "data/processed/stance_classifier_training_data_gen2.parquet"

SEED = 42
VAL_FRACTION = 0.15


def main():
    base = pd.read_parquet(BASE_PATH)
    mined_aug = pd.read_parquet(MINED_AUG_PATH)
    irr_aug = pd.read_parquet(IRR_AUG_PATH)

    base_texts = set(base["text"])
    mined_new = mined_aug[~mined_aug["text"].isin(base_texts)].copy()
    irr_new = irr_aug[~irr_aug["text"].isin(base_texts)].copy()
    overlap = set(mined_new["text"]) & set(irr_new["text"])
    if overlap:
        raise ValueError(f"{len(overlap)} rows appear in both new-row sets -- resolve before proceeding")

    new_rows = pd.concat([mined_new, irr_new], ignore_index=True)
    print(f"New rows: {len(mined_new)} mined + {len(irr_new)} IRR = {len(new_rows)} total", flush=True)

    # All new rows are human-labeled (mined = HITL-reviewed, IRR = genuine
    # triple-rater majority vote) -- same "human labels only in val" rule
    # as the original build script.
    new_rows["is_human"] = True
    new_rows["weight"] = new_rows.get("weight", 1.0)
    if "weight" not in new_rows.columns or new_rows["weight"].isna().any():
        new_rows["weight"] = 1.0

    rng = np.random.RandomState(SEED)
    new_rows["split"] = "train"
    for label in new_rows["label"].unique():
        idx = new_rows[new_rows["label"] == label].index
        n_val = max(1, int(len(idx) * VAL_FRACTION))
        val_idx = rng.choice(idx, size=min(n_val, len(idx)), replace=False)
        new_rows.loc[val_idx, "split"] = "train" if len(idx) < 2 else "val"
        new_rows.loc[val_idx, "split"] = "val"

    print("New-rows split assignment:", flush=True)
    print(new_rows.groupby(["label", "split"]).size(), flush=True)

    combined = pd.concat([base, new_rows], ignore_index=True)
    combined.to_parquet(OUT_PATH, index=False)

    old_val_n = (base["split"] == "val").sum()
    new_val_n = (combined["split"] == "val").sum()
    old_train_n = (base["split"] == "train").sum()
    new_train_n = (combined["split"] == "train").sum()

    print(f"\nSaved {len(combined):,} rows to {OUT_PATH}", flush=True)
    print(f"  train: {old_train_n:,} -> {new_train_n:,} (+{new_train_n - old_train_n})", flush=True)
    print(f"  val:   {old_val_n:,} -> {new_val_n:,} (+{new_val_n - old_val_n})", flush=True)

    old_val_texts = set(base[base["split"] == "val"]["text"])
    new_val_texts = set(combined[combined["split"] == "val"]["text"])
    print(f"  original val is a strict subset of new val: {old_val_texts.issubset(new_val_texts)}", flush=True)


if __name__ == "__main__":
    main()
