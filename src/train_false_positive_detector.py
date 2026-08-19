"""train_false_positive_detector.py

Nash's plan (2026-08-19): the paraphrase-flip diagnostic found that 76/526
(14.4%) of train-split human "other" rows get confidently (>=0.7) gated as
"stanced" by binconf_other015 -- either on the original text, the
paraphrase, or (41 of 76) both. Those 41 "wrong on both" cases are
especially telling: not a paraphrasing-fragility artifact, a persistent
content-level blind spot (dense conspiracy-topic vocabulary and meta/
hedging discussion overwhelming the classifier regardless of exact
wording -- see the feature analysis in conversation, not reproduced here).

Rather than hand-write a keyword/regex detector for that pattern, train a
lightweight classifier directly on binconf_other015's own pooled
embeddings to distinguish "known false positive" from "genuine true
positive" -- reuses the base model's actual representation instead of a
separate reimplementation of what the pattern might be, and is fair to
try with a small sample:
    - Positive class: the 76 confidently-wrong "other" rows.
    - Negative class: TRAIN hostile/endorsement rows the model gets
      genuinely, confidently right (matched count, sampled across the
      same entities/confidence range where possible) -- what a REAL
      confident correct stance detection looks like, as contrast.

Logistic regression on frozen pooled embeddings (not fine-tuning the
whole encoder again) -- appropriate given the tiny positive sample (76),
evaluated via stratified k-fold since 76 examples is too small to trust a
single train/test split.
"""
import sys

sys.path.insert(0, "src")
import numpy as np
import pandas as pd
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import classification_report, roc_auc_score
from transformers import AutoTokenizer

from train_binary_confidence import ConfidenceModel, MODEL_NAME

CHECKPOINT_DIR = "outputs/checkpoints/binconf_other015_binary_confidence"
MAX_LENGTH = 768
BATCH_SIZE = 8
CONF_THRESHOLD_CONFIDENT = 0.7


