"""build_entity_mentions_cache_v2.py

Rescores the round9 215-entity full mention pool (data/processed/round9/
full_entity_mention_pool.parquet -- built via build_full_entity_mention_pool.py,
see handoff/task_2026-08-18_session_handoff_full_entity_pool_and_cascade_design.md
for the disambiguation/dedup/domain-matching fixes that went into it) with
the CURRENT best classifier checkpoint, instead of build_entity_mentions_
cache.py's stance_classifier_2stage_pooled.joblib (dated 2026-07-22, an
older sklearn TF-IDF cascade) and the narrower entity_categories_lookup.csv-
derived entity set it was built against.

Deliberately modular: CHECKPOINT_DIR is the one thing to change to rerun
this against a future classifier checkpoint as Nash's cascade/false-
positive-detector work lands -- nothing else in this script is tied to
today's specific checkpoint.

Output schema matches entity_mentions_cache_2stage_pooled.parquet (comment_id
| entity_key | construct | p_hostile | p_endorsement | p_other |
predicted_label) so it's a drop-in for rerun_maverick_whistleblower_split.py
and similar downstream consumers -- just point CACHE_PATH at this file's
output instead.

METHODOLOGICAL SIMPLIFICATION vs the original cache (flagged explicitly,
not silently): the original cache built MERGED text windows (combining
spans when a comment mentions multiple same-subgroup entities) before a
single model call per merged window. The round9 pool is already one row
per (comment, entity) mention with its own pre-extracted window text; this
script scores at that per-mention granularity and aggregates to
merged_whistleblower/merged_other_maverick via a comment-count-weighted
mean of p_hostile/p_endorsement/p_other across same-subgroup mentions in
the same comment, rather than re-deriving a merged window and rescoring
it. Close approximation, not byte-identical methodology -- worth knowing
if a result from this cache doesn't reproduce the original cache's numbers
exactly even controlling for the classifier-version change.

Only scores entity_category in ('maverick', 'consensus') and population
=='long' (the reddit long-comment corpus that rerun_maverick_whistleblower_
split.py's downstream regressions actually join against via comment id) --
skips alt_media/leak_whistleblower (domain-level entities, not used by
the current whistleblower/other_maverick person-level split) and the
short-comment population, to keep runtime down given the 1-week deadline.
Rerun with those filters loosened if a future analysis needs them.
"""
import os
import sys

import numpy as np
import pandas as pd
import torch
from transformers import AutoTokenizer

sys.path.insert(0, os.path.dirname(__file__))
from train_binary_confidence import ConfidenceModel, MODEL_NAME

POOL_PATH = "data/processed/round9/full_entity_mention_pool.parquet"
LOOKUP_PATH = "data/processed/entity_categories_lookup.csv"
CHECKPOINT_DIR = "outputs/checkpoints/binconf_other015_binary_confidence"
OUT_PARQUET = "data/processed/entity_mentions_cache_binconf_other015.parquet"
OUT_CSV = "data/processed/entity_mentions_cache_binconf_other015.csv"

MAX_LENGTH = 768
BATCH_SIZE = 32  # matches score_fp_detector_full_train.py's full-scale override
CONFIDENCE_THRESHOLD = 0.5  # matches the established stage1-proxy threshold
                             # (best kappa 0.348 at 0.5, see experiment_log.jsonl
                             # binconf_other015 entry, 2026-08-17)


