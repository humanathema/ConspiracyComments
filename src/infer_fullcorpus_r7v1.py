"""infer_fullcorpus_r7v1.py

Scores r7v1_baseline (one of the 5 models in the documented 0.5773
kappa ensemble, r7v2_split+r7v1_baseline+r5v2_baseline+r5v2_split+
r7v3_baseline majority vote + frontier escalation) over the full
451,815-row entity-mention corpus. Runs on the conspiracycomments-gce
project since that's where this checkpoint lives (checkpoints split
across 2 GCP projects, see infra_map.jsonl).

Adapted from infer_round9_twostage.py -- same two-stage architecture
(stage1 has-stance-vs-other, stage2 hostile-vs-endorsement), but saves
p_other (continuous probability) not just argmax, since the validated
0.5656-kappa blend formula needs the continuous ensemble p_hasstance
value (old_p_hasstance = 1 - mean(p_other across the 5 models)), not a
majority-vote label alone.

Model: ~/retrain_twostage/r7v1_baseline_stage{1,2}
Input: full_entity_mention_pool.parquet
Output: r7v1_fullcorpus_scores.parquet (id, target_entity, r7v1_p_other,
  r7v1_stage2_pred [only for stance-predicted rows])
"""
import os
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification

CKPT_ROOT = os.path.expanduser("~/retrain_twostage")
TAG_ARM = "r7v1_baseline"
BATCH_FILE = os.path.expanduser("~/full_entity_mention_pool.parquet")
OUT_PATH = os.path.expanduser("~/r7v1_fullcorpus_scores.parquet")
MAX_LENGTH = 768
INFER_BATCH = 48
CHECKPOINT_EVERY = 20000

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Device: {device}", flush=True)


def load_model(path):
    return AutoModelForSequenceClassification.from_pretrained(
        path, torch_dtype=torch.float16
    ).to(device).eval()


def score_texts(tokenizer, model, texts, label=""):
    probs = []
    n = len(texts)
    with torch.no_grad():
        for i in range(0, n, INFER_BATCH):
            batch = list(texts[i:i + INFER_BATCH])
            enc = tokenizer(batch, max_length=MAX_LENGTH, truncation=True, padding=True, return_tensors="pt")
            enc = {k: v.to(device) for k, v in enc.items()}
            probs.append(F.softmax(model(**enc).logits, dim=-1).cpu().float().numpy())
            if i % (INFER_BATCH * 200) == 0:
                print(f"  [{label}] {i}/{n}", flush=True)
    return np.concatenate(probs, axis=0)


def main():
    print(f"Loading batch from {BATCH_FILE} ...", flush=True)
    df = pd.read_parquet(BATCH_FILE)
    print(f"{len(df):,} rows", flush=True)
    texts = ("[ENTITY: " + df["target_entity"].fillna("unknown").astype(str) + "] " + df["text"].astype(str)).tolist()

    s1_path = f"{CKPT_ROOT}/{TAG_ARM}_stage1"
    s2_path = f"{CKPT_ROOT}/{TAG_ARM}_stage2"
    tokenizer = AutoTokenizer.from_pretrained(s1_path)

    print(f"\n=== Stage1 ({TAG_ARM}) ===", flush=True)
    s1_model = load_model(s1_path)
    s1_probs = score_texts(tokenizer, s1_model, texts, label="stage1")
    p_other = s1_probs[:, 0] if s1_probs.shape[1] == 2 else s1_probs[:, -1]
    df["r7v1_p_other"] = p_other
    del s1_model
    torch.cuda.empty_cache()
    df.to_parquet(OUT_PATH, index=False)
    print(f"Checkpointed after stage1: {OUT_PATH}", flush=True)

    stance_mask = p_other < 0.5
    print(f"\n=== Stage2 ({TAG_ARM}), {stance_mask.sum():,} stance-predicted rows ===", flush=True)
    stance_texts = [texts[i] for i in np.where(stance_mask)[0]]
    s2_model = load_model(s2_path)
    s2_probs = score_texts(tokenizer, s2_model, stance_texts, label="stage2")
    s2_pred = np.argmax(s2_probs, axis=1)
    del s2_model
    torch.cuda.empty_cache()

    df["r7v1_stage2_pred"] = np.nan
    df.loc[stance_mask, "r7v1_stage2_pred"] = s2_pred

    df.to_parquet(OUT_PATH, index=False)
    print(f"\nSaved final: {OUT_PATH}", flush=True)
    print(f"Mean p_other: {p_other.mean():.4f}", flush=True)


if __name__ == "__main__":
    main()
