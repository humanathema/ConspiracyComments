"""retrain_fp_detector_v3_augmented.py

Round 3 of the false-positive detector. Same task scope as round 1
(other-rows-confidently-gated-as-stance) -- round 2's mistake was adding
453 hard negatives against only 119 positives (~5.8:1 imbalance), which
collapsed recall (93.9%->10.2%) and CV AUC (0.823->0.571). This round
fixes that by growing the POSITIVE side instead of just dumping negatives:

1. Positives: the original 76 confirmed "other"-row confidently-wrong
   TRAIN rows, PLUS their back-translated paraphrase text (76 more, full
   coverage confirmed -- doubles to 152) PLUS any NEW positives found by
   scanning the 248 human-labeled "other" TRAIN rows that the original
   diagnostic never checked (excluded upfront as "thin-comment/too-many-
   links" without ever being scored).
2. Negatives: original 238 (119 confident-correct-polar + 119 confident-
   correct-other) PLUS a CAPPED, randomly-sampled subset of the hard
   negatives found in round 2 (human polar rows the round-1 detector
   wrongly flagged) -- capped at roughly 1x the new positive count rather
   than dumping all 453, to avoid round 2's imbalance failure.
"""
import sys

sys.path.insert(0, "src")
import numpy as np
import pandas as pd
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import classification_report, roc_auc_score

from train_binary_confidence import ConfidenceModel, MODEL_NAME
from train_false_positive_detector import score_and_embed, CHECKPOINT_DIR, MAX_LENGTH, CONF_THRESHOLD_CONFIDENT
from transformers import AutoTokenizer

HARD_NEG_CAP_MULTIPLIER = 1.0  # cap hard negatives at ~1x new positive count


