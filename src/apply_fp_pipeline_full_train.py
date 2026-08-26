"""apply_fp_pipeline_full_train.py

Applies the recommended two-part FP-detector pipeline (see
handoff/task_2026-08-23_session_handoff_fp_detector_v4_to_v9_and_ensemble.md
section 8) to the full 32,607-row currently-stanced-labeled train
population -- the first time this has been run at that scale (prior work
was validated only on the 288/274-row ground-truth sets).

Pipeline:
  1. binconf confidence < 0.3 -> flagged directly (44.4pct precision on
     the 288-row ground truth, per fp_detector_final_synthesis... in
     data/experiment_log.jsonl).
  2. binconf confidence >= 0.5 -> scored with the blind-spot ensemble
     (fp_detector_blindspot_ensemble_v1.joblib, features fp_v8_score,
     fp_v9_score, confidence). Recommended operating thresholds from the
     handoff: 0.3 for higher precision (~41pct) / lower recall, 0.15 for
     more coverage (~26pct) / higher recall.
  3. confidence in [0.3, 0.5) -- NOT covered by either arm of the
     documented pipeline. Left unflagged and reported separately; this is
     an honest gap, not an oversight to paper over.

Input: outputs/reinfer_probs/full_train_fp_v8_stanced_scores.csv (has
  fp_v8_score) joined row-for-row with
  outputs/reinfer_probs/full_train_fp_v9_stanced_scores.csv (has
  fp_v9_score) -- verified row-aligned (identical text/confidence order)
  before this script was written.
Output: outputs/reinfer_probs/full_train_fp_pipeline_flags.csv
"""
import joblib
import pandas as pd

V8_PATH = "outputs/reinfer_probs/full_train_fp_v8_stanced_scores.csv"
V9_PATH = "outputs/reinfer_probs/full_train_fp_v9_stanced_scores.csv"
ENSEMBLE_PATH = "outputs/checkpoints/fp_detector_blindspot_ensemble_v1.joblib"
OUT_PATH = "outputs/reinfer_probs/full_train_fp_pipeline_flags.csv"

BINCONF_LOW_THRESHOLD = 0.3
BLINDSPOT_THRESHOLD = 0.5
ENSEMBLE_FLAG_THRESHOLD = 0.3  # higher-precision operating point from the handoff


def main():
    v8 = pd.read_csv(V8_PATH)
    v9 = pd.read_csv(V9_PATH)
    assert (v8["text"].astype(str) == v9["text"].astype(str)).all(), "row misalignment"
    assert (v8["confidence"] == v9["confidence"]).all(), "row misalignment"

    df = v8.copy()
    df["fp_v9_score"] = v9["fp_v9_score"]

    n = len(df)
    low_conf = df["confidence"] < BINCONF_LOW_THRESHOLD
    blind_spot = df["confidence"] >= BLINDSPOT_THRESHOLD
    gap = ~low_conf & ~blind_spot

    print(f"Population: {n}", flush=True)
    print(f"  confidence<0.3 (binconf direct flag arm): {low_conf.sum()} ({low_conf.sum()/n:.3f})", flush=True)
    print(f"  confidence>=0.5 (blind-spot ensemble arm): {blind_spot.sum()} ({blind_spot.sum()/n:.3f})", flush=True)
    print(f"  confidence in [0.3,0.5) (NOT covered by pipeline): {gap.sum()} ({gap.sum()/n:.3f})", flush=True)

    df["flag_binconf_low"] = low_conf

    bundle = joblib.load(ENSEMBLE_PATH)
    model = bundle["model"]
    feat_cols = bundle["feature_cols"]
    df["ensemble_score"] = float("nan")
    X = df.loc[blind_spot, feat_cols].values
    df.loc[blind_spot, "ensemble_score"] = model.predict_proba(X)[:, 1]
    df["flag_ensemble"] = blind_spot & (df["ensemble_score"] >= ENSEMBLE_FLAG_THRESHOLD)

    df["flag_pipeline_final"] = df["flag_binconf_low"] | df["flag_ensemble"].fillna(False)

    print(f"\n=== Final flag counts ===", flush=True)
    print(f"  binconf<0.3 direct flags: {df['flag_binconf_low'].sum()}", flush=True)
    print(f"  ensemble flags (threshold={ENSEMBLE_FLAG_THRESHOLD}) within blind spot: {df['flag_ensemble'].sum()}", flush=True)
    print(f"  TOTAL flagged (either arm): {df['flag_pipeline_final'].sum()} ({df['flag_pipeline_final'].sum()/n:.3f} of population)", flush=True)
    print(f"  Uncovered gap population (confidence 0.3-0.5, never flagged by design): {gap.sum()}", flush=True)

    for t in [0.15, 0.2, 0.3, 0.4, 0.5]:
        c = (blind_spot & (df["ensemble_score"] >= t)).sum()
        print(f"  ensemble threshold={t}: {c} flagged within blind spot", flush=True)

    df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
