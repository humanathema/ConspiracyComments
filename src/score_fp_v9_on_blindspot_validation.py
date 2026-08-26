"""score_fp_v9_on_blindspot_validation.py

Scores v9 against the binconf-confident SUBSET of the real 288-row human-
labeled ground truth -- the actual population v9 is meant for (binconf's
blind spot: currently-stanced-labeled rows where binconf's own confidence
is >=0.5, so a simple threshold rule would never flag them). Also reports
binconf-alone and v8-alone numbers on this SAME restricted population for
a direct, fair comparison -- not the full 288-row numbers reported
earlier, which include many rows outside this detector's intended job.

Input: /home/nash/real_validation_blindspot_merged.csv (text,
target_entity, genuinely_other, confidence, fp_v8_score)
Output: outputs/reinfer_probs/fp_v9_blindspot_validation_scored.csv
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import pandas as pd
from sklearn.metrics import roc_auc_score, classification_report
from transformers import AutoModel, AutoTokenizer

MODEL_DIR = "/home/nash/retrain_twostage/fp_detector_v9_blindspot"
MODEL_NAME = "answerdotai/ModernBERT-large"
MAX_LENGTH = 768
BATCH_SIZE = 16
INPUT_PATH = "/home/nash/real_validation_blindspot_merged.csv"
OUT_PATH = "outputs/reinfer_probs/fp_v9_blindspot_validation_scored.csv"


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


def report(name, true, probs, preds):
    tp = ((preds == 1) & (true == 1)).sum()
    fp = ((preds == 1) & (true == 0)).sum()
    fn = ((preds == 0) & (true == 1)).sum()
    prec = tp / (tp + fp) if (tp + fp) > 0 else float("nan")
    rec = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
    auc = roc_auc_score(true, probs)
    print(f"{name}: AUC={auc:.4f} precision={prec:.3f} recall={rec:.3f} (TP={tp} FP={fp} FN={fn})", flush=True)


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}", flush=True)

    df = pd.read_csv(INPUT_PATH)
    print(f"{len(df)} rows -- binconf-confident (blind spot) subset of real human ground truth", flush=True)
    print(f"True base rate here: {df['genuinely_other'].mean():.3f}", flush=True)

    texts = ("[ENTITY: " + df["target_entity"].fillna("unknown").astype(str) + "] " + df["text"].astype(str)).tolist()

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

    logits = torch.cat(all_logits).numpy()
    probs = F.softmax(torch.tensor(logits), dim=1).numpy()[:, 1]
    preds = (probs >= 0.5).astype(int)
    true = df["genuinely_other"].astype(int).to_numpy()

    print(f"\n=== On binconf's blind spot (n={len(df)}), the population v9 is actually meant for ===", flush=True)
    report("v9 (blind-spot-trained)", true, probs, preds)
    print()
    print("For direct comparison, SAME restricted population:", flush=True)
    v8_preds = (df["fp_v8_score"] >= 0.5).astype(int).to_numpy()
    report("v8 (random-sample-trained)", true, df["fp_v8_score"].to_numpy(), v8_preds)
    print("binconf alone cannot be scored here in the same way -- by construction every row has confidence>=0.5,", flush=True)
    print("so a confidence<0.5 threshold rule flags ZERO of these rows (0 recall, undefined precision) -- that IS the blind spot.", flush=True)

    df["fp_v9_score"] = probs
    df["fp_v9_flagged"] = preds.astype(bool)
    df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
