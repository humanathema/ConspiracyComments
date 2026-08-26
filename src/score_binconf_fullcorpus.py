"""score_binconf_fullcorpus.py

Scores binconf_other015 over the full 451,815-row entity-mention corpus.
Needed for the validated non-frontier blend
(ensemble_binconf_blend_DISCREPANCY_RESOLVED, kappa 0.5656):
  combined = 0.7 * ensemble_p_hasstance + 0.3 * binconf_confidence
  threshold 0.55 -> stanced vs other

Input: full_entity_mention_pool.parquet
Output: binconf_fullcorpus_scores.parquet (id, target_entity, confidence,
  binconf_predicted)
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import pandas as pd
import numpy as np
from transformers import AutoModel, AutoTokenizer

BINCONF_CHECKPOINT = "/home/nash/retrain_twostage/binconf_other015_binary_confidence"
MODEL_NAME = "answerdotai/ModernBERT-large"
MAX_LENGTH = 768
BATCH_SIZE = 32
INPUT_PATH = "/home/nash/full_entity_mention_pool.parquet"
OUT_PATH = "/home/nash/binconf_fullcorpus_scores.parquet"


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
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}", flush=True)

    df = pd.read_parquet(INPUT_PATH)
    print(f"{len(df)} rows to score", flush=True)
    texts = ("[ENTITY: " + df["target_entity"].fillna("unknown").astype(str) + "] " + df["text"].astype(str)).tolist()

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = ConfidenceModel(MODEL_NAME).to(device)
    state = torch.load(f"{BINCONF_CHECKPOINT}/model_state.pt", map_location=device)
    model.load_state_dict(state)
    # NOTE: staying fp32 -- Nash recalls a low-precision (bf16, possibly
    # fp16) run causing NaN/zero-divide crashes on some model in this
    # project before, uncertain if it was this one. fp32 is confirmed
    # working on this exact checkpoint (ran cleanly for ~19K rows earlier
    # today before being stopped for an unrelated reason), so not worth
    # the risk for a ~2x speed gain.
    model.eval()

    all_conf, all_logits = [], []
    with torch.no_grad():
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            enc = tokenizer(batch, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt").to(device)
            logits, conf = model(**enc)
            all_conf.append(conf.cpu())
            all_logits.append(logits.cpu())
            if i % (BATCH_SIZE * 200) == 0:
                print(f"  {i}/{len(texts)}", flush=True)

    confidence = torch.cat(all_conf).numpy()
    logits = torch.cat(all_logits).numpy()
    probs = F.softmax(torch.tensor(logits), dim=1).numpy()

    df["confidence"] = confidence
    df["binconf_predicted"] = np.where(
        confidence < 0.5, "other",
        np.where(probs[:, 0] >= probs[:, 1], "hostile", "endorsement"),
    )

    df[["id", "target_entity", "confidence", "binconf_predicted"]].to_parquet(OUT_PATH, index=False)
    print(f"\nSaved {OUT_PATH}", flush=True)
    print(df["binconf_predicted"].value_counts(), flush=True)


if __name__ == "__main__":
    main()
