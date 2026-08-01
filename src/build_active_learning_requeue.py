"""build_active_learning_requeue.py

Active-learning re-review queue: scores every HUMAN-labeled row in the
current training data against the verified two-stage baseline model
(stance_stage1_baseline / stance_stage2_baseline), and surfaces the rows
where the model most confidently disagrees with the recorded label --
prioritized so the highest-value corrections come first.

This directly tests Nash's own stated hypothesis (2026-08-01): some
"other" labels are really skimmed/defaulted-to-other endorsement or
hostile rows, not genuinely ambiguous content -- and possibly some
hostile/endorsement labels are wrong too. Rather than an unsupervised
similarity-propagation mechanism (rejected as an overfitting/validity
risk -- see conversation), this is the safe version: active learning.
Every correction Nash makes here is a real, reviewed label change; the
"one correction improves many" effect comes from periodically retraining
on the corrected data, not from auto-propagating to unreviewed rows.

Priority tiers (highest first):
  1. label == "other", model confidently predicts hostile/endorsement
     -- directly tests the "defaulted to other" hypothesis.
  2. label in {hostile, endorsement}, model confidently predicts a
     DIFFERENT label (including other) -- catches the "some hostile/
     endorse could be wrong too" worry.
  3. boundary cases (stage1 or stage2 probability near 0.5) regardless
     of agreement -- secondary, smaller tier.

Output: data/hitl/queue_active_learning_requeue.csv, in the same schema
hitl_rater.py already expects (id/full_text/human_stance/notes/
entity_spans/target_entity), plus extra diagnostic columns
(current_label/predicted_label/confidence/tier) kept for transparency --
NOT shown to the rater by the existing hitl_rater.py UI, just useful for
review/debugging this script's own output.
"""
import os

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from transformers import AutoModelForSequenceClassification, AutoTokenizer

TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
STAGE1_MODEL_PATH = os.environ.get("STAGE1_MODEL_PATH", "/tmp/kaggle_results_arm1/stance_stage1_baseline")
STAGE2_MODEL_PATH = os.environ.get("STAGE2_MODEL_PATH", "/tmp/kaggle_results_arm1/stance_stage2_baseline")
OUT_PATH = "data/hitl/queue_active_learning_requeue.csv"

BOUNDARY_WIDTH = 0.10  # within +/-0.10 of 0.5 counts as "boundary"
MAX_ROWS = 150  # cap the queue size -- this is meant to feed a few-at-a-time review, not a big backlog


def score_all(df, tokenizer, stage1_model, stage2_model):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    stage1_model.to(device).eval()
    stage2_model.to(device).eval()

    texts = df["text"].tolist()
    batch_size = 32
    stage1_probs, stage2_probs = [], []

    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            enc = tokenizer(batch, truncation=True, padding=True, max_length=512, return_tensors="pt").to(device)
            s1_out = F.softmax(stage1_model(**enc).logits, dim=-1).cpu().numpy()
            s2_out = F.softmax(stage2_model(**enc).logits, dim=-1).cpu().numpy()
            stage1_probs.append(s1_out)
            stage2_probs.append(s2_out)
            print(f"  scored {min(i+batch_size, len(texts))}/{len(texts)}", flush=True)

    stage1_probs = np.concatenate(stage1_probs, axis=0)  # [:,1] = p(has_stance)
    stage2_probs = np.concatenate(stage2_probs, axis=0)  # [:,1] = p(endorsement)

    p_has_stance = stage1_probs[:, 1]
    p_endorsement_given_stance = stage2_probs[:, 1]

    predicted = []
    confidence = []
    for p1, p2 in zip(p_has_stance, p_endorsement_given_stance):
        if p1 < 0.5:
            predicted.append("other")
            confidence.append(1 - p1)  # confidence in "other"
        elif p2 >= 0.5:
            predicted.append("endorsement")
            confidence.append(p1 * p2)
        else:
            predicted.append("hostile")
            confidence.append(p1 * (1 - p2))

    df = df.copy()
    df["p_has_stance"] = p_has_stance
    df["p_endorsement_given_stance"] = p_endorsement_given_stance
    df["predicted_label"] = predicted
    df["confidence"] = confidence
    return df


def assign_tier(row):
    if row["label"] == "other" and row["predicted_label"] in ("hostile", "endorsement"):
        return 1
    if row["label"] in ("hostile", "endorsement") and row["predicted_label"] != row["label"]:
        return 2
    is_boundary_s1 = abs(row["p_has_stance"] - 0.5) < BOUNDARY_WIDTH
    is_boundary_s2 = row["p_has_stance"] >= 0.5 and abs(row["p_endorsement_given_stance"] - 0.5) < BOUNDARY_WIDTH
    if is_boundary_s1 or is_boundary_s2:
        return 3
    return None  # not flagged -- model agrees confidently, not worth re-checking


def main():
    df = pd.read_parquet(TRAINING_DATA_PATH)
    human = df[df["is_human"]].copy()
    print(f"Scoring {len(human)} human-labeled rows against the baseline two-stage model...", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(STAGE1_MODEL_PATH)
    stage1_model = AutoModelForSequenceClassification.from_pretrained(STAGE1_MODEL_PATH)
    stage2_model = AutoModelForSequenceClassification.from_pretrained(STAGE2_MODEL_PATH)

    scored = score_all(human, tokenizer, stage1_model, stage2_model)
    scored["tier"] = scored.apply(assign_tier, axis=1)
    flagged = scored[scored["tier"].notna()].copy()
    print(f"\nFlagged {len(flagged)} / {len(scored)} rows across all tiers:", flush=True)
    print(flagged["tier"].value_counts().sort_index(), flush=True)

    # Sort: tier ascending (1 = highest priority), then confidence descending within tier
    flagged = flagged.sort_values(["tier", "confidence"], ascending=[True, False])
    flagged = flagged.head(MAX_ROWS)

    queue = pd.DataFrame({
        "id": [f"al_{i:04d}" for i in range(len(flagged))],
        "full_text": flagged["text"],
        "human_stance": "",  # blank for re-rating, matches existing queue convention
        "notes": "",
        "entity_spans": flagged["entity_spans"],
        "target_entity": flagged["target_entity"],
        # Diagnostic columns, not rendered by the existing hitl_rater.py UI,
        # kept for anyone auditing this script's own row selection later.
        "current_label": flagged["label"],
        "predicted_label": flagged["predicted_label"],
        "confidence": flagged["confidence"].round(3),
        "tier": flagged["tier"],
        "source_file": flagged["source_file"],
    })

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    queue.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(queue)} rows to {OUT_PATH}", flush=True)
    print("\nTier 1 sample (label=other, model confidently says hostile/endorsement):", flush=True)
    print(queue[queue["tier"] == 1][["current_label", "predicted_label", "confidence"]].head(10), flush=True)


if __name__ == "__main__":
    main()
