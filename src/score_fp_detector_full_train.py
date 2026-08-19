"""score_fp_detector_full_train.py

Applies the trained false-positive detector (outputs/checkpoints/
false_positive_detector.joblib, trained on 119 known binconf_other015
errors -- 76 train-original + 43 val-paraphrase, see
train_false_positive_detector.py) to the FULL train set, not just the
2,131-row human-labeled polar subset it was validated on. Nash's ask
(2026-08-20): now that confidence-gating is confirmed useless for
finding false positives (the blend's confidence range overlaps too much
between TP/FP to threshold on), the detector itself -- trained on
binconf's real, known errors -- is the actual tool, and should run at
real scale: the ~39,281 machine/silver-labeled train rows this project
has never applied it to, not just the small human-labeled slice.
"""
import sys

sys.path.insert(0, "src")
import pandas as pd
import torch
from transformers import AutoTokenizer

from train_binary_confidence import ConfidenceModel, MODEL_NAME
from train_false_positive_detector import score_and_embed, CHECKPOINT_DIR

DETECTOR_PATH = "outputs/checkpoints/false_positive_detector.joblib"
TRAIN_FILE = "data/processed/stance_classifier_training_data_round10_truncation_fixed.parquet"
OUT_PATH = "outputs/reinfer_probs/full_train_fp_detector_scores.csv"
BATCH_SIZE = 32  # override the module default for full-scale throughput


def main():
    import train_false_positive_detector as tfpd
    tfpd.BATCH_SIZE = BATCH_SIZE

    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Using device: {device}", flush=True)

    import joblib
    clf = joblib.load(DETECTOR_PATH)

    df = pd.read_parquet(TRAIN_FILE)
    train_all = df[df["split"] == "train"].copy().reset_index(drop=True)
    print(f"{len(train_all)} total train rows (human + machine-labeled)", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = ConfidenceModel(MODEL_NAME).to(device)
    state = torch.load(f"{CHECKPOINT_DIR}/model_state.pt", map_location=device)
    model.load_state_dict(state)
    model.eval()

    texts = ("[ENTITY: " + train_all["target_entity"].fillna("unknown").astype(str) + "] " + train_all["text"].astype(str)).tolist()
    print("Scoring (single pass: embeddings + confidence + logits)...", flush=True)
    emb, conf, logits = score_and_embed(model, tokenizer, texts, device)

    train_all["confidence"] = conf
    train_all["fp_detector_score"] = clf.predict_proba(emb)[:, 1]
    train_all.to_csv(OUT_PATH, index=False)

    flagged = train_all[train_all["fp_detector_score"] >= 0.5]
    print(f"\n{len(flagged)}/{len(train_all)} = {len(flagged)/len(train_all):.1%} flagged as likely false positives", flush=True)
    print(f"Saved {OUT_PATH}", flush=True)

    print("\nBy is_human:", flush=True)
    print(train_all.groupby("is_human").apply(lambda g: (g["fp_detector_score"] >= 0.5).mean()), flush=True)
    print("\nBy label:", flush=True)
    print(train_all.groupby("label").apply(lambda g: (g["fp_detector_score"] >= 0.5).mean()), flush=True)


if __name__ == "__main__":
    main()
