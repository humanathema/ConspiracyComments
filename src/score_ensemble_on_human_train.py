"""score_ensemble_on_human_train.py

Runs the two-stage (stage1 has-stance-vs-other, stage2 hostile-vs-
endorsement) ensemble models against the human-labeled TRAIN set --
the population val680_ensemble_combined.csv already covers for val, but
no ensemble scores exist yet for train at all (checked directly,
2026-08-20). MODELS/CKPT_ROOT are configurable per-VM since the 8
checkpoints are split across two GCP projects/VMs (see
data/infra_map.jsonl) -- run this once per VM with only the models whose
checkpoints actually live there, never move the checkpoints themselves.

Usage:
  MODELS=r7v1_baseline,r7v1_redesign CKPT_ROOT=~/retrain_twostage \
    CKPT_PATTERN='{root}/{tag}_{arm}_stage{stage}' \
    OUT=~/r7v1_ensemble_scores.csv python3 score_ensemble_on_human_train.py
"""
import os

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MAX_LENGTH = 768
INFER_BATCH = 32
TRAIN_FILE = os.environ.get(
    "TRAIN_FILE",
    "data/processed/stance_classifier_training_data_round10_truncation_fixed.parquet",
)
# When INPUT_FILE is set (CSV, e.g. the back-translation paraphrase set),
# score TEXT_COL directly with no is_human/split filtering -- the CSV is
# already exactly the target population. Otherwise falls back to the
# original human-labeled-train behavior via TRAIN_FILE.
INPUT_FILE = os.environ.get("INPUT_FILE", "")
TEXT_COL = os.environ.get("TEXT_COL", "text")
OUT_PATH = os.path.expanduser(os.environ.get("OUT", "~/ensemble_scores.csv"))
# tag,arm pairs to run this invocation -- e.g. "r7v1:baseline,r7v1:redesign"
MODEL_SPEC = os.environ.get("MODELS", "")
# path template -- {root}/{tag}/{arm}/stage{stage} or {root}/{tag}_{arm}_stage{stage}
CKPT_ROOT = os.path.expanduser(os.environ.get("CKPT_ROOT", "~/retrain_twostage"))
CKPT_PATTERN = os.environ.get("CKPT_PATTERN", "{root}/{tag}_{arm}_stage{stage}")

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Device: {device}", flush=True)


def load_model(path):
    model = AutoModelForSequenceClassification.from_pretrained(
        str(path), torch_dtype=torch.float16
    ).to(device).eval()
    # Found 2026-08-20: r5v2's checkpoints are RoBERTa (max_position_embeddings=514),
    # not ModernBERT (8192) like the rest of the ensemble -- a hardcoded
    # MAX_LENGTH=768 (fine for ModernBERT) overflows RoBERTa's much smaller
    # position-embedding table and crashes with a CUDA scatter/gather
    # index-out-of-bounds assert. Cap per-model from the loaded config
    # itself rather than assuming one architecture for the whole ensemble.
    model_max_pos = getattr(model.config, "max_position_embeddings", MAX_LENGTH)
    safe_max_length = min(MAX_LENGTH, model_max_pos - 2)  # -2 for RoBERTa's reserved/pad offset
    return model, safe_max_length


def score_texts(tokenizer, model, texts, max_length):
    probs = []
    with torch.no_grad():
        for i in range(0, len(texts), INFER_BATCH):
            batch = list(texts[i:i + INFER_BATCH])
            enc = tokenizer(batch, max_length=max_length, truncation=True,
                            padding=True, return_tensors="pt")
            enc = {k: v.to(device) for k, v in enc.items()}
            probs.append(F.softmax(model(**enc).logits, dim=-1).cpu().float().numpy())
    return np.concatenate(probs, axis=0)


def main():
    if INPUT_FILE:
        human_train = pd.read_csv(INPUT_FILE)
        print(f"{len(human_train)} rows from {INPUT_FILE} to score (column '{TEXT_COL}')", flush=True)
    else:
        df = pd.read_parquet(TRAIN_FILE)
        human_train = df[(df["is_human"] == True) & (df["split"] == "train")].copy().reset_index(drop=True)
        print(f"{len(human_train)} human-labeled train rows to score", flush=True)

    texts = (
        "[ENTITY: " + human_train["target_entity"].fillna("unknown").astype(str) + "] "
        + human_train[TEXT_COL].astype(str)
    ).tolist()

    model_pairs = [tuple(p.split(":")) for p in MODEL_SPEC.split(",") if p]
    print(f"Models this run: {model_pairs}", flush=True)

    keep_cols = [c for c in ["id", "text", "paraphrase", "target_entity", "label", "true_label", "semantic_similarity", "entity_category", "subgroup"] if c in human_train.columns]
    out = human_train[keep_cols].copy()
    for tag, arm in model_pairs:
        s1_path = CKPT_PATTERN.format(root=CKPT_ROOT, tag=tag, arm=arm, stage=1)
        s2_path = CKPT_PATTERN.format(root=CKPT_ROOT, tag=tag, arm=arm, stage=2)
        if not Path(s1_path).exists() or not Path(s2_path).exists():
            print(f"MISSING: {tag}_{arm} (checked {s1_path} / {s2_path}) -- skipping", flush=True)
            continue
        print(f"\n[{tag}_{arm}] loading + scoring stage1...", flush=True)
        tokenizer = AutoTokenizer.from_pretrained(s1_path)
        s1_model, s1_max_len = load_model(s1_path)
        print(f"[{tag}_{arm}] stage1 max_length={s1_max_len} (model max_position_embeddings={s1_model.config.max_position_embeddings})", flush=True)
        s1 = score_texts(tokenizer, s1_model, texts, s1_max_len)
        p_other = s1[:, 0] if s1.shape[1] == 2 else s1[:, -1]  # assume [other, hasstance] or check id2label upstream
        del s1_model
        torch.cuda.empty_cache()

        print(f"[{tag}_{arm}] loading + scoring stage2 (all rows, cheap, filtered downstream)...", flush=True)
        s2_model, s2_max_len = load_model(s2_path)
        print(f"[{tag}_{arm}] stage2 max_length={s2_max_len} (model max_position_embeddings={s2_model.config.max_position_embeddings})", flush=True)
        s2 = score_texts(tokenizer, s2_model, texts, s2_max_len)
        del s2_model
        torch.cuda.empty_cache()

        out[f"{tag}_{arm}_p_other"] = p_other
        out[f"{tag}_{arm}_p_hostile"] = s2[:, 0]
        out[f"{tag}_{arm}_p_endorsement"] = s2[:, 1]
        # Save after every model, not just at the end -- a crash on model N
        # (e.g. the RoBERTa max_length bug found 2026-08-20) previously lost
        # every already-completed model's results too since nothing was
        # written until the very end.
        out.to_csv(OUT_PATH, index=False)
        print(f"[{tag}_{arm}] done, checkpointed to {OUT_PATH}", flush=True)

    print(f"\nFinal save: {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
