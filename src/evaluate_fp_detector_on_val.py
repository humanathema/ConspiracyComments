"""evaluate_fp_detector_on_val.py

Nash's idea (2026-08-19): rather than trust the false-positive detector's
in-sample 5-fold CV (resampling within the same small 76-positive train
pool it was trained on), check it against the FULL 680-row val set --
completely untouched during detector training (the detector only ever
saw TRAIN-derived positives + a handful of val-PARAPHRASE positives, never
original val text). This is a real generalization test: does the detector
actually flag the known confidently-wrong "other" rows already found in
val (via original, unparaphrased text -- see check_val_other_confident_wrong
work earlier this session), while leaving genuinely-correct val rows alone?
"""
import sys

sys.path.insert(0, "src")
import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import roc_auc_score, precision_recall_curve
from transformers import AutoTokenizer

from train_binary_confidence import ConfidenceModel, MODEL_NAME
from train_false_positive_detector import score_and_embed, CHECKPOINT_DIR, CONF_THRESHOLD_CONFIDENT

DETECTOR_PATH = "outputs/checkpoints/false_positive_detector.joblib"


def main():
    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Using device: {device}", flush=True)

    clf = joblib.load(DETECTOR_PATH)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = ConfidenceModel(MODEL_NAME).to(device)
    state = torch.load(f"{CHECKPOINT_DIR}/model_state.pt", map_location=device)
    model.load_state_dict(state)
    model.eval()

    df = pd.read_parquet("data/processed/stance_classifier_training_data_round10_truncation_fixed.parquet")
    val_df = df[(df["split"] == "val") & (df["label"].isin(["hostile", "endorsement", "other"]))].copy().reset_index(drop=True)
    print(f"{len(val_df)} val rows (never seen by the detector during training)", flush=True)

    texts = ("[ENTITY: " + val_df["target_entity"].fillna("unknown").astype(str) + "] " + val_df["text"].astype(str)).tolist()
    emb, conf, logits = score_and_embed(model, tokenizer, texts, device)
    val_df["confidence"] = conf
    val_df["gate_has_stance"] = conf >= 0.5
    val_df["fp_detector_score"] = clf.predict_proba(emb)[:, 1]

    # Known false positives: true label "other", but the base model
    # confidently (>=0.7) gates it as stanced -- the exact population this
    # whole thread has been trying to detect, computed here fresh on val
    # (never used to train the detector).
    is_other = val_df["label"] == "other"
    known_fp = is_other & val_df["gate_has_stance"] & (val_df["confidence"] >= CONF_THRESHOLD_CONFIDENT)
    print(f"\nKnown false positives in val (other, confidently gated stanced): {known_fp.sum()}/{is_other.sum()} other rows", flush=True)

    # Genuine true positives: real hostile/endorsement rows the base model
    # gets right, confidently -- the contrast population.
    is_polar = ~is_other
    true_label_id = val_df["label"].map({"hostile": 0, "endorsement": 1, "other": -1})
    pred_id = logits.argmax(axis=1)
    val_df["pred_correct"] = (pred_id == true_label_id) & is_polar
    genuine_tp = is_polar & val_df["gate_has_stance"] & val_df["pred_correct"] & (val_df["confidence"] >= CONF_THRESHOLD_CONFIDENT)
    print(f"Genuine confident true positives in val: {genuine_tp.sum()}/{is_polar.sum()} polar rows", flush=True)

    # Does the detector separate these two known populations on a set it
    # never trained on?
    eval_mask = known_fp | genuine_tp
    y_eval = known_fp[eval_mask].astype(int).to_numpy()
    scores_eval = val_df.loc[eval_mask, "fp_detector_score"].to_numpy()
    print(f"\n=== detector performance on held-out VAL (n={eval_mask.sum()}: "
          f"{known_fp.sum()} known-FP vs {genuine_tp.sum()} genuine-TP) ===", flush=True)
    print(f"AUC: {roc_auc_score(y_eval, scores_eval):.4f}", flush=True)
    for thresh in [0.3, 0.5, 0.7]:
        flagged = scores_eval >= thresh
        precision = (y_eval[flagged] == 1).mean() if flagged.sum() else float("nan")
        recall = (scores_eval[y_eval == 1] >= thresh).mean()
        print(f"  threshold={thresh}: precision={precision:.3f} recall={recall:.3f} "
              f"(flags {flagged.sum()}/{len(y_eval)})", flush=True)

    val_df.to_csv("outputs/reinfer_probs/val_fp_detector_scores.csv", index=False)
    print("\nSaved outputs/reinfer_probs/val_fp_detector_scores.csv", flush=True)


if __name__ == "__main__":
    main()
