"""score_frontier_val_diagnostic.py

Diagnostic-only companion to score_frontier_continuous_targets.py: scores
the 212 val-split hostile/endorsement rows the frontier judge has NEVER
seen (val is deliberately excluded from frontier scoring, see that
script's docstring -- train/val stay separated the same way any
model's training signal would be). This is the one clean way to check
the frontier judge's own raw accuracy against real held-out human
ground truth, independent of whether the ordinal-v2 distillation
(training a regression head on its train-split scores) worked -- see
conversation 2026-08-01: Nash's hypothesis that the judge itself might
be fine even though the distillation pass underperformed the hard-
target baseline.

NOT used to retrain anything -- purely a correlation/accuracy check.
Uses the reasoning="none" + max_tokens=150 fix confirmed working in
retry_failed_frontier_scores.py (the account's earlier truncation/quota
issue was hidden reasoning tokens eating the budget, not the actual
prompt).

Output: data/processed/stance_frontier_val_diagnostic.parquet
  (text, true_label, frontier_score, frontier_reason)
"""
import json
import os
import re
import subprocess
import time

import pandas as pd

TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
OUT_PATH = "data/processed/stance_frontier_val_diagnostic.parquet"
ENV_FILE = "/tmp/kbench_val_diagnostic.env"
MODEL_NAME = "google/gemini-3.5-flash"
CHECKPOINT_EVERY = 15
REAUTH_EVERY_SECONDS = 45 * 60

PROMPT_TEMPLATE = """You are scoring a comment's STANCE STRENGTH toward a specific entity, for a research project on epistemic credibility in online discussion.

Entity: "{entity}"

Comment text:
\"\"\"{text}\"\"\"

Score how strongly hostile or endorsing this text is toward "{entity}", on a continuous scale:
  -1.0 = extremely hostile/attacking
  -0.5 = mildly critical or hostile but hedged
   0.0 = no real stance, or perfectly balanced/mixed
  +0.5 = mildly supportive or approving but hedged
  +1.0 = extremely endorsing/supportive
Use the full range, including intermediate values (e.g. -0.7, 0.3, -0.2) where warranted -- do not default to round numbers.

Respond with ONLY a JSON object, no other text, no markdown code fences, no preamble or explanation before or after it: {{"score": <float from -1.0 to 1.0>, "reason": "one short sentence"}}
"""


def get_env():
    os.environ.pop("MODEL_PROXY_URL", None)
    os.environ.pop("MODEL_PROXY_API_KEY", None)
    result = subprocess.run(
        ["/Users/nash/miniforge3/bin/kaggle", "benchmarks", "auth", "-y", "--env-file", ENV_FILE],
        env={**os.environ, "KAGGLE_API_TOKEN": os.path.expanduser("~/.kaggle/access_token0")},
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"benchmarks auth failed: {result.stderr}")
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                env[k] = v
    os.environ["MODEL_PROXY_URL"] = env["MODEL_PROXY_URL"]
    os.environ["MODEL_PROXY_API_KEY"] = env["MODEL_PROXY_API_KEY"]
    print(f"  re-authenticated, proxy token expires {env.get('MODEL_PROXY_EXPIRY_TIME', '?')}", flush=True)
    return time.time()


def parse_response(raw):
    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        obj = json.loads(match.group(0) if match else raw)
        score = float(obj.get("score"))
        score = max(-1.0, min(1.0, score))
        return score, obj.get("reason", "")
    except Exception as e:
        return None, f"{type(e).__name__}: {raw[:200]}"


def main():
    df = pd.read_parquet(TRAINING_DATA_PATH)
    rows = df[(df["split"] == "val") & (df["label"] != "other")].copy().reset_index(drop=True)
    print(f"Scoring {len(rows)} held-out val rows (never seen by the frontier judge before)", flush=True)

    last_auth = get_env()
    os.environ["LLM_DEFAULT"] = MODEL_NAME
    from kaggle_benchmarks.kaggle.models import load_model
    model = load_model(MODEL_NAME)

    if os.path.exists(OUT_PATH):
        done = pd.read_parquet(OUT_PATH)
        print(f"Resuming: {len(done)} rows already scored.", flush=True)
        start_idx = len(done)
        results = done.to_dict("records")
    else:
        start_idx = 0
        results = []

    for i in range(start_idx, len(rows)):
        if time.time() - last_auth > REAUTH_EVERY_SECONDS:
            print("  refreshing proxy auth...", flush=True)
            last_auth = get_env()
            model = load_model(MODEL_NAME)

        row = rows.iloc[i]
        entity = row["target_entity"] if isinstance(row.get("target_entity"), str) and row["target_entity"].strip() else "the entity mentioned"
        prompt = PROMPT_TEMPLATE.format(entity=entity, text=row["text"])
        try:
            raw = model.prompt(prompt, reasoning="none", extra_api_params={"max_tokens": 150})
            score, reason = parse_response(raw)
        except Exception as e:
            score, reason = None, f"call_error: {type(e).__name__}: {e}"

        results.append({
            "text": row["text"],
            "target_entity": entity,
            "true_label": row["label"],
            "frontier_score": score,
            "frontier_reason": reason,
        })

        if (i + 1) % CHECKPOINT_EVERY == 0 or (i + 1) == len(rows):
            pd.DataFrame(results).to_parquet(OUT_PATH, index=False)
            print(f"  {i + 1}/{len(rows)} scored, checkpointed", flush=True)

    out = pd.DataFrame(results)
    valid = out[out["frontier_score"].notna()]
    print(f"\n{len(valid)}/{len(out)} valid scores", flush=True)
    print("\nMean frontier_score by TRUE held-out label:", flush=True)
    print(valid.groupby("true_label")["frontier_score"].agg(["mean", "median", "std", "count"]), flush=True)

    thresholded = valid.copy()
    thresholded["pred"] = thresholded["frontier_score"].apply(lambda s: "endorsement" if s >= 0 else "hostile")
    acc = (thresholded["pred"] == thresholded["true_label"]).mean()
    from sklearn.metrics import cohen_kappa_score
    kappa = cohen_kappa_score(thresholded["true_label"], thresholded["pred"])
    print(f"\nThresholded at 0.0 -- accuracy: {acc:.4f}, kappa: {kappa:.4f}", flush=True)
    print("(reference: round1 trained classifier combined kappa = 0.4667; round2 pending)", flush=True)


if __name__ == "__main__":
    main()
