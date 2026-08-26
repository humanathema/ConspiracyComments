"""train_fp_detector_v6_expanded.py

Round 6: same text-only, no-tag architecture as v5b (class-balanced), but
with a much larger training set -- adds the 564 confirmed-positive and 714
confirmed-negative rows found by verifying v5's own full-scan flags
(1,298 rows) via blind frontier judge (see fp_detector_v5_flagged_frontier_
verified in data/experiment_log.jsonl). This is an active-learning loop:
v5's own flagged candidates (including the 1,149 "binconf agrees but v5
flags anyway" rows -- territory no previous detector could reach) become
verified training data for v6, roughly tripling the positive class.

Data:
  POSITIVES:
    - 76 human orig + 76 backtranslation-paraphrase + 43 val-paraphrase
      (weight 1.0)
    - 149 frontier-confirmed from the original d1 check (weight 0.6)
    - 564 NEW frontier-confirmed from verifying v5's full-scan flags
      (weight 0.6)
  NEGATIVES:
    - up to 1200 human-verified confidently-correct-stanced (weight 1.0)
    - 236 frontier-confirmed from the original d1 check (weight 0.6)
    - 714 NEW frontier-confirmed from verifying v5's full-scan flags
      (weight 0.6)

Same class-balance fix as v5b (positives weight multiplied by
negatives/positives ratio) -- kept since it produced a real F1 gain even
though AUC didn't move, and there's no reason to expect that not to still
help here.
"""
import os
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import classification_report, roc_auc_score
from transformers import AutoModel, AutoTokenizer, Trainer, TrainingArguments

MODEL_NAME = "answerdotai/ModernBERT-large"
MAX_LENGTH = 768
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "8"))
NUM_EPOCHS = int(os.environ.get("NUM_EPOCHS", "3"))
LEARNING_RATE = float(os.environ.get("LEARNING_RATE", "1e-5"))
SAVE_DIR = os.environ.get("SAVE_DIR", "/home/nash/retrain_twostage/fp_detector_v6_expanded")


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


def build_texts(df, text_col, entity_col):
    return (
        "[ENTITY: " + df[entity_col].fillna("unknown").astype(str) + "] " + df[text_col].astype(str)
    ).tolist()


