"""train_binary_confidence.py

Stage 1 of the cascade-design reframe (2026-08-14/15 session): instead of a
3-way (hostile/endorsement/other) classifier where stage1's has-stance-vs-
other gate has repeatedly stalled around kappa 0.32-0.35 across every
intervention tried (class reweighting, more context, more human "other"
labels -- see handoff/task_stance_classifier_finetune.md and this session's
round10 retrain), train a clean BINARY hostile-vs-endorsement classifier
only (drop "other" from training entirely -- stage2_baseline has
consistently scored kappa 0.7+ across every run this project has done,
confirming polarity is a well-learned task; it's specifically the "is
there a stance at all" gate that's weak).

Paired with a self-assessed confidence head (DeVries & Taylor 2018,
"Learning Confidence for Out-of-Distribution Detection"): the model
outputs both class logits and a scalar confidence c in [0,1]. At training
time, the model may "peek" at the true label proportional to (1-c) to
reduce its task loss, but pays a -log(c) penalty for doing so -- this
teaches it to output low c specifically when uncertain, without needing
any new labels beyond the existing hostile/endorsement ones. Compared at
eval time against plain softmax margin (top prob - second prob) as a
baseline confidence signal, since margin is "free" from any classifier
and the DeVries head needs to actually beat it to be worth the added
complexity.

Ensemble-disagreement as a third confidence signal is deliberately NOT
built here -- it can be computed later from the existing 6-model
ensemble's predictions on the same val set (already run, already have
prediction files) without training anything new. Comparing all three is
Stage 6 (validation harness), not this script.

Reuses the training patterns established in train_twostage_patched.py
(WeightedTrainer, entity-prefix encoding, class weighting) rather than
reinventing them.
"""
import os

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import classification_report, cohen_kappa_score
from transformers import (
    AutoModel,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

INPUT_FILE = os.environ.get("INPUT_FILE", "/data/stance_classifier_training_data_round7_bigval_split_v2.parquet")
MODEL_NAME = os.environ.get("MODEL_NAME", "answerdotai/ModernBERT-large")
MAX_LENGTH = int(os.environ.get("MAX_LENGTH", "768"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "4"))
NUM_EPOCHS = int(os.environ.get("NUM_EPOCHS", "2"))
GRAD_CKPT = os.environ.get("GRAD_CKPT", "0") == "1"
TAG = os.environ.get("TAG", "binconf")
SAVE_ROOT = os.environ.get("SAVE_ROOT", "/home/nash/retrain_twostage")
# Continuing training from an already-converged checkpoint needs a much
# lower LR than training from scratch -- the original 2e-5 caused a real
# NaN divergence (loss->0, grad_norm->nan, never recovers) a few hundred
# steps into a continuation run 2026-08-18. Default drops automatically
# when INIT_FROM_CHECKPOINT is set; LEARNING_RATE env var overrides either way.
_default_lr = 2e-6 if os.environ.get("INIT_FROM_CHECKPOINT") else 2e-5
LEARNING_RATE = float(os.environ.get("LEARNING_RATE", str(_default_lr)))
# Defensive cap on marked-window text length -- some rows produced up to
# 61,535 chars (932 rows >5,000 chars) when every occurrence of a
# frequently-mentioned entity gets its own wrapped window; tokenizer
# truncation (MAX_LENGTH) should handle this, but capping upstream avoids
# feeding pathologically long strings into the tokenizer at all.
MAX_MARKED_TEXT_CHARS = int(os.environ.get("MAX_MARKED_TEXT_CHARS", "4000"))
# DeVries & Taylor's budget parameter: target average -log(c) penalty.
# Their paper anneals lambda to hit this target; we use a fixed lambda and
# report the achieved average confidence directly instead of dynamic
# annealing, to keep this a tractable single run -- flagged as a known
# simplification, worth revisiting if the confidence head's calibration
# looks off in the Stage 6 validation.
CONF_LAMBDA = float(os.environ.get("CONF_LAMBDA", "0.1"))
# Separate lambda for the "other" branch's pure confidence-suppression
# loss -- other rows have no classification signal at all, only a
# confidence target, so this doesn't need to trade off against a task
# loss the way CONF_LAMBDA does.
OTHER_CONF_LAMBDA = float(os.environ.get("OTHER_CONF_LAMBDA", "0.15"))

LABEL_TO_ID = {"hostile": 0, "endorsement": 1, "other": -1}


class ConfidenceModel(nn.Module):
    """Wraps a base transformer encoder with two heads: a 2-class
    classifier and a scalar confidence head, per DeVries & Taylor 2018."""

    def __init__(self, model_name):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size = self.encoder.config.hidden_size
        self.classifier = nn.Linear(hidden_size, 2)
        self.confidence_head = nn.Linear(hidden_size, 1)

    def forward(self, input_ids=None, attention_mask=None, **kwargs):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        # Mean-pool over the attention mask -- works for any encoder
        # architecture (RoBERTa, ModernBERT) without relying on a
        # model-specific pooler output.
        last_hidden = out.last_hidden_state
        mask = attention_mask.unsqueeze(-1).float()
        pooled = (last_hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        logits = self.classifier(pooled)
        confidence = torch.sigmoid(self.confidence_head(pooled)).squeeze(-1)
        return logits, confidence


class BinaryConfDataset(torch.utils.data.Dataset):
    """labels: 0=hostile, 1=endorsement, -1=other (sentinel -- no valid
    polarity target, but a real, explicit confidence-supervision signal:
    other rows should push the confidence head toward 0)."""

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


class ConfidenceTrainer(Trainer):
    """Two-branch confidence loss, split by whether a row has a valid
    polarity label:
    - hostile/endorsement rows: DeVries & Taylor (2018) interpolation --
      the model may "peek" at the true label proportional to (1-c),
      lowering task_loss, but pays a -log(c) penalty for doing so. Teaches
      "how sure are you about polarity."
    - other rows (labels == -1): no polarity target exists, so there's no
      classification loss to compute -- instead, directly penalize high
      confidence (-log(1-c)), teaching "when there's no clear stance, say
      so regardless of what polarity you'd guess." This is a direct,
      explicit use of the human "other" labels, not something we hope
      emerges implicitly from training on polar examples alone."""

    def __init__(self, *args, class_weights=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.class_weights = class_weights

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        # 2026-08-17 variant: 2026-08-15's polar-only version (below, in the
        # is_polar branch) is proven -- kappa 0.7111, confidence spread
        # 94.7%/74.0% high/low, P(other conf < polar conf)=0.700 on a real
        # VM run. This adds back "other" supervision, but properly this
        # time: OTHER_CONF_LAMBDA defaults to 0.15 (not the original 1.0,
        # which was 10x CONF_LAMBDA and let the other-suppression loss
        # dominate -- Nash's original, correct critique of the first
        # attempt). At low weight this nudges confidence down on "other"
        # rows without the loss term dominating the shared encoder the way
        # it did before. Whether this beats the polar-only 0.700 baseline
        # -- or just costs polarity kappa for no real gain -- is the
        # empirical question this run answers; not assumed either way.
        weights = inputs.pop("sample_weight")
        labels = inputs.pop("labels")
        logits, confidence = model(**inputs)
        probs = F.softmax(logits, dim=-1)

        eps = 1e-12
        c = confidence.clamp(eps, 1 - eps)
        is_other = labels == -1
        is_polar = ~is_other

        per_example_loss = torch.zeros_like(c)

        if is_polar.any():
            polar_labels = labels[is_polar].clamp(min=0)
            one_hot = F.one_hot(polar_labels, num_classes=2).float()
            interpolated = c[is_polar].unsqueeze(-1) * probs[is_polar] + (1 - c[is_polar].unsqueeze(-1)) * one_hot
            task_loss = -torch.log(interpolated.gather(1, polar_labels.unsqueeze(-1)).squeeze(-1).clamp(min=eps))
            confidence_loss = -torch.log(c[is_polar])
            polar_weights = weights[is_polar]
            if self.class_weights is not None:
                polar_weights = polar_weights * self.class_weights.to(logits.device)[polar_labels]
            per_example_loss[is_polar] = (task_loss + CONF_LAMBDA * confidence_loss) * polar_weights

        if is_other.any():
            other_conf_loss = -torch.log(1 - c[is_other])
            per_example_loss[is_other] = OTHER_CONF_LAMBDA * other_conf_loss * weights[is_other]

        loss = per_example_loss.mean()
        return (loss, {"logits": logits, "confidence": confidence}) if return_outputs else loss

    def prediction_step(self, model, inputs, prediction_loss_only, ignore_keys=None):
        # Deliberately simple: HF's default prediction_step assumes a
        # standard ModelOutput with .loss/.logits, which this custom
        # two-head model doesn't produce. Rather than risk an internals
        # mismatch crashing a multi-hour run, this only computes loss (for
        # eval_loss logging) -- kappa/margin/confidence are all computed
        # in the standalone manual eval pass at the end of main(), which
        # doesn't touch Trainer internals at all.
        inputs = {k: v.to(self.args.device) for k, v in inputs.items()}
        with torch.no_grad():
            loss = self.compute_loss(model, dict(inputs))
        return (loss.detach(), None, None)


def compute_metrics(eval_pred):
    # Not used for this model -- eval_strategy is "no" below, and the
    # manual eval pass in main() reports kappa/margin/confidence properly.
    return {}


def encode(tokenizer, texts):
    return tokenizer(list(texts), truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt")


def _texts_with_entity(df):
    if "target_entity" in df.columns:
        return ("[ENTITY: " + df["target_entity"].fillna("unknown").astype(str) + "] "
                + df["text"].astype(str)).tolist()
    return df["text"].tolist()


WINDOW_WORDS = 15


def _texts_with_marked_window(df, desc_lookup):
    """[ENTITY: name] [ABOUT: description] <full text, with the entity's
    +-15-word local window wrapped in >>...<< markers in place>. Full text
    is preserved (not replaced by the window, unlike the older
    stance_window_utils.py design) -- see test_marked_window_input.py's
    docstring for why this exists and the inference-only result
    (2026-08-18: kappa 0.7466->0.6953, a real drop, but on a checkpoint
    that had never seen this format during training -- this run is the
    fair test, continuing from that same checkpoint so the model gets a
    chance to actually learn what the markers mean."""
    import json as _json

    texts = []
    for _, row in df.iterrows():
        text = str(row["text"])
        entity = row.get("target_entity", "unknown")
        desc = desc_lookup.get(str(entity).lower(), "")
        about = f" [ABOUT: {desc}]" if desc else ""

        spans = row.get("entity_spans")
        if isinstance(spans, str):
            try:
                spans = _json.loads(spans)
            except (_json.JSONDecodeError, TypeError):
                spans = []
        if not spans:
            texts.append(f"[ENTITY: {entity}]{about} {text}")
            continue

        marked = text
        offset = 0
        for s in sorted(spans, key=lambda x: x["start"]):
            start, end = s["start"] + offset, s["end"] + offset
            before_words = marked[:start].split()
            win_start_word_idx = max(0, len(before_words) - WINDOW_WORDS)
            win_start_char = len(" ".join(before_words[:win_start_word_idx])) if win_start_word_idx else 0
            if win_start_word_idx > 0:
                win_start_char += 1
            marked = marked[:win_start_char] + ">>" + marked[win_start_char:end] + "<<" + marked[end:]
            offset += 4
        if len(marked) > MAX_MARKED_TEXT_CHARS:
            marked = marked[:MAX_MARKED_TEXT_CHARS]
        texts.append(f"[ENTITY: {entity}]{about} {marked}")
    return texts


INCLUDE_OTHER = os.environ.get("INCLUDE_OTHER", "0") == "1"
INPUT_FORMAT = os.environ.get("INPUT_FORMAT", "plain")  # "plain" or "marked_window"
INIT_FROM_CHECKPOINT = os.environ.get("INIT_FROM_CHECKPOINT", "")  # path to model_state.pt to continue from
DESC_LOOKUP_FILE = os.environ.get("DESC_LOOKUP_FILE", "entity_description_lookup.csv")


def main():
    os.makedirs(SAVE_ROOT, exist_ok=True)
    print(f"MODEL_NAME={MODEL_NAME} MAX_LENGTH={MAX_LENGTH} BATCH_SIZE={BATCH_SIZE} "
          f"NUM_EPOCHS={NUM_EPOCHS} GRAD_CKPT={GRAD_CKPT} CONF_LAMBDA={CONF_LAMBDA} "
          f"INCLUDE_OTHER={INCLUDE_OTHER} OTHER_CONF_LAMBDA={OTHER_CONF_LAMBDA if INCLUDE_OTHER else 'n/a'} "
          f"LEARNING_RATE={LEARNING_RATE} INPUT_FORMAT={INPUT_FORMAT}", flush=True)

    df = pd.read_parquet(INPUT_FILE)
    df["stage_label"] = df["label"].map(LABEL_TO_ID)

    # TRAIN: polar only by default (hostile/endorsement) -- "other" rows
    # excluded, matching the proven-good 2026-08-15 run (kappa 0.7111,
    # P(other conf < polar conf)=0.700). Set INCLUDE_OTHER=1 to add "other"
    # rows back in at OTHER_CONF_LAMBDA weight (default 0.15, not the
    # original 1.0 that let it dominate) -- see ConfidenceTrainer's
    # docstring for the full reasoning either way.
    train_labels = ["hostile", "endorsement", "other"] if INCLUDE_OTHER else ["hostile", "endorsement"]
    train_df = df[(df["split"] == "train") & (df["label"].isin(train_labels))].copy()
    # VAL: keep "other" rows too (never trained on) specifically so the
    # final eval can test whether polarity-difficulty confidence happens
    # to separate them from polar rows -- an empirical question, not
    # something assumed or forced.
    val_df = df[(df["split"] == "val") & (df["label"].isin(["hostile", "endorsement", "other"]))].copy()
    print(f"train ({'polar+other' if INCLUDE_OTHER else 'polar only'})={len(train_df):,} val (polar+other)={len(val_df):,}", flush=True)
    print(f"train label counts={dict(train_df['label'].value_counts())}", flush=True)
    print(f"val label counts={dict(val_df['label'].value_counts())}", flush=True)

    if torch.cuda.is_available():
        device = "cuda"
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    if INPUT_FORMAT == "marked_window":
        desc_lookup = pd.read_csv(DESC_LOOKUP_FILE).assign(
            entity_lower=lambda d: d["entity"].str.lower()
        ).set_index("entity_lower")["description"].to_dict()
        print(f"INPUT_FORMAT=marked_window, {len(desc_lookup)} entity descriptions loaded", flush=True)
        train_texts = _texts_with_marked_window(train_df, desc_lookup)
        val_texts = _texts_with_marked_window(val_df, desc_lookup)
    else:
        train_texts = _texts_with_entity(train_df)
        val_texts = _texts_with_entity(val_df)
    train_enc = encode(tokenizer, train_texts)
    val_enc = encode(tokenizer, val_texts)
    train_ds = BinaryConfDataset(train_enc, train_df["stage_label"].tolist(), train_df["weight"].tolist())
    val_ds = BinaryConfDataset(val_enc, val_df["stage_label"].tolist(), [1.0] * len(val_df))

    model = ConfidenceModel(MODEL_NAME).to(device)
    if INIT_FROM_CHECKPOINT:
        print(f"Continuing from checkpoint: {INIT_FROM_CHECKPOINT}", flush=True)
        state = torch.load(INIT_FROM_CHECKPOINT, map_location=device)
        model.load_state_dict(state)

    polar_train = train_df[train_df["stage_label"] != -1]
    class_counts = polar_train["stage_label"].value_counts().sort_index()
    class_weights = torch.tensor(
        [len(polar_train) / (2 * class_counts.get(i, 1)) for i in range(2)], dtype=torch.float
    )

    out_dir = f"{SAVE_ROOT}/{TAG}_binary_confidence"
    os.makedirs(out_dir, exist_ok=True)
    args = TrainingArguments(
        output_dir=out_dir,
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
        gradient_checkpointing=GRAD_CKPT,
        label_names=["labels"],
    )

    trainer = ConfidenceTrainer(
        model=model, args=args, train_dataset=train_ds, eval_dataset=val_ds,
        compute_metrics=compute_metrics, class_weights=class_weights,
    )
    trainer.train()

    torch.save(model.state_dict(), f"{out_dir}/model_state.pt")
    tokenizer.save_pretrained(out_dir)
    print(f"Saved to {out_dir}", flush=True)

    # Final eval on the FULL val set (polar + other) -- run the model over
    # everything once, then split the analysis by row type.
    model.eval()
    with torch.no_grad():
        all_logits, all_conf = [], []
        for i in range(0, len(val_df), 8):
            batch = {k: v[i:i+8].to(device) for k, v in val_enc.items()}
            logits, conf = model(**batch)
            all_logits.append(logits.cpu())
            all_conf.append(conf.cpu())
    logits = torch.cat(all_logits).numpy()
    confidence = torch.cat(all_conf).numpy()
    probs = F.softmax(torch.tensor(logits), dim=-1).numpy()
    preds = np.argmax(logits, axis=1)
    margin = np.abs(probs[:, 0] - probs[:, 1])
    stage_label = val_df["stage_label"].to_numpy()
    is_other = stage_label == -1

    # 1. Polar-only: does the binary classifier itself work, and does its
    #    confidence track correctness on the task it's actually trained for.
    true_polar = stage_label[~is_other]
    preds_polar = preds[~is_other]
    correct_polar = (preds_polar == true_polar).astype(int)
    margin_polar = margin[~is_other]
    conf_polar = confidence[~is_other]

    kappa = cohen_kappa_score(true_polar, preds_polar)
    print(f"\n=== binary hostile/endorsement validation (polar rows only, n={len(true_polar)}) === kappa={kappa:.4f}", flush=True)
    print(classification_report(true_polar, preds_polar, target_names=["hostile", "endorsement"]), flush=True)

    margin_corr = np.corrcoef(margin_polar, correct_polar)[0, 1]
    conf_corr = np.corrcoef(conf_polar, correct_polar)[0, 1]
    print(f"\nSoftmax margin vs correctness: corr={margin_corr:.4f}, mean_margin={margin_polar.mean():.4f}", flush=True)
    print(f"Self-assessed confidence vs correctness: corr={conf_corr:.4f}, mean_confidence={conf_polar.mean():.4f}", flush=True)

    hi_margin = margin_polar >= np.median(margin_polar)
    hi_conf = conf_polar >= np.median(conf_polar)
    print(f"Accuracy at high margin (>=median): {correct_polar[hi_margin].mean():.4f} (n={hi_margin.sum()})", flush=True)
    print(f"Accuracy at low margin (<median):   {correct_polar[~hi_margin].mean():.4f} (n={(~hi_margin).sum()})", flush=True)
    print(f"Accuracy at high self-conf (>=median): {correct_polar[hi_conf].mean():.4f} (n={hi_conf.sum()})", flush=True)
    print(f"Accuracy at low self-conf (<median):   {correct_polar[~hi_conf].mean():.4f} (n={(~hi_conf).sum()})", flush=True)

    # 2. THE key new check: does self-assessed confidence actually come
    #    out lower for genuine human-labeled "other" rows than for polar
    #    rows? This is the real test of whether the redesign worked --
    #    without it, there's no evidence the confidence head learned
    #    anything about ambiguity specifically, vs. just general task
    #    difficulty on the polar rows alone.
    print(f"\n=== other vs polar confidence comparison (n_other={is_other.sum()}, n_polar={(~is_other).sum()}) ===", flush=True)
    print(f"Mean self-confidence on OTHER rows:  {confidence[is_other].mean():.4f}", flush=True)
    print(f"Mean self-confidence on POLAR rows:  {confidence[~is_other].mean():.4f}", flush=True)
    print(f"Mean softmax margin on OTHER rows:   {margin[is_other].mean():.4f}", flush=True)
    print(f"Mean softmax margin on POLAR rows:   {margin[~is_other].mean():.4f}", flush=True)
    # AUC-style separation check: what fraction of (other, polar) pairs
    # have other's confidence lower than polar's? 0.5 = no separation,
    # 1.0 = perfect separation.
    other_conf = confidence[is_other]
    polar_conf = confidence[~is_other]
    if len(other_conf) and len(polar_conf):
        separation = (other_conf[:, None] < polar_conf[None, :]).mean()
        print(f"P(other confidence < polar confidence) [self-conf]: {separation:.4f}", flush=True)
        other_margin, polar_margin = margin[is_other], margin[~is_other]
        separation_margin = (other_margin[:, None] < polar_margin[None, :]).mean()
        print(f"P(other margin < polar margin) [softmax margin]: {separation_margin:.4f}", flush=True)

    pd.DataFrame({
        "label": val_df["label"].to_numpy(), "stage_label": stage_label, "pred": preds,
        "margin": margin, "self_confidence": confidence, "is_other": is_other,
    }).to_csv(f"/home/nash/preds_{TAG}_binary_confidence.csv", index=False)


if __name__ == "__main__":
    main()
