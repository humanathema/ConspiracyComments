"""train_fp_detector_v9_blindspot.py

A properly-scoped return to the ORIGINAL false-positive-detector task:
"is binconf's own prediction wrong" -- not "is the random population's
label wrong" (v8's task). Nash's insight (2026-08-23): v5-v7's original
Gen1/Gen2 training data (76+76+43 human-verified + 149 frontier-verified)
was ALREADY correctly scoped to this narrower task, verified directly by
re-reading train_fp_detector_v4_finetuned.py's d1_neg construction
("frontier just confirmed 'other' was right DESPITE" binconf predicting
stanced) -- but v6/v7 diluted it by blending in Gen3/Gen4 data (verifying
full RANDOM-population scan flags, which includes many cases binconf was
never confused about), and v8 dropped the binconf-blind-spot framing
entirely, training purely on a random sample regardless of binconf's own
prediction.

This round trains ONLY on binconf's actual blind spot: rows where
CURRENT label = stanced AND binconf confidence >= 0.5 (binconf itself
would never flag these via a simple threshold rule) -- using the
genuinely random 3,000-row frontier-labeled batch, filtered to this
confident subset (2,829 of 3,000 rows, 675 genuine positives -- far more
usable signal than the 41-row pure-human polish attempt, and correctly
targeted this time).

Text-only, no tags (that fix from v5 stays) -- same architecture as v8,
different, properly-scoped training population.

Evaluation is separate (score_fp_v9_on_blindspot_validation.py), against
the binconf-confident SUBSET of the real 288-row human-labeled ground
truth -- the actual population this detector is meant for, not the full
288 (which includes many rows binconf already correctly flags via its
own confidence, outside this detector's intended job).
"""
import os
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

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
SAVE_DIR = os.environ.get("SAVE_DIR", "/home/nash/retrain_twostage/fp_detector_v9_blindspot")


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

    data = pd.read_csv("/home/nash/random_3k_frontier_MERGED.csv")
    spot_key_df = pd.read_csv("/home/nash/random_3k_spotcheck_ANSWER_KEY.csv")
    spot_keys = set(zip(spot_key_df["text"].astype(str).str.strip(), spot_key_df["target_entity"].astype(str).str.strip().str.lower()))
    data["key"] = list(zip(data["text"].astype(str).str.strip(), data["target_entity"].astype(str).str.strip().str.lower()))
    data = data[~data["key"].isin(spot_keys)].copy()
    print(f"After excluding {len(spot_keys)} reserved-for-validation rows: {len(data)}", flush=True)

    # THE key scoping fix: only binconf's actual blind spot.
    data = data[data["confidence"] >= 0.5].copy()
    print(f"Restricted to binconf's blind spot (confidence>=0.5): {len(data)}", flush=True)

    data["y"] = (data["frontier_classification"] == "other").astype(int)
    data["weight"] = 1.0
    pos_class_weight = min((data["y"] == 0).sum() / (data["y"] == 1).sum(), 4.0)
    data.loc[data["y"] == 1, "weight"] = pos_class_weight
    print(f"Positives: {(data['y']==1).sum()}  Negatives: {(data['y']==0).sum()}  "
          f"pos_weight={pos_class_weight:.3f} (capped at 4.0, per the earlier polish-stage lesson)", flush=True)

    data = data.sample(frac=1.0, random_state=42).reset_index(drop=True)
    n_val = int(len(data) * 0.10)
    val_data = data.iloc[:n_val]
    train_data = data.iloc[n_val:]
    print(f"train={len(train_data)} in-sample-sanity-val={len(val_data)} "
          f"(real eval is separate, see score_fp_v9_on_blindspot_validation.py)", flush=True)

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

    print(f"\n=== In-sample sanity check ONLY (n={len(true)}) -- NOT the real eval ===", flush=True)
    print(classification_report(true, preds, target_names=["label_correct", "label_wrong"]), flush=True)
    print(f"AUC: {roc_auc_score(true, probs):.4f}", flush=True)


if __name__ == "__main__":
    main()