def score_and_embed(model, tokenizer, texts, device):
    """One forward pass returning everything downstream needs: confidence,
    classifier logits, AND the pooled embedding the classifier head sees.
    Found 2026-08-19: an earlier version of this script called the model
    twice over the same 32,607-row set (once for confidence/logits, once
    more for embeddings) -- 40+ minutes into just the first pass with a
    second full pass still to come. ConfidenceModel.forward already does
    this exact mean-pooling internally right before its classifier/
    confidence heads; replicating that computation here once, in the same
    pass, avoids paying for it twice."""
    all_pooled, all_conf, all_logits = [], [], []
    with torch.no_grad():
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            enc = tokenizer(batch, truncation=True, padding=True, max_length=MAX_LENGTH, return_tensors="pt").to(device)
            out = model.encoder(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"])
            last_hidden = out.last_hidden_state
            mask = enc["attention_mask"].unsqueeze(-1).float()
            pooled = (last_hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
            logits = model.classifier(pooled)
            confidence = torch.sigmoid(model.confidence_head(pooled)).squeeze(-1)
            all_pooled.append(pooled.cpu())
            all_conf.append(confidence.cpu())
            all_logits.append(logits.cpu())
    return torch.cat(all_pooled).numpy(), torch.cat(all_conf).numpy(), torch.cat(all_logits).numpy()


def main():
    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Using device: {device}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = ConfidenceModel(MODEL_NAME).to(device)
    state = torch.load(f"{CHECKPOINT_DIR}/model_state.pt", map_location=device)
    model.load_state_dict(state)
    model.eval()

    # Positive class: the 76 confidently-wrong "other" rows from TRAIN
    # (original text, not paraphrase -- the paraphrase was a diagnostic
    # tool to FIND these, the detector should learn to spot them from
    # real, as-written text -- no leakage concern, this is train data).
    fp_df = pd.read_csv("outputs/reinfer_probs/other_to_stance_ALL_confident_wrong_TRAIN.csv")
    train_positives = fp_df[fp_df["confidently_wrong_either"]][["text", "target_entity"]].copy()

    # PLUS extra positives from VAL -- Nash's idea 2026-08-19: use the
    # PARAPHRASE text (not the original val text) as the positive example,
    # since that's a meaning-preserving rewrite, not literally training on
    # val. Restricted to the 43/48 rows where the paraphrase ITSELF was
    # confidently wrong (>=0.7) -- the other 5 were only wrong on the
    # original val text (paraphrase actually "fixed" them), so there's no
    # non-val-text version of those to use; excluded rather than falling
    # back to the original.
    val_fp_df = pd.read_csv("outputs/reinfer_probs/other_to_stance_ALL_confident_wrong_VAL_PARAPHRASE.csv")
    val_wrong_on_para = val_fp_df[val_fp_df["para_gate_has_stance"] & (val_fp_df["para_confidence"] >= CONF_THRESHOLD_CONFIDENT)]
    val_positives = val_wrong_on_para[["paraphrase", "target_entity"]].rename(columns={"paraphrase": "text"}).copy()
    print(f"{len(train_positives)} train positives + {len(val_positives)} val-paraphrase positives", flush=True)

    positives = pd.concat([train_positives, val_positives], ignore_index=True)
    print(f"{len(positives)} known false-positive rows (positive class)", flush=True)

    # Negative class -- TWO kinds, not one. Found 2026-08-20 (real bug):
    # the original version of this script sourced negatives ONLY from
    # confident-correct POLAR rows -- the detector was never shown a
    # single genuine, correctly-classified "other" row as a negative
    # example. Applied at full scale (42,183 rows), it flagged 94.6% of
    # ALL "other"-labeled rows as false positives -- not because that many
    # are actually mislabeled, but because it had only ever learned
    # roughly "does this look like a confident polar prediction," and
    # real "other" rows structurally never do, regardless of whether
    # they're correctly classified. Fixed by including confident-correct
    # OTHER rows as negatives too, so the detector has to learn the actual
    # distinction (known-error vs known-correct) instead of a proxy for it
    # (polar-shaped vs not).
    #
    # Restricted to is_human==True (2026-08-19, Nash's call): the
    # 39,281-row machine/silver-labeled majority of train isn't trustworthy
    # ground truth to source negatives from or scan for flags against --
    # a flag on a silver-labeled row is ambiguous (detector right, silver
    # label wrong? or vice versa?), whereas human labels give a clean
    # answer either way. Also ~15x cheaper (2,178 vs 32,607 rows).
    df = pd.read_parquet("data/processed/stance_classifier_training_data_round10_truncation_fixed.parquet")
    train_polar = df[(df["split"] == "train") & (df["is_human"] == True) & (df["label"].isin(["hostile", "endorsement"]))].copy()
    train_other = df[(df["split"] == "train") & (df["is_human"] == True) & (df["label"] == "other")].copy()
    print(f"Scoring {len(train_polar)} HUMAN-labeled train polar rows + {len(train_other)} other rows "
          f"(single pass each: confidence + logits + embeddings)...", flush=True)
    polar_texts = ("[ENTITY: " + train_polar["target_entity"].fillna("unknown").astype(str) + "] " + train_polar["text"].astype(str)).tolist()
    other_texts = ("[ENTITY: " + train_other["target_entity"].fillna("unknown").astype(str) + "] " + train_other["text"].astype(str)).tolist()

    polar_emb, polar_conf, polar_logits = score_and_embed(model, tokenizer, polar_texts, device)
    train_polar["confidence"] = polar_conf
    preds = polar_logits.argmax(axis=1)
    true_label_id = train_polar["label"].map({"hostile": 0, "endorsement": 1}).to_numpy()
    train_polar["correct"] = preds == true_label_id
    # Keep embeddings aligned to train_polar's row order for reuse below --
    # avoids re-scoring this same set a second time just to also get
    # false-positive-detector scores on it.
    train_polar_emb = polar_emb

    other_emb, other_conf, _ = score_and_embed(model, tokenizer, other_texts, device)
    train_other["confidence"] = other_conf

    confident_correct_polar = train_polar[(train_polar["confidence"] >= CONF_THRESHOLD_CONFIDENT) & train_polar["correct"]]
    # "Correct" for other rows means LOW confidence (correctly gated as
    # other) -- confident_correct here means clearly, unambiguously other,
    # the mirror case of confident_correct_polar.
    confident_correct_other = train_other[train_other["confidence"] < (1 - CONF_THRESHOLD_CONFIDENT)]
    print(f"{len(confident_correct_polar)} confident-correct polar rows, "
          f"{len(confident_correct_other)} confident-correct other rows available as negative pool", flush=True)

    n_each = min(len(positives), len(confident_correct_polar), len(confident_correct_other))
    neg_polar = confident_correct_polar.sample(n=n_each, random_state=42)
    neg_other = confident_correct_other.sample(n=n_each, random_state=42)
    print(f"Sampling {n_each} of each kind as negative class ({2*n_each} total, "
          f"balanced against {len(positives)} positives)", flush=True)

    pos_texts = ("[ENTITY: " + positives["target_entity"].fillna("unknown").astype(str) + "] " + positives["text"].astype(str)).tolist()
    pos_emb, _, _ = score_and_embed(model, tokenizer, pos_texts, device)
    # Both negative subsets are drawn from sets we already embedded above --
    # reuse by position instead of a third/fourth pass.
    neg_polar_positions = train_polar.index.get_indexer(neg_polar.index)
    neg_other_positions = train_other.index.get_indexer(neg_other.index)
    neg_emb = np.vstack([train_polar_emb[neg_polar_positions], other_emb[neg_other_positions]])

    X = np.vstack([pos_emb, neg_emb])
    y = np.array([1] * len(pos_emb) + [0] * len(neg_emb))
    print(f"\nTraining set: {len(X)} rows ({y.sum()} positive / {(y==0).sum()} negative: "
          f"{n_each} polar + {n_each} other)", flush=True)

    # Stratified k-fold rather than a single train/test split -- 76
    # positives is too small to trust one split's numbers.
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    clf = LogisticRegression(max_iter=2000, class_weight="balanced", C=1.0)
    cv_probs = cross_val_predict(clf, X, y, cv=cv, method="predict_proba")[:, 1]
    cv_preds = (cv_probs >= 0.5).astype(int)

    print("\n=== 5-fold cross-validated false-positive detector performance ===", flush=True)
    print(classification_report(y, cv_preds, target_names=["genuine_true_positive", "known_false_positive"]), flush=True)
    print(f"AUC: {roc_auc_score(y, cv_probs):.4f}", flush=True)

    # Fit on the full labeled set for actual downstream use.
    clf.fit(X, y)
    import joblib
    joblib.dump(clf, "outputs/checkpoints/false_positive_detector.joblib")
    print("\nSaved outputs/checkpoints/false_positive_detector.joblib", flush=True)

    # Immediate, cheap validation: apply the detector to the FULL train
    # polar set (not just the confident-correct subset used as negatives)
    # to see what fraction of "stanced" predictions it flags as suspect --
    # reuses train_polar_emb from the single pass above, no new inference.
    fp_scores = clf.predict_proba(train_polar_emb)[:, 1]
    train_polar["fp_detector_score"] = fp_scores
    train_polar.to_csv("outputs/reinfer_probs/train_polar_fp_detector_scores.csv", index=False)
    flagged = train_polar[train_polar["fp_detector_score"] >= 0.5]
    print(f"{len(flagged)}/{len(train_polar)} = {len(flagged)/len(train_polar):.1%} of ALL train polar rows "
          f"flagged as likely false positives by the detector", flush=True)
    print("Saved outputs/reinfer_probs/train_polar_fp_detector_scores.csv", flush=True)


if __name__ == "__main__":
    main()
