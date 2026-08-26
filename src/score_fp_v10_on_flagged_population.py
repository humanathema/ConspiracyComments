"""score_fp_v10_on_flagged_population.py

Scores v10 (fp_detector_v10_real_human -- the first generation in this
lineage trained on pure genuine human labels, held-out AUC 0.733) over
the 10,824 rows already flagged by the old v8+v9+confidence ensemble
across both train (6,158) and round9 (4,666).

Purpose: (1) see how much v10 agrees/disagrees with the old pipeline's
flags, (2) provide v10_score as a feature for building a combined
v8+v9+v10+confidence ensemble. The `in_v10_training` column (carried
through from the input) marks the ~196 rows that were part of v10's own
training/val data -- any precision check computed downstream MUST
exclude these to avoid the same train/eval leakage this project has
been burned by before.

Input: v10_score_input.csv (text, target_entity, population, in_v10_training)
Output: v10_score_input_scored.csv (+ v10_score column)
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import pandas as pd
from transformers import AutoModel, AutoTokenizer

MODEL_DIR = "/home/nash/retrain_twostage/fp_detector_v10_real_human"
MODEL_NAME = "answerdotai/ModernBERT-large"
MAX_LENGTH = 768
BATCH_SIZE = 16
INPUT_PATH = "/home/nash/v10_score_input.csv"
OUT_PATH = "/home/nash/v10_score_input_scored.csv"


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
    print(f"{len(df)} rows to score", flush=True)
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
            if i % (BATCH_SIZE * 50) == 0:
                print(f"  {i}/{len(texts)}", flush=True)

    logits = torch.cat(all_logits).numpy()
    probs = F.softmax(torch.tensor(logits), dim=1).numpy()[:, 1]
    df["v10_score"] = probs

    print(f"\n=== v10 on flagged population (n={len(df)}) -- threshold sweep ===", flush=True)
    for t in [0.2, 0.3, 0.4, 0.5, 0.6]:
        n_flagged = (probs >= t).sum()
        print(f"threshold={t}: flagged={n_flagged} ({n_flagged/len(df):.3f} of population)", flush=True)

    df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
