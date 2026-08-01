"""score_frontier_continuous_targets.py

Generates genuine continuous stance-strength targets (-1.0 to +1.0) for
every stage-2-eligible training row (currently labeled hostile or
endorsement, human + AI-silver), using the frontier model proxy
(kaggle_benchmarks, tobiasnash account) instead of forcing every row to
a hard -1/+1 -- this is the real version of Nash's "regression trained
on genuinely continuous/confidence-based targets" idea (2026-08-01),
which arm 4's ordinal ablation did NOT actually test (that arm used a
continuous OUTPUT but hard ±1 TRAINING targets, so it never tested
whether soft targets themselves help).

Deliberately an INDEPENDENT model's judgment, not the production
classifier's own confidence -- self-distillation would just replicate
whatever biases the existing classifier already has (kappa 0.34-0.41,
confirmed independently unreliable earlier tonight). Blind by
construction: the model is never shown the recorded label, matching the
same anchoring-avoidance design as audit_entity_stance_frontier_judge.py.

Input: data/processed/stance_classifier_training_data.parquet (train
  split, label in {hostile, endorsement})
Output: data/processed/stance_frontier_continuous_targets.parquet
  (text, current_label, frontier_score, frontier_reason), checkpointed
  incrementally every CHECKPOINT_EVERY rows.

Usage:
    python src/score_frontier_continuous_targets.py --limit 20   # smoke test
    python src/score_frontier_continuous_targets.py              # full run
"""
import argparse
import json
import os
import re
import subprocess
import time

import pandas as pd

TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
OUT_PATH = "data/processed/stance_frontier_continuous_targets.parquet"
ENV_FILE = "/tmp/kbench_continuous_scoring.env"
MODEL_NAME = "google/gemini-3.5-flash"
CHECKPOINT_EVERY = 25
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

Respond with ONLY a JSON object, no other text: {{"score": <float from -1.0 to 1.0>, "reason": "one short sentence"}}
"""


def get_env():
    os.environ.pop("MODEL_PROXY_URL", None)
    os.environ.pop("MODEL_PROXY_API_KEY", None)
    subprocess.run(
        ["/Users/nash/miniforge3/bin/kaggle", "benchmarks", "auth", "-y", "--env-file", ENV_FILE],
        env={**os.environ, "KAGGLE_API_TOKEN": os.path.expanduser("~/.kaggle/access_token0")},
        check=True, capture_output=True, text=True,
    )
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                env[k] = v
    os.environ["MODEL_PROXY_URL"] = env["MODEL_PROXY_URL"]
    os.environ["MODEL_PROXY_API_KEY"] = env["MODEL_PROXY_API_KEY"]
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--model", type=str, default=MODEL_NAME)
    args = parser.parse_args()

    df = pd.read_parquet(TRAINING_DATA_PATH)
    train = df[df["split"] == "train"]
    rows = train[train["label"] != "other"].copy().reset_index(drop=True)
    if args.limit:
        rows = rows.head(args.limit).copy()
    print(f"Scoring {len(rows)} stage2-eligible rows with {args.model} (blind, continuous)", flush=True)

    last_auth = get_env()
    os.environ["LLM_DEFAULT"] = args.model
    from kaggle_benchmarks.kaggle.models import load_model
    model = load_model(args.model)

    if os.path.exists(OUT_PATH) and not args.limit:
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
            model = load_model(args.model)

        row = rows.iloc[i]
        entity = row["target_entity"] if isinstance(row.get("target_entity"), str) and row["target_entity"].strip() else "the entity mentioned"
        prompt = PROMPT_TEMPLATE.format(entity=entity, text=row["text"])
        try:
            raw = model.prompt(prompt)
            score, reason = parse_response(raw)
        except Exception as e:
            score, reason = None, f"call_error: {type(e).__name__}: {e}"

        results.append({
            "text": row["text"],
            "current_label": row["label"],
            "frontier_score": score,
            "frontier_reason": reason,
        })

        if (i + 1) % CHECKPOINT_EVERY == 0 or (i + 1) == len(rows):
            pd.DataFrame(results).to_parquet(OUT_PATH, index=False)
            print(f"  {i + 1}/{len(rows)} scored, checkpointed", flush=True)

    out = pd.DataFrame(results)
    valid = out[out["frontier_score"].notna()]
    print(f"\n{len(valid)}/{len(out)} valid scores", flush=True)
    print("\nMean frontier_score by current_label (sanity check -- hostile should be negative, endorsement positive):", flush=True)
    print(valid.groupby("current_label")["frontier_score"].agg(["mean", "median", "std", "count"]), flush=True)


if __name__ == "__main__":
    main()