def score_batch(model, tokenizer, texts, device):
    """Single forward pass: confidence (stage1 proxy) + hostile/endorsement
    logits. Same pattern as score_and_embed() in train_false_positive_
    detector.py / score_fp_detector_full_train.py, without the pooled-
    embedding return (not needed here)."""
    all_conf, all_logits = [], []
    with torch.no_grad():
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            enc = tokenizer(batch, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt").to(device)
            logits, confidence = model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"])
            all_conf.append(confidence.cpu())
            all_logits.append(logits.cpu())
            if (i // BATCH_SIZE) % 50 == 0:
                print(f"  scored {i + len(batch):,}/{len(texts):,}", flush=True)
    return torch.cat(all_conf).numpy(), torch.cat(all_logits).numpy()


def main():
    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Using device: {device}", flush=True)

    print(f"Loading round9 pool from {POOL_PATH}...")
    df = pd.read_parquet(POOL_PATH)
    df = df[(df["entity_category"].isin(["maverick", "consensus"])) & (df["population"] == "long")].copy()
    print(f"Filtered to {len(df):,} rows (maverick+consensus, long population).")

    print(f"Loading entity category lookup from {LOOKUP_PATH}...")
    lookup_df = pd.read_csv(LOOKUP_PATH)
    entity_to_cat = dict(zip(lookup_df["entity_key"], lookup_df["category"]))

    df["entity_key"] = df["target_entity"].str.lower()
    df["subgroup"] = np.where(
        df["entity_category"] == "maverick",
        df["entity_key"].map(entity_to_cat).apply(lambda c: "whistleblower" if c == "whistleblower" else "other_maverick"),
        np.nan,
    )
    unmapped = df[(df["entity_category"] == "maverick") & (~df["entity_key"].isin(entity_to_cat))]["entity_key"].unique()
    if len(unmapped):
        print(f"WARNING: {len(unmapped)} maverick entity_key(s) not found in {LOOKUP_PATH}, "
              f"defaulted to other_maverick: {sorted(unmapped)}")

    print("Loading binconf_other015 checkpoint...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = ConfidenceModel(MODEL_NAME).to(device)
    state = torch.load(f"{CHECKPOINT_DIR}/model_state.pt", map_location=device)
    model.load_state_dict(state)
    model.eval()

    texts = ("[ENTITY: " + df["target_entity"].fillna("unknown").astype(str) + "] " + df["text"].astype(str)).tolist()
    print(f"Scoring {len(texts):,} mentions...", flush=True)
    confidence, logits = score_batch(model, tokenizer, texts, device)

    logits_t = torch.tensor(logits)
    probs_polar = torch.softmax(logits_t, dim=1).numpy()  # [:, 0]=hostile, [:, 1]=endorsement
    p_clear = confidence
    p_other = 1.0 - p_clear
    p_hostile = p_clear * probs_polar[:, 0]
    p_endorsement = p_clear * probs_polar[:, 1]

    df["p_hostile"] = p_hostile
    df["p_endorsement"] = p_endorsement
    df["p_other"] = p_other
    df["predicted_label"] = np.where(
        p_clear < CONFIDENCE_THRESHOLD, "other",
        np.where(probs_polar[:, 0] >= probs_polar[:, 1], "hostile", "endorsement"),
    )

    # Per-entity granularity, matches the original cache's schema directly.
    per_entity = df[["id", "entity_key", "entity_category", "p_hostile", "p_endorsement", "p_other", "predicted_label"]].rename(
        columns={"id": "comment_id", "entity_category": "construct"}
    )

    # Merged-subgroup granularity for maverick rows only (comment-count-
    # weighted mean across same-subgroup mentions in the same comment --
    # see module docstring for how this differs from the original merged-
    # window methodology).
    mav = df[df["entity_category"] == "maverick"].copy()
    merged = (
        mav.groupby(["id", "subgroup"])
        .agg(p_hostile=("p_hostile", "mean"), p_endorsement=("p_endorsement", "mean"), p_other=("p_other", "mean"))
        .reset_index()
    )
    merged["entity_key"] = "merged_" + merged["subgroup"]
    merged["construct"] = "maverick"
    merged["predicted_label"] = np.where(
        (1.0 - merged["p_other"]) < CONFIDENCE_THRESHOLD, "other",
        np.where(merged["p_hostile"] >= merged["p_endorsement"], "hostile", "endorsement"),
    )
    merged = merged.rename(columns={"id": "comment_id"})[
        ["comment_id", "entity_key", "construct", "p_hostile", "p_endorsement", "p_other", "predicted_label"]
    ]

    out = pd.concat([per_entity, merged], ignore_index=True)
    out.to_parquet(OUT_PARQUET, index=False)
    out.to_csv(OUT_CSV, index=False)
    print(f"\nSaved {len(out):,} rows to {OUT_PARQUET} and {OUT_CSV}")
    print(f"\nSubgroup mention counts (per-entity rows, maverick only):")
    print(mav.groupby("subgroup").size())
    print(f"\npredicted_label distribution:")
    print(out["predicted_label"].value_counts())


if __name__ == "__main__":
    main()
