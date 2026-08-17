"""reinfer_ensemble_probs.py

Re-inference to recover full softmax probabilities (not just argmax) from
the existing 8-model two-stage ensemble (r7v1/r7v2/r7v3/r5v2 x baseline/
split), for both the 680-row val set and the round9 unlabeled pool
(22,459 rows). Motivation: the confidence-stratification check earlier
tonight showed ensemble vote-agreement is already a strong signal
(81.7% accuracy at 8/8 agreement vs 53.2% at any disagreement), but only
hard argmax predictions were ever saved -- this recovers the continuous
probabilities so confidence can be computed per-model, not just via vote
count, ahead of feeding a confidence-weighted score into the regression.

Runs stage1 (has_stance vs other) + stage2 (endorsement vs hostile, or
3-way for the split/redesign arm's stage2) for ONE model, on ONE input
file, outputting full class probabilities per row. Meant to be invoked
once per (model, stage) combination present on whichever VM is running it
-- each VM only has a subset of the 8 models' checkpoints.

Usage (env vars):
  STAGE1_DIR, STAGE2_DIR: checkpoint directories for this model's two stages
  ARM: "baseline" (stage2 is 2-class endorsement/hostile) or "split" (stage2 is
       3-class hostile/endorsement/ambiguous, per train_twostage_patched.py's
       run_redesign_arm)
  INPUT_FILE: parquet with text + target_entity columns
  OUTPUT_FILE: where to write per-row probabilities
  MODEL_TAG: label for this model, included in output for later merging
  MAX_LENGTH, BATCH_SIZE: same defaults as training
"""
import os

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from transformers import AutoModelForSequenceClassification, AutoTokenizer

STAGE1_DIR = os.environ["STAGE1_DIR"]
STAGE2_DIR = os.environ["STAGE2_DIR"]
ARM = os.environ.get("ARM", "baseline")
INPUT_FILE = os.environ["INPUT_FILE"]
OUTPUT_FILE = os.environ["OUTPUT_FILE"]
MODEL_TAG = os.environ["MODEL_TAG"]
MAX_LENGTH = int(os.environ.get("MAX_LENGTH", "768"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "16"))


def _texts_with_entity(df):
    if "target_entity" in df.columns:
        return ("[ENTITY: " + df["target_entity"].fillna("unknown").astype(str) + "] "
                + df["text"].astype(str)).tolist()
    return df["text"].tolist()


def run_stage(model_dir, texts, tokenizer, device):
    model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(device)
    model.eval()
    all_probs = []
    with torch.no_grad():
        for i in range(0, len(texts), BATCH_SIZE):
            batch_texts = texts[i:i + BATCH_SIZE]
            enc = tokenizer(batch_texts, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt").to(device)
            logits = model(**enc).logits
            probs = F.softmax(logits, dim=-1).cpu().numpy()
            all_probs.append(probs)
            if i % (BATCH_SIZE * 50) == 0:
                print(f"  {i}/{len(texts)}", flush=True)
    del model
    torch.cuda.empty_cache()
    return np.concatenate(all_probs, axis=0)


def main():
    print(f"MODEL_TAG={MODEL_TAG} ARM={ARM} INPUT_FILE={INPUT_FILE}", flush=True)
    df = pd.read_parquet(INPUT_FILE)
    texts = _texts_with_entity(df)
    print(f"{len(texts):,} rows to score", flush=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(STAGE1_DIR)

    print("Stage 1 (has_stance vs other)...", flush=True)
    s1_probs = run_stage(STAGE1_DIR, texts, tokenizer, device)  # [:,0]=other-ish, [:,1]=has_stance-ish per training label map
    print("Stage 2...", flush=True)
    s2_probs = run_stage(STAGE2_DIR, texts, tokenizer, device)

    out = pd.DataFrame({
        "id": df["id"] if "id" in df.columns else np.arange(len(df)),
        f"{MODEL_TAG}_s1_p_other": s1_probs[:, 0],
        f"{MODEL_TAG}_s1_p_hasstance": s1_probs[:, 1],
    })
    if ARM == "baseline":
        out[f"{MODEL_TAG}_s2_p_hostile"] = s2_probs[:, 0]
        out[f"{MODEL_TAG}_s2_p_endorsement"] = s2_probs[:, 1]
    else:
        out[f"{MODEL_TAG}_s2_p_hostile"] = s2_probs[:, 0]
        out[f"{MODEL_TAG}_s2_p_endorsement"] = s2_probs[:, 1]
        out[f"{MODEL_TAG}_s2_p_ambiguous"] = s2_probs[:, 2]

    out.to_csv(OUTPUT_FILE, index=False)
    print(f"Saved to {OUTPUT_FILE}", flush=True)


if __name__ == "__main__":
    main()
