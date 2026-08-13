"""train_ctx.py — submission-context-conditioned training variant

Same as train.py but prepends [SUBMISSION: title] to every training text
when available, in addition to [ENTITY: name]. This trains the model to
use post title context for disambiguation, matching how infer_context_rerun
works at inference time.

Expects INPUT_FILE to be the _with_context parquet (has a post_title column).
Rows with empty post_title train without submission context (graceful fallback).

Usage on VM2:
  SKIP_REDESIGN=1 TAG=r8ctx \
  SAVE_ROOT=$HOME/outputs/round8/checkpoints_twostage/r8ctx \
  INPUT_FILE=$HOME/stance_classifier_training_data_round8_combined_with_context.parquet \
  python3 ~/train_ctx.py
"""
import os

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from sklearn.metrics import classification_report, cohen_kappa_score
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

INPUT_FILE = os.environ.get("INPUT_FILE", "/data/stance_classifier_training_data_round8_combined_with_context.parquet")
MODEL_NAME = os.environ.get("MODEL_NAME", "answerdotai/ModernBERT-large")
MAX_LENGTH = int(os.environ.get("MAX_LENGTH", "512"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "4"))
NUM_EPOCHS = int(os.environ.get("NUM_EPOCHS", "3"))
GRAD_CKPT = os.environ.get("GRAD_CKPT", "1") == "1"
TAG = os.environ.get("TAG", "r8ctx")
SKIP_REDESIGN = os.environ.get("SKIP_REDESIGN", "0") == "1"

LABELS_3WAY = ["hostile", "endorsement", "other"]
LABEL_TO_ID = {"hostile": 0, "endorsement": 1, "other": 2}
LABELS_STAGE2_REDESIGN = ["hostile", "endorsement", "ambiguous"]


class MultiClassDataset(torch.utils.data.Dataset):
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
    def __init__(self, *args, class_weights=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.class_weights = class_weights

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        weights = inputs.pop("sample_weight")
        outputs = model(**inputs)
        logits = outputs.logits
        loss_fct = torch.nn.CrossEntropyLoss(reduction="none")
        per_example_loss = loss_fct(logits, inputs["labels"])
        if self.class_weights is not None:
            class_w = self.class_weights.to(logits.device)[inputs["labels"]]
            weights = weights * class_w
        loss = (per_example_loss * weights).mean()
        return (loss, outputs) if return_outputs else loss


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=1)
    return {"kappa": cohen_kappa_score(labels, preds), "accuracy": (preds == labels).mean()}


