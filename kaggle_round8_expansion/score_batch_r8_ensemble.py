"""score_batch_r8_ensemble.py — Kaggle GPU kernel

Round 8 active-learning batch: train 5 ModernBERT-large models on current
training data, then score the 25k unlabeled batch. Filter uncertain rows
(ensemble margin < 0.45) for frontier escalation.

This is the correct pipeline — NOT the broken train_ensemble_score_batch.py.
Key fix: unlabeled_batch_r8_clean.parquet already has target_entity column.

Inputs (Kaggle datasets):
  /kaggle/input/stance-classifier-training-data/stance_classifier_training_data.parquet
  /kaggle/input/stance-round8-unlabeled-batch/unlabeled_batch_r8_clean.parquet

Outputs (/kaggle/working/):
  batch_ensemble_scores_r8.parquet   — all 25k rows with ensemble scores
  batch_escalation_candidates_r8.csv — uncertain rows (margin < 0.45) for frontier
  model_r8_*/                        — 5 saved model dirs (for potential reuse)
"""

import os
import json
import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    get_linear_schedule_with_warmup,
)
from torch.optim import AdamW
from tqdm import tqdm

# ── Fix multi-GPU DataParallel bug in ModernBERT ──────────────────────────
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

# ── Config ────────────────────────────────────────────────────────────────
MODEL_NAME  = "answerdotai/ModernBERT-large"
BATCH_SIZE  = 4
MAX_LENGTH  = 512
NUM_EPOCHS  = 2
LR          = 2e-5
WARMUP_FRAC = 0.1
MARGIN_THRESHOLD = 0.45

TRAIN_PATH  = "/kaggle/input/stance-classifier-training-data/stance_classifier_training_data.parquet"
BATCH_PATH  = "/kaggle/input/stance-round8-unlabeled-batch/unlabeled_batch_r8_clean.parquet"
OUT_DIR     = "/kaggle/working"

LABEL_MAP    = {"hostile": 0, "endorsement": 1, "other": 2}
ID_TO_LABEL  = {v: k for k, v in LABEL_MAP.items()}

# 5 seeds — same diversity approach as original r7v2/r7v1/r5v2/r5v2_split/r7v3 ensemble
SEEDS = [42, 7, 123, 17, 99]

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Device: {device}\n")


# ── Dataset ───────────────────────────────────────────────────────────────
class StanceDataset(Dataset):
    def __init__(self, texts, labels=None):
        self.texts  = texts
        self.labels = labels

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        item = {"text": self.texts[idx]}
        if self.labels is not None:
            item["label"] = self.labels[idx]
        return item


def collate(tokenizer, max_length):
    def _collate(batch):
        texts  = [b["text"] for b in batch]
        enc    = tokenizer(texts, max_length=max_length, truncation=True,
                           padding=True, return_tensors="pt")
        result = dict(enc)
        if "label" in batch[0]:
            result["labels"] = torch.tensor([b["label"] for b in batch],
                                             dtype=torch.long)
        return result
    return _collate


# ── Train one model ───────────────────────────────────────────────────────
def train_model(train_texts, train_labels, seed, model_tag):
    torch.manual_seed(seed)
    np.random.seed(seed)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model     = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME, num_labels=3,
        torch_dtype=torch.float16 if device.type == "cuda" else torch.float32,
        ignore_mismatched_sizes=True,
    ).to(device)

    dataset    = StanceDataset(train_texts, train_labels)
    loader     = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True,
                            collate_fn=collate(tokenizer, MAX_LENGTH))

    n_steps    = len(loader) * NUM_EPOCHS
    optimizer  = AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    scheduler  = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(WARMUP_FRAC * n_steps),
        num_training_steps=n_steps,
    )

    for epoch in range(NUM_EPOCHS):
        model.train()
        total_loss = 0
        for batch in tqdm(loader, desc=f"{model_tag} epoch {epoch+1}/{NUM_EPOCHS}"):
            batch     = {k: v.to(device) for k, v in batch.items()}
            outputs   = model(**batch)
            loss      = outputs.loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            total_loss += loss.item()
        print(f"  {model_tag} epoch {epoch+1} loss: {total_loss/len(loader):.4f}")

    out_path = f"{OUT_DIR}/{model_tag}"
    model.save_pretrained(out_path)
    tokenizer.save_pretrained(out_path)
    print(f"  Saved to {out_path}")
    return model, tokenizer


# ── Score unlabeled batch ─────────────────────────────────────────────────
def score_batch(model, tokenizer, texts):
    model.eval()
    dataset = StanceDataset(texts)
    loader  = DataLoader(dataset, batch_size=16,
                         collate_fn=collate(tokenizer, MAX_LENGTH))
    preds   = []
    with torch.no_grad():
        for batch in tqdm(loader, desc="  scoring"):
            batch   = {k: v.to(device) for k, v in batch.items()}
            logits  = model(**batch).logits
            pred    = torch.argmax(logits, dim=-1).cpu().numpy()
            preds.extend(pred)
    return np.array(preds)


