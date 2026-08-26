"""score_fp_v4_on_full_polar_population.py

The real, decisive check: apply the round-4 fine-tuned detector to the
SAME 2,131-row full human-labeled train polar population used to
establish round 1's baseline (93.9% recall / 8.4% precision) and to
diagnose rounds 2-3's failures. This is the only genuinely comparable
number -- the round-4 held-out val split (88% accuracy, 0.938 AUC) is a
real check but drawn from the same distribution as training data, not
this independent population.

Ground truth: the existing 'correct' column in train_polar_fp_detector_scores.csv.
Input format matches training exactly: [ENTITY: X | SILVER_LABEL: true_label |
CLASSIFIER_PREDICTED: stanced_or_other] text -- classifier_predicted derived
from confidence>=0.5 for this population, same convention as training data.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import pandas as pd
import numpy as np
from sklearn.metrics import cohen_kappa_score
from transformers import AutoModel, AutoTokenizer

MODEL_DIR = "/home/nash/retrain_twostage/fp_detector_v4_finetuned"
MODEL_NAME = "answerdotai/ModernBERT-large"
MAX_LENGTH = 768


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

    df = pd.read_csv("outputs/reinfer_probs/train_polar_fp_detector_scores.csv")
    print(f"{len(df)} rows (full human polar population)", flush=True)

    df["classifier_predicted"] = np.where(df["confidence"] >= 0.5, "stanced", "other")
    texts = (
        "[ENTITY: " + df["target_entity"].fillna("unknown").astype(str)
        + " | SILVER_LABEL: " + df["label"].astype(str)
        + " | CLASSIFIER_PREDICTED: " + df["classifier_predicted"].astype(str)
        + "] " + df["text"].astype(str)
    ).tolist()

    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = WrongLabelModel(MODEL_NAME).to(device)
    state = torch.load(f"{MODEL_DIR}/model_state.pt", map_location=device)
    model.load_state_dict(state)
    model.eval()

    all_logits = []
    batch_size = 16
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            enc = tokenizer(batch, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt").to(device)
            logits = model(**enc)
            all_logits.append(logits.cpu())
            if i % (batch_size * 20) == 0:
                print(f"  {i}/{len(texts)}", flush=True)

    logits = torch.cat(all_logits).numpy()
    probs = F.softmax(torch.tensor(logits), dim=1).numpy()[:, 1]
    preds = (probs >= 0.5).astype(int)
    true = (df["correct"] == False).astype(int).to_numpy()  # 1 = genuinely wrong (matches training's y=1 convention)

    tp = ((preds == 1) & (true == 1)).sum()
    fp = ((preds == 1) & (true == 0)).sum()
    fn = ((preds == 0) & (true == 1)).sum()
    tn = ((preds == 0) & (true == 0)).sum()

    print(f"\n=== Round 4 (fine-tuned) on the FULL 2,131-row human polar population ===", flush=True)
    print(f"flagged (predicted wrong): {preds.sum()}  TP={tp}  FP={fp}  FN={fn}  TN={tn}", flush=True)
    print(f"precision: {tp/(tp+fp):.3f}  recall: {tp/(tp+fn):.3f}", flush=True)
    print(f"\nFor direct comparison:", flush=True)
    print(f"  round 1: precision=0.084 recall=0.939", flush=True)
    print(f"  round 2: precision=0.122 recall=0.102 (failed)", flush=True)
    print(f"  round 3: precision=0.044 recall=0.122 (failed)", flush=True)

    df["fp_v4_score"] = probs
    df["fp_v4_pred"] = preds
    df.to_csv("outputs/reinfer_probs/train_polar_fp_detector_scores_v4.csv", index=False)
    print("\nSaved outputs/reinfer_probs/train_polar_fp_detector_scores_v4.csv", flush=True)


if __name__ == "__main__":
    main()