def encode(tokenizer, texts):
    return tokenizer(list(texts), truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt")


def _texts_with_context(df):
    """Prepend [ENTITY: X] and optionally [SUBMISSION: title] to each text."""
    entity = df["target_entity"].fillna("unknown").astype(str)
    text = df["text"].astype(str)
    title = df["post_title"].fillna("").astype(str) if "post_title" in df.columns else pd.Series([""] * len(df))

    result = []
    for e, t, ttl in zip(entity, text, title):
        if ttl.strip():
            result.append(f"[ENTITY: {e}] [SUBMISSION: {ttl}] {t}")
        else:
            result.append(f"[ENTITY: {e}] {t}")
    return result


def train_stage(tokenizer, train_df, val_df, num_labels, stage_name, out_dir):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    train_enc = encode(tokenizer, _texts_with_context(train_df))
    val_enc = encode(tokenizer, _texts_with_context(val_df))

    train_ds = MultiClassDataset(train_enc, train_df["stage_label"].tolist(), train_df["weight"].tolist())
    val_ds = MultiClassDataset(val_enc, val_df["stage_label"].tolist(), [1.0] * len(val_df))

    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=num_labels).to(device)

    class_counts = train_df["stage_label"].value_counts().sort_index()
    class_weights = torch.tensor(
        [len(train_df) / (num_labels * class_counts.get(i, 1)) for i in range(num_labels)], dtype=torch.float
    )
    print(f"[{stage_name}] train={len(train_df):,} val={len(val_df):,} class_counts={dict(class_counts)}", flush=True)

    args = TrainingArguments(
        output_dir=f"/tmp/checkpoints_{stage_name}",
        remove_unused_columns=False,
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=max(BATCH_SIZE * 2, 4),
        gradient_accumulation_steps=max(1, 16 // BATCH_SIZE),
        learning_rate=2e-5,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="no",
        logging_steps=20,
        report_to=[],
        bf16=torch.cuda.is_available(),
        gradient_checkpointing=GRAD_CKPT,
    )

    trainer = WeightedTrainer(
        model=model, args=args, train_dataset=train_ds, eval_dataset=val_ds,
        compute_metrics=compute_metrics, class_weights=class_weights,
    )
    trainer.train()

    preds = trainer.predict(val_ds)
    pred_labels = np.argmax(preds.predictions, axis=1)
    true_labels = val_df["stage_label"].to_numpy()
    kappa = cohen_kappa_score(true_labels, pred_labels)
    print(f"\n=== {stage_name} validation === kappa={kappa:.3f}", flush=True)
    return trainer


def run_baseline_arm(tokenizer, train_df, val_df):
    print("\n########## ARM: baseline (collapsed) ##########", flush=True)
    train_df, val_df = train_df.copy(), val_df.copy()
    train_df["stage_label"] = (train_df["label"] != "other").astype(int)
    val_df["stage_label"] = (val_df["label"] != "other").astype(int)
    stage1 = train_stage(tokenizer, train_df, val_df, 2, "stage1_baseline", "/tmp/stance_stage1_baseline")

    tr2 = train_df[train_df["label"] != "other"].copy()
    va2 = val_df[val_df["label"] != "other"].copy()
    tr2["stage_label"] = (tr2["label"] == "endorsement").astype(int)
    va2["stage_label"] = (va2["label"] == "endorsement").astype(int)
    stage2 = train_stage(tokenizer, tr2, va2, 2, "stage2_baseline", "/tmp/stance_stage2_baseline")

    val_enc = encode(tokenizer, _texts_with_context(val_df))
    dummy = MultiClassDataset(val_enc, [0] * len(val_df), [1.0] * len(val_df))
    s1_probs = F.softmax(torch.tensor(stage1.predict(dummy).predictions), dim=-1).numpy()
    s2_probs = F.softmax(torch.tensor(stage2.predict(dummy).predictions), dim=-1).numpy()
    s1_preds, s2_preds = np.argmax(s1_probs, axis=1), np.argmax(s2_probs, axis=1)

    preds = []
    for s1, s2 in zip(s1_preds, s2_preds):
        preds.append("other" if s1 == 0 else ("endorsement" if s2 == 1 else "hostile"))

    true_ids = np.array([LABEL_TO_ID[l] for l in val_df["label"].to_numpy()])
    pred_ids = np.array([LABEL_TO_ID[l] for l in preds])
    kappa = cohen_kappa_score(true_ids, pred_ids)
    print(f"\n=== baseline (collapsed): combined 3-way kappa = {kappa:.4f} ===", flush=True)
    print(classification_report(true_ids, pred_ids, target_names=LABELS_3WAY), flush=True)
    save_root = os.environ.get("SAVE_ROOT", f"/tmp/saved_{TAG}")
    os.makedirs(f"{save_root}/baseline/stage1", exist_ok=True)
    os.makedirs(f"{save_root}/baseline/stage2", exist_ok=True)
    stage1.model.save_pretrained(f"{save_root}/baseline/stage1")
    tokenizer.save_pretrained(f"{save_root}/baseline/stage1")
    stage2.model.save_pretrained(f"{save_root}/baseline/stage2")
    tokenizer.save_pretrained(f"{save_root}/baseline/stage2")
    print(f"Saved baseline models to {save_root}/baseline/", flush=True)
    preds_dir = os.environ.get("PREDS_DIR", "/tmp/preds")
    os.makedirs(preds_dir, exist_ok=True)
    pd.DataFrame({"true": true_ids, "pred": pred_ids}).to_csv(f"{preds_dir}/preds_{TAG}_baseline.csv", index=False)
    return true_ids, pred_ids, kappa


def main():
    import gc
    print(f"MODEL_NAME={MODEL_NAME} MAX_LENGTH={MAX_LENGTH} BATCH_SIZE={BATCH_SIZE} NUM_EPOCHS={NUM_EPOCHS} GRAD_CKPT={GRAD_CKPT} SKIP_REDESIGN={SKIP_REDESIGN}", flush=True)
    df = pd.read_parquet(INPUT_FILE)
    if "raw_label" not in df.columns:
        raise RuntimeError("raw_label column missing")
    if "post_title" not in df.columns:
        print("WARNING: post_title column missing — training without submission context", flush=True)
        df["post_title"] = ""

    train_df = df[df["split"] == "train"].copy()
    val_df = df[df["split"] == "val"].copy()
    ctx_covered = (train_df["post_title"].fillna("") != "").sum()
    print(f"train={len(train_df):,} val={len(val_df):,} post_title_coverage={ctx_covered}/{len(train_df)} ({ctx_covered/len(train_df)*100:.1f}%)", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    true_a, preds_a, kappa_a = run_baseline_arm(tokenizer, train_df, val_df)
    gc.collect()
    torch.cuda.empty_cache()

    if not SKIP_REDESIGN:
        print("\n########## ARM: bucket_redesign (split) ##########", flush=True)
        print("(redesign arm — not used in ensemble, skipping by default)", flush=True)

    print("\n########## SUMMARY ##########", flush=True)
    print(f"model={MODEL_NAME} tag={TAG}", flush=True)
    print(f"baseline (collapsed) kappa: {kappa_a:.4f}", flush=True)


if __name__ == "__main__":
    main()
