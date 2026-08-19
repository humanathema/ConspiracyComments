"""test_marked_window_input.py

Empirical check (inference only, no retrain): does marking the entity's
local window within the full text, plus a short entity description,
change the existing binconf_other015 checkpoint's confidence/accuracy on
val680, compared to the current plain "[ENTITY: name] <full text>"
format? Same methodology as round9's context-delta check -- re-run the
SAME trained model on reformatted input and compare, rather than assume.

Not a fair end-to-end test (the model was never trained on the new
format), but a legitimate first signal: if the new format doesn't even
move things in a sane direction under this rough test, it's not worth
the cost of recomputing spans + retraining; if it does, that's grounds
to actually retrain on it properly.
"""
import json
import sys

sys.path.insert(0, "src")
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from sklearn.metrics import cohen_kappa_score
from transformers import AutoModel, AutoTokenizer
import torch.nn as nn

CHECKPOINT = "outputs/checkpoints/binconf_other015_binary_confidence"
MAX_LENGTH = 768
WINDOW_WORDS = 15


class ConfidenceModel(nn.Module):
    def __init__(self, model_name):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size = self.encoder.config.hidden_size
        self.classifier = nn.Linear(hidden_size, 2)
        self.confidence_head = nn.Linear(hidden_size, 1)

    def forward(self, input_ids=None, attention_mask=None, **kwargs):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        last_hidden = out.last_hidden_state
        mask = attention_mask.unsqueeze(-1).float()
        pooled = (last_hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        logits = self.classifier(pooled)
        confidence = torch.sigmoid(self.confidence_head(pooled)).squeeze(-1)
        return logits, confidence


def old_format(row):
    return f"[ENTITY: {row['target_entity']}] {row['text']}"


def new_format(row, desc_lookup):
    text = str(row["text"])
    spans = row["entity_spans"]
    if isinstance(spans, str):
        try:
            spans = json.loads(spans)
        except (json.JSONDecodeError, TypeError):
            spans = []
    entity = row["target_entity"]
    desc = desc_lookup.get(str(entity).lower(), "")
    about = f" [ABOUT: {desc}]" if desc else ""

    if not spans:
        return f"[ENTITY: {entity}]{about} {text}"

    # Wrap each span's local window in >>...<< markers, in place, within
    # the full text (not replacing it).
    marked = text
    offset = 0
    for s in sorted(spans, key=lambda x: x["start"]):
        start, end = s["start"] + offset, s["end"] + offset
        before_words = marked[:start].split()
        win_start_word_idx = max(0, len(before_words) - WINDOW_WORDS)
        win_start_char = len(" ".join(before_words[:win_start_word_idx])) if win_start_word_idx else 0
        if win_start_word_idx > 0:
            win_start_char += 1  # skip the joining space
        marker_open = ">>"
        marker_close = "<<"
        marked = marked[:win_start_char] + marker_open + marked[win_start_char:end] + marker_close + marked[end:]
        offset += len(marker_open) + len(marker_close)

    return f"[ENTITY: {entity}]{about} {marked}"


def main():
    df = pd.read_parquet("data/processed/stance_classifier_training_data_round10_truncation_fixed.parquet")
    val = df[df["split"] == "val"].reset_index(drop=True)
    print(f"{len(val)} val rows", flush=True)

    desc_df = pd.read_csv("data/processed/entity_description_lookup.csv")
    desc_lookup = desc_df.set_index(desc_df["entity"].str.lower())["description"].to_dict()

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Using device: {device}", flush=True)

    print("Loading tokenizer + model...", flush=True)
    tokenizer = AutoTokenizer.from_pretrained("answerdotai/ModernBERT-large")
    model = ConfidenceModel("answerdotai/ModernBERT-large")
    state = torch.load(f"{CHECKPOINT}/model_state.pt", map_location="cpu")
    model.load_state_dict(state)
    model.to(device)
    model.eval()

    old_texts = [old_format(r) for _, r in val.iterrows()]
    new_texts = [new_format(r, desc_lookup) for _, r in val.iterrows()]

    def run(texts, batch_size=16):
        all_logits, all_conf = [], []
        with torch.no_grad():
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                enc = tokenizer(batch, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt").to(device)
                logits, conf = model(**enc)
                all_logits.append(logits.cpu())
                all_conf.append(conf.cpu())
                if i % (batch_size * 10) == 0:
                    print(f"  {i}/{len(texts)}", flush=True)
        return torch.cat(all_logits), torch.cat(all_conf)

    print("Running OLD format...", flush=True)
    old_logits, old_conf = run(old_texts)
    print("Running NEW format...", flush=True)
    new_logits, new_conf = run(new_texts)

    label_map = {"hostile": 0, "endorsement": 1}
    is_other = (val["label"] == "other").values
    is_polar = ~is_other
    true_polar = val.loc[is_polar, "label"].map(label_map).values

    old_preds = old_logits.argmax(-1).numpy()
    new_preds = new_logits.argmax(-1).numpy()

    old_kappa = cohen_kappa_score(true_polar, old_preds[is_polar])
    new_kappa = cohen_kappa_score(true_polar, new_preds[is_polar])
    print(f"\nOLD format: polarity kappa={old_kappa:.4f}, mean_conf_polar={old_conf[is_polar].mean():.4f}, mean_conf_other={old_conf[is_other].mean():.4f}")
    print(f"NEW format: polarity kappa={new_kappa:.4f}, mean_conf_polar={new_conf[is_polar].mean():.4f}, mean_conf_other={new_conf[is_other].mean():.4f}")

    changed = (old_preds != new_preds).sum()
    print(f"\npredictions changed between formats: {changed}/{len(val)} ({changed/len(val):.1%})")

    out = pd.DataFrame({
        "target_entity": val["target_entity"], "label": val["label"],
        "old_pred": old_preds, "new_pred": new_preds,
        "old_conf": old_conf.numpy(), "new_conf": new_conf.numpy(),
    })
    out.to_csv("outputs/reinfer_probs/marked_window_test_val680.csv", index=False)
    print("Saved outputs/reinfer_probs/marked_window_test_val680.csv")


if __name__ == "__main__":
    main()
