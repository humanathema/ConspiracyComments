"""score_fp_v8_fullcorpus.py

Scores v8 (fp_detector_v8_representative) over the full-corpus
stanced-predicted subset (270,951 rows) from the blended 5-model
ensemble + binconf pipeline.

Input: fullcorpus_stanced_for_fpdetector.parquet (id, text,
  target_entity, confidence, final_label)
Output: fp_v8_fullcorpus_scores.parquet (+ fp_v8_score column)
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import pandas as pd
from transformers import AutoModel, AutoTokenizer

MODEL_DIR = "/home/nash/retrain_twostage/fp_detector_v8_representative"
MODEL_NAME = "answerdotai/ModernBERT-large"
MAX_LENGTH = 768
BATCH_SIZE = 16
INPUT_PATH = "/home/nash/fullcorpus_stanced_for_fpdetector.parquet"
OUT_PATH = "/home/nash/fp_v8_fullcorpus_scores.parquet"


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

    df = pd.read_parquet(INPUT_PATH)
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
            if i % (BATCH_SIZE * 200) == 0:
                print(f"  {i}/{len(texts)}", flush=True)

    logits = torch.cat(all_logits).numpy()
    probs = F.softmax(torch.tensor(logits), dim=1).numpy()[:, 1]
    df["fp_v8_score"] = probs

    df.to_parquet(OUT_PATH, index=False)
    print(f"\nSaved {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
