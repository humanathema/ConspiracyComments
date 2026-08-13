"""Train two-stage ModernBERT ensemble — TAG=r7v1

Runs both arms (baseline + redesign) via train_kaggle.py.
Copies model weights from /tmp/ to /kaggle/working/ after each arm
so they survive as kernel output.
"""
import os, sys, subprocess, shutil

subprocess.run([sys.executable, "-m", "pip", "install", "-q",
    "transformers", "scikit-learn", "accelerate"], check=True)

import shutil

TRAIN_PY = "/kaggle/input/stance-r8-training-splits/train_kaggle.py"
DATA_FILE = "/kaggle/input/stance-r8-training-splits/stance_classifier_training_data_round7_bigval_split.parquet"
OUT = "/kaggle/working"
TAG = "r7v1"

os.makedirs(OUT, exist_ok=True)

env = {
    **os.environ,
    "MODEL_NAME": "answerdotai/ModernBERT-large",
    "MAX_LENGTH": "768",
    "BATCH_SIZE": "4",
    "NUM_EPOCHS": "2",
    "GRAD_CKPT": "1",
    "TAG": TAG,
    "INPUT_FILE": DATA_FILE,
    "CUDA_VISIBLE_DEVICES": "0",
}

print(f"=== Training TAG={TAG} ===")
result = subprocess.run([sys.executable, TRAIN_PY], env=env, check=True)

# Copy model weights to persistent output
for arm in ["baseline", "redesign"]:
    for stage in ["stage1", "stage2"]:
        src_map = {"baseline": {"stage1": "stage1_baseline", "stage2": "stage2_baseline"},
                   "redesign": {"stage1": "stage1_redesign", "stage2": "stage2_redesign"}}
        src = f"/tmp/stance_{src_map[arm][stage]}"
        dst = f"{OUT}/{TAG}_{arm}/{stage}"
        if os.path.exists(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"Saved {src} -> {dst}")
        else:
            print(f"WARNING: {src} not found")

print(f"Done. Outputs in {OUT}/")
import os
for root, dirs, files in os.walk(OUT):
    for f in files:
        path = os.path.join(root, f)
        print(f"  {path} ({os.path.getsize(path)//1024}KB)")
