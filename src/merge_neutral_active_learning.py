"""merge_neutral_active_learning.py

Merges the labeled queue_neutral_active_learning_REVIEW.csv (550 rows, built
2026-08-14: unanimous 6-model-then-5-model "other" candidates from the
entity-mismatch-cleaned round9 pool + a dedicated original-11 pull, routed
through active learning specifically to grow real human-labeled
other/neutral training rows) into the current canonical training file.

Same merge discipline as merge_round9_hitl_backlog.py: drop anything
overlapping the frozen val pool entirely, upgrade AI-silver train rows to
human labels on text match, apply the backlog label when two human labels
disagree on the same text, append genuinely new rows otherwise. Label
taxonomy identical (endorsement/hostile pass through, neutral/ambiguous
collapse to "other", wrong_match dropped -- these are exactly the rows the
entity-disambiguation fixes still let through, real signal, not silver
training data).

Output: a NEW file, not an overwrite, so it's reviewable side by side.
"""
import pandas as pd

LABEL_MAP = {
    "endorsement": "endorsement",
    "hostile": "hostile",
    "neutral": "other",
    "ambiguous": "other",
}

PREV_COMBINED = "data/processed/stance_classifier_training_data_round9_hitl_backlog.parquet"
OUT_PATH = "data/processed/stance_classifier_training_data_round10_neutral_al.parquet"
SOURCE_FILE = "queue_neutral_active_learning_REVIEW.csv"


def load_source():
    df = pd.read_csv(f"data/hitl/{SOURCE_FILE}", low_memory=False)
    df = df[df["human_stance"].notna() & (df["human_stance"].astype(str).str.strip() != "")]
    df = df[df["human_stance"] != "wrong_match"]

    rows = []
    n_unmapped = 0
    for _, row in df.iterrows():
        raw = row["human_stance"]
        if raw not in LABEL_MAP:
            n_unmapped += 1
            continue
        rows.append({
            "id": row["id"],
            "text": row["full_text"],
            "target_entity": row.get("target_entity"),
            "label": LABEL_MAP[raw],
            "raw_label": raw,
            "weight": 1.0,
            "source_file": SOURCE_FILE,
        })
    if n_unmapped:
        print(f"  {n_unmapped} rows with unrecognized human_stance value, skipped")
    return pd.DataFrame(rows)


def main():
    new_rows = load_source()
    print(f"Labeled, mappable rows from {SOURCE_FILE}: {len(new_rows)}")
    print(new_rows["label"].value_counts().to_string())
    new_rows = new_rows.drop_duplicates(subset=["id"])

    prev = pd.read_parquet(PREV_COMBINED)
    val_mask_prev = prev["split"] == "val"
    val_texts = set(prev.loc[val_mask_prev, "text"].astype(str))
    train_texts = set(prev.loc[~val_mask_prev, "text"].astype(str))

    before = len(new_rows)
    new_rows = new_rows[~new_rows["text"].astype(str).isin(val_texts)]
    n_val_overlap = before - len(new_rows)
    if n_val_overlap:
        print(f"Dropped {n_val_overlap} rows overlapping the frozen val pool (excluded entirely, not merged)")

    train_lookup = prev[~val_mask_prev].set_index(prev[~val_mask_prev]["text"].astype(str))
    is_dup_text = new_rows["text"].astype(str).isin(train_texts)
    dup_rows = new_rows[is_dup_text]
    genuinely_new = new_rows[~is_dup_text].copy()

    n_confirmed = 0
    n_upgraded = 0
    n_corrected = 0
    for _, row in dup_rows.iterrows():
        text_key = str(row["text"])
        existing = train_lookup.loc[text_key]
        if isinstance(existing, pd.DataFrame):
            existing = existing.iloc[0]

        if bool(existing["is_human"]):
            if existing["label"] == row["label"]:
                n_confirmed += 1
                continue
            idx = prev.index[(~val_mask_prev) & (prev["text"].astype(str) == text_key)][0]
            prev.loc[idx, "label"] = row["label"]
            prev.loc[idx, "raw_label"] = row["raw_label"]
            prev.loc[idx, "weight"] = row["weight"]
            prev.loc[idx, "source_file"] = row["source_file"]
            n_corrected += 1
            continue

        idx = prev.index[(~val_mask_prev) & (prev["text"].astype(str) == text_key)][0]
        prev.loc[idx, "label"] = row["label"]
        prev.loc[idx, "raw_label"] = row["raw_label"]
        prev.loc[idx, "weight"] = row["weight"]
        prev.loc[idx, "source_file"] = row["source_file"]
        prev.loc[idx, "is_human"] = True
        n_upgraded += 1

    print(f"Of {len(dup_rows)} rows matching existing train text: "
          f"{n_confirmed} confirmed (already human-labeled, agreed), "
          f"{n_corrected} corrected (human labels disagreed, new label applied), "
          f"{n_upgraded} AI-silver rows upgraded to human label")
    print(f"Genuinely new rows to append: {len(genuinely_new)}")

    genuinely_new["is_human"] = True
    genuinely_new["split"] = "train"
    for col in ["entity_spans", "label_target_std", "label_agreement_level", "label_notes", "label_target_score"]:
        genuinely_new[col] = None

    all_cols = list(prev.columns)
    for col in all_cols:
        if col not in genuinely_new.columns:
            genuinely_new[col] = None

    combined = pd.concat([prev, genuinely_new[all_cols]], ignore_index=True)

    actual_val = (combined["split"] == "val").sum()
    if actual_val != val_mask_prev.sum():
        raise RuntimeError(
            f"Val split changed size during merge: expected {val_mask_prev.sum()}, got {actual_val}."
        )

    print(f"\nCombined: {len(combined):,} rows "
          f"(train={(combined['split']=='train').sum():,}, val={(combined['split']=='val').sum():,})")
    print("\nFull-corpus label distribution before vs after:")
    print("before:", prev["label"].value_counts().to_dict())
    print("after: ", combined["label"].value_counts().to_dict())
    combined.to_parquet(OUT_PATH, index=False)
    print(f"\nSaved to {OUT_PATH}")


if __name__ == "__main__":
    main()
