"""score_round9_binconf_and_fpv4.py

Scores the full round9 unlabeled pool (22,459 rows) with binconf_other015
(confidence + hostile/endorsement logits) AND the round-4 fine-tuned
false-positive detector, in one script since both need the pooled
representation from a forward pass (though NOT the same encoder --
binconf uses its own weights, fp_v4 uses its own fine-tuned weights, so
this is two separate forward passes, not a shared one).

For the FP-detector v4 input, silver_label = the row's target_entity's
current classification is unknown for round9 (it's an UNLABELED pool) --
so this uses binconf's OWN prediction as a stand-in for "claimed label"
where confidence is high, and marks genuinely-uncertain rows separately.
Concretely: silver_label = binconf's own argmax prediction (hostile/
endorsement/other via confidence threshold) -- this makes the FP-detector
ask "does binconf's own confident call on this row look suspicious",
which is the right question for a genuinely unlabeled population (there's
no separate silver source to check against here, unlike the training data
case).

SCOPE FIX (2026-08-21, see fp_detector_v4_no_conflict_other_FAILURE in
data/experiment_log.jsonl): v4 is ONLY scored for rows where binconf
predicts stanced (SILVER_LABEL=stanced). Rows where binconf predicts
"other" are SKIPPED for v4 -- feeding v4 a SILVER_LABEL=other/
CLASSIFIER_PREDICTED=other input (which is what binconf-predicted-other
rows would produce) is untested territory v4's training never covered,
and a direct test on 632 genuinely-correct held-out "other" rows showed
it flags 100% of them as wrong, confidently (mean score 0.915) -- a real,
confirmed failure mode, not a theoretical risk. fp_v4_score/fp_v4_flagged
are left null for these rows rather than silently producing a meaningless
number.

Output: data/processed/round9/round9_binconf_fpv4_scores.parquet
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import pandas as pd
import numpy as np
from transformers import AutoModel, AutoTokenizer

BINCONF_CHECKPOINT = "outputs/checkpoints/binconf_other015_binary_confidence"
FPV4_CHECKPOINT = "/home/nash/retrain_twostage/fp_detector_v4_finetuned"
MODEL_NAME = "answerdotai/ModernBERT-large"
MAX_LENGTH = 768
BATCH_SIZE = 16
INPUT_PATH = "data/processed/round9/round9_unlabeled_pool.parquet"
OUT_PATH = "data/processed/round9/round9_binconf_fpv4_scores.parquet"
CHECKPOINT_EVERY = 2000


class ConfidenceModel(nn.Module):
    def __init__(self, model_name):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size = self.encoder.config.hidden_size
        self.classifier = nn.Linear(hidden_size, 2)
        self.confidence_head = nn.Linear(hidden_size, 1)

    def forward(self, input_ids=None, attention_mask=None, **kwargs):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        last_hidden = out.last_hidden_state
        mask = attention_mask.unsqueeze(-1).float()
        pooled = (last_hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        logits = self.classifier(pooled)
        confidence = torch.sigmoid(self.confidence_head(pooled)).squeeze(-1)
        return logits, confidence


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


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}", flush=True)

    df = pd.read_parquet(INPUT_PATH)
    print(f"{len(df)} rows to score", flush=True)
    plain_texts = ("[ENTITY: " + df["target_entity"].fillna("unknown").astype(str) + "] " + df["text"].astype(str)).tolist()

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    # --- Pass 1: binconf_other015 ---
    print("\n=== Scoring with binconf_other015 ===", flush=True)
    binconf = ConfidenceModel(MODEL_NAME).to(device)
    state = torch.load(f"{BINCONF_CHECKPOINT}/model_state.pt", map_location=device)
    binconf.load_state_dict(state)
    binconf.eval()

    all_conf, all_logits = [], []
    with torch.no_grad():
        for i in range(0, len(plain_texts), BATCH_SIZE):
            batch = plain_texts[i:i + BATCH_SIZE]
            enc = tokenizer(batch, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt").to(device)
            logits, conf = binconf(**enc)
            all_conf.append(conf.cpu())
            all_logits.append(logits.cpu())
            if i % (BATCH_SIZE * 50) == 0:
                print(f"  {i}/{len(plain_texts)}", flush=True)
    confidence = torch.cat(all_conf).numpy()
    logits = torch.cat(all_logits).numpy()
    probs = F.softmax(torch.tensor(logits), dim=1).numpy()

    df["binconf_confidence"] = confidence
    df["binconf_predicted"] = np.where(
        confidence < 0.5, "other",
        np.where(probs[:, 0] >= probs[:, 1], "hostile", "endorsement"),
    )
    del binconf
    torch.cuda.empty_cache()

    df.to_parquet(OUT_PATH, index=False)
    print(f"Checkpointed after binconf pass: {OUT_PATH}", flush=True)
    print(df["binconf_predicted"].value_counts(), flush=True)

    # --- Pass 2: FP-detector v4 (silver_label = binconf's own prediction) ---
    # SCOPE FIX: only score rows where binconf predicts stanced. Rows where
    # binconf predicts "other" would produce SILVER_LABEL=other/
    # CLASSIFIER_PREDICTED=other -- untested, confirmed-broken input (see
    # module docstring). Left null rather than silently wrong.
    print("\n=== Scoring with FP-detector v4 (stanced-predicted rows only) ===", flush=True)
    stanced_mask = df["binconf_predicted"] != "other"
    n_skipped = (~stanced_mask).sum()
    print(f"Skipping {n_skipped} rows binconf predicted as 'other' (untested input shape for v4)", flush=True)

    df["fp_v4_score"] = np.nan
    df["fp_v4_flagged"] = pd.NA

    fpv4_texts = (
        "[ENTITY: " + df.loc[stanced_mask, "target_entity"].fillna("unknown").astype(str)
        + " | SILVER_LABEL: " + df.loc[stanced_mask, "binconf_predicted"].astype(str)
        + " | CLASSIFIER_PREDICTED: stanced] "
        + df.loc[stanced_mask, "text"].astype(str)
    ).tolist()

    fpv4_tokenizer = AutoTokenizer.from_pretrained(FPV4_CHECKPOINT)
    fpv4 = WrongLabelModel(MODEL_NAME).to(device)
    state2 = torch.load(f"{FPV4_CHECKPOINT}/model_state.pt", map_location=device)
    fpv4.load_state_dict(state2)
    fpv4.eval()

    all_fp_logits = []
    with torch.no_grad():
        for i in range(0, len(fpv4_texts), BATCH_SIZE):
            batch = fpv4_texts[i:i + BATCH_SIZE]
            enc = fpv4_tokenizer(batch, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt").to(device)
            logits = fpv4(**enc)
            all_fp_logits.append(logits.cpu())
            if i % (BATCH_SIZE * 50) == 0:
                print(f"  {i}/{len(fpv4_texts)}", flush=True)
    fp_logits = torch.cat(all_fp_logits).numpy()
    fp_probs = F.softmax(torch.tensor(fp_logits), dim=1).numpy()[:, 1]
    df.loc[stanced_mask, "fp_v4_score"] = fp_probs
    df.loc[stanced_mask, "fp_v4_flagged"] = fp_probs >= 0.5

    df.to_parquet(OUT_PATH, index=False)
    print(f"\nSaved final: {OUT_PATH}", flush=True)
    print(f"binconf low-confidence (0.3-0.7, genuinely uncertain): {((confidence>=0.3)&(confidence<=0.7)).sum()}", flush=True)
    print(f"FP-v4 flagged (score>=0.5), among scored rows: {(df['fp_v4_flagged']==True).sum()}", flush=True)
    print(f"FP-v4 not scored (binconf predicted other): {n_skipped}", flush=True)


if __name__ == "__main__":
    main()
