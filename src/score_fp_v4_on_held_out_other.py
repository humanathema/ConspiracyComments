"""score_fp_v4_on_held_out_other.py

Stress test for the round-4 fine-tuned FP detector on a population it
genuinely never saw in training. All 632 rows here have:
  - human label = "other" (confirmed correct by a human annotator)
  - binconf_other015's own confidence < 0.3 -- i.e. binconf ITSELF agrees
    "other" is right, no disagreement at all

Every "other"-labeled row v4 trained on required confidence >= 0.5 (that's
what defined the disagreement pools it was built from) -- so this
confidence<0.3 population is disjoint from v4's training data by
threshold construction, not by row-id matching.

Since v4's own input format explicitly shows CLASSIFIER_PREDICTED=other
(no conflict signal), any row v4 flags here is v4 inventing disagreement
from the text alone that isn't even present in its own explicit inputs --
a clean, decisive false-alarm-rate check.

Input: scratchpad/v4_test_held_out_other.csv (632 rows)
Output: outputs/reinfer_probs/fp_v4_held_out_other_scores.csv
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import pandas as pd
import numpy as np
from transformers import AutoModel, AutoTokenizer

MODEL_DIR = "/home/nash/retrain_twostage/fp_detector_v4_finetuned"
MODEL_NAME = "answerdotai/ModernBERT-large"
MAX_LENGTH = 768
INPUT_PATH = "/home/nash/v4_test_held_out_other.csv"
OUT_PATH = "outputs/reinfer_probs/fp_v4_held_out_other_scores.csv"


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
    print(f"{len(df)} rows (held-out, genuinely-correct 'other' rows, never in v4 training)", flush=True)
    assert (df["confidence"] < 0.3).all(), "population invariant violated -- some rows have confidence>=0.3"

    texts = (
        "[ENTITY: " + df["target_entity"].fillna("unknown").astype(str)
        + " | SILVER_LABEL: other | CLASSIFIER_PREDICTED: other] "
        + df["text"].astype(str)
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

    logits = torch.cat(all_logits).numpy()
    probs = F.softmax(torch.tensor(logits), dim=1).numpy()[:, 1]
    preds = (probs >= 0.5).astype(int)

    n_flagged = preds.sum()
    print(f"\n=== v4 false-alarm check on {len(df)} genuinely-correct, never-trained-on 'other' rows ===", flush=True)
    print(f"Flagged as 'label wrong' (false alarm, since ground truth is these ARE correctly 'other'): {n_flagged}/{len(df)} = {n_flagged/len(df):.3f}", flush=True)
    print(f"Score distribution: mean={probs.mean():.3f} median={np.median(probs):.3f} max={probs.max():.3f}", flush=True)
    print(f"\nFor reference, raw binconf-threshold rule's false-alarm rate on this SAME population: 0/{len(df)} = 0.000", flush=True)
    print("(structurally guaranteed -- these rows have confidence<0.3, so the threshold rule never flags them by definition)", flush=True)

    df["fp_v4_score"] = probs
    df["fp_v4_flagged"] = preds.astype(bool)
    df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
