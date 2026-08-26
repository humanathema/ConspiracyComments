"""score_fp_v8_on_full_train_stanced.py

Applies v8 (fp_detector_v8_representative -- the first version of this
detector lineage validated to have real signal on genuinely random data,
AUC 0.6417 on 288 rows of real human ground truth) to all 32,607
currently stanced-labeled (hostile/endorsement) rows in the full
42,183-row train set.

Reports flag counts at multiple thresholds (0.5 through 0.95) so a
precision/candidate-count tradeoff can be chosen without re-running --
see fp_detector_v8_representative_REAL_VALIDATION_SUCCESS and the
threshold sweep on the 288-row real validation set in
data/experiment_log.jsonl for the precision each threshold corresponds to.

Input: outputs/reinfer_probs/full_train_fp_detector_scores.csv
Output: outputs/reinfer_probs/full_train_fp_v8_stanced_scores.csv
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import pandas as pd
import numpy as np
from transformers import AutoModel, AutoTokenizer

MODEL_DIR = "/home/nash/retrain_twostage/fp_detector_v8_representative"
MODEL_NAME = "answerdotai/ModernBERT-large"
MAX_LENGTH = 768
BATCH_SIZE = 16
INPUT_PATH = "outputs/reinfer_probs/full_train_fp_detector_scores.csv"
OUT_PATH = "outputs/reinfer_probs/full_train_fp_v8_stanced_scores.csv"


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
            if i % (BATCH_SIZE * 100) == 0:
                print(f"  {i}/{len(texts)}", flush=True)

    logits = torch.cat(all_logits).numpy()
    probs = F.softmax(torch.tensor(logits), dim=1).numpy()[:, 1]
    df["fp_v8_score"] = probs

    print(f"\n=== v8 on full train stanced population (n={len(df)}) -- threshold sweep ===", flush=True)
    for t in [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95]:
        n_flagged = (probs >= t).sum()
        print(f"threshold={t}: flagged={n_flagged} ({n_flagged/len(df):.3f} of population)", flush=True)

    df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
