"""infer_round9_twostage.py — VM inference script for round 9

Loads 3 r8 baseline models, scores the round 9 unlabeled batch,
computes ensemble majority vote + margin, outputs escalation candidates.

Model paths: ~/outputs/round8/checkpoints_twostage/{tag}/baseline/stage{1,2}/
  where tag in {r7v1, r5v2, r7v3}

Usage (on VM):
  BATCH_FILE=~/unlabeled_batch_round9.parquet python3 ~/infer_round9_twostage.py
"""

import os
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForSequenceClassification

CKPT_ROOT   = Path(os.path.expanduser("~/outputs/round8/checkpoints_twostage"))
BATCH_FILE  = Path(os.environ.get("BATCH_FILE", os.path.expanduser("~/unlabeled_batch_round9.parquet")))
OUT_DIR     = Path(os.path.expanduser("~/outputs/round9"))
MAX_LENGTH  = 768
INFER_BATCH = 64
MARGIN_THR  = 0.45
ROUND       = "round9"

MODELS = [
    ("r7v1", "baseline"),
    ("r5v2", "baseline"),
    ("r7v3", "baseline"),
]

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Device: {device}")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_model(path):
    return AutoModelForSequenceClassification.from_pretrained(
        str(path), torch_dtype=torch.float16
    ).to(device).eval()


def score_texts(tokenizer, model, texts):
    probs = []
    with torch.no_grad():
        for i in range(0, len(texts), INFER_BATCH):
            batch = list(texts[i:i + INFER_BATCH])
            enc = tokenizer(batch, max_length=MAX_LENGTH, truncation=True,
                            padding=True, return_tensors="pt")
            enc = {k: v.to(device) for k, v in enc.items()}
            probs.append(F.softmax(model(**enc).logits, dim=-1).cpu().float().numpy())
    return np.concatenate(probs, axis=0)


def run_twostage(tokenizer, s1_model, s2_model, texts):
    N = len(texts)
    s1 = score_texts(tokenizer, s1_model, texts)
    preds = np.full(N, 2, dtype=int)
    stance_mask = s1[:, 1] >= 0.5
    if stance_mask.sum() == 0:
        return preds
    stance_texts = [texts[i] for i in np.where(stance_mask)[0]]
    s2 = score_texts(tokenizer, s2_model, stance_texts)
    s2_pred = np.argmax(s2, axis=1)
    preds[np.where(stance_mask)[0]] = s2_pred
    return preds


def main():
    print(f"Loading batch from {BATCH_FILE} ...")
    df = pd.read_parquet(BATCH_FILE)
    print(f"  {len(df):,} rows")
    print(df['target_entity'].value_counts().to_string())

    texts = (
        "[ENTITY: " + df["target_entity"].fillna("unknown").astype(str) + "] "
        + df["text"].astype(str)
    ).tolist()

    all_preds = []
    for tag, arm in MODELS:
        s1_path = CKPT_ROOT / tag / arm / "stage1"
        s2_path = CKPT_ROOT / tag / arm / "stage2"
        if not s1_path.exists() or not s2_path.exists():
            print(f"MISSING: {tag}/{arm} — skipping")
            continue
        print(f"\n[{tag}_{arm}] scoring {len(texts):,} texts ...")
        tokenizer = AutoTokenizer.from_pretrained(str(s1_path))
        s1 = load_model(s1_path)
        s2 = load_model(s2_path)
        preds = run_twostage(tokenizer, s1, s2, texts)
        all_preds.append(preds)
        dist = {0: int((preds==0).sum()), 1: int((preds==1).sum()), 2: int((preds==2).sum())}
        print(f"  hostile={dist[0]} endorse={dist[1]} other={dist[2]}")
        del s1, s2
        torch.cuda.empty_cache()

    print(f"\nEnsemble over {len(all_preds)} models ...")
    arr = np.stack(all_preds, axis=1)
    ensemble_pred = np.array([np.bincount(row, minlength=3).argmax() for row in arr])

    margins = []
    for row in arr:
        h, e = (row == 0).sum(), (row == 1).sum()
        total = h + e
        margins.append(abs(h / total - 0.5) if total > 0 else np.nan)
    margins = np.array(margins)

    id_to_label = {0: "hostile", 1: "endorsement", 2: "other"}
    df["ensemble_pred"] = ensemble_pred
    df["pred_label"]    = pd.Series(ensemble_pred).map(id_to_label).values
    df["margin"]        = margins
    for i, (tag, arm) in enumerate(MODELS[:len(all_preds)]):
        df[f"pred_{tag}_{arm}"] = all_preds[i]

    full_path = OUT_DIR / f"batch_ensemble_scores_{ROUND}.parquet"
    df.to_parquet(full_path, index=False)
    print(f"\nFull scores: {full_path}")

    esc = df[df["margin"] < MARGIN_THR].copy()
    esc_path = OUT_DIR / f"batch_escalation_candidates_{ROUND}.csv"
    esc[["id", "text", "target_entity", "ensemble_pred", "pred_label", "margin"]].to_csv(esc_path, index=False)
    print(f"Escalation candidates: {len(esc):,} ({len(esc)/len(df)*100:.1f}%) → {esc_path}")


if __name__ == "__main__":
    main()