def main():
    print(f"MODEL={MODEL_NAME} BATCH_SIZE={BATCH_SIZE} NUM_EPOCHS={NUM_EPOCHS} LR={LEARNING_RATE}", flush=True)

    # --- Positives ---
    orig_pos = pd.read_csv("outputs/reinfer_probs/other_to_stance_ALL_confident_wrong_TRAIN.csv")
    orig_pos = orig_pos[orig_pos["confidently_wrong_either"]][["text", "target_entity"]].copy()
    orig_pos["weight"] = 1.0

    para_df = pd.read_csv("outputs/reinfer_probs/paraphrase_backtranslation_full.csv")
    orig_pos_keys = set(zip(orig_pos["text"].astype(str).str.strip(), orig_pos["target_entity"].astype(str).str.strip().str.lower()))
    para_df["key"] = list(zip(para_df["text"].astype(str).str.strip(), para_df["target_entity"].astype(str).str.strip().str.lower()))
    para_pos = para_df[para_df["key"].isin(orig_pos_keys)][["paraphrase", "target_entity"]].rename(columns={"paraphrase": "text"}).copy()
    para_pos["weight"] = 1.0

    val_fp_df = pd.read_csv("outputs/reinfer_probs/other_to_stance_ALL_confident_wrong_VAL_PARAPHRASE.csv")
    val_wrong = val_fp_df[val_fp_df["para_gate_has_stance"] & (val_fp_df["para_confidence"] >= 0.7)]
    val_pos = val_wrong[["paraphrase", "target_entity"]].rename(columns={"paraphrase": "text"}).copy()
    val_pos["weight"] = 1.0

    frontier_pos_r1 = pd.read_csv("/home/nash/v5_frontier_pos.csv")
    frontier_pos_r1["weight"] = 0.6

    verified = pd.read_csv("/home/nash/fp_v5_flagged_frontier_VERIFIED.csv")
    frontier_pos_r2 = verified[verified["confirmed_other"] == True][["text", "target_entity"]].copy()
    frontier_pos_r2["weight"] = 0.6

    positives = pd.concat([orig_pos, para_pos, val_pos, frontier_pos_r1, frontier_pos_r2], ignore_index=True)
    positives["y"] = 1
    print(f"Positives: {len(orig_pos)} orig + {len(para_pos)} paraphrase + {len(val_pos)} val-paraphrase "
          f"+ {len(frontier_pos_r1)} frontier-r1 + {len(frontier_pos_r2)} frontier-r2(NEW) = {len(positives)}", flush=True)

    # --- Negatives ---
    polar_scores = pd.read_csv("/home/nash/train_polar_fp_detector_scores.csv")
    bigneg_pool = polar_scores[(polar_scores["confidence"] >= 0.7) & (polar_scores["correct"] == True)]
    n_bigneg = min(len(bigneg_pool), 1200)
    bigneg = bigneg_pool.sample(n=n_bigneg, random_state=42)[["text", "target_entity"]].copy()
    bigneg["weight"] = 1.0

    frontier_neg_r1 = pd.read_csv("/home/nash/v5_frontier_neg.csv")
    frontier_neg_r1["weight"] = 0.6

    frontier_neg_r2 = verified[verified["confirmed_still_stanced"] == True][["text", "target_entity"]].copy()
    frontier_neg_r2["weight"] = 0.6

    negatives = pd.concat([bigneg, frontier_neg_r1, frontier_neg_r2], ignore_index=True)
    negatives["y"] = 0
    print(f"Negatives: {len(bigneg)} human-verified-pool + {len(frontier_neg_r1)} frontier-r1 "
          f"+ {len(frontier_neg_r2)} frontier-r2(NEW) = {len(negatives)}", flush=True)

    pos_class_weight = len(negatives) / len(positives)
    positives["weight"] = positives["weight"] * pos_class_weight
    print(f"Class-balance fix: positives' weight multiplied by {pos_class_weight:.3f}", flush=True)

    all_data = pd.concat([positives, negatives], ignore_index=True)
    before = len(all_data)
    all_data = all_data.drop_duplicates(subset=["text", "target_entity"], keep="first")
    print(f"Dropped {before - len(all_data)} exact text+entity duplicates across pools", flush=True)
    all_data = all_data.sample(frac=1.0, random_state=42).reset_index(drop=True)
    print(f"\nTotal: {len(all_data)} rows ({(all_data['y']==1).sum()} positive / {(all_data['y']==0).sum()} negative)", flush=True)

    n_val = int(len(all_data) * 0.15)
    val_data = all_data.iloc[:n_val]
    train_data = all_data.iloc[n_val:]
    print(f"train={len(train_data)} val={len(val_data)}", flush=True)

    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Device: {device}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    def encode(df):
        texts = build_texts(df, "text", "target_entity")
        return tokenizer(texts, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt")

    train_ds = WeightedDataset(encode(train_data), train_data["y"].tolist(), train_data["weight"].tolist())
    val_ds = WeightedDataset(encode(val_data), val_data["y"].tolist(), val_data["weight"].tolist())

    model = WrongLabelModel(MODEL_NAME).to(device)

    os.makedirs(SAVE_DIR, exist_ok=True)
    args = TrainingArguments(
        output_dir=SAVE_DIR,
        remove_unused_columns=False,
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=max(BATCH_SIZE * 2, 4),
        gradient_accumulation_steps=max(1, 16 // BATCH_SIZE),
        learning_rate=LEARNING_RATE,
        weight_decay=0.01,
        eval_strategy="no",
        save_strategy="no",
        logging_steps=20,
        report_to=[],
        bf16=torch.cuda.is_available(),
        label_names=["labels"],
    )

    trainer = WeightedTrainer(model=model, args=args, train_dataset=train_ds, eval_dataset=val_ds)
    trainer.train()

    torch.save(model.state_dict(), f"{SAVE_DIR}/model_state.pt")
    tokenizer.save_pretrained(SAVE_DIR)
    print(f"Saved to {SAVE_DIR}", flush=True)

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
    preds = (probs >= 0.5).astype(int)
    true = val_data["y"].to_numpy()

    print(f"\n=== Held-out val performance (n={len(true)}) ===", flush=True)
    print(classification_report(true, preds, target_names=["label_correct", "label_wrong"]), flush=True)
    print(f"AUC: {roc_auc_score(true, probs):.4f}", flush=True)


if __name__ == "__main__":
    main()
