"""merge_round9_hitl_backlog.py

Merges the backlog of already-labeled HITL stance queues (2026-08-12 audit
found 1,264 real, correct-construct rows never folded into training data)
into stance_classifier_training_data_round8_combined.parquet.

Excludes (checked directly, not from filename): queue_maverick_authority.csv,
queue_personal_experience.csv, queue_procedural_skepticism.csv,
queue_hedged_suspicion_extension.csv, queue_intra_rater_hedged_suspicion.csv --
different construct entirely (negative/lean_positive/positive/unsure), not
stance. Also excludes the base (non-REVIEW) *_stance_quality_check.csv files
for wikileaks/snowden/assange/greenwald/jones-short, since their REVIEW
counterpart is already present in round8_combined.parquet's source_file
column and merging both would duplicate the same comments.

Label taxonomy: standard raw_label -> label collapse, matching
merge_active_learning_requeue_v2.py's convention exactly (endorsement/
endorse -> endorsement, hostile -> hostile, neutral/ambiguous -> other).
wrong_match rows dropped entirely (not a stance label).

Jones quality-check special case (per Nash 2026-08-12): use the REVIEW
file's already-built human_norm column (a prior session already normalized
"endorse"->endorsement, "lean hostile"->hostile, "neutral/list"->neutral,
"unclear"/"unclear/list"->ambiguous) rather than re-deriving it -- except
"unclear, lean hostile?" gets weight=0.5 (rater's own uncertainty, marked
with a literal "?"), not the standard weight.

Output: stance_classifier_training_data_round9_hitl_backlog.parquet --
a NEW file, not an overwrite of round8_combined.parquet, so it's reviewable
side by side.
"""
import pandas as pd

LABEL_MAP = {
    "endorsement": "endorsement",
    "endorse": "endorsement",
    "hostile": "hostile",
    "neutral": "other",
    "ambiguous": "other",
}

PREV_COMBINED = "data/processed/stance_classifier_training_data_round8_combined.parquet"
OUT_PATH = "data/processed/stance_classifier_training_data_round9_hitl_backlog.parquet"

# (file, label_col, default_target_entity_if_missing)
SOURCES = [
    ("queue_escalation_round8_aleatoric.csv", "human_label", None),
    ("queue_maverick_stance_round8.csv", "human_stance", None),
    ("queue_consensus_stance_round8.csv", "human_stance", None),
    ("queue_active_learning_requeue.csv", "human_stance", None),
    ("queue_active_learning_requeue_v2.csv", "human_stance", None),
    ("queue_escalation_aleatoric_review.csv", "human_stance", None),
    ("queue_escalation_human_review.csv", "human_stance", None),
    ("queue_frontier_disagreement_qc.csv", "human_stance", None),
    ("queue_qwen_escalation_review.csv", "human_stance", None),
]


def load_standard(fname, label_col):
    df = pd.read_csv(f"data/hitl/{fname}", low_memory=False)
    df = df[df[label_col].notna() & (df[label_col].astype(str).str.strip() != "")]
    df = df[df[label_col] != "wrong_match"]

    rows = []
    n_unmapped = 0
    for _, row in df.iterrows():
        raw = row[label_col]
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
            "source_file": fname,
        })
    if n_unmapped:
        print(f"  {fname}: {n_unmapped} rows with unrecognized label, skipped")
    return pd.DataFrame(rows)


def load_jones_review():
    fname = "queue_jones_stance_quality_check_REVIEW.csv"
    df = pd.read_csv(f"data/hitl/{fname}")
    df = df[df["human_norm"].notna()]

    rows = []
    for _, row in df.iterrows():
        weight = 0.5 if row["human_stance"] == "unclear, lean hostile?" else 1.0
        rows.append({
            "id": row["id"],
            "text": row["full_text"],
            "target_entity": "Alex Jones",
            "label": LABEL_MAP[row["human_norm"]],
            "raw_label": row["human_norm"],
            "weight": weight,
            "source_file": fname,
        })
    return pd.DataFrame(rows)


def main():
    frames = []
    for fname, label_col, _ in SOURCES:
        f = load_standard(fname, label_col)
        print(f"{fname}: {len(f)} rows")
        frames.append(f)

    jones = load_jones_review()
    print(f"queue_jones_stance_quality_check_REVIEW.csv: {len(jones)} rows "
          f"({(jones['weight'] == 0.5).sum()} at weight=0.5)")
    frames.append(jones)

    new_rows = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["id"])
    print(f"\nTotal new rows (deduped by id): {len(new_rows):,}")
    print(new_rows["label"].value_counts().to_string())

    prev = pd.read_parquet(PREV_COMBINED)
    val_mask_prev = prev["split"] == "val"
    val_texts = set(prev.loc[val_mask_prev, "text"].astype(str))
    train_texts = set(prev.loc[~val_mask_prev, "text"].astype(str))

    # 1. Drop anything overlapping the frozen val pool entirely -- these
    #    comments were already drawn into the 680-row human-labeled val set
    #    by an earlier round; adding them as train would leak val into train.
    before = len(new_rows)
    new_rows = new_rows[~new_rows["text"].astype(str).isin(val_texts)]
    n_val_overlap = before - len(new_rows)
    if n_val_overlap:
        print(f"Dropped {n_val_overlap} rows overlapping the frozen val pool (excluded entirely, not merged)")

    # 2. For rows matching existing TRAIN text: if the existing row is
    #    already human-labeled, it's a true duplicate -- drop. If the
    #    existing row is AI-silver, upgrade it in place to the human label
    #    instead of just appending a duplicate row.
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
            # Two human labels disagree on the same text -- per Nash
            # (2026-08-12), the backlog label wins: update the existing
            # training row's label in place rather than silently keeping
            # whichever one happened to be there first.
            idx = prev.index[(~val_mask_prev) & (prev["text"].astype(str) == text_key)][0]
            prev.loc[idx, "label"] = row["label"]
            prev.loc[idx, "raw_label"] = row["raw_label"]
            prev.loc[idx, "weight"] = row["weight"]
            prev.loc[idx, "source_file"] = row["source_file"]
            n_corrected += 1
            continue

        # AI-silver row being upgraded to a human label.
        idx = prev.index[(~val_mask_prev) & (prev["text"].astype(str) == text_key)][0]
        prev.loc[idx, "label"] = row["label"]
        prev.loc[idx, "raw_label"] = row["raw_label"]
        prev.loc[idx, "weight"] = row["weight"]
        prev.loc[idx, "source_file"] = row["source_file"]
        prev.loc[idx, "is_human"] = True
        n_upgraded += 1

    print(f"Of {len(dup_rows)} rows matching existing train text: "
          f"{n_confirmed} confirmed (already human-labeled, agreed), "
          f"{n_corrected} corrected (two human labels disagreed, backlog label applied), "
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
            f"Val split changed size during merge: expected {val_mask_prev.sum()}, got {actual_val}. "
            "Check for text collisions between new rows and the frozen val set."
        )

    print(f"\nCombined: {len(combined):,} rows "
          f"(train={(combined['split']=='train').sum():,}, val={(combined['split']=='val').sum():,})")
    combined.to_parquet(OUT_PATH, index=False)
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
