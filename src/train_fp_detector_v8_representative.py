"""train_fp_detector_v8_representative.py

Round 8 -- a deliberate break from the v4-v7 lineage, not another
active-learning round on top of it. v7 was found to have essentially zero
real-world discriminative power (AUC 0.4852 on a genuinely random sample --
see fp_detector_v7_RANDOM_SAMPLE_VALIDATION_CRITICAL_FAILURE in
data/experiment_log.jsonl) because its ENTIRE training set, across all
prior generations, was built from confidence-filtered and self-referential
(prior-model-flagged) populations -- never from a representative sample of
the real population.

This round fixes that at the source: trains on a genuinely RANDOM 3,000-row
sample of the stanced population, labeled by a frontier judge that was
itself validated against real human judgment on this exact kind of
representative data (frontier_judge_random_sample_spotcheck_VALIDATED:
78.7% 3-way / 83.1% binary agreement with Nash on a blind spot-check --
categorically more reliable on representative data than v7 turned out to
be).

Same text-only, no-tag input format as v5-v7 (that fix was validated and
kept). Same class-balance weighting (validated to improve F1, doesn't
hurt AUC).

CRITICAL: evaluation is NOT a random split of this training data (that is
exactly the mistake that made v7's val numbers meaningless). It is scored
separately, after training, against the 288-row pool of genuinely random,
human-labeled ground truth (199 from queue_random_fp_validation_r1.csv +
89 from queue_random_3k_frontier_spotcheck.csv) -- see
score_fp_v8_on_real_validation_set.py. This script trains and reports an
in-sample sanity check only; the real number comes from that separate
script.

Data:
  3,000-row genuinely random sample of the stanced population, frontier-
  judged (blind, no label shown), MINUS the 89 rows reserved for real
  validation. Label: frontier says "other" = positive, frontier says
  hostile/endorsement = negative. Weight 1.0 uniformly (frontier's
  ~80% reliability on this population is high enough not to warrant the
  0.6 discount used for the earlier, less-validated disagreement-pool
  frontier data).
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
SAVE_DIR = os.environ.get("SAVE_DIR", "/home/nash/retrain_twostage/fp_detector_v8_representative")


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
    spotcheck_ids = set(pd.read_csv("/home/nash/random_3k_spotcheck_ANSWER_KEY.csv")["id"])
    # spotcheck rows were drawn from this same 3k pool by row_id, not id -- exclude by
    # text+entity match against the spotcheck answer key instead, since that's the
    # reliable join key here.
    spot_key_df = pd.read_csv("/home/nash/random_3k_spotcheck_ANSWER_KEY.csv")
    spot_keys = set(zip(spot_key_df["text"].astype(str).str.strip(), spot_key_df["target_entity"].astype(str).str.strip().str.lower()))
    data["key"] = list(zip(data["text"].astype(str).str.strip(), data["target_entity"].astype(str).str.strip().str.lower()))
    data = data[~data["key"].isin(spot_keys)].copy()
    print(f"Training pool after excluding {len(spot_keys)} reserved-for-validation rows: {len(data)}", flush=True)

    data["y"] = (data["frontier_classification"] == "other").astype(int)
    data["weight"] = 1.0
    print(f"Positives (frontier=other): {(data['y']==1).sum()}  Negatives: {(data['y']==0).sum()}", flush=True)

    pos_class_weight = (data["y"] == 0).sum() / (data["y"] == 1).sum()
    data.loc[data["y"] == 1, "weight"] = data.loc[data["y"] == 1, "weight"] * pos_class_weight
    print(f"Class-balance fix: positives' weight multiplied by {pos_class_weight:.3f}", flush=True)

    data = data.sample(frac=1.0, random_state=42).reset_index(drop=True)
    n_val = int(len(data) * 0.10)  # small in-sample sanity split only -- NOT the real eval
    val_data = data.iloc[:n_val]
    train_data = data.iloc[n_val:]
    print(f"train={len(train_data)} in-sample-sanity-val={len(val_data)} (real eval is separate, see score_fp_v8_on_real_validation_set.py)", flush=True)

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

    print(f"\n=== In-sample sanity check ONLY (n={len(true)}) -- NOT the real eval, frontier-labeled not human ===", flush=True)
    print(classification_report(true, preds, target_names=["label_correct", "label_wrong"]), flush=True)
    print(f"AUC: {roc_auc_score(true, probs):.4f}", flush=True)


if __name__ == "__main__":
    main()
