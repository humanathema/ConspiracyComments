"""score_round9_binconf_v8_v9.py

Scores the full round9 unlabeled pool (22,459 rows) with binconf_other015
(confidence + predicted class) and, for rows binconf predicts as stanced
(hostile/endorsement), the v8 and v9 false-positive detectors -- the
same scoping convention established in score_round9_binconf_and_fpv4.py
(2026-08-21): the FP-detector lineage asks "is this row's implied stanced
label wrong", which is only a meaningful question for rows binconf itself
called stanced. Unlike v4, v8/v9 take text-only [ENTITY: X] input with no
silver-label tag baked in, so there's no risk of the v4 shortcut-learning
bug here -- the scoping is about task relevance, not a known failure mode.

Note the input path: /home/nash/round9_unlabeled_pool.parquet (NOT
data/processed/round9/round9_unlabeled_pool.parquet, which is where the
older score_round9_binconf_and_fpv4.py looked -- that path doesn't exist
on this VM; confirmed directly 2026-08-23/24 by both this session and the
peer session that wrote the 2026-08-23 handoff).

Output: data/processed/round9/round9_binconf_v8_v9_scores.parquet
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import pandas as pd
import numpy as np
from transformers import AutoModel, AutoTokenizer

BINCONF_CHECKPOINT = "/home/nash/retrain_twostage/binconf_other015_binary_confidence"
FPV8_CHECKPOINT = "/home/nash/retrain_twostage/fp_detector_v8_representative"
FPV9_CHECKPOINT = "/home/nash/retrain_twostage/fp_detector_v9_blindspot"
MODEL_NAME = "answerdotai/ModernBERT-large"
MAX_LENGTH = 768
BATCH_SIZE = 16
INPUT_PATH = "/home/nash/round9_unlabeled_pool.parquet"
OUT_PATH = "data/processed/round9/round9_binconf_v8_v9_scores.parquet"


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


class WrongLabelModel(nn.Module):
    def __init__(self, model_name):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size = self.encoder.config.hidden_size
        self.classifier = nn.Linear(hidden_size, 2)

    def forward(self, input_ids=None, attention_mask=None, **kwargs):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        last_hidden = out.last_hidden_state
        mask = attention_mask.unsqueeze(-1).float()
        pooled = (last_hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        return self.classifier(pooled)


def score_wrong_label_model(checkpoint_dir, texts, device):
    tokenizer = AutoTokenizer.from_pretrained(checkpoint_dir)
    model = WrongLabelModel(MODEL_NAME).to(device)
    state = torch.load(f"{checkpoint_dir}/model_state.pt", map_location=device)
    model.load_state_dict(state)
    model.eval()

    all_logits = []
    with torch.no_grad():
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            enc = tokenizer(batch, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt").to(device)
            logits = model(**enc)
            all_logits.append(logits.cpu())
            if i % (BATCH_SIZE * 50) == 0:
                print(f"  {i}/{len(texts)}", flush=True)
    logits = torch.cat(all_logits).numpy()
    probs = F.softmax(torch.tensor(logits), dim=1).numpy()[:, 1]
    del model
    torch.cuda.empty_cache()
    return probs


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}", flush=True)

    df = pd.read_parquet(INPUT_PATH)
    print(f"{len(df)} rows to score", flush=True)
    plain_texts = ("[ENTITY: " + df["target_entity"].fillna("unknown").astype(str) + "] " + df["text"].astype(str)).tolist()

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    # --- Pass 1: binconf_other015 ---
    print("\n=== Scoring with binconf_other015 ===", flush=True)
    binconf = ConfidenceModel(MODEL_NAME).to(device)
    state = torch.load(f"{BINCONF_CHECKPOINT}/model_state.pt", map_location=device)
    binconf.load_state_dict(state)
    binconf.eval()

    all_conf, all_logits = [], []
    with torch.no_grad():
        for i in range(0, len(plain_texts), BATCH_SIZE):
            batch = plain_texts[i:i + BATCH_SIZE]
            enc = tokenizer(batch, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt").to(device)
            logits, conf = binconf(**enc)
            all_conf.append(conf.cpu())
            all_logits.append(logits.cpu())
            if i % (BATCH_SIZE * 50) == 0:
                print(f"  {i}/{len(plain_texts)}", flush=True)
    confidence = torch.cat(all_conf).numpy()
    logits = torch.cat(all_logits).numpy()
    probs = F.softmax(torch.tensor(logits), dim=1).numpy()

    df["confidence"] = confidence
    df["binconf_predicted"] = np.where(
        confidence < 0.5, "other",
        np.where(probs[:, 0] >= probs[:, 1], "hostile", "endorsement"),
    )
    del binconf
    torch.cuda.empty_cache()

    df.to_parquet(OUT_PATH, index=False)
    print(f"Checkpointed after binconf pass: {OUT_PATH}", flush=True)
    print(df["binconf_predicted"].value_counts(), flush=True)

    # --- Pass 2 & 3: v8, v9 (only rows binconf predicts as stanced) ---
    stanced_mask = df["binconf_predicted"] != "other"
    n_skipped = (~stanced_mask).sum()
    print(f"\nScoring v8/v9 for {stanced_mask.sum()} binconf-predicted-stanced rows "
          f"(skipping {n_skipped} binconf-predicted-other rows -- not this detector's task)", flush=True)

    fp_texts = ("[ENTITY: " + df.loc[stanced_mask, "target_entity"].fillna("unknown").astype(str)
                + "] " + df.loc[stanced_mask, "text"].astype(str)).tolist()

    df["fp_v8_score"] = np.nan
    df["fp_v9_score"] = np.nan

    print("\n=== Scoring with v8 ===", flush=True)
    df.loc[stanced_mask, "fp_v8_score"] = score_wrong_label_model(FPV8_CHECKPOINT, fp_texts, device)
    df.to_parquet(OUT_PATH, index=False)
    print(f"Checkpointed after v8 pass: {OUT_PATH}", flush=True)

    print("\n=== Scoring with v9 ===", flush=True)
    df.loc[stanced_mask, "fp_v9_score"] = score_wrong_label_model(FPV9_CHECKPOINT, fp_texts, device)

    df.to_parquet(OUT_PATH, index=False)
    print(f"\nSaved final: {OUT_PATH}", flush=True)
    print(f"binconf predicted other: {n_skipped}", flush=True)
    print(f"binconf predicted stanced (v8/v9 scored): {stanced_mask.sum()}", flush=True)


if __name__ == "__main__":
    main()
