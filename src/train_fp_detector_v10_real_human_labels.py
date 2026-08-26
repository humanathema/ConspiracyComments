"""train_fp_detector_v10_real_human_labels.py

First generation in the fp_detector lineage (v4-v9) trained on PURE
genuine human ground truth -- not frontier-silver labels, not
self-referential model flags. Training data: 470 rows pooling the
original 274-row blind-spot ground truth + this session's 220-row
spot-check of the actual flagged train/round9 populations (rated blind
by Nash), deduped.

Motivation: fp_ensemble_retrain_on_unified_470_human_labels_WORSE_not_better
(2026-08-24, data/experiment_log.jsonl) showed retraining the small GBT
ensemble on fp_v8_score/fp_v9_score/confidence -- even with this same
expanded real-label pool -- made cross-validated AUC WORSE (0.694 ->
0.568), proving the ceiling is in those 3 pre-computed scalar features,
not the training composition. This round tests a genuinely different
lever: a text-based model with direct access to the comment content,
same architecture as v8/v9 (ModernBERT-large, [ENTITY: X] input,
text-only, no tags), but trained on real labels for the first time.

Honest caveat: n=470 (82 positives) is small for a full fine-tune --
success is not guaranteed. Single stratified 80/20 train/val split
(train/csv 'split' column, built by the calling session), not k-fold --
consistent with how v8/v9 were evaluated.

Input: v10_training_data.csv (text, target_entity, y, split)
Output: SAVE_DIR/model_state.pt + tokenizer
"""
import os
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import classification_report, roc_auc_score, precision_recall_curve
from transformers import AutoModel, AutoTokenizer, Trainer, TrainingArguments

MODEL_NAME = "answerdotai/ModernBERT-large"
MAX_LENGTH = 768
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "8"))
NUM_EPOCHS = int(os.environ.get("NUM_EPOCHS", "5"))
LEARNING_RATE = float(os.environ.get("LEARNING_RATE", "1e-5"))
SAVE_DIR = os.environ.get("SAVE_DIR", "/home/nash/retrain_twostage/fp_detector_v10_real_human")
DATA_PATH = os.environ.get("DATA_PATH", "/home/nash/v10_training_data.csv")


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
    print(f"MODEL={MODEL_NAME} BATCH_SIZE={BATCH_SIZE} NUM_EPOCHS={NUM_EPOCHS} LR={LEARNING_RATE}", flush=True)

    data = pd.read_csv(DATA_PATH)
    train_data = data[data["split"] == "train"].reset_index(drop=True)
    val_data = data[data["split"] == "val"].reset_index(drop=True)
    print(f"train={len(train_data)} (pos={train_data['y'].sum()})  val={len(val_data)} (pos={val_data['y'].sum()})", flush=True)

    pos_class_weight = min((train_data["y"] == 0).sum() / max((train_data["y"] == 1).sum(), 1), 4.0)
    train_data["weight"] = 1.0
    train_data.loc[train_data["y"] == 1, "weight"] = pos_class_weight
    val_data["weight"] = 1.0
    print(f"pos_class_weight={pos_class_weight:.3f} (capped at 4.0)", flush=True)

    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Device: {device}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    def encode(df):
        texts = build_texts(df)
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
        logging_steps=10,
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
    true = val_data["y"].to_numpy()

    print(f"\n=== HELD-OUT VAL (n={len(true)}, REAL human labels, never trained on) ===", flush=True)
    preds = (probs >= 0.5).astype(int)
    print(classification_report(true, preds, target_names=["label_correct", "label_wrong"]), flush=True)
    print(f"AUC: {roc_auc_score(true, probs):.4f}", flush=True)

    print("\n=== Threshold sweep on held-out val ===", flush=True)
    for t in [0.3, 0.4, 0.5, 0.6, 0.7]:
        flag = probs >= t
        prec = true[flag].mean() if flag.sum() else float("nan")
        rec = true[flag].sum() / max(true.sum(), 1)
        print(f"  t={t}: n_flagged={flag.sum()}  precision={prec:.3f}  recall={rec:.3f}", flush=True)

    val_data["v10_score"] = probs
    val_data.to_csv(f"{SAVE_DIR}/val_scored.csv", index=False)


if __name__ == "__main__":
    main()
