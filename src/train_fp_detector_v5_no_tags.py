"""train_fp_detector_v5_no_tags.py

Round 5 of the false-positive detector. Fixes the shortcut-learning bug
found in round 4 (see fp_detector_v4_no_conflict_other_FAILURE in
data/experiment_log.jsonl): v4 showed the model SILVER_LABEL and
CLASSIFIER_PREDICTED as explicit input tags, and the training-pool
construction made those two fields an almost-perfect predictor of the
target on their own (e.g. every SILVER_LABEL=stanced/CLASSIFIER_PREDICTED
=stanced training example was negative, by construction) -- so the model
learned to read that field instead of the actual text, and its output
collapsed to reproducing raw binconf-disagreement almost exactly
(0% flags when binconf agrees with the label, 97.1% when it disagrees).

Round 5 removes ALL of that: no label tags, no prediction tags, no
agreement signal -- just [ENTITY: X] <text>. The model has to learn
genuine content signal to do the task at all.

Task: given a comment (currently labeled stanced -- hostile/endorsement)
and its target entity, predict whether it's actually "other" (no real
stance toward the entity).

Data:
  POSITIVES (genuinely other, mislabeled/misclassified as stanced):
    - 76 human-verified confidently-wrong-other rows (original text)
    - 76 backtranslation-paraphrase versions of the same rows
    - 43 val-paraphrase confidently-wrong rows
    - 149 machine-labeled rows where an independent blind frontier judge
      said "other" (classifier had confidently said stanced) -- weight 0.6
  NEGATIVES (genuinely stanced):
    - up to 1,683 human-verified confidently-correct stanced rows
    - 236 machine-labeled rows where frontier confirmed the row really is
      stanced (hostile/endorsement) -- weight 0.6

Fine-tunes the full ModernBERT-large encoder end to end (not frozen
embeddings, not a linear probe).
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
SAVE_DIR = os.environ.get("SAVE_DIR", "/home/nash/retrain_twostage/fp_detector_v5_no_tags")


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
    """NO label tags, NO prediction tags -- just entity + raw text.
    This is the deliberate fix for round 4's shortcut-learning bug."""
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

    frontier_pos = pd.read_csv("/home/nash/v5_frontier_pos.csv")
    frontier_pos["weight"] = 0.6

    positives = pd.concat([orig_pos, para_pos, val_pos, frontier_pos], ignore_index=True)
    positives["y"] = 1
    print(f"Positives: {len(orig_pos)} orig + {len(para_pos)} paraphrase + {len(val_pos)} val-paraphrase "
          f"+ {len(frontier_pos)} frontier = {len(positives)}", flush=True)

    # --- Negatives ---
    polar_scores = pd.read_csv("/home/nash/train_polar_fp_detector_scores.csv")
    bigneg_pool = polar_scores[(polar_scores["confidence"] >= 0.7) & (polar_scores["correct"] == True)]
    n_bigneg = min(len(bigneg_pool), 1200)
    bigneg = bigneg_pool.sample(n=n_bigneg, random_state=42)[["text", "target_entity"]].copy()
    bigneg["weight"] = 1.0

    frontier_neg = pd.read_csv("/home/nash/v5_frontier_neg.csv")
    frontier_neg["weight"] = 0.6

    negatives = pd.concat([bigneg, frontier_neg], ignore_index=True)
    negatives["y"] = 0
    print(f"Negatives: {len(bigneg)} human-verified-pool (sampled from {len(bigneg_pool)}) "
          f"+ {len(frontier_neg)} frontier = {len(negatives)}", flush=True)

    # Class-imbalance fix (2026-08-21): v5's first run had no class-balance
    # correction at all -- only the reliability weight (1.0/0.6) -- on a
    # 344:1436 (~1:4.2) positive:negative split, which biased the model
    # toward predicting negative and produced only 24pct held-out recall.
    # Multiply positives' existing reliability weight by the inverse class
    # ratio so the loss weights the two classes equally in aggregate, while
    # still preserving the relative human-vs-frontier reliability distinction
    # within the positive class.
    pos_class_weight = len(negatives) / len(positives)
    positives["weight"] = positives["weight"] * pos_class_weight
    print(f"Class-balance fix: positives' weight multiplied by {pos_class_weight:.3f} "
          f"(negatives/positives = {len(negatives)}/{len(positives)})", flush=True)

    all_data = pd.concat([positives, negatives], ignore_index=True).sample(frac=1.0, random_state=42).reset_index(drop=True)
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
