"""score_fp_v7_on_hitl_r1_human_validation.py

The first real human-grounded validation of ANY version of this FP
detector (v4-v7 have all only been checked against frontier AI judgments
so far -- see fp_detector_v6_flagged_frontier_verified in
data/experiment_log.jsonl for that caveat). Scores v7 against 331 rows
from Nash's queue_expanded_entity_val_r1.csv HITL batch: human-labeled
hostile/endorsement rows, confirmed zero overlap with the 42k population
v7's entire training pipeline draws from.

Since these rows are all human-CONFIRMED genuinely stanced, this mainly
tests v7's false-alarm rate (does it wrongly flag good rows) rather than
recall -- there's no expectation of a meaningful count of genuine
"should-be-other" errors in a batch a human already read and labeled.

Input: /home/nash/hitl_r1_clean_stanced_validation.csv (id, text,
target_entity, label)
Output: outputs/reinfer_probs/fp_v7_hitl_r1_human_validation_scored.csv
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import pandas as pd
from transformers import AutoModel, AutoTokenizer

MODEL_DIR = "/home/nash/retrain_twostage/fp_detector_v7_expanded"
MODEL_NAME = "answerdotai/ModernBERT-large"
MAX_LENGTH = 768
BATCH_SIZE = 16
INPUT_PATH = "/home/nash/hitl_r1_clean_stanced_validation.csv"
OUT_PATH = "outputs/reinfer_probs/fp_v7_hitl_r1_human_validation_scored.csv"


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
    print(f"{len(df)} human-labeled stanced rows, zero overlap with v7's training population", flush=True)

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

    n_flagged = preds.sum()
    print(f"\n=== v7 on 331 genuinely-correct human-labeled stanced rows (never in training) ===", flush=True)
    print(f"Flagged (false alarm, since ground truth is these ARE correctly stanced): {n_flagged}/{len(df)} = {n_flagged/len(df):.3f}", flush=True)
    print(f"Score distribution: mean={probs.mean():.3f} median={probs.__class__.__name__ and pd.Series(probs).median():.3f} max={probs.max():.3f}", flush=True)

    df["fp_v7_score"] = probs
    df["fp_v7_flagged"] = preds.astype(bool)
    df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {OUT_PATH}", flush=True)
    if n_flagged > 0:
        print("\nFlagged rows (worth a quick human look -- either real detector errors or, rarely, real human-label noise):", flush=True)
        print(df[df["fp_v7_flagged"]][["id", "text", "target_entity", "label", "fp_v7_score"]].to_string(), flush=True)


if __name__ == "__main__":
    main()
