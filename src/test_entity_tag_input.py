"""test_entity_tag_input.py

Empirical check (inference only, no retrain): does adding a short
"[ENTITY: name | TYPE: category]" tag change the existing binconf_other015
checkpoint's confidence/accuracy on val680, compared to the current plain
"[ENTITY: name] <full text>" format? Same methodology as
test_marked_window_input.py (which tested the free-text [ABOUT: description]
variant and found a real drop, kappa 0.7466->0.6953, on an untrained
checkpoint) -- re-run the SAME trained model on reformatted input and
compare, rather than assume either variant is better.

Not a fair end-to-end test (the model was never trained on this format) --
a first rough signal only. If this doesn't move things in a sane direction,
it's not worth the cost of the fair fine-tuned test
(INPUT_FORMAT=entity_tag in train_binary_confidence.py, with
INIT_FROM_CHECKPOINT set to continue from this same checkpoint); if it
does, that's grounds to actually run the fine-tune.

CIRCULARITY WARNING carried over from train_binary_confidence.py's
_texts_with_entity_tag docstring: this tag format must never feed the
whistleblower/other_maverick regression's stance_prob column -- see that
docstring for the full reasoning. This script is a diagnostic check only.
"""
import sys

sys.path.insert(0, "src")
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import cohen_kappa_score
from transformers import AutoModel, AutoTokenizer

CHECKPOINT = "outputs/checkpoints/binconf_other015_binary_confidence"
CATEGORIES_LOOKUP_FILE = "data/processed/entity_categories_lookup.csv"
MAX_LENGTH = 768


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


def load_entity_to_coarse_cat(path):
    lookup_df = pd.read_csv(path)
    raw = dict(zip(lookup_df["entity_key"], lookup_df["category"]))
    return {
        k: (v if v in ("whistleblower", "consensus_expert") else "other_maverick")
        for k, v in raw.items()
    }


def old_format(row):
    return f"[ENTITY: {row['target_entity']}] {row['text']}"


def new_format(row, entity_to_cat):
    entity = str(row["target_entity"])
    tag = entity_to_cat.get(entity.lower(), "other_maverick")
    return f"[ENTITY: {entity} | TYPE: {tag}] {row['text']}"


def main():
    df = pd.read_parquet("data/processed/stance_classifier_training_data_round10_truncation_fixed.parquet")
    val = df[df["split"] == "val"].reset_index(drop=True)
    print(f"{len(val)} val rows", flush=True)

    entity_to_cat = load_entity_to_coarse_cat(CATEGORIES_LOOKUP_FILE)
    print(f"{len(entity_to_cat)} entity categories loaded", flush=True)

    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Using device: {device}", flush=True)

    print("Loading tokenizer + model...", flush=True)
    tokenizer = AutoTokenizer.from_pretrained("answerdotai/ModernBERT-large")
    model = ConfidenceModel("answerdotai/ModernBERT-large")
    state = torch.load(f"{CHECKPOINT}/model_state.pt", map_location="cpu")
    model.load_state_dict(state)
    model.to(device)
    model.eval()

    old_texts = [old_format(r) for _, r in val.iterrows()]
    new_texts = [new_format(r, entity_to_cat) for _, r in val.iterrows()]

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

    print("Running OLD format (plain [ENTITY: name])...", flush=True)
    old_logits, old_conf = run(old_texts)
    print("Running NEW format ([ENTITY: name | TYPE: category])...", flush=True)
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
    out.to_csv("outputs/reinfer_probs/entity_tag_test_val680.csv", index=False)
    print("Saved outputs/reinfer_probs/entity_tag_test_val680.csv")


if __name__ == "__main__":
    main()
