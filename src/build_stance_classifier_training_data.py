"""build_stance_classifier_training_data.py

Consolidates every real, human-labeled stance rating queue in data/hitl/
into one clean training set for fine-tuning a proper transformer-based
stance classifier (see handoff docs for why: the current production
classifier is TF-IDF + LogisticRegression, kappa 0.345, and independent
AIITL audits this session found only 33-36% agreement with a small judge
model on a stratified sample -- corroborated by a bigger model on the
disagreement subset). Also folds in today's AI-silver labels (the AIITL
judge outputs) as weakly-supervised additional signal, kept separate from
the gold human labels so training can weight them differently.

Deliberately excludes: personal_experience/procedural_skepticism/
maverick_authority queues (different constructs entirely, not stance --
their label taxonomy is positive/lean_positive/negative/unsure, not
endorsement/hostile/neutral/ambiguous), and hedged_suspicion queues
(also a different construct). Only files using the stance taxonomy
(endorsement/hostile/neutral/ambiguous/wrong_match) are stance data.

Where a queue has both a base file and a more-complete _REVIEW or
_BACKUP variant (checked by hand: same ids, same labels, REVIEW/BACKUP
just has more columns or more complete labeling), the more-complete
variant is used, not both -- avoids double-counting the same examples.

wrong_match rows are dropped, not remapped: they mean the entity mention
itself was spurious/misidentified, not that the stance judgment was hard
-- a different failure mode than what this classifier predicts.
neutral and ambiguous are both collapsed into 'other' to match the
production classifier's 3-way scheme (hostile/endorsement/other).

Output: data/processed/stance_classifier_training_data.parquet
  text | label | source | weight | split | target_entity | entity_spans
    source: 'human' or one of the AI-silver source tags
    weight: 1.0 for human labels, lower for AI-silver (configurable)
    split: 'train' or 'val' (stratified 85/15 by label, human labels only
      in val -- never validate against silver labels)
    target_entity: best-effort single entity this stance judgment is
      about (see ENTITY_QUEUE_MAP / entity_spans handling below). None
      where it can't be determined without guessing.
    entity_spans: raw JSON string from the source queue when present
      (start/end/text per mention, possibly multiple different entities
      per row for the general maverick/consensus queues) -- kept
      alongside target_entity rather than instead of it, since collapsing
      to one entity is lossy for genuinely multi-entity comments.

Entity identity was previously dropped entirely at this consolidation
step even though most source queues have it (either an entity_spans
column, or -- for the single-entity quality-check queues -- the entity is
fixed by which queue the row came from). Recovering it after the fact via
fuzzy text-matching joins (tried in an exploratory notebook) is fragile;
carrying it through here at build time from the same source files this
script already reads is not.
"""
import glob
import json
import os

import pandas as pd

HITL_DIR = "data/hitl"
OUT_PATH = "data/processed/stance_classifier_training_data.parquet"

# Single-entity quality-check queues: the entity isn't ambiguous or worth
# parsing out of entity_spans -- every row in these files is about this
# one entity by construction (see build_*_stance_quality_check queue
# builders). Matched as a case-insensitive substring of the filename.
# Canonical spelling taken from maverick_authority_verified.py.
ENTITY_QUEUE_MAP = {
    "assange": "Julian Assange",
    "wikileaks": "WikiLeaks",
    "snowden": "Edward Snowden",
    "greenwald": "Glenn Greenwald",
    "jones": "Alex Jones",
}


def _target_entity_for_queue(fname: str) -> str | None:
    lower = fname.lower()
    for needle, canonical in ENTITY_QUEUE_MAP.items():
        if needle in lower:
            return canonical
    return None


