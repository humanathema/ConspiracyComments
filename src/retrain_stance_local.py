"""retrain_stance_local.py

Local (MPS/Apple Silicon) retrain of the two-stage stance cascade, for
the active-learning loop: rate a batch via hitl_rater.py -> merge
corrections (merge_active_learning_corrections.py) -> retrain locally
-> regenerate the requeue against the freshly-updated model -> repeat.

Deliberately the plain baseline architecture only (no entity-conditioning/
ordinal/bucket-redesign experiments) -- this is the workhorse loop for
label-quality improvement, not another architecture ablation. Runs on
mps if available, falls back to cpu.

Prints and appends val kappa (plus per-class breakdown) to
data/processed/active_learning_kappa_log.csv after every run, so
progress across active-learning iterations is visible as a simple
growing log -- not a live dashboard, just enough to see the trend.

Output: models saved to models/stance_stage1_local/, models/stance_stage2_local/
(gitignored -- these are working artifacts, not committed).

Batch size etc. are CLI args, not hardcoded -- this machine has 8GB
unified memory and MPS OOM'd at the original batch_size=16/seq_len=512
defaults (8.84GiB allocated vs 9.07GiB cap, crashed on step 1). Defaults
below are deliberately conservative (safe, not fast); raise
--batch-size first if you've closed everything else and have headroom,
drop --max-length before dropping batch size further if you still OOM
(sequence length matters more than batch size for attention memory).

Usage:
    python src/retrain_stance_local.py                          # safe defaults
    python src/retrain_stance_local.py --batch-size 16           # faster, more memory
    python src/retrain_stance_local.py --batch-size 8 --grad-accum-steps 2   # effective 16, less peak memory than a bare batch_size=16
    python src/retrain_stance_local.py --max-length 256          # shorter sequences if still OOMing
"""
import argparse
import os
from datetime import datetime, timezone

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

TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
MODEL_NAME = "roberta-base"
STAGE1_OUT = "models/stance_stage1_local"
STAGE2_OUT = "models/stance_stage2_local"
KAPPA_LOG_PATH = "data/processed/active_learning_kappa_log.csv"

LABELS_3WAY = ["hostile", "endorsement", "other"]
LABEL_TO_ID = {"hostile": 0, "endorsement": 1, "other": 2}


def get_device():
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class BinaryDataset(torch.utils.data.Dataset):
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


def encode(tokenizer, texts, max_length):
    return tokenizer(list(texts), truncation=True, padding=True, max_length=max_length, return_tensors="pt")


