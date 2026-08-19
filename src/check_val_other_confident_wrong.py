"""check_val_other_confident_wrong.py

Companion to the train-split paraphrase-flip check
(check_paraphrase_confident_flips.py / other_to_stance_paraphrase_flips_TRAIN.csv):
that script finds "other"-labeled TRAIN rows where paraphrasing alone flips
a correct "other" gate to confidently "stanced" -- a paraphrase-induced
error. This script finds the more direct, no-paraphrasing-needed version
on the frozen VAL set: human-labeled "other" rows the current best
checkpoint (binconf_other015) already gets confidently wrong on the
ORIGINAL text, no rewording involved. Nash's question (2026-08-19): do
these two populations share the same features?

Runs fresh inference rather than reusing the stale preds_binconf_other015
CSV (which has no text column, only alignable by row position) -- direct
and verifiable instead of a positional join with silent-failure risk.
"""
import sys

sys.path.insert(0, "src")
import pandas as pd
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer

from train_binary_confidence import ConfidenceModel, MODEL_NAME

CHECKPOINT_DIR = "outputs/checkpoints/binconf_other015_binary_confidence"
MAX_LENGTH = 768
BATCH_SIZE = 8
CONF_THRESHOLD_GATE = 0.5   # has-stance vs other gate
CONF_THRESHOLD_CONFIDENT = 0.7  # matches the train-paraphrase-flip analysis's confident-wrong bar


def main():
    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Using device: {device}", flush=True)

    df = pd.read_parquet("data/processed/stance_classifier_training_data_round10_truncation_fixed.parquet")
    val_df = df[(df["split"] == "val") & (df["label"].isin(["hostile", "endorsement", "other"]))].copy().reset_index(drop=True)
    print(f"{len(val_df)} val rows, label counts: {dict(val_df['label'].value_counts())}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = ConfidenceModel(MODEL_NAME).to(device)
    state = torch.load(f"{CHECKPOINT_DIR}/model_state.pt", map_location=device)
    model.load_state_dict(state)
    model.eval()

    texts = ("[ENTITY: " + val_df["target_entity"].fillna("unknown").astype(str) + "] " + val_df["text"].astype(str)).tolist()
    all_conf = []
    with torch.no_grad():
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            enc = tokenizer(batch, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt").to(device)
            _, conf = model(**enc)
            all_conf.append(conf.cpu())
    confidence = torch.cat(all_conf).numpy()
    val_df["confidence"] = confidence
    val_df["gate_has_stance"] = confidence >= CONF_THRESHOLD_GATE

    other = val_df[val_df["label"] == "other"].copy()
    print(f"\nval 'other' rows: n={len(other)}", flush=True)
    wrong = other[other["gate_has_stance"]]
    print(f"Gated as stanced at all (confidence>=0.5): {len(wrong)}/{len(other)} = {len(wrong)/len(other):.1%}", flush=True)
    confident_wrong = other[other["gate_has_stance"] & (other["confidence"] >= CONF_THRESHOLD_CONFIDENT)]
    print(f"Confidently gated as stanced (confidence>={CONF_THRESHOLD_CONFIDENT}): "
          f"{len(confident_wrong)}/{len(other)} = {len(confident_wrong)/len(other):.1%}", flush=True)

    other.to_csv("outputs/reinfer_probs/val_other_confident_wrong.csv", index=False)
    print("\nSaved outputs/reinfer_probs/val_other_confident_wrong.csv", flush=True)


if __name__ == "__main__":
    main()
