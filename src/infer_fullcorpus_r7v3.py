"""infer_fullcorpus_r7v3.py

Scores r7v3_baseline (retrain variant, ~/outputs/round8/checkpoints_twostage/
r7v3_retrain/baseline/stage{1,2}) over the full 451,815-row entity-mention
corpus, on conspiracycomments-gce (single-model sibling of
infer_fullcorpus_r7v1.py, same checkpoint also covered by
infer_fullcorpus_gpuincrease4.py's MODELS list on the other project --
this copy was queued to run in parallel on this project's spare capacity).

NOTE: this run turned out to be REDUNDANT -- a kill-monitor meant to stop
it before it duplicated gpuincrease4's r7v3_baseline pass failed to fire,
so this ran to completion anyway (~5.5 hrs of wasted GPU time, no data
harm since both copies agree). Reconstructed here from the /tmp copy
pushed to the VM (ensemble-r7v3-run, asia-southeast1-c) for the repo's
own record -- kept as a straight sibling of infer_fullcorpus_r7v1.py,
not deduplicated with infer_fullcorpus_gpuincrease4.py, to match what
actually ran.

Model: ~/outputs/round8/checkpoints_twostage/r7v3_retrain/baseline/stage{1,2}
Input: full_entity_mention_pool.parquet
Output: r7v3_fullcorpus_scores.parquet (id, target_entity, r7v3_p_other,
  r7v3_stage2_pred [only for stance-predicted rows])
"""
import os
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification

CKPT_S1 = os.path.expanduser("~/outputs/round8/checkpoints_twostage/r7v3_retrain/baseline/stage1")
CKPT_S2 = os.path.expanduser("~/outputs/round8/checkpoints_twostage/r7v3_retrain/baseline/stage2")
TAG_ARM = "r7v3_baseline"
BATCH_FILE = os.path.expanduser("~/full_entity_mention_pool.parquet")
OUT_PATH = os.path.expanduser("~/r7v3_fullcorpus_scores.parquet")
MAX_LENGTH = 768
INFER_BATCH = 48

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

    tokenizer = AutoTokenizer.from_pretrained(CKPT_S1)

    print(f"\n=== Stage1 ({TAG_ARM}) ===", flush=True)
    s1_model = load_model(CKPT_S1)
    s1_probs = score_texts(tokenizer, s1_model, texts, label="stage1")
    p_other = s1_probs[:, 0] if s1_probs.shape[1] == 2 else s1_probs[:, -1]
    df["r7v3_p_other"] = p_other
    del s1_model
    torch.cuda.empty_cache()
    df.to_parquet(OUT_PATH, index=False)
    print(f"Checkpointed after stage1: {OUT_PATH}", flush=True)

    stance_mask = p_other < 0.5
    print(f"\n=== Stage2 ({TAG_ARM}), {stance_mask.sum():,} stance-predicted rows ===", flush=True)
    stance_texts = [texts[i] for i in np.where(stance_mask)[0]]
    s2_model = load_model(CKPT_S2)
    s2_probs = score_texts(tokenizer, s2_model, stance_texts, label="stage2")
    s2_pred = np.argmax(s2_probs, axis=1)
    del s2_model
    torch.cuda.empty_cache()

    df["r7v3_stage2_pred"] = np.nan
    df.loc[stance_mask, "r7v3_stage2_pred"] = s2_pred

    df.to_parquet(OUT_PATH, index=False)
    print(f"\nSaved final: {OUT_PATH}", flush=True)
    print(f"Mean p_other: {p_other.mean():.4f}", flush=True)


if __name__ == "__main__":
    main()