# ── Main ──────────────────────────────────────────────────────────────────
print("=== Round 8 Ensemble Score Batch ===\n")

# Load training data
print("Loading training data...")
train_df = pd.read_parquet(TRAIN_PATH)
print(f"  {len(train_df):,} rows")
print(f"  Label distribution: {train_df['label'].value_counts().to_dict()}")

X_train = (
    "[ENTITY: " + train_df["target_entity"].fillna("unknown").astype(str) + "] "
    + train_df["text"].astype(str)
).tolist()
y_train = train_df["label"].map(LABEL_MAP).values

# Load unlabeled batch
print("\nLoading unlabeled batch...")
batch_df = pd.read_parquet(BATCH_PATH)
print(f"  {len(batch_df):,} rows, columns: {list(batch_df.columns)}")
print(f"  Entity distribution:\n{batch_df['target_entity'].value_counts().to_string()}")

X_batch = (
    "[ENTITY: " + batch_df["target_entity"].fillna("unknown").astype(str) + "] "
    + batch_df["text"].astype(str)
).tolist()

# Train 5 models and collect predictions
all_preds = []
for i, seed in enumerate(SEEDS):
    tag = f"model_r8_seed{seed}"
    print(f"\n{'='*50}")
    print(f"Model {i+1}/5  (seed={seed}, tag={tag})")
    print('='*50)
    model, tokenizer = train_model(X_train, y_train, seed=seed, model_tag=tag)
    preds = score_batch(model, tokenizer, X_batch)
    all_preds.append(preds)
    print(f"  Pred distribution: {dict(zip(*np.unique(preds, return_counts=True)))}")
    # Free GPU memory
    del model
    torch.cuda.empty_cache()

# Ensemble voting + margin
print("\n=== Ensemble Voting ===")
all_preds = np.stack(all_preds, axis=1)  # (N, 5)
ensemble_preds = np.array([np.bincount(row, minlength=3).argmax() for row in all_preds])

margins = []
for row_votes in all_preds:
    hostile_count  = (row_votes == 0).sum()
    endorse_count  = (row_votes == 1).sum()
    total_stance   = hostile_count + endorse_count
    if total_stance > 0:
        margin = abs(hostile_count / total_stance - 0.5)
    else:
        margin = np.nan
    margins.append(margin)
margins = np.array(margins)

# Build full scored dataframe
batch_df["ensemble_pred"]  = ensemble_preds
batch_df["pred_label"]     = pd.Series(ensemble_preds).map(ID_TO_LABEL).values
batch_df["margin"]         = margins
for i in range(5):
    batch_df[f"pred_model_{i}"] = all_preds[:, i]

print(f"\nPrediction distribution:")
print(batch_df["pred_label"].value_counts().to_string())
print(f"\nMargin stats:")
print(batch_df["margin"].describe())

# Save full scores
full_out = f"{OUT_DIR}/batch_ensemble_scores_r8.parquet"
batch_df.to_parquet(full_out, index=False)
print(f"\n✓ Saved full scores: {full_out}")

# Filter uncertain rows for frontier escalation
uncertain_mask = batch_df["margin"] < MARGIN_THRESHOLD
escalation_df  = batch_df[uncertain_mask].copy()
n_esc          = len(escalation_df)
print(f"\nEscalation candidates (margin < {MARGIN_THRESHOLD}): {n_esc:,} / {len(batch_df):,} ({n_esc/len(batch_df)*100:.1f}%)")
print("\nEscalation entity distribution:")
print(escalation_df["target_entity"].value_counts().to_string())

esc_out = f"{OUT_DIR}/batch_escalation_candidates_r8.csv"
escalation_df[["id", "text", "target_entity", "ensemble_pred", "pred_label", "margin"]].to_csv(esc_out, index=False)
print(f"\n✓ Saved escalation candidates: {esc_out}")

# Summary JSON for easy reference
summary = {
    "total_batch": int(len(batch_df)),
    "escalation_candidates": int(n_esc),
    "escalation_pct": round(n_esc / len(batch_df) * 100, 1),
    "margin_threshold": MARGIN_THRESHOLD,
    "seeds": SEEDS,
    "pred_distribution": batch_df["pred_label"].value_counts().to_dict(),
}
with open(f"{OUT_DIR}/batch_r8_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

print("\n=== Done ===")
print(f"Outputs in {OUT_DIR}/:")
print(f"  batch_ensemble_scores_r8.parquet  ({len(batch_df):,} rows)")
print(f"  batch_escalation_candidates_r8.csv ({n_esc:,} rows)")
print(f"  model_r8_seed*/                   (5 saved models)")
