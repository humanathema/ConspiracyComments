"""finetune_fp_detector_v8_polish_on_human.py

Two-stage fine-tune, stage 2. v8 was pretrained on 2,910 frontier-labeled
(genuinely random) rows -- real signal (AUC 0.6417 on held-out human
ground truth), but capped by frontier's own ~79-83% agreement with human
judgment (frontier_judge_random_sample_spotcheck_VALIDATED in
data/experiment_log.jsonl), including a known, characterized bias
(frontier over-calls "other" 13x vs under-calls it 2x in the spot-check
confusion matrix).

This stage continues fine-tuning v8's own checkpoint on:
  - the 199-row genuinely-random, human-labeled set (positives AND
    negatives), and
  - an EXPANDED trusted-negative pool: up to 1,000 additional rows sampled
    from the large existing human-verified-stanced population (2,131 rows,
    train_polar_fp_detector_scores.csv, is_human=True, "correct" polarity
    match -- i.e. rows a human independently confirmed genuinely have a
    stance). Adding these is safe -- a human-confirmed "this genuinely has
    a stance" label is unambiguous ground truth regardless of how the row
    was originally selected for labeling, unlike the OLD "confidently
    wrong" positive pool (76+76+43=195 rows) that caused v4-v7's failure,
    which is deliberately NOT reused here since it was selected via a
    confidence filter on the POSITIVE side specifically, and re-adding it
    risks reintroducing "hard adversarial other vs random stanced" rather
    than the real, general task.

Low learning rate, few epochs, to nudge the decision boundary toward
matching human judgment specifically without catastrophically overwriting
what stage 1 learned from volume.

The 89-row spot-check set is deliberately NOT used here -- it stays
completely untouched as the held-out eval for this stage (see
score_fp_v8_polished_on_spotcheck.py), since training and evaluating on
the same data would repeat the exact mistake this whole investigation was
about avoiding.
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
NUM_EPOCHS = int(os.environ.get("NUM_EPOCHS", "5"))
LEARNING_RATE = float(os.environ.get("LEARNING_RATE", "2e-6"))  # 5x lower than stage 1's 1e-5
BASE_CHECKPOINT = "/home/nash/retrain_twostage/fp_detector_v8_representative"
SAVE_DIR = os.environ.get("SAVE_DIR", "/home/nash/retrain_twostage/fp_detector_v8_polished")


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
    print(f"Stage 2 polish: base={BASE_CHECKPOINT} LR={LEARNING_RATE} EPOCHS={NUM_EPOCHS}", flush=True)

    rand199 = pd.read_csv("/home/nash/random_fp_validation_r1_merged.csv")
    rand199 = rand199.rename(columns={"full_text": "text"})[["text", "target_entity", "genuinely_other"]]
    rand199["source"] = "random199"

    polar = pd.read_csv("/home/nash/train_polar_fp_detector_scores.csv")
    extra_neg_pool = polar[(polar["is_human"] == True) & (polar["correct"] == True)]
    # exclude any row already present in the random-199 set (unlikely given disjoint sampling, but check)
    r_keys = set(zip(rand199["text"].astype(str).str.strip(), rand199["target_entity"].astype(str).str.strip().str.lower()))
    extra_neg_pool = extra_neg_pool[~extra_neg_pool.apply(
        lambda r: (str(r["text"]).strip(), str(r["target_entity"]).strip().lower()) in r_keys, axis=1)]
    # 2026-08-23 fix #2: 1000 extra negatives (28:1 unweighted vs the 41
    # positives) swamped the positive signal even after capping the class
    # weight at 4x -- scores collapsed to near-zero for every row (max
    # 0.079, mean 0.006), no threshold from 0.5 down to 0.02 recovered
    # ANY of the 9 real positives in the held-out spot-check, despite
    # AUC=0.6264 suggesting weak aggregate ranking signal existed. Cut
    # the expansion down substantially so the positive class isn't
    # diluted past the point a gentle low-LR nudge can move it.
    n_extra = min(len(extra_neg_pool), 150)
    extra_neg = extra_neg_pool.sample(n=n_extra, random_state=99)[["text", "target_entity"]].copy()
    extra_neg["genuinely_other"] = False
    extra_neg["source"] = "expanded_human_negatives"

    df = pd.concat([rand199, extra_neg], ignore_index=True)
    df["y"] = df["genuinely_other"].astype(int)
    df["weight"] = 1.0
    # 2026-08-23 fix: full inverse-frequency weighting (28.2x here, since
    # positives dropped to 3.4% once the 1000 expanded negatives were
    # added) destabilized training -- loss oscillated wildly (0.009 to
    # 15+, grad_norm spikes to 2500+) and the model collapsed to
    # predicting everything negative (TP=0, FP=0) despite AUC actually
    # improving underneath (0.57->0.63), confirming this was a
    # calibration/instability failure, not a signal failure. Stage 1 (the
    # v8 base checkpoint) already learned reasonable class balance from
    # its own training -- this stage only needs a gentle nudge, not a
    # full rebalancing fight. Capped at 4x instead of the full ~28x.
    pos_class_weight = min((df["y"] == 0).sum() / (df["y"] == 1).sum(), 4.0)
    df.loc[df["y"] == 1, "weight"] = pos_class_weight
    print(f"Polish set: {len(df)} rows ({(df['y']==1).sum()} positive / {(df['y']==0).sum()} negative), "
          f"positive weight={pos_class_weight:.3f} (capped at 4.0)", flush=True)
    print(df.groupby("source")["y"].agg(["count"]), flush=True)

    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Device: {device}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(BASE_CHECKPOINT)

    def encode(d):
        texts = build_texts(d, "text", "target_entity")
        return tokenizer(texts, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt")

    train_ds = WeightedDataset(encode(df), df["y"].tolist(), df["weight"].tolist())

    model = WrongLabelModel(MODEL_NAME).to(device)
    state = torch.load(f"{BASE_CHECKPOINT}/model_state.pt", map_location=device)
    model.load_state_dict(state)
    print("Loaded v8 base checkpoint, continuing fine-tune on human labels only", flush=True)

    os.makedirs(SAVE_DIR, exist_ok=True)
    args = TrainingArguments(
        output_dir=SAVE_DIR,
        remove_unused_columns=False,
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=max(1, 16 // BATCH_SIZE),
        learning_rate=LEARNING_RATE,
        weight_decay=0.01,
        eval_strategy="no",
        save_strategy="no",
        logging_steps=5,
        report_to=[],
        bf16=torch.cuda.is_available(),
        label_names=["labels"],
    )

    trainer = WeightedTrainer(model=model, args=args, train_dataset=train_ds)
    trainer.train()

    torch.save(model.state_dict(), f"{SAVE_DIR}/model_state.pt")
    tokenizer.save_pretrained(SAVE_DIR)
    print(f"Saved to {SAVE_DIR}", flush=True)


if __name__ == "__main__":
    main()
