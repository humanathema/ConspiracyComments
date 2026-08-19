"""
Futureproof sklearn .joblib checkpoints against version drift -- cheap fix,
NOT retraining. Loads each checkpoint once (works today, just warns via
sklearn's InconsistentVersionWarning), then immediately re-saves it under
the current environment's library versions. The model's actual learned
parameters are untouched; this only updates the pickle's internal version
metadata so future loads under this same (or newer-compatible) sklearn
don't warn or risk silent behavior drift.

Backs up the original file (.bak) before overwriting, never deletes it.

Run under the canonical env: /Users/nash/miniforge3/bin/python3

Usage:
    python3 tools/repickle_sklearn_checkpoints.py                # dry-run, lists what it would do
    python3 tools/repickle_sklearn_checkpoints.py --apply         # actually re-saves
"""
import argparse
import shutil
import sys
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

CHECKPOINTS = [
    "data/processed/stance_classifier_2stage_pooled.joblib",
    "data/processed/staged_pipeline_models.joblib",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually re-save (default is dry-run)")
    args = ap.parse_args()

    try:
        import joblib
        import sklearn
    except ImportError as e:
        sys.exit(
            f"Missing package: {e}. Run this under the canonical env: "
            "/Users/nash/miniforge3/bin/python3 tools/repickle_sklearn_checkpoints.py"
        )

    print(f"Current sklearn version: {sklearn.__version__}\n")

    for rel_path in CHECKPOINTS:
        path = REPO_ROOT / rel_path
        if not path.exists():
            print(f"SKIP (not found): {rel_path}")
            continue

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            obj = joblib.load(path)
            n_warnings = len(w)

        print(f"{rel_path}: loaded OK, {n_warnings} version warning(s) on load.")

        if not args.apply:
            print("  (dry-run -- pass --apply to actually re-save)")
            continue

        backup_path = path.with_suffix(path.suffix + ".bak")
        if not backup_path.exists():
            shutil.copy2(path, backup_path)
            print(f"  backed up original to {backup_path.relative_to(REPO_ROOT)}")
        else:
            print(f"  backup already exists at {backup_path.relative_to(REPO_ROOT)}, not overwriting it")

        joblib.dump(obj, path)

        with warnings.catch_warnings(record=True) as w2:
            warnings.simplefilter("always")
            joblib.load(path)
            print(f"  re-saved under sklearn {sklearn.__version__} -- reload now gives {len(w2)} warning(s)")

    print("\nDone.")


if __name__ == "__main__":
    main()
