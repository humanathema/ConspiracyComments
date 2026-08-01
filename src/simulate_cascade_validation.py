"""simulate_cascade_validation.py

Offline validation of the tier2(classifier) -> tier3(frontier judge)
escalation cascade, using data we've already paid for tonight -- zero
new API calls. Nash's question (2026-08-01): before deploying the
cascade on the full corpus, we need a held-out validation of it, but
without a fresh expensive labeling round.

Key insight: the 212-row val split (real human ground truth, never
used to train the classifier) has now ALSO been independently scored by
the frontier judge tonight (stance_frontier_val_diagnostic.parquet,
kappa=0.8266 alone). That means for this one val set we already have
all three ingredients needed to simulate the cascade end-to-end:
  - true label (ground truth)
  - tier2 (trained classifier) probability/confidence per row
  - tier3 (frontier judge) score per row
So we can sweep escalation thresholds ("send to frontier when tier2's
confidence margin is below X") entirely offline and measure the
resulting COMBINED accuracy/kappa at each threshold, plus what fraction
of rows would actually get escalated (the real cost proxy for the full
corpus later) -- this validates the cascade POLICY, not just each
tier's isolated accuracy.

Requires local inference with the round2 stage1/stage2 model
checkpoints (pulled from the stance-retrain-corrected-round2 Kaggle
kernel output) against the val split -- CPU/MPS is fine, only 212 rows.

Output: printed threshold sweep table + saved
  data/processed/cascade_validation_sweep.csv
"""
import argparse

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from sklearn.metrics import cohen_kappa_score
from transformers import AutoModelForSequenceClassification, AutoTokenizer

TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
FRONTIER_VAL_PATH = "data/processed/stance_frontier_val_diagnostic.parquet"
OUT_PATH = "data/processed/cascade_validation_sweep.csv"

LABEL_TO_ID = {"hostile": 0, "endorsement": 1, "other": 2}


def score_batch(tokenizer, model, texts, device, max_length=512, batch_size=32):
    probs = []
    model.eval()
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            batch = list(texts[i:i + batch_size])
            enc = tokenizer(batch, truncation=True, padding=True, max_length=max_length, return_tensors="pt").to(device)
            out = F.softmax(model(**enc).logits, dim=-1).cpu().numpy()
            probs.append(out)
    return np.concatenate(probs, axis=0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage1-dir", required=True)
    parser.add_argument("--stage2-dir", required=True)
    args = parser.parse_args()

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"device: {device}", flush=True)

    base = pd.read_parquet(TRAINING_DATA_PATH)
    val_all = base[base["split"] == "val"].copy().reset_index(drop=True)
    print(f"val rows (all labels, incl 'other'): {len(val_all)}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(args.stage1_dir)
    stage1 = AutoModelForSequenceClassification.from_pretrained(args.stage1_dir).to(device)
    stage2 = AutoModelForSequenceClassification.from_pretrained(args.stage2_dir).to(device)

    s1_probs = score_batch(tokenizer, stage1, val_all["text"], device)
    s2_probs = score_batch(tokenizer, stage2, val_all["text"], device)
    val_all["p_has_stance"] = s1_probs[:, 1]
    val_all["p_endorsement"] = s2_probs[:, 1]

    # tier2's own combined 3-way prediction (same logic as the retrain script)
    val_all["tier2_pred"] = [
        "other" if p1 < 0.5 else ("endorsement" if p2 >= 0.5 else "hostile")
        for p1, p2 in zip(val_all["p_has_stance"], val_all["p_endorsement"])
    ]
    # confidence margin: distance from the nearest decision boundary tier2 actually used
    val_all["tier2_margin"] = np.where(
        val_all["p_has_stance"] < 0.5,
        (val_all["p_has_stance"] - 0.5).abs(),
        (val_all["p_endorsement"] - 0.5).abs(),
    )

    frontier = pd.read_parquet(FRONTIER_VAL_PATH)
    frontier = frontier[frontier["frontier_score"].notna()][["text", "frontier_score"]]
    merged = val_all.merge(frontier, on="text", how="left")
    has_frontier = merged["frontier_score"].notna()
    print(f"val rows with a frontier score available (hostile/endorsement only): {has_frontier.sum()}/{len(merged)}", flush=True)

    true_ids = merged["label"].map(LABEL_TO_ID).to_numpy()
    tier2_only_ids = merged["tier2_pred"].map(LABEL_TO_ID).to_numpy()
    tier2_only_kappa = cohen_kappa_score(true_ids, tier2_only_ids)
    print(f"\nTier2-only kappa (no escalation at all): {tier2_only_kappa:.4f}", flush=True)

    frontier_only = merged[has_frontier].copy()
    frontier_only["frontier_pred"] = np.where(frontier_only["frontier_score"] >= 0, "endorsement", "hostile")
    fo_true = frontier_only["label"].map(LABEL_TO_ID).to_numpy()
    fo_pred = frontier_only["frontier_pred"].map(LABEL_TO_ID).to_numpy()
    print(f"Frontier-only kappa on its {len(frontier_only)} eligible rows: {cohen_kappa_score(fo_true, fo_pred):.4f} (reference)", flush=True)

    print("\n=== Cascade sweep: escalate to frontier when tier2_margin < threshold ===", flush=True)
    rows = []
    for thresh in [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]:
        cascade_pred = merged["tier2_pred"].copy()
        escalate_mask = (merged["tier2_margin"] < thresh) & has_frontier
        cascade_pred.loc[escalate_mask] = np.where(
            merged.loc[escalate_mask, "frontier_score"] >= 0, "endorsement", "hostile"
        )
        cascade_ids = cascade_pred.map(LABEL_TO_ID).to_numpy()
        kappa = cohen_kappa_score(true_ids, cascade_ids)
        pct_escalated = escalate_mask.mean() * 100
        rows.append({"threshold": thresh, "pct_escalated": pct_escalated, "cascade_kappa": kappa})
        print(f"  threshold={thresh:.2f}  escalated={pct_escalated:5.1f}%  cascade_kappa={kappa:.4f}", flush=True)

    pd.DataFrame(rows).to_csv(OUT_PATH, index=False)
    print(f"\nSaved sweep to {OUT_PATH}", flush=True)
    print(f"(reference: tier2-only={tier2_only_kappa:.4f}, frontier-only-on-eligible={cohen_kappa_score(fo_true, fo_pred):.4f})", flush=True)


if __name__ == "__main__":
    main()
