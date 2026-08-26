"""train_fp_detector_v10_5fold_cv.py

5-fold cross-validated version of train_fp_detector_v10_real_human_labels.py,
run for two purposes:
  1. An honest, non-leaked v10 score for every one of the 470 real
     human-labeled rows (each row scored by a fold that never trained on
     it) -- needed to build a v8+v9+v10+confidence ensemble without
     repeating the exact leakage mistake this project has hit before
     (scoring a model on data it was trained on).
  2. A properly cross-validated v10-alone AUC, comparable on equal
     footing to the single 93-row held-out split reported earlier
     (0.733) -- 5-fold uses ALL 470 rows for evaluation instead of 93,
     so this is the more statistically solid number.

Each fold trains a fresh ModernBERT-large from scratch (not incremental)
-- 5x the single-run compute (~12-15 min total on this GPU based on the
single run's ~2.5 min).

Input: v10_training_data_470.csv (text, target_entity, y -- NOT
  pre-split, this script does its own 5-fold split)
Output: v10_oof_scores.csv (text, target_entity, y, v10_oof_score, fold)
"""
import os
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
from transformers import AutoModel, AutoTokenizer, Trainer, TrainingArguments

MODEL_NAME = "answerdotai/ModernBERT-large"
MAX_LENGTH = 768
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "8"))
NUM_EPOCHS = int(os.environ.get("NUM_EPOCHS", "5"))
LEARNING_RATE = float(os.environ.get("LEARNING_RATE", "1e-5"))
DATA_PATH = os.environ.get("DATA_PATH", "/home/nash/v10_training_data_470.csv")
OUT_PATH = "/home/nash/v10_oof_scores.csv"
N_FOLDS = 5


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


class WeightedDataset(torch.utils.data.Dataset):
    def __init__(self, encodings, labels, weights):
        self.encodings = encodings
        self.labels = labels
        self.weights = weights

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {k: v[idx] for k, v in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx])
        item["sample_weight"] = torch.tensor(self.weights[idx], dtype=torch.float)
        return item


class WeightedTrainer(Trainer):
    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        weights = inputs.pop("sample_weight")
        labels = inputs.pop("labels")
        logits = model(**inputs)
        per_example_loss = F.cross_entropy(logits, labels, reduction="none")
        loss = (per_example_loss * weights).mean()
        return (loss, {"logits": logits}) if return_outputs else loss

    def prediction_step(self, model, inputs, prediction_loss_only, ignore_keys=None):
        inputs = {k: v.to(self.args.device) for k, v in inputs.items()}
        with torch.no_grad():
            loss = self.compute_loss(model, dict(inputs))
        return (loss.detach(), None, None)


def build_texts(df):
    return ("[ENTITY: " + df["target_entity"].fillna("unknown").astype(str) + "] " + df["text"].astype(str)).tolist()


def main():
    print(f"MODEL={MODEL_NAME} BATCH_SIZE={BATCH_SIZE} NUM_EPOCHS={NUM_EPOCHS} LR={LEARNING_RATE} N_FOLDS={N_FOLDS}", flush=True)
    data = pd.read_csv(DATA_PATH).reset_index(drop=True)
    print(f"Total rows: {len(data)}, positives: {data['y'].sum()}", flush=True)

    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Device: {device}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    def encode(df):
        texts = build_texts(df)
        return tokenizer(texts, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt")

    oof_scores = np.zeros(len(data))
    fold_assignment = np.zeros(len(data), dtype=int)

    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=42)
    for fold_i, (train_idx, val_idx) in enumerate(skf.split(data, data["y"])):
        print(f"\n{'='*20} FOLD {fold_i+1}/{N_FOLDS} {'='*20}", flush=True)
        train_data = data.iloc[train_idx].reset_index(drop=True)
        val_data = data.iloc[val_idx].reset_index(drop=True)
        fold_assignment[val_idx] = fold_i

        pos_weight = min((train_data["y"] == 0).sum() / max((train_data["y"] == 1).sum(), 1), 4.0)
        train_data["weight"] = 1.0
        train_data.loc[train_data["y"] == 1, "weight"] = pos_weight
        val_data["weight"] = 1.0

        train_ds = WeightedDataset(encode(train_data), train_data["y"].tolist(), train_data["weight"].tolist())
        val_ds = WeightedDataset(encode(val_data), val_data["y"].tolist(), val_data["weight"].tolist())

        model = WrongLabelModel(MODEL_NAME).to(device)
        args = TrainingArguments(
            output_dir=f"/tmp/v10_fold{fold_i}",
            remove_unused_columns=False,
            num_train_epochs=NUM_EPOCHS,
            per_device_train_batch_size=BATCH_SIZE,
            per_device_eval_batch_size=max(BATCH_SIZE * 2, 4),
            gradient_accumulation_steps=max(1, 16 // BATCH_SIZE),
            learning_rate=LEARNING_RATE,
            weight_decay=0.01,
            eval_strategy="no",
            save_strategy="no",
            logging_steps=50,
            report_to=[],
            bf16=torch.cuda.is_available(),
            label_names=["labels"],
        )
        trainer = WeightedTrainer(model=model, args=args, train_dataset=train_ds, eval_dataset=val_ds)
        trainer.train()

        model.eval()
        with torch.no_grad():
            all_logits = []
            val_enc = encode(val_data)
            for i in range(0, len(val_data), 16):
                batch = {k: v[i:i+16].to(device) for k, v in val_enc.items()}
                logits = model(**batch)
                all_logits.append(logits.cpu())
        logits = torch.cat(all_logits).numpy()
        probs = F.softmax(torch.tensor(logits), dim=1).numpy()[:, 1]
        oof_scores[val_idx] = probs

        fold_auc = roc_auc_score(val_data["y"].to_numpy(), probs)
        print(f"Fold {fold_i+1} val AUC: {fold_auc:.4f}", flush=True)

        del model, trainer
        torch.cuda.empty_cache()

    overall_auc = roc_auc_score(data["y"].to_numpy(), oof_scores)
    print(f"\n{'='*20} FINAL 5-FOLD OOF AUC: {overall_auc:.4f} {'='*20}", flush=True)

    data["v10_oof_score"] = oof_scores
    data["fold"] = fold_assignment
    data.to_csv(OUT_PATH, index=False)
    print(f"Saved {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
