"""score_r7v3retrain_on_clean_r1.py

Scores r7v3_retrain_baseline (the two-stage has-stance-vs-other + hostile-
vs-endorsement architecture, NOT binconf's confidence-head architecture)
against data/hitl/queue_expanded_entity_val_r1_CLEAN_for_comparison.csv --
362 rows, confirmed via (text, target_entity) exact-match check to be
absent from binconf_other015's training data (round10 parquet). This is
the first genuinely-checked-clean comparison population between
binconf_other015 and an individual two-stage ensemble model -- the earlier
425-row "aleatoric" set turned out to be 100% inside binconf's training
data (see handoff/task_2026-08-20c_session_handoff_kappa_comparison_
gotchas.md), so that comparison was invalid.

Checkpoint: ~/outputs/round8/checkpoints_twostage/r7v3_retrain/baseline/
stage{1,2} on vm2image (per data/infra_map.jsonl's checkpoint_location
entry).

neutral/ambiguous human_label -> "other" for 3-way scoring, matching this
project's established convention (same as score_binconf_on_aleatoric.py).
"""
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from sklearn.metrics import cohen_kappa_score, classification_report
from transformers import AutoTokenizer, AutoModelForSequenceClassification

CKPT_ROOT = "outputs/round8/checkpoints_twostage/r7v3_retrain/baseline"
INPUT_FILE = "data/hitl/queue_expanded_entity_val_r1_CLEAN_for_comparison.csv"
MAX_LENGTH = 768
INFER_BATCH = 32
LABEL_TO_ID = {"hostile": 0, "endorsement": 1}


def load_model(path):
    return AutoModelForSequenceClassification.from_pretrained(str(path), torch_dtype=torch.float16)


def score_texts(tokenizer, model, texts, device, max_length):
    probs = []
    with torch.no_grad():
        for i in range(0, len(texts), INFER_BATCH):
            batch = list(texts[i:i + INFER_BATCH])
            enc = tokenizer(batch, max_length=max_length, truncation=True, padding=True, return_tensors="pt")
            enc = {k: v.to(device) for k, v in enc.items()}
            probs.append(F.softmax(model(**enc).logits, dim=-1).cpu().float().numpy())
    return np.concatenate(probs, axis=0)


def main():
    df = pd.read_csv(INPUT_FILE)
    print(f"{len(df)} total rows", flush=True)
    df["human_label_3way"] = df["human_label"].map(
        lambda x: x if x in ("hostile", "endorsement") else "other"
    )
    print(df["human_label_3way"].value_counts().to_string(), flush=True)

    texts = ("[ENTITY: " + df["target_entity"].fillna("unknown").astype(str) + "] "
              + df["full_text"].astype(str)).tolist()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}", flush=True)

    s1_path = f"{CKPT_ROOT}/stage1"
    s2_path = f"{CKPT_ROOT}/stage2"
    tokenizer = AutoTokenizer.from_pretrained(s1_path)

    print("Scoring stage1 (has-stance-vs-other)...", flush=True)
    s1_model = load_model(s1_path).to(device).eval()
    s1_probs = score_texts(tokenizer, s1_model, texts, device, MAX_LENGTH)
    del s1_model
    torch.cuda.empty_cache()

    # id2label convention check -- print so it's auditable, don't assume index order
    print(f"stage1 id2label: {AutoModelForSequenceClassification.from_pretrained(s1_path).config.id2label}", flush=True)

    print("Scoring stage2 (hostile-vs-endorsement) on ALL rows (cheap, filtered downstream)...", flush=True)
    s2_model = load_model(s2_path).to(device).eval()
    s2_probs = score_texts(tokenizer, s2_model, texts, device, MAX_LENGTH)
    del s2_model
    torch.cuda.empty_cache()
    print(f"stage2 id2label: {AutoModelForSequenceClassification.from_pretrained(s2_path).config.id2label}", flush=True)

    # stage1 id2label came back as generic LABEL_0/LABEL_1 (not informative) --
    # confirmed via a real bug this session (first attempt guessed other_idx=1,
    # gave 82% predicted-other against an 8.6% true rate, exactly backwards).
    # Correct convention per infer_round9_twostage.py's own code
    # (`stance_mask = s1[:, 1] >= 0.5`): index 1 = has-stance, index 0 = other.
    other_idx = 0
    p_other = s1_probs[:, other_idx]

    s2_id2label = AutoModelForSequenceClassification.from_pretrained(s2_path).config.id2label
    hostile_idx = [i for i, lbl in s2_id2label.items() if "hostil" in str(lbl).lower()]
    hostile_idx = hostile_idx[0] if hostile_idx else 0
    endorsement_idx = 1 - hostile_idx

    pred_3way = np.where(
        p_other >= 0.5, "other",
        np.where(s2_probs[:, hostile_idx] >= s2_probs[:, endorsement_idx], "hostile", "endorsement"),
    )
    true_3way = df["human_label_3way"].values
    overall_kappa = cohen_kappa_score(true_3way, pred_3way)

    is_polar = df["human_label"].isin(["hostile", "endorsement"]).values
    true_polar = df.loc[is_polar, "human_label"].map(LABEL_TO_ID).values
    pred_polar_idx = np.argmax(s2_probs[is_polar][:, [hostile_idx, endorsement_idx]], axis=1)
    polarity_kappa = cohen_kappa_score(true_polar, pred_polar_idx)

    print(f"\n=== r7v3_retrain_baseline on CLEAN r1 set (n={len(df)}) ===", flush=True)
    print(f"OVERALL 3-way kappa: {overall_kappa:.4f}", flush=True)
    print(f"Polarity-only kappa (n={is_polar.sum()}): {polarity_kappa:.4f}", flush=True)
    print(classification_report(true_polar, pred_polar_idx, target_names=["hostile", "endorsement"]), flush=True)

    out = df[["id", "target_entity", "human_label", "human_label_3way"]].copy()
    out["pred_3way"] = pred_3way
    out["p_other"] = p_other
    out.to_csv("outputs/reinfer_probs/r7v3retrain_baseline_clean_r1_scores.csv", index=False)
    print("\nSaved outputs/reinfer_probs/r7v3retrain_baseline_clean_r1_scores.csv", flush=True)


if __name__ == "__main__":
    main()
