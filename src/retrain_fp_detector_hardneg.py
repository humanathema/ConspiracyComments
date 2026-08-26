"""retrain_fp_detector_hardneg.py

Round 2 of the false-positive detector (train_false_positive_detector.py),
same task, same positive class -- adds hard negatives found this session:
human-labeled POLAR (hostile/endorsement) rows the detector flagged as
"false positive" that are actually genuinely correct (confirmed via
outputs/reinfer_probs/train_polar_fp_detector_scores.csv's own 'correct'
column, ground truth from the human label itself, no new labeling).
503 such rows found, out of the full 2,131-row human-labeled polar
population (precision on that population was 8.4% -- this directly
targets that failure mode).

Positive class: UNCHANGED from train_false_positive_detector.py -- the
same 76 confidently-wrong "other" rows. Task scope stays exactly the same
(other-rows-confidently-gated-as-stance); this is not expanding to
polarity-flip errors, only adding corrective negative signal.

Negative class: original 238 (119 confident-correct polar + 119
confident-correct other) PLUS 503 new hard negatives.
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
from train_false_positive_detector import score_and_embed, CHECKPOINT_DIR, MAX_LENGTH, CONF_THRESHOLD_CONFIDENT

BATCH_SIZE = 8


def main():
    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Using device: {device}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = ConfidenceModel(MODEL_NAME).to(device)
    state = torch.load(f"{CHECKPOINT_DIR}/model_state.pt", map_location=device)
    model.load_state_dict(state)
    model.eval()

    # Positive class -- IDENTICAL to train_false_positive_detector.py, not touched.
    fp_df = pd.read_csv("outputs/reinfer_probs/other_to_stance_ALL_confident_wrong_TRAIN.csv")
    train_positives = fp_df[fp_df["confidently_wrong_either"]][["text", "target_entity"]].copy()
    val_fp_df = pd.read_csv("outputs/reinfer_probs/other_to_stance_ALL_confident_wrong_VAL_PARAPHRASE.csv")
    val_wrong_on_para = val_fp_df[val_fp_df["para_gate_has_stance"] & (val_fp_df["para_confidence"] >= CONF_THRESHOLD_CONFIDENT)]
    val_positives = val_wrong_on_para[["paraphrase", "target_entity"]].rename(columns={"paraphrase": "text"}).copy()
    positives = pd.concat([train_positives, val_positives], ignore_index=True)
    print(f"{len(positives)} positives (unchanged from round 1)", flush=True)

    # Original negative pools -- rebuilt the same way train_false_positive_detector.py did.
    df = pd.read_parquet("data/processed/stance_classifier_training_data_round10_truncation_fixed.parquet")
    train_polar = df[(df["split"] == "train") & (df["is_human"] == True) & (df["label"].isin(["hostile", "endorsement"]))].copy()
    train_other = df[(df["split"] == "train") & (df["is_human"] == True) & (df["label"] == "other")].copy()
    polar_texts = ("[ENTITY: " + train_polar["target_entity"].fillna("unknown").astype(str) + "] " + train_polar["text"].astype(str)).tolist()
    other_texts = ("[ENTITY: " + train_other["target_entity"].fillna("unknown").astype(str) + "] " + train_other["text"].astype(str)).tolist()

    print(f"Scoring {len(train_polar)} human train polar + {len(train_other)} human train other rows...", flush=True)
    polar_emb, polar_conf, polar_logits = score_and_embed(model, tokenizer, polar_texts, device)
    train_polar["confidence"] = polar_conf
    preds = polar_logits.argmax(axis=1)
    true_label_id = train_polar["label"].map({"hostile": 0, "endorsement": 1}).to_numpy()
    train_polar["correct"] = preds == true_label_id

    other_emb, other_conf, _ = score_and_embed(model, tokenizer, other_texts, device)
    train_other["confidence"] = other_conf

    confident_correct_polar = train_polar[(train_polar["confidence"] >= CONF_THRESHOLD_CONFIDENT) & train_polar["correct"]]
    confident_correct_other = train_other[train_other["confidence"] < (1 - CONF_THRESHOLD_CONFIDENT)]
    n_each = min(len(positives), len(confident_correct_polar), len(confident_correct_other))
    neg_polar = confident_correct_polar.sample(n=n_each, random_state=42)
    neg_other = confident_correct_other.sample(n=n_each, random_state=42)
    print(f"{n_each} original confident-correct-polar negatives, {n_each} original confident-correct-other negatives", flush=True)

    # NEW hard negatives: score the FULL human polar population with the
    # ROUND-1 detector to find rows it wrongly flagged (correct==True but
    # flagged) -- reuses polar_emb already computed above, no extra pass.
    import joblib
    clf_round1 = joblib.load("outputs/checkpoints/false_positive_detector.joblib")
    train_polar["fp_detector_score_round1"] = clf_round1.predict_proba(polar_emb)[:, 1]
    hard_neg = train_polar[(train_polar["fp_detector_score_round1"] >= 0.5) & (train_polar["correct"] == True)]
    print(f"{len(hard_neg)} NEW hard negatives (detector wrongly flagged these, true label confirms they're correct)", flush=True)

    pos_texts = ("[ENTITY: " + positives["target_entity"].fillna("unknown").astype(str) + "] " + positives["text"].astype(str)).tolist()
    pos_emb, _, _ = score_and_embed(model, tokenizer, pos_texts, device)

    neg_polar_positions = train_polar.index.get_indexer(neg_polar.index)
    neg_other_positions = train_other.index.get_indexer(neg_other.index)
    hard_neg_positions = train_polar.index.get_indexer(hard_neg.index)
    neg_emb = np.vstack([polar_emb[neg_polar_positions], other_emb[neg_other_positions], polar_emb[hard_neg_positions]])

    X = np.vstack([pos_emb, neg_emb])
    y = np.array([1] * len(pos_emb) + [0] * len(neg_emb))
    print(f"\nRound-2 training set: {len(X)} rows ({y.sum()} positive / {(y==0).sum()} negative: "
          f"{n_each} orig-polar + {n_each} orig-other + {len(hard_neg)} new-hard-negatives)", flush=True)

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    clf = LogisticRegression(max_iter=2000, class_weight="balanced", C=1.0)
    cv_probs = cross_val_predict(clf, X, y, cv=cv, method="predict_proba")[:, 1]
    cv_preds = (cv_probs >= 0.5).astype(int)

    print("\n=== 5-fold CV, round 2 (with hard negatives) ===", flush=True)
    print(classification_report(y, cv_preds, target_names=["genuine_true_positive", "known_false_positive"]), flush=True)
    print(f"AUC: {roc_auc_score(y, cv_probs):.4f}", flush=True)

    clf.fit(X, y)
    joblib.dump(clf, "outputs/checkpoints/false_positive_detector_v2_hardneg.joblib")
    print("\nSaved outputs/checkpoints/false_positive_detector_v2_hardneg.joblib", flush=True)

    # Re-check against the SAME full human polar population used to find
    # the hard negatives -- this is in-sample for the hard negatives
    # themselves (expected to improve, that's the point), but the 46
    # original true positives + the untouched confident_correct_polar
    # negatives give a real signal on whether precision improved without
    # destroying recall.
    fp_scores_v2 = clf.predict_proba(polar_emb)[:, 1]
    train_polar["fp_detector_score_v2"] = fp_scores_v2
    flagged_v2 = train_polar[train_polar["fp_detector_score_v2"] >= 0.5]
    tp_v2 = ((flagged_v2["correct"] == False)).sum()
    fp_v2 = ((flagged_v2["correct"] == True)).sum()
    not_flagged_v2 = train_polar[train_polar["fp_detector_score_v2"] < 0.5]
    fn_v2 = (not_flagged_v2["correct"] == False).sum()
    print(f"\n=== Round 2 detector re-applied to the SAME full human polar population (n={len(train_polar)}) ===", flush=True)
    print(f"flagged: {len(flagged_v2)}  TP={tp_v2}  FP={fp_v2}  FN={fn_v2}", flush=True)
    print(f"precision: {tp_v2/(tp_v2+fp_v2):.3f}  recall: {tp_v2/(tp_v2+fn_v2):.3f}", flush=True)
    print("NOTE: this re-check is partially in-sample (503 of the FPs were used as training negatives) -- ", flush=True)
    print("expected to look better almost by construction. True test is whether recall holds and whether it", flush=True)
    print("generalizes on val (separate check, not run here).", flush=True)

    train_polar.to_csv("outputs/reinfer_probs/train_polar_fp_detector_scores_v2_hardneg.csv", index=False)
    print("\nSaved outputs/reinfer_probs/train_polar_fp_detector_scores_v2_hardneg.csv", flush=True)


if __name__ == "__main__":
    main()
