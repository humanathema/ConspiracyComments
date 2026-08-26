"""score_entitytag_finetuned_overall_kappa.py

Computes the OVERALL 3-way kappa (hostile/endorsement/other, confidence-
threshold gated) for the entity_tag fine-tuned checkpoint
(binconf_entitytag_v1_binary_confidence), on val680 -- same methodology as
score_binconf_on_aleatoric.py, so the number is directly comparable to
binconf_other015's baseline overall kappa (0.5219 on val680, 0.5303 on the
clean r1 set).

train_binary_confidence.py's own built-in eval pass only reports
POLARITY-only kappa (0.6990 for this checkpoint) -- it never applies the
confidence threshold to build a 3-way prediction, so that number is NOT
comparable to the overall-kappa figures cited elsewhere tonight. This
script fills that specific gap.

Scores val680 using the SAME entity_tag input format the checkpoint was
trained on (not the plain [ENTITY: name] format) -- scoring format must
match training format for a fair read.
"""
import sys

sys.path.insert(0, "src")
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import cohen_kappa_score, classification_report
from transformers import AutoModel, AutoTokenizer

CHECKPOINT = "/home/nash/retrain_twostage/binconf_entitytag_v1_binary_confidence"
BASELINE_CHECKPOINT = "outputs/checkpoints/binconf_other015_binary_confidence"
TRAIN_FILE = "data/processed/stance_classifier_training_data_round10_truncation_fixed.parquet"
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


def score(model, tokenizer, texts, device, batch_size=16):
    all_logits, all_conf = [], []
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            enc = tokenizer(batch, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt").to(device)
            logits, conf = model(**enc)
            all_logits.append(logits.cpu())
            all_conf.append(conf.cpu())
    return torch.cat(all_logits).numpy(), torch.cat(all_conf).numpy()


def overall_and_polarity_kappa(logits, confidence, true_3way, is_polar, true_polar):
    probs = torch.softmax(torch.tensor(logits), dim=1).numpy()
    pred_3way = np.where(
        confidence < 0.5, "other",
        np.where(probs[:, 0] >= probs[:, 1], "hostile", "endorsement"),
    )
    overall_kappa = cohen_kappa_score(true_3way, pred_3way)
    pred_polar = np.argmax(logits[is_polar], axis=1)
    polarity_kappa = cohen_kappa_score(true_polar, pred_polar)
    return overall_kappa, polarity_kappa, pred_3way


def main():
    df = pd.read_parquet(TRAIN_FILE)
    val = df[df["split"] == "val"].reset_index(drop=True)
    print(f"{len(val)} val680 rows", flush=True)

    entity_to_cat = load_entity_to_coarse_cat(CATEGORIES_LOOKUP_FILE)
    tags = val["target_entity"].fillna("unknown").astype(str).str.lower().map(
        lambda e: entity_to_cat.get(e, "other_maverick")
    )
    entity_tag_texts = (
        "[ENTITY: " + val["target_entity"].fillna("unknown").astype(str)
        + " | TYPE: " + tags + "] " + val["text"].astype(str)
    ).tolist()
    plain_texts = ("[ENTITY: " + val["target_entity"].fillna("unknown").astype(str) + "] "
                   + val["text"].astype(str)).tolist()

    LABEL_TO_ID = {"hostile": 0, "endorsement": 1}
    is_other = (val["label"] == "other").values
    is_polar = ~is_other
    true_3way = val["label"].values
    true_polar = val.loc[is_polar, "label"].map(LABEL_TO_ID).values

    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Using device: {device}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained("answerdotai/ModernBERT-large")

    print("\n=== entity_tag fine-tuned checkpoint, scored with entity_tag format (matches its training) ===", flush=True)
    model = ConfidenceModel("answerdotai/ModernBERT-large").to(device)
    state = torch.load(f"{CHECKPOINT}/model_state.pt", map_location=device)
    model.load_state_dict(state)
    model.eval()
    logits, confidence = score(model, tokenizer, entity_tag_texts, device)
    overall_kappa, polarity_kappa, _ = overall_and_polarity_kappa(logits, confidence, true_3way, is_polar, true_polar)
    print(f"OVERALL 3-way kappa: {overall_kappa:.4f}", flush=True)
    print(f"Polarity-only kappa: {polarity_kappa:.4f} (should roughly match the training script's own reported 0.6990)", flush=True)
    del model
    torch.cuda.empty_cache()

    print("\n=== baseline binconf_other015, scored with plain format (for direct comparison) ===", flush=True)
    model2 = ConfidenceModel("answerdotai/ModernBERT-large").to(device)
    state2 = torch.load(f"{BASELINE_CHECKPOINT}/model_state.pt", map_location=device)
    model2.load_state_dict(state2)
    model2.eval()
    logits2, confidence2 = score(model2, tokenizer, plain_texts, device)
    overall_kappa2, polarity_kappa2, _ = overall_and_polarity_kappa(logits2, confidence2, true_3way, is_polar, true_polar)
    print(f"OVERALL 3-way kappa: {overall_kappa2:.4f} (should roughly match the previously-logged 0.5219)", flush=True)
    print(f"Polarity-only kappa: {polarity_kappa2:.4f} (should roughly match the previously-logged 0.7386/0.7466)", flush=True)

    print("\n=== SUMMARY ===", flush=True)
    print(f"binconf_other015 (baseline):      overall={overall_kappa2:.4f}  polarity={polarity_kappa2:.4f}", flush=True)
    print(f"binconf_entitytag_v1 (fine-tuned): overall={overall_kappa:.4f}  polarity={polarity_kappa:.4f}", flush=True)


if __name__ == "__main__":
    main()
