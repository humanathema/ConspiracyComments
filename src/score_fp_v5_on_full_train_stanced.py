"""score_fp_v5_on_full_train_stanced.py

Applies the round-5 (text-only, no-tag) FP detector to all currently
stanced-labeled (hostile/endorsement) rows in the full 42,183-row train
set. Same population as score_fp_v4_on_full_train_stanced.py, so this is
a direct, apples-to-apples comparison: does v5 (which has no access to
binconf's own confidence/prediction at all) produce a genuinely different
flag pattern than v4 did, or does it still end up correlating almost
perfectly with binconf's agree/disagree signal despite having no way to
read it directly?

Input: outputs/reinfer_probs/full_train_fp_detector_scores.csv
Output: outputs/reinfer_probs/full_train_fp_v5_stanced_scores.csv
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import pandas as pd
import numpy as np
from transformers import AutoModel, AutoTokenizer

MODEL_DIR = "/home/nash/retrain_twostage/fp_detector_v5_no_tags"
MODEL_NAME = "answerdotai/ModernBERT-large"
MAX_LENGTH = 768
BATCH_SIZE = 16
INPUT_PATH = "outputs/reinfer_probs/full_train_fp_detector_scores.csv"
OUT_PATH = "outputs/reinfer_probs/full_train_fp_v5_stanced_scores.csv"


class WrongLabelModel(nn.Module):
    def __init__(self, model_name):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size = self.encoder.config.hidden_size
        self.classifier = nn.Linear(hidden_size, 2)

    def forward(self, input_ids=None, attention_mask=None, **kwargs):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        last_hidden = out.last_hidden_state
        mask = attention_mask.unsqueeze(-1).float()
        pooled = (last_hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        return self.classifier(pooled)


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}", flush=True)

    df = pd.read_csv(INPUT_PATH)
    df = df[(df["split"] == "train") & (df["label"].isin(["hostile", "endorsement"]))].reset_index(drop=True)
    print(f"{len(df)} stanced (hostile/endorsement) train rows to score", flush=True)

    df["classifier_predicted"] = np.where(df["confidence"] >= 0.5, "stanced", "other")

    texts = (
        "[ENTITY: " + df["target_entity"].fillna("unknown").astype(str) + "] " + df["text"].astype(str)
    ).tolist()

    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = WrongLabelModel(MODEL_NAME).to(device)
    state = torch.load(f"{MODEL_DIR}/model_state.pt", map_location=device)
    model.load_state_dict(state)
    model.eval()

    all_logits = []
    with torch.no_grad():
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            enc = tokenizer(batch, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt").to(device)
            logits = model(**enc)
            all_logits.append(logits.cpu())
            if i % (BATCH_SIZE * 50) == 0:
                print(f"  {i}/{len(texts)}", flush=True)

    logits = torch.cat(all_logits).numpy()
    probs = F.softmax(torch.tensor(logits), dim=1).numpy()[:, 1]
    preds = (probs >= 0.5).astype(int)

    df["fp_v5_score"] = probs
    df["fp_v5_flagged"] = preds.astype(bool)

    n_flagged = preds.sum()
    print(f"\n=== v5 (text-only) on full train stanced population (n={len(df)}) ===", flush=True)
    print(f"Flagged: {n_flagged} ({n_flagged/len(df):.3f})", flush=True)
    print(f"\nBy label:", flush=True)
    print(df.groupby("label")["fp_v5_flagged"].mean(), flush=True)
    print(f"\nBy is_human:", flush=True)
    print(df.groupby("is_human")["fp_v5_flagged"].mean(), flush=True)
    print(f"\nBy classifier_predicted (agreement vs disagreement with binconf) -- KEY CHECK:", flush=True)
    print(df.groupby("classifier_predicted")["fp_v5_flagged"].mean(), flush=True)
    print(f"\nCross-tab vs v4 (if available) would show real independence; for now compare the two 'By classifier_predicted' breakdowns directly against v4's (0.000 agree / 0.971 disagree).", flush=True)

    df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
