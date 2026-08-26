"""score_fp_v8_polished_on_spotcheck.py

Scores the polished checkpoint (v8 base + stage-2 fine-tune on the 199-row
human set) against ONLY the 89-row spot-check set -- the one slice that
was never touched by either training stage, so this is a genuinely fair
before/after comparison against v8's own score on the identical 89 rows.

Input: /home/nash/spotcheck_89_only.csv (text, target_entity,
genuinely_other)
Output: outputs/reinfer_probs/fp_v8_polished_spotcheck_scored.csv
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import pandas as pd
from sklearn.metrics import roc_auc_score, classification_report

from transformers import AutoModel, AutoTokenizer

MODEL_DIR = "/home/nash/retrain_twostage/fp_detector_v8_polished"
MODEL_NAME = "answerdotai/ModernBERT-large"
MAX_LENGTH = 768
BATCH_SIZE = 16
INPUT_PATH = "/home/nash/spotcheck_89_only.csv"
OUT_PATH = "outputs/reinfer_probs/fp_v8_polished_spotcheck_scored.csv"


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
    print(f"{len(df)} rows -- held-out spot-check set, never trained on by either stage", flush=True)

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

    tp = ((preds == 1) & (true == 1)).sum()
    fp = ((preds == 1) & (true == 0)).sum()
    fn = ((preds == 0) & (true == 1)).sum()
    tn = ((preds == 0) & (true == 0)).sum()

    print(f"\n=== v8-POLISHED on the 89-row held-out spot-check (never trained on) ===", flush=True)
    print(f"TP={tp} FP={fp} FN={fn} TN={tn}", flush=True)
    print(f"Precision: {tp/(tp+fp) if (tp+fp)>0 else float('nan'):.3f}", flush=True)
    print(f"Recall: {tp/(tp+fn) if (tp+fn)>0 else float('nan'):.3f}", flush=True)
    print(f"AUC: {roc_auc_score(true, probs):.4f}", flush=True)
    print(classification_report(true, preds, target_names=["genuinely_stanced", "genuinely_other"]), flush=True)

    df["fp_v8_polished_score"] = probs
    df["fp_v8_polished_flagged"] = preds.astype(bool)
    df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
