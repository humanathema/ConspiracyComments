"""reinfer_uncollapsed_v1.py

Re-inference variant for uncollapsed_v1 specifically -- a genuinely mixed
architecture, confirmed directly from checkpoint tensor shapes (2026-08-16,
after an initial wrong assumption from misleading config.json metadata):
stage1 classifier.weight is [2,1024] -- a real 2-class classifier (bare
mention vs not), evaluated via kappa in the original run. stage2
classifier.weight is [1,1024] -- a genuine single-scalar regression head
(continuous stance score), evaluated via MAE. Handles each stage with the
architecture it actually has, not a single shared assumption.

Same usage pattern as reinfer_ensemble_probs.py (env vars: STAGE1_DIR,
STAGE2_DIR, INPUT_FILE, OUTPUT_FILE, MAX_LENGTH, BATCH_SIZE).
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
INPUT_FILE = os.environ["INPUT_FILE"]
OUTPUT_FILE = os.environ["OUTPUT_FILE"]
MAX_LENGTH = int(os.environ.get("MAX_LENGTH", "768"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "16"))


def _texts_with_entity(df):
    if "target_entity" in df.columns:
        return ("[ENTITY: " + df["target_entity"].fillna("unknown").astype(str) + "] "
                + df["text"].astype(str)).tolist()
    return df["text"].tolist()


def run_stage(model_dir, texts, tokenizer, device, num_labels):
    model = AutoModelForSequenceClassification.from_pretrained(model_dir, num_labels=num_labels).to(device)
    model.eval()
    all_out = []
    with torch.no_grad():
        for i in range(0, len(texts), BATCH_SIZE):
            batch_texts = texts[i:i + BATCH_SIZE]
            enc = tokenizer(batch_texts, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt").to(device)
            logits = model(**enc).logits
            if num_labels == 1:
                all_out.append(logits.squeeze(-1).cpu().numpy())
            else:
                all_out.append(F.softmax(logits, dim=-1).cpu().numpy())
            if i % (BATCH_SIZE * 50) == 0:
                print(f"  {i}/{len(texts)}", flush=True)
    del model
    torch.cuda.empty_cache()
    return np.concatenate(all_out, axis=0)


def main():
    print(f"INPUT_FILE={INPUT_FILE}", flush=True)
    df = pd.read_parquet(INPUT_FILE)
    texts = _texts_with_entity(df)
    print(f"{len(texts):,} rows to score", flush=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(STAGE1_DIR)

    print("Stage 1 (bare-mention, 2-class)...", flush=True)
    s1_probs = run_stage(STAGE1_DIR, texts, tokenizer, device, num_labels=2)
    print("Stage 2 (continuous stance score, regression)...", flush=True)
    s2_scores = run_stage(STAGE2_DIR, texts, tokenizer, device, num_labels=1)

    out = pd.DataFrame({
        "id": df["id"] if "id" in df.columns else np.arange(len(df)),
        "uncollapsed_v1_s1_p0": s1_probs[:, 0],
        "uncollapsed_v1_s1_p1": s1_probs[:, 1],
        "uncollapsed_v1_s2_score": s2_scores,
    })
    out.to_csv(OUTPUT_FILE, index=False)
    print(f"Saved to {OUTPUT_FILE}", flush=True)


if __name__ == "__main__":
    main()