def main():
    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Using device: {device}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = ConfidenceModel(MODEL_NAME).to(device)
    state = torch.load(f"{CHECKPOINT_DIR}/model_state.pt", map_location=device)
    model.load_state_dict(state)
    model.eval()

    # --- Positives, part 1+2: original 76 + their paraphrases ---
    fp_df = pd.read_csv("outputs/reinfer_probs/other_to_stance_ALL_confident_wrong_TRAIN.csv")
    orig_pos = fp_df[fp_df["confidently_wrong_either"]][["text", "target_entity"]].copy()
    para_df = pd.read_csv("outputs/reinfer_probs/paraphrase_backtranslation_full.csv")
    orig_pos["key"] = list(zip(orig_pos["text"].astype(str).str.strip(), orig_pos["target_entity"].astype(str).str.strip().str.lower()))
    para_df["key"] = list(zip(para_df["text"].astype(str).str.strip(), para_df["target_entity"].astype(str).str.strip().str.lower()))
    para_matched = para_df[para_df["key"].isin(set(orig_pos["key"]))][["paraphrase", "target_entity"]].rename(columns={"paraphrase": "text"})
    print(f"{len(orig_pos)} original positives, {len(para_matched)} paraphrase positives", flush=True)

    val_fp_df = pd.read_csv("outputs/reinfer_probs/other_to_stance_ALL_confident_wrong_VAL_PARAPHRASE.csv")
    val_wrong_on_para = val_fp_df[val_fp_df["para_gate_has_stance"] & (val_fp_df["para_confidence"] >= CONF_THRESHOLD_CONFIDENT)]
    val_positives = val_wrong_on_para[["paraphrase", "target_entity"]].rename(columns={"paraphrase": "text"}).copy()
    print(f"{len(val_positives)} val-paraphrase positives (unchanged from round 1)", flush=True)

    # --- Positives, part 3: scan the 248 never-checked "other" rows ---
    df = pd.read_parquet("data/processed/stance_classifier_training_data_round10_truncation_fixed.parquet")
    all_other = df[(df["split"] == "train") & (df["is_human"] == True) & (df["label"] == "other")].copy()
    checked_keys = set(orig_pos["key"])
    all_other["key"] = list(zip(all_other["text"].astype(str).str.strip(), all_other["target_entity"].astype(str).str.strip().str.lower()))
    unscanned = all_other[~all_other["key"].isin(checked_keys)].copy()
    print(f"Scanning {len(unscanned)} never-checked 'other' rows for confident-wrongness...", flush=True)
    unscanned_texts = ("[ENTITY: " + unscanned["target_entity"].fillna("unknown").astype(str) + "] " + unscanned["text"].astype(str)).tolist()
    unscanned_emb, unscanned_conf, _ = score_and_embed(model, tokenizer, unscanned_texts, device)
    unscanned["confidence"] = unscanned_conf
    new_positives_mask = unscanned["confidence"] >= CONF_THRESHOLD_CONFIDENT
    new_positives = unscanned[new_positives_mask][["text", "target_entity"]].copy()
    new_positives_emb = unscanned_emb[new_positives_mask.values]
    print(f"{len(new_positives)} NEW positives found in the previously-unscanned pool", flush=True)

    positives = pd.concat([orig_pos[["text", "target_entity"]], para_matched, val_positives, new_positives], ignore_index=True)
    print(f"\nTOTAL positives this round: {len(positives)} "
          f"({len(orig_pos)} orig + {len(para_matched)} paraphrase + {len(val_positives)} val-paraphrase + {len(new_positives)} newly-found)", flush=True)

    # --- Negatives: original pools + capped hard negatives ---
    train_polar = df[(df["split"] == "train") & (df["is_human"] == True) & (df["label"].isin(["hostile", "endorsement"]))].copy()
    train_other = df[(df["split"] == "train") & (df["is_human"] == True) & (df["label"] == "other")].copy()
    polar_texts = ("[ENTITY: " + train_polar["target_entity"].fillna("unknown").astype(str) + "] " + train_polar["text"].astype(str)).tolist()
    other_texts = ("[ENTITY: " + train_other["target_entity"].fillna("unknown").astype(str) + "] " + train_other["text"].astype(str)).tolist()
    print(f"\nScoring {len(train_polar)} human train polar + {len(train_other)} human train other rows (for negative pools)...", flush=True)
    polar_emb, polar_conf, polar_logits = score_and_embed(model, tokenizer, polar_texts, device)
    train_polar["confidence"] = polar_conf
    preds = polar_logits.argmax(axis=1)
    true_label_id = train_polar["label"].map({"hostile": 0, "endorsement": 1}).to_numpy()
    train_polar["correct"] = preds == true_label_id
    other_emb, other_conf, _ = score_and_embed(model, tokenizer, other_texts, device)
    train_other["confidence"] = other_conf

    confident_correct_polar = train_polar[(train_polar["confidence"] >= CONF_THRESHOLD_CONFIDENT) & train_polar["correct"]]
    confident_correct_other = train_other[train_other["confidence"] < (1 - CONF_THRESHOLD_CONFIDENT)]
    n_each = min(119, len(confident_correct_polar), len(confident_correct_other))
    neg_polar = confident_correct_polar.sample(n=n_each, random_state=42)
    neg_other = confident_correct_other.sample(n=n_each, random_state=42)
    print(f"{n_each} original confident-correct-polar negatives, {n_each} original confident-correct-other negatives", flush=True)

    import joblib
    clf_round1 = joblib.load("outputs/checkpoints/false_positive_detector.joblib")
    train_polar["fp_detector_score_round1"] = clf_round1.predict_proba(polar_emb)[:, 1]
    hard_neg_pool = train_polar[(train_polar["fp_detector_score_round1"] >= 0.5) & (train_polar["correct"] == True)]
    hard_neg_cap = int(len(positives) * HARD_NEG_CAP_MULTIPLIER)
    hard_neg_cap = min(hard_neg_cap, len(hard_neg_pool))
    hard_neg = hard_neg_pool.sample(n=hard_neg_cap, random_state=42)
    print(f"{len(hard_neg_pool)} hard negatives available, capped/sampled to {len(hard_neg)} "
          f"(~{HARD_NEG_CAP_MULTIPLIER}x the {len(positives)} positives, vs round 2's uncapped 453)", flush=True)

    # --- Embed positives ---
    orig_pos_texts = ("[ENTITY: " + orig_pos["target_entity"].fillna("unknown").astype(str) + "] " + orig_pos["text"].astype(str)).tolist()
    para_texts = ("[ENTITY: " + para_matched["target_entity"].fillna("unknown").astype(str) + "] " + para_matched["text"].astype(str)).tolist()
    val_pos_texts = ("[ENTITY: " + val_positives["target_entity"].fillna("unknown").astype(str) + "] " + val_positives["text"].astype(str)).tolist()
    orig_pos_emb, _, _ = score_and_embed(model, tokenizer, orig_pos_texts, device)
    para_emb, _, _ = score_and_embed(model, tokenizer, para_texts, device)
    val_pos_emb, _, _ = score_and_embed(model, tokenizer, val_pos_texts, device)
    pos_emb = np.vstack([orig_pos_emb, para_emb, val_pos_emb, new_positives_emb])

    neg_polar_positions = train_polar.index.get_indexer(neg_polar.index)
    neg_other_positions = train_other.index.get_indexer(neg_other.index)
    hard_neg_positions = train_polar.index.get_indexer(hard_neg.index)
    neg_emb = np.vstack([polar_emb[neg_polar_positions], other_emb[neg_other_positions], polar_emb[hard_neg_positions]])

    X = np.vstack([pos_emb, neg_emb])
    y = np.array([1] * len(pos_emb) + [0] * len(neg_emb))
    print(f"\nRound-3 training set: {len(X)} rows ({y.sum()} positive / {(y==0).sum()} negative)", flush=True)

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    clf = LogisticRegression(max_iter=2000, class_weight="balanced", C=1.0)
    cv_probs = cross_val_predict(clf, X, y, cv=cv, method="predict_proba")[:, 1]
    cv_preds = (cv_probs >= 0.5).astype(int)

    print("\n=== 5-fold CV, round 3 (augmented positives + capped hard negatives) ===", flush=True)
    print(classification_report(y, cv_preds, target_names=["genuine_true_positive", "known_false_positive"]), flush=True)
    print(f"AUC: {roc_auc_score(y, cv_probs):.4f}", flush=True)

    clf.fit(X, y)
    joblib.dump(clf, "outputs/checkpoints/false_positive_detector_v3_augmented.joblib")
    print("\nSaved outputs/checkpoints/false_positive_detector_v3_augmented.joblib", flush=True)

    fp_scores_v3 = clf.predict_proba(polar_emb)[:, 1]
    train_polar["fp_detector_score_v3"] = fp_scores_v3
    flagged_v3 = train_polar[train_polar["fp_detector_score_v3"] >= 0.5]
    tp_v3 = ((flagged_v3["correct"] == False)).sum()
    fp_v3 = ((flagged_v3["correct"] == True)).sum()
    not_flagged_v3 = train_polar[train_polar["fp_detector_score_v3"] < 0.5]
    fn_v3 = (not_flagged_v3["correct"] == False).sum()
    print(f"\n=== Round 3 re-applied to the full human polar population (n={len(train_polar)}) ===", flush=True)
    print(f"flagged: {len(flagged_v3)}  TP={tp_v3}  FP={fp_v3}  FN={fn_v3}", flush=True)
    print(f"precision: {tp_v3/(tp_v3+fp_v3):.3f}  recall: {tp_v3/(tp_v3+fn_v3):.3f}", flush=True)
    print("(partially in-sample re: hard negatives used in training -- directional signal, not a clean held-out test)", flush=True)

    train_polar.to_csv("outputs/reinfer_probs/train_polar_fp_detector_scores_v3.csv", index=False)
    print("\nSaved outputs/reinfer_probs/train_polar_fp_detector_scores_v3.csv", flush=True)


if __name__ == "__main__":
    main()
