"""infer_fullcorpus_gpuincrease4.py

Scores the 4 gpuincrease-hosted models from the documented 0.5773-kappa
5-model ensemble (r7v2_split, r5v2_baseline, r5v2_split, r7v3_baseline --
the 5th, r7v1_baseline, runs separately on conspiracycomments-gce via
infer_fullcorpus_r7v1.py) over the full 451,815-row entity-mention
corpus. Same two-stage architecture and p_other-tracking approach as
that script.

Model paths:
  r7v2_split (redesign): ~/retrain_twostage/r7v2_redesign_stage{1,2}
  r5v2_baseline:         ~/retrain_twostage/r5v2_baseline_stage{1,2}
  r5v2_split (redesign): ~/retrain_twostage/r5v2_redesign_stage{1,2}
  r7v3_baseline:         ~/outputs/round8/checkpoints_twostage/r7v3_retrain/baseline/stage{1,2}
    (r7v3_retrain used, not plain r7v3 -- documented as the better
    checkpoint, see infra_map.jsonl)

Input: full_entity_mention_pool.parquet
Output: gpuincrease4_fullcorpus_scores.parquet (id, target_entity, one
  <model>_p_other + <model>_stage2_pred column pair per model)
"""
import os
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification

BATCH_FILE = os.path.expanduser("~/full_entity_mention_pool.parquet")
OUT_PATH = os.path.expanduser("~/gpuincrease4_fullcorpus_scores.parquet")
MAX_LENGTH = 768
INFER_BATCH = 48

MODELS = [
    ("r7v2_split", os.path.expanduser("~/retrain_twostage/r7v2_redesign_stage1"), os.path.expanduser("~/retrain_twostage/r7v2_redesign_stage2")),
    ("r5v2_baseline", os.path.expanduser("~/retrain_twostage/r5v2_baseline_stage1"), os.path.expanduser("~/retrain_twostage/r5v2_baseline_stage2")),
    ("r5v2_split", os.path.expanduser("~/retrain_twostage/r5v2_redesign_stage1"), os.path.expanduser("~/retrain_twostage/r5v2_redesign_stage2")),
    ("r7v3_baseline", os.path.expanduser("~/outputs/round8/checkpoints_twostage/r7v3_retrain/baseline/stage1"), os.path.expanduser("~/outputs/round8/checkpoints_twostage/r7v3_retrain/baseline/stage2")),
]

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Device: {device}", flush=True)


def load_model(path):
    return AutoModelForSequenceClassification.from_pretrained(path, torch_dtype=torch.float16).to(device).eval()


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

    for name, s1_path, s2_path in MODELS:
        print(f"\n{'='*20} {name} {'='*20}", flush=True)
        tokenizer = AutoTokenizer.from_pretrained(s1_path)

        s1_model = load_model(s1_path)
        s1_probs = score_texts(tokenizer, s1_model, texts, label=f"{name}_stage1")
        p_other = s1_probs[:, 0] if s1_probs.shape[1] == 2 else s1_probs[:, -1]
        df[f"{name}_p_other"] = p_other
        del s1_model
        torch.cuda.empty_cache()
        df.to_parquet(OUT_PATH, index=False)
        print(f"Checkpointed after {name} stage1: {OUT_PATH}", flush=True)

        stance_mask = p_other < 0.5
        stance_texts = [texts[i] for i in np.where(stance_mask)[0]]
        s2_model = load_model(s2_path)
        s2_probs = score_texts(tokenizer, s2_model, stance_texts, label=f"{name}_stage2")
        s2_pred = np.argmax(s2_probs, axis=1)
        del s2_model
        torch.cuda.empty_cache()

        df[f"{name}_stage2_pred"] = np.nan
        df.loc[stance_mask, f"{name}_stage2_pred"] = s2_pred
        df.to_parquet(OUT_PATH, index=False)
        print(f"Checkpointed after {name} stage2: {OUT_PATH} (mean p_other={p_other.mean():.4f})", flush=True)

    print(f"\nAll 4 models done. Saved {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
