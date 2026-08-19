"""score_binconf_on_aleatoric.py

Scores binconf_other015 against the 418-usable-row aleatoric held-out set
(data/hitl/queue_escalation_round8_aleatoric.csv, 425 rows total, human-
labeled) -- the SAME held-out check used to find that r7v3_retrain_redesign's
strong val680 kappa (0.5374) was a real overfitting artifact (aleat kappa
0.2116, see handoff/round8_state_v4.md section 4), while r7v3_retrain_
baseline generalized well (val 0.5283 -> aleat 0.5594).

binconf_other015 has only ever been checked against val680 (0.7386 polarity
kappa) -- never against this genuinely-held-out aleatoric set. This gives
the first apples-to-apples comparison against r7v3_retrain_baseline's 0.5594
aleat number.

Usable rows: human_label in {hostile, endorsement} only (418/425) -- matches
the project's standard polar-only convention.
"""
import sys

import os
sys.path.insert(0, "src")
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import cohen_kappa_score, classification_report
from transformers import AutoModel, AutoTokenizer

CHECKPOINT = "outputs/checkpoints/binconf_other015_binary_confidence"
INPUT_FILE = os.environ.get("INPUT_FILE", "data/hitl/queue_escalation_round8_aleatoric.csv")
OUT_PATH = os.environ.get("OUT_PATH", "outputs/reinfer_probs/binconf_other015_aleatoric_scores.csv")
MAX_LENGTH = 768
LABEL_TO_ID = {"hostile": 0, "endorsement": 1}


class ConfidenceModel(nn.Module):
    def __init__(self, model_name):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size = self.encoder.config.hidden_size
        self.classifier = nn.Linear(hidden_size, 2)
        self.confidence_head = nn.Linear(hidden_size, 1)

    def forward(self, input_ids=None, attention_mask=None, **kwargs):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        last_hidden = out.last_hidden_state
        mask = attention_mask.unsqueeze(-1).float()
        pooled = (last_hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        logits = self.classifier(pooled)
        confidence = torch.sigmoid(self.confidence_head(pooled)).squeeze(-1)
        return logits, confidence


def main():
    df = pd.read_csv(INPUT_FILE)
    print(f"{len(df)} total rows", flush=True)
    # ambiguous/neutral -> "other" for scoring, matching this project's
    # established 3-way convention (e.g. "combined 3-way kappa
    # (ambiguous->other for scoring)" used elsewhere) -- needed so the
    # OVERALL kappa computed here is the same metric as r7v3_retrain's
    # 0.5283/0.5594 (stage1 gate + stage2 polarity chained), not just a
    # polarity-only number that would silently compare apples to oranges.
    df["human_label_3way"] = df["human_label"].map(
        lambda x: x if x in ("hostile", "endorsement") else "other"
    )
    polar = df[df["human_label"].isin(["hostile", "endorsement"])].copy()
    print(f"{len(polar)} usable polar rows (excluding ambiguous/neutral) -- for polarity-only kappa", flush=True)
    print(f"human_label_3way distribution (n={len(df)}, for OVERALL kappa):", flush=True)
    print(df["human_label_3way"].value_counts().to_string(), flush=True)

    # Score ALL rows (not just polar) -- overall kappa needs the "other"
    # rows too, to test binconf's own confidence-threshold stage1 gate.
    texts = ("[ENTITY: " + df["target_entity"].fillna("unknown").astype(str) + "] "
              + df["full_text"].astype(str)).tolist()

    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Using device: {device}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained("answerdotai/ModernBERT-large")
    model = ConfidenceModel("answerdotai/ModernBERT-large")
    state = torch.load(f"{CHECKPOINT}/model_state.pt", map_location="cpu")
    model.load_state_dict(state)
    model.to(device)
    model.eval()

    all_logits, all_conf = [], []
    batch_size = 16
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            enc = tokenizer(batch, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt").to(device)
            logits, conf = model(**enc)
            all_logits.append(logits.cpu())
            all_conf.append(conf.cpu())
            if i % (batch_size * 5) == 0:
                print(f"  {i}/{len(texts)}", flush=True)

    logits = torch.cat(all_logits).numpy()
    confidence = torch.cat(all_conf).numpy()
    probs_polar = torch.softmax(torch.tensor(logits), dim=1).numpy()

    # OVERALL 3-way: confidence < 0.5 -> "other" (matches the established
    # stage1-proxy threshold, see experiment_log.jsonl binconf_other015
    # entry), else argmax(hostile, endorsement) -- computed on ALL 425 rows.
    pred_3way = np.where(
        confidence < 0.5, "other",
        np.where(probs_polar[:, 0] >= probs_polar[:, 1], "hostile", "endorsement"),
    )
    true_3way = df["human_label_3way"].values
    overall_kappa = cohen_kappa_score(true_3way, pred_3way)

    # Polarity-only: argmax on the polar subset alone (matches how binconf's
    # 0.7386 val polarity kappa was computed) -- useful context, NOT the
    # number to compare against r7v3_retrain's 0.5283/0.5594/0.2116.
    is_polar = df["human_label"].isin(["hostile", "endorsement"]).values
    true_polar = df.loc[is_polar, "human_label"].map(LABEL_TO_ID).values
    pred_polar = np.argmax(logits[is_polar], axis=1)
    polarity_kappa = cohen_kappa_score(true_polar, pred_polar)

    print(f"\n=== binconf_other015 on aleatoric held-out set (n={len(df)}) ===", flush=True)
    print(f"OVERALL 3-way kappa (hostile/endorsement/other, n={len(df)}): {overall_kappa:.4f}", flush=True)
    print(f"Polarity-only kappa (hostile/endorsement, n={is_polar.sum()}): {polarity_kappa:.4f}", flush=True)
    print(f"mean self-confidence: {confidence.mean():.4f}", flush=True)
    print(classification_report(true_polar, pred_polar, target_names=["hostile", "endorsement"]), flush=True)

    print("\n=== Fair comparison against handoff/round8_state_v4.md section 4 (all overall 3-way kappa) ===", flush=True)
    print(f"  r7v3_retrain_baseline:  val680=0.5283  aleat418=0.5594  (generalizes well)", flush=True)
    print(f"  r7v3_retrain_redesign:  val680=0.5374  aleat418=0.2116  (overfit, disqualified)", flush=True)
    print(f"  binconf_other015:       val680=0.5219  aleat425={overall_kappa:.4f}", flush=True)

    out = df[["id", "target_entity", "human_label", "human_label_3way"]].copy()
    out["pred_3way"] = pred_3way
    out["confidence"] = confidence
    out.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