def _first_span_entity(entity_spans_json) -> str | None:
    """Best-effort single entity from a general (multi-entity-capable)
    queue's entity_spans column -- first match, not a disambiguation.
    Real limitation: rows with >1 distinct entity in entity_spans (e.g. a
    comment mentioning both a maverick and a consensus figure) only get
    their first-found entity recorded here; the full set is still in
    entity_spans for anyone who needs it."""
    if not isinstance(entity_spans_json, str) or not entity_spans_json.strip():
        return None
    try:
        spans = json.loads(entity_spans_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not spans:
        return None
    return spans[0].get("text")

# Prefer the more-complete variant over its base file (checked by hand,
# see docstring) -- listed as (variant_to_use, base_to_skip).
PREFER_VARIANT = {
    "queue_ats_stance_quality_check_BACKUP_56rated.csv": "queue_ats_stance_quality_check.csv",
    "queue_assange_stance_quality_check_REVIEW.csv": "queue_assange_stance_quality_check.csv",
    "queue_greenwald_stance_quality_check_REVIEW.csv": "queue_greenwald_stance_quality_check.csv",
    "queue_jones_short_stance_quality_check_REVIEW.csv": "queue_jones_short_stance_quality_check.csv",
    "queue_jones_stance_quality_check_REVIEW.csv": "queue_jones_stance_quality_check.csv",
    "queue_snowden_stance_quality_check_REVIEW.csv": "queue_snowden_stance_quality_check.csv",
    "queue_wikileaks_stance_quality_check_REVIEW.csv": "queue_wikileaks_stance_quality_check.csv",
}

STANCE_LABELS = {"endorsement", "hostile", "neutral", "ambiguous", "wrong_match"}

LABEL_MAP = {
    "endorsement": "endorsement",
    "hostile": "hostile",
    "neutral": "other",
    "ambiguous": "other",
    # wrong_match dropped entirely, handled below
}


def load_human_queues():
    skip = set(PREFER_VARIANT.values())
    rows = []
    for path in sorted(glob.glob(os.path.join(HITL_DIR, "*.csv"))):
        fname = os.path.basename(path)
        if fname in skip:
            continue
        try:
            df = pd.read_csv(path, low_memory=False)
        except Exception as exc:
            print(f"  [skip] {fname}: read error ({exc})")
            continue
        label_col = "human_stance" if "human_stance" in df.columns else (
            "human_label" if "human_label" in df.columns else None
        )
        if label_col is None or "full_text" not in df.columns:
            continue
        df = df[df[label_col].notna()].copy()
        if df.empty:
            continue
        # Only keep files actually using the stance taxonomy -- this is
        # what excludes personal_experience/procedural_skepticism/
        # maverick_authority/hedged_suspicion automatically, no hardcoded
        # filename list needed.
        if not set(df[label_col].unique()).issubset(STANCE_LABELS):
            continue
        df = df[df[label_col] != "wrong_match"]
        if df.empty:
            continue
        df["label"] = df[label_col].map(LABEL_MAP)
        df["raw_label"] = df[label_col]  # pre-collapse value: endorsement/hostile/neutral/ambiguous
        df["source_file"] = fname

        entity_spans = df["entity_spans"] if "entity_spans" in df.columns else None
        fixed_entity = _target_entity_for_queue(fname)
        if fixed_entity is not None:
            # Single-entity queue: entity is known regardless of what
            # else entity_spans happens to match in the same comment.
            df["target_entity"] = fixed_entity
        elif entity_spans is not None:
            df["target_entity"] = entity_spans.apply(_first_span_entity)
        else:
            df["target_entity"] = None
        df["entity_spans"] = entity_spans if entity_spans is not None else None

        df["label_target_std"] = None  # only the IRR-shared queue has a real value (see load_irr_shared_rows)
        df["label_agreement_level"] = None
        n_with_entity = df["target_entity"].notna().sum()
        rows.append(
            df[["full_text", "label", "raw_label", "source_file", "target_entity", "entity_spans",
                "label_target_std", "label_agreement_level"]]
            .rename(columns={"full_text": "text"})
        )
        print(f"  [use]  {fname}: {len(df)} rows ({n_with_entity} with target_entity)")

    if os.environ.get("INCLUDE_IRR_SHARED", "1") != "0":
        irr_rows = load_irr_shared_rows()
        if not irr_rows.empty:
            rows.append(irr_rows)
            print(f"  [use]  queue_irr_stance_shared.csv (via ordinal_targets.csv majority_label): {len(irr_rows)} rows")

    if not rows:
        return pd.DataFrame(columns=["text", "label", "raw_label", "source_file", "target_entity", "entity_spans",
                                      "label_target_std", "label_agreement_level"])
    combined = pd.concat(rows, ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(subset=["text", "label"])
    if len(combined) != before:
        print(f"  Dropped {before - len(combined)} exact text+label duplicates across queues.")
    return combined


IRR_QUEUE_PATH = os.path.join(HITL_DIR, "queue_irr_stance_shared.csv")
ORDINAL_TARGETS_PATH = "data/processed/ordinal_targets.csv"


def load_irr_shared_rows():
    """The 99 genuinely triple-rated (Tobias/Jono/Lw) IRR rows.

    queue_irr_stance_shared.csv's own human_stance column is 100% null --
    the real per-rater votes only exist in ordinal_targets.csv (built
    separately from the raw vote_Tobias/vote_Jono/vote_Lw columns). The
    normal load_human_queues() filter (drop rows where human_stance is
    null) silently excluded all 99 rows from training entirely, not just
    from having a confidence weight -- this recovers them, using
    majority_label as the label and target_std/agreement_level as a real,
    non-invented confidence signal (unlike every other row in this build,
    which has no genuine second-rater signal to draw on)."""
    if not (os.path.exists(IRR_QUEUE_PATH) and os.path.exists(ORDINAL_TARGETS_PATH)):
        return pd.DataFrame()
    queue = pd.read_csv(IRR_QUEUE_PATH, low_memory=False)
    targets = pd.read_csv(ORDINAL_TARGETS_PATH)

    merged = targets.merge(queue, on="id", how="inner")
    if len(merged) != len(targets):
        print(f"  [warn] only {len(merged)}/{len(targets)} ordinal_targets ids matched queue_irr_stance_shared.csv")

    entity_spans = merged["entity_spans"] if "entity_spans" in merged.columns else None
    return pd.DataFrame({
        "text": merged["full_text"],
        "label": merged["majority_label"],
        "raw_label": merged["majority_label"],  # majority vote already collapses to the 3-way scheme
        "source_file": "queue_irr_stance_shared.csv",
        "target_entity": merged["target_entity"] if "target_entity" in merged.columns else None,
        "entity_spans": entity_spans,
        # 0.0 = unanimous, higher = more rater disagreement (NOT
        # "confidence" -- higher is less confident, named for what it
        # literally is to avoid an inverted-sense column name). Stored
        # as-is, not yet converted into a training weight -- that
        # conversion is a separate, later design decision.
        "label_target_std": merged["target_std"],
        "label_agreement_level": merged["agreement_level"],
        # Genuine fractional consensus score (-1..+1) from the real
        # triple-rater vote, e.g. 0.3333 for a 2-endorsement/1-hostile
        # split -- only these 94 rows have this; everything else in the
        # build only ever has a forced -1/0/+1 label.
        "label_target_score": merged["target_score"],
    })


def load_ai_silver_labels():
    """AI-judged labels from this session's AIITL work, kept as a
    separate lower-trust signal. Only includes cases with real
    corroboration, not raw small-model output:
    - entity_stance rows where the 1.5B judge AGREED with the classifier
      (876 of 2,518) -- both systems agreeing is itself weak evidence
      the label is right, used as silver-standard, not gold.
    - entity_stance disagreement rows where the 7B re-judge sided with
      the 1.5B judge at high/medium confidence -- this is the strongest
      silver signal available (two independent models agreeing against
      the classifier), used with the 7B's own label.
    """
    rows = []

    judged_path = "/tmp/entity_stance_pull/entity_stance_judged.parquet"
    if os.path.exists(judged_path):
        df = pd.read_parquet(judged_path)
        df["real_match"] = (
            df["predicted_label"].str.lower().str.strip() == df["judged_label"].str.lower().str.strip()
        )
        agreed = df[df["real_match"] & (df["judged_label"] != "parse_error")]
        rows.append(pd.DataFrame({
            "text": agreed["text_window"],
            "label": agreed["judged_label"],
            "source_file": "ai_silver__entity_stance_agreed",
            "target_entity": agreed["entity_key"] if "entity_key" in agreed.columns else None,
        }))
        print(f"  [ai]   entity_stance agreed-with-classifier: {len(agreed)} rows")

    bigmodel_path = "data/processed/entity_stance_bigmodel_judged.parquet"
    if os.path.exists(bigmodel_path):
        df = pd.read_parquet(bigmodel_path)
        trusted = df[
            (df["bigmodel_confidence"].isin(["high", "medium"]))
            & (df["bigmodel_label"] == df["judged_label"])
            & (df["bigmodel_label"] != df["predicted_label"])
        ]
        rows.append(pd.DataFrame({
            "text": trusted["text_window"],
            "label": trusted["bigmodel_label"],
            "source_file": "ai_silver__entity_stance_7b_corrected",
            "target_entity": trusted["entity_key"] if "entity_key" in trusted.columns else None,
        }))
        print(f"  [ai]   entity_stance 7B-corrected (2 models agree, override classifier): {len(trusted)} rows")

    if not rows:
        return pd.DataFrame(columns=["text", "label", "source_file", "target_entity"])
    combined = pd.concat(rows, ignore_index=True)
    combined = combined[combined["label"].isin(["hostile", "endorsement", "other"])]
    return combined.drop_duplicates(subset=["text", "label"])


def main():
    print("Loading human-labeled queues...")
    human = load_human_queues()
    human["weight"] = 1.0
    human["is_human"] = True

    print("\nLoading AI-silver labels...")
    silver = load_ai_silver_labels()
    silver["weight"] = 0.5
    silver["is_human"] = False

    combined = pd.concat([human, silver], ignore_index=True)
    combined = combined.dropna(subset=["text", "label"])
    combined = combined[combined["text"].str.strip() != ""]

    # Stratified 85/15 split by label, human rows only in val -- never
    # validate a model against its own weakly-supervised training signal.
    import numpy as np
    rng = np.random.RandomState(42)
    combined["split"] = "train"
    human_mask = combined["is_human"]
    for label in combined.loc[human_mask, "label"].unique():
        idx = combined[human_mask & (combined["label"] == label)].index
        n_val = max(1, int(len(idx) * 0.15))
        val_idx = rng.choice(idx, size=n_val, replace=False)
        combined.loc[val_idx, "split"] = "val"

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    combined.to_parquet(OUT_PATH, index=False)

    print(f"\nSaved {len(combined):,} rows to {OUT_PATH}")
    print(f"  Human: {human_mask.sum():,} | AI-silver: {(~human_mask).sum():,}")
    print(f"  Train: {(combined['split']=='train').sum():,} | Val: {(combined['split']=='val').sum():,}")
    print("\nLabel distribution (human only):")
    print(combined[human_mask]["label"].value_counts())
    print("\nLabel distribution (AI-silver only):")
    print(combined[~human_mask]["label"].value_counts())

    n_with_entity = combined["target_entity"].notna().sum()
    print(f"\nRows with target_entity: {n_with_entity:,} / {len(combined):,} ({n_with_entity/len(combined):.1%})")
    print("Top target_entity values:")
    print(combined["target_entity"].value_counts().head(15))


if __name__ == "__main__":
    main()
