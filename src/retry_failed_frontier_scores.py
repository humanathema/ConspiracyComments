"""retry_failed_frontier_scores.py

Retries only the rows that failed in score_frontier_continuous_targets.py's
first pass (760/2047, mostly AuthenticationError from a broken 45-min
token-refresh cycle across tonight's several session interruptions, not
genuine rate-limiting -- see conversation 2026-08-01). Re-authenticates
fresh at start rather than trusting whatever credential state survived.

Updates stance_frontier_continuous_targets.parquet IN PLACE for rows
that succeed this time -- does not touch the 1,287 already-valid rows.
Checkpoints every CHECKPOINT_EVERY successes so a repeat interruption
doesn't lose progress, same as the original script.

Usage:
    python src/retry_failed_frontier_scores.py --limit 20   # smoke test
    python src/retry_failed_frontier_scores.py              # retry all failures
"""
import argparse
import json
import os
import re
import subprocess
import time

import pandas as pd

TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
SCORES_PATH = "data/processed/stance_frontier_continuous_targets.parquet"
ENV_FILE = "/tmp/kbench_continuous_scoring_retry.env"
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--model", type=str, default=MODEL_NAME)
    args = parser.parse_args()

    scores = pd.read_parquet(SCORES_PATH)
    train_data = pd.read_parquet(TRAINING_DATA_PATH)

    failed_mask = scores["frontier_score"].isna()
    failed = scores[failed_mask].copy()
    print(f"{len(failed)} rows need retry (of {len(scores)} total)", flush=True)

    # Re-attach target_entity from the training data (not stored in the
    # checkpoint file) by matching on text.
    entity_lookup = train_data.drop_duplicates(subset="text").set_index("text")["target_entity"]
    failed["target_entity"] = failed["text"].map(entity_lookup)

    if args.limit:
        failed = failed.head(args.limit)
    print(f"Retrying {len(failed)} rows with {args.model}", flush=True)

    last_auth = get_env()
    os.environ["LLM_DEFAULT"] = args.model
    from kaggle_benchmarks.kaggle.models import load_model
    model = load_model(args.model)

    n_fixed = 0
    since_checkpoint = 0
    for idx, row in failed.iterrows():
        if time.time() - last_auth > REAUTH_EVERY_SECONDS:
            print("  refreshing proxy auth...", flush=True)
            last_auth = get_env()
            model = load_model(args.model)

        entity = row["target_entity"] if isinstance(row.get("target_entity"), str) and row["target_entity"].strip() else "the entity mentioned"
        prompt = PROMPT_TEMPLATE.format(entity=entity, text=row["text"])
        try:
            # Response is one short JSON object ({"score": ..., "reason": "..."}) --
            # without an explicit cap, the proxy reserves quota against its
            # default max_output_tokens ceiling per call (~$0.59 estimated,
            # confirmed via the PermissionDeniedError this was failing with).
            # Truncation at low caps turned out to be hidden reasoning tokens
            # (gemini-3.5-flash spends tokens on internal reasoning before any
            # visible output, counted against max_tokens) -- reasoning="none"
            # turns that off so a small visible-output cap is actually enough.
            raw = model.prompt(prompt, reasoning="none", extra_api_params={"max_tokens": 150})
            score, reason = parse_response(raw)
        except Exception as e:
            score, reason = None, f"call_error: {type(e).__name__}: {e}"

        if score is not None:
            scores.loc[idx, "frontier_score"] = score
            scores.loc[idx, "frontier_reason"] = reason
            n_fixed += 1
            since_checkpoint += 1
        else:
            scores.loc[idx, "frontier_reason"] = reason  # update the error reason at least

        if since_checkpoint >= CHECKPOINT_EVERY:
            scores.to_parquet(SCORES_PATH, index=False)
            print(f"  {n_fixed} fixed so far, checkpointed", flush=True)
            since_checkpoint = 0

    scores.to_parquet(SCORES_PATH, index=False)
    still_failed = scores["frontier_score"].isna().sum()
    print(f"\nDone. {n_fixed}/{len(failed)} retried rows now have a score.", flush=True)
    print(f"Overall: {len(scores) - still_failed}/{len(scores)} valid, {still_failed} still failed.", flush=True)


if __name__ == "__main__":
    main()
