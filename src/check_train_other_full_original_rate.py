"""check_train_other_full_original_rate.py

Nash asked (2026-08-20) whether the train-vs-val confidently-wrong-"other"
rate difference (14.4% train vs 27.4%/35.6% val, depending on which
earlier number) is statistically real given the sample sizes -- but the
train figure used only the 526 "other" rows that survived the
back-translation pipeline's thin-comment/too-many-links filters, not the
TRUE full human-labeled "other" count in train (771). Val's number was
already computed on its full, unfiltered 175 "other" rows. Comparing
526-vs-175 would silently compare a filtered population to an unfiltered
one -- this script gets the true, unfiltered, ORIGINAL-text-only (no
paraphrasing involved, this isn't a paraphrase diagnostic) rate on the
full 771 train "other" rows so the train-vs-val comparison is apples to
apples before doing any significance test.
"""
import sys

sys.path.insert(0, "src")
import pandas as pd
import torch
from transformers import AutoTokenizer

from train_binary_confidence import ConfidenceModel, MODEL_NAME
from train_false_positive_detector import score_and_embed, CHECKPOINT_DIR, CONF_THRESHOLD_CONFIDENT


def main():
    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Using device: {device}", flush=True)

    df = pd.read_parquet("data/processed/stance_classifier_training_data_round10_truncation_fixed.parquet")
    train_other = df[(df["split"] == "train") & (df["is_human"] == True) & (df["label"] == "other")].copy().reset_index(drop=True)
    print(f"{len(train_other)} FULL human-labeled train 'other' rows (unfiltered)", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = ConfidenceModel(MODEL_NAME).to(device)
    state = torch.load(f"{CHECKPOINT_DIR}/model_state.pt", map_location=device)
    model.load_state_dict(state)
    model.eval()

    texts = ("[ENTITY: " + train_other["target_entity"].fillna("unknown").astype(str) + "] " + train_other["text"].astype(str)).tolist()
    _, conf, _ = score_and_embed(model, tokenizer, texts, device)
    train_other["confidence"] = conf
    train_other["gate_has_stance"] = conf >= 0.5

    confident_wrong = train_other["gate_has_stance"] & (train_other["confidence"] >= CONF_THRESHOLD_CONFIDENT)
    print(f"\nConfidently (>={CONF_THRESHOLD_CONFIDENT}) gated as stanced, ORIGINAL text, FULL train 'other' set: "
          f"{confident_wrong.sum()}/{len(train_other)} = {confident_wrong.mean():.1%}", flush=True)

    train_other.to_csv("outputs/reinfer_probs/train_other_FULL_original_confidence.csv", index=False)
    print("Saved outputs/reinfer_probs/train_other_FULL_original_confidence.csv", flush=True)


if __name__ == "__main__":
    main()