def train_binary_stage(tokenizer, train_df, val_df, device, stage_name, out_dir, cfg):
    train_enc = encode(tokenizer, train_df["text"], cfg.max_length)
    val_enc = encode(tokenizer, val_df["text"], cfg.max_length)
    train_ds = BinaryDataset(train_enc, train_df["stage_label"].tolist(), train_df["weight"].tolist())
    val_ds = BinaryDataset(val_enc, val_df["stage_label"].tolist(), [1.0] * len(val_df))

    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=2).to(device)
    class_counts = train_df["stage_label"].value_counts().sort_index()
    class_weights = torch.tensor([len(train_df) / (2 * class_counts.get(i, 1)) for i in range(2)], dtype=torch.float)

    n_steps_per_epoch = max(1, len(train_df) // (cfg.batch_size * cfg.grad_accum_steps))
    print(
        f"[{stage_name}] batch_size={cfg.batch_size} x grad_accum={cfg.grad_accum_steps} "
        f"(effective {cfg.batch_size * cfg.grad_accum_steps}), max_length={cfg.max_length}, "
        f"~{n_steps_per_epoch} steps/epoch, {cfg.epochs} epochs",
        flush=True,
    )

    args = TrainingArguments(
        output_dir=f"/tmp/checkpoints_{stage_name}", remove_unused_columns=False,
        num_train_epochs=cfg.epochs,
        per_device_train_batch_size=cfg.batch_size, gradient_accumulation_steps=cfg.grad_accum_steps,
        per_device_eval_batch_size=cfg.eval_batch_size,
        learning_rate=2e-5, weight_decay=0.01, eval_strategy="epoch", save_strategy="epoch",
        save_total_limit=1, load_best_model_at_end=True, metric_for_best_model="kappa",
        logging_steps=5, disable_tqdm=False, report_to=[], use_mps_device=(device == "mps"),
    )
    trainer = WeightedTrainer(
        model=model, args=args, train_dataset=train_ds, eval_dataset=val_ds,
        compute_metrics=compute_metrics, class_weights=class_weights,
    )
    trainer.train()
    trainer.save_model(out_dir)
    tokenizer.save_pretrained(out_dir)
    return trainer


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--batch-size", type=int, default=4, help="per-device train batch size (default 4, safe for 8GB)")
    parser.add_argument("--grad-accum-steps", type=int, default=4, help="gradient accumulation steps (default 4 -> effective batch 16)")
    parser.add_argument("--eval-batch-size", type=int, default=8, help="per-device eval batch size (default 8)")
    parser.add_argument("--epochs", type=int, default=6, help="training epochs per stage (default 6)")
    parser.add_argument("--max-length", type=int, default=512, help="tokenizer max sequence length (default 512; try 256 if still OOMing)")
    return parser.parse_args()


def main():
    cfg = parse_args()
    device = get_device()
    print(f"Using device: {device}", flush=True)

    df = pd.read_parquet(TRAINING_DATA_PATH)
    train_df = df[df["split"] == "train"].copy()
    val_df = df[df["split"] == "val"].copy()
    print(f"train={len(train_df):,} val={len(val_df):,}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    train_df["stage_label"] = (train_df["label"] != "other").astype(int)
    val_df["stage_label"] = (val_df["label"] != "other").astype(int)
    stage1_trainer = train_binary_stage(tokenizer, train_df, val_df, device, "stage1_local", STAGE1_OUT, cfg)

    tr2 = train_df[train_df["label"] != "other"].copy()
    va2 = val_df[val_df["label"] != "other"].copy()
    tr2["stage_label"] = (tr2["label"] == "endorsement").astype(int)
    va2["stage_label"] = (va2["label"] == "endorsement").astype(int)
    stage2_trainer = train_binary_stage(tokenizer, tr2, va2, device, "stage2_local", STAGE2_OUT, cfg)

    val_enc = encode(tokenizer, val_df["text"], cfg.max_length)
    dummy = BinaryDataset(val_enc, [0] * len(val_df), [1.0] * len(val_df))
    s1_probs = F.softmax(torch.tensor(stage1_trainer.predict(dummy).predictions), dim=-1).numpy()
    s2_probs = F.softmax(torch.tensor(stage2_trainer.predict(dummy).predictions), dim=-1).numpy()
    s1_preds, s2_preds = np.argmax(s1_probs, axis=1), np.argmax(s2_probs, axis=1)

    preds = ["other" if s1 == 0 else ("endorsement" if s2 == 1 else "hostile") for s1, s2 in zip(s1_preds, s2_preds)]
    true_ids = np.array([LABEL_TO_ID[l] for l in val_df["label"].to_numpy()])
    pred_ids = np.array([LABEL_TO_ID[l] for l in preds])
    kappa = cohen_kappa_score(true_ids, pred_ids)

    print(f"\n=== Combined 3-way kappa: {kappa:.4f} ===", flush=True)
    report = classification_report(true_ids, pred_ids, target_names=LABELS_3WAY, output_dict=True)
    print(classification_report(true_ids, pred_ids, target_names=LABELS_3WAY), flush=True)

    log_row = pd.DataFrame([{
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "n_train": len(train_df),
        "kappa": round(kappa, 4),
        "hostile_recall": round(report["hostile"]["recall"], 3),
        "endorsement_recall": round(report["endorsement"]["recall"], 3),
        "other_recall": round(report["other"]["recall"], 3),
        "batch_size": cfg.batch_size,
        "grad_accum_steps": cfg.grad_accum_steps,
        "max_length": cfg.max_length,
        "epochs": cfg.epochs,
    }])
    if os.path.exists(KAPPA_LOG_PATH):
        log_row.to_csv(KAPPA_LOG_PATH, mode="a", header=False, index=False)
    else:
        os.makedirs(os.path.dirname(KAPPA_LOG_PATH), exist_ok=True)
        log_row.to_csv(KAPPA_LOG_PATH, index=False)
    print(f"\nAppended to {KAPPA_LOG_PATH} -- run `tail {KAPPA_LOG_PATH}` any time to see progress across iterations.", flush=True)


if __name__ == "__main__":
    main()
