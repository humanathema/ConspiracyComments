"""score_fp_blindspot_ensemble.py

Applies the saved blind-spot ensemble (outputs/checkpoints/
fp_detector_blindspot_ensemble_v1.joblib) to new rows. This is the second
stage of the recommended two-part pipeline (see
handoff/task_2026-08-23_session_handoff_fp_detector_v4_to_v9_and_ensemble.md):
binconf confidence<0.3 as the primary flag, this ensemble for the
confidence>=0.5 remainder (binconf's structural blind spot).

Requires all three input scores already computed for each row:
  - binconf confidence (already scored for the full 42k, and needed for
    round9 regardless)
  - v8 score (src/score_fp_v8_on_full_train_stanced.py)
  - v9 score (src/train_fp_detector_v9_blindspot.py's checkpoint, scored
    the same way as v8 -- text-only, [ENTITY: X] text input)

No GPU needed for this script itself -- it's a small sklearn model, only
the v8/v9 scores it consumes require GPU inference to produce.

Input: a CSV with columns fp_v8_score, fp_v9_score, confidence (plus
whatever identifying columns you want carried through)
Output: same CSV with an added ensemble_score column
"""
import sys
import joblib
import pandas as pd

MODEL_PATH = "outputs/checkpoints/fp_detector_blindspot_ensemble_v1.joblib"


def main():
    input_path = sys.argv[1]
    output_path = sys.argv[2]

    bundle = joblib.load(MODEL_PATH)
    model = bundle["model"]
    feat_cols = bundle["feature_cols"]
    print(f"Loaded ensemble (trained on {bundle['training_n']} rows, "
          f"{bundle['training_positives']} positives). Features: {feat_cols}", flush=True)

    df = pd.read_csv(input_path)
    missing = [c for c in feat_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Input is missing required columns: {missing}")

    X = df[feat_cols].values
    df["ensemble_score"] = model.predict_proba(X)[:, 1]

    df.to_csv(output_path, index=False)
    print(f"Saved {output_path}", flush=True)
    print(f"Score distribution: mean={df['ensemble_score'].mean():.3f} "
          f"median={df['ensemble_score'].median():.3f} max={df['ensemble_score'].max():.3f}", flush=True)


if __name__ == "__main__":
    main()
