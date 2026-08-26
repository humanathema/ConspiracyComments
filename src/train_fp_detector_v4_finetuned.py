"""train_fp_detector_v4_finetuned.py

Round 4 of the false-positive detector -- a genuinely different approach
from rounds 1-3 (all a frozen-embeddings logistic regression, which
failed twice at hard-negative-mining despite different designs). This
round tests the alternative hypothesis directly: maybe the signal exists
in binconf_other015's representation but isn't LINEARLY separable, so a
real fine-tune (not a linear probe on frozen features) is needed.

Also fixes a real design flaw found this session: rounds 1-3 never showed
the model what label was actually being claimed for a row -- they judged
text alone, disconnected from the specific claim being checked. That's
why round 1's detector fired on 87% of its "flags" with zero actual
disagreement behind them. This round's task is explicit: given
[ENTITY: X] [LABEL: claimed_label] <text>, predict whether claimed_label
is wrong (1) or right (0).

Data (see this session's conversation for full provenance):
  POSITIVES (label is wrong), weighted by source reliability:
    - 76 original + 76 backtranslation-paraphrase + 43 val-paraphrase
      human-verified rows, weight 1.0 (direct ground truth)
    - 236 + 201 frontier-judge-confirmed corrections (binconf disagreed
      with silver label, blind frontier judge sided with binconf),
      weight 0.6 (matches this session's measured ~57-61% empirical
      precision of that signal -- not certain, weighted down accordingly)
  NEGATIVES (label is correct):
    - 149 + 66 frontier-confirmed-correct rows, weight 0.6 (same logic)
    - 1,200 sampled from the 1,823-row human-verified genuinely-correct
      pool, weight 1.0 (direct ground truth, zero additional cost)

Fine-tunes the FULL ModernBERT-large encoder (not frozen) with a simple
2-class head, weighted cross-entropy loss via per-sample weights.
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
SAVE_DIR = os.environ.get("SAVE_DIR", "/home/nash/retrain_twostage/fp_detector_v4_finetuned")


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


def build_texts(df, text_col, entity_col, label_col, classifier_col):
    """Shows BOTH the silver/claimed label AND what binconf_other015 itself
    predicted (stanced vs other) -- the disagreement PATTERN is the actual
    signal this task needs, not just raw text. Without this, the model has
    to re-derive from embeddings alone whether there's a conflict at all,
    which is exactly what round 1's detector failed at (fired on text
    style with no connection to real label-vs-prediction disagreement)."""
    return (
        "[ENTITY: " + df[entity_col].fillna("unknown").astype(str)
        + " | SILVER_LABEL: " + df[label_col].astype(str)
        + " | CLASSIFIER_PREDICTED: " + df[classifier_col].astype(str)
        + "] " + df[text_col].astype(str)
    ).tolist()


def main():
    print(f"MODEL={MODEL_NAME} BATCH_SIZE={BATCH_SIZE} NUM_EPOCHS={NUM_EPOCHS} LR={LEARNING_RATE}", flush=True)

    # --- Positives ---
    orig_pos = pd.read_csv("outputs/reinfer_probs/other_to_stance_ALL_confident_wrong_TRAIN.csv")
    orig_pos = orig_pos[orig_pos["confidently_wrong_either"]][["text", "target_entity"]].copy()
    orig_pos["claimed_label"] = "other"
    orig_pos["classifier_predicted"] = "stanced"  # confidently gated as stanced -- that IS the error
    orig_pos["weight"] = 1.0

    para_df = pd.read_csv("outputs/reinfer_probs/paraphrase_backtranslation_full.csv")
    orig_pos_keys = set(zip(orig_pos["text"].astype(str).str.strip(), orig_pos["target_entity"].astype(str).str.strip().str.lower()))
    para_df["key"] = list(zip(para_df["text"].astype(str).str.strip(), para_df["target_entity"].astype(str).str.strip().str.lower()))
    para_pos = para_df[para_df["key"].isin(orig_pos_keys)][["paraphrase", "target_entity"]].rename(columns={"paraphrase": "text"}).copy()
    para_pos["claimed_label"] = "other"
    para_pos["classifier_predicted"] = "stanced"
    para_pos["weight"] = 1.0

    val_fp_df = pd.read_csv("outputs/reinfer_probs/other_to_stance_ALL_confident_wrong_VAL_PARAPHRASE.csv")
    val_wrong = val_fp_df[val_fp_df["para_gate_has_stance"] & (val_fp_df["para_confidence"] >= 0.7)]
    val_pos = val_wrong[["paraphrase", "target_entity"]].rename(columns={"paraphrase": "text"}).copy()
    val_pos["claimed_label"] = "other"
    val_pos["classifier_predicted"] = "stanced"
    val_pos["weight"] = 1.0

    # d1 pool = silver said 'other', binconf confidence>=0.5 (predicted stanced)
    d1_pos = pd.read_csv("/tmp/newdetector_d1_pos.csv")[["text", "target_entity", "label"]].rename(columns={"label": "claimed_label"})
    d1_pos["classifier_predicted"] = "stanced"
    d1_pos["weight"] = 0.6
    # d2 pool = silver said stanced, binconf confidence<0.5 (predicted other)
    d2_pos = pd.read_csv("/tmp/newdetector_d2_pos.csv")[["text", "target_entity", "label"]].rename(columns={"label": "claimed_label"})
    d2_pos["classifier_predicted"] = "other"
    d2_pos["weight"] = 0.6

    positives = pd.concat([orig_pos, para_pos, val_pos, d1_pos, d2_pos], ignore_index=True)
    positives["y"] = 1
    print(f"Positives: {len(orig_pos)} orig + {len(para_pos)} paraphrase + {len(val_pos)} val-paraphrase "
          f"+ {len(d1_pos)} d1-frontier + {len(d2_pos)} d2-frontier = {len(positives)}", flush=True)

    # --- Negatives ---
    d1_neg = pd.read_csv("/tmp/newdetector_d1_neg.csv")[["text", "target_entity", "label"]].rename(columns={"label": "claimed_label"})
    d1_neg["classifier_predicted"] = "stanced"  # same pool as d1_pos (confidence>=0.5), frontier just confirmed 'other' was right despite that
    d1_neg["weight"] = 0.6
    d2_neg = pd.read_csv("/tmp/newdetector_d2_neg.csv")[["text", "target_entity", "label"]].rename(columns={"label": "claimed_label"})
    d2_neg["classifier_predicted"] = "other"  # same pool as d2_pos (confidence<0.5), frontier confirmed the stance label was right anyway
    d2_neg["weight"] = 0.6
    bigneg = pd.read_csv("/tmp/newdetector_bigneg_pool.csv")[["text", "target_entity", "label"]].rename(columns={"label": "claimed_label"})
    bigneg["classifier_predicted"] = "stanced"  # confidence>=0.5 pool, genuinely correct
    bigneg["weight"] = 1.0

    negatives = pd.concat([d1_neg, d2_neg, bigneg], ignore_index=True)
    negatives["y"] = 0
    print(f"Negatives: {len(d1_neg)} d1-frontier + {len(d2_neg)} d2-frontier + {len(bigneg)} human-verified-pool = {len(negatives)}", flush=True)

    all_data = pd.concat([positives, negatives], ignore_index=True).sample(frac=1.0, random_state=42).reset_index(drop=True)
    print(f"\nTotal: {len(all_data)} rows ({(all_data['y']==1).sum()} positive / {(all_data['y']==0).sum()} negative)", flush=True)

    # simple train/val split for a real held-out check
    n_val = int(len(all_data) * 0.15)
    val_data = all_data.iloc[:n_val]
    train_data = all_data.iloc[n_val:]
    print(f"train={len(train_data)} val={len(val_data)}", flush=True)

    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Device: {device}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    def encode(df):
        texts = build_texts(df, "text", "target_entity", "claimed_label", "classifier_predicted")
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

    # Manual eval on the held-out val split
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
