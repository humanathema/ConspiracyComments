"""score_frontier_anchored_variance_test.py

Quick before/after check (not a full rescore) of whether adding fixed
calibration anchors to the frontier-judge prompt reduces the per-example
score noise found in the ordinal-v2 distillation diagnostic (std ~0.45
for hostile, ~0.38 for endorsement, within the SAME true label -- see
conversation 2026-08-01). Hypothesis: scoring each comment in total
isolation lets the model's internal sense of "how hostile is -0.9 vs
-0.5" drift call to call; giving it 3 fixed reference examples with
pre-agreed scores in every prompt should tighten that without needing a
second reconciliation pass (which risks compressing genuine severity
differences, not just fixing miscalibration -- deliberately not doing
that yet).

Anchors are synthetic, generic (not drawn from the corpus, not tied to
any real entity) so they calibrate the SCALE without leaking any
particular entity's framing into the judgment.

Samples a fixed set of rows that ALREADY have an original (unanchored)
frontier_score, rescoring the exact same rows so std can be compared
directly, paired, not just on a fresh independent sample.

Output: data/processed/stance_frontier_anchored_test.parquet
  (text, target_entity, true_label, old_score, new_anchored_score, new_reason)
"""
import json
import os
import re
import subprocess
import time

import pandas as pd

TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
SCORES_PATH = "data/processed/stance_frontier_continuous_targets.parquet"
OUT_PATH = "data/processed/stance_frontier_anchored_test.parquet"
ENV_FILE = "/tmp/kbench_anchored_test.env"
MODEL_NAME = "google/gemini-3.5-flash"
CHECKPOINT_EVERY = 15
REAUTH_EVERY_SECONDS = 45 * 60
N_PER_LABEL = 40

ANCHOR_BLOCK = """Before you score, calibrate against these three fixed reference points (use them as your scale, not the actual entity):

Reference A (score -1.0): "This guy is a complete fraud and everyone who still listens to him is an idiot. He's been caught lying so many times it's embarrassing."
Reference B (score 0.0): "He mentioned this in an interview last year, I think it was on a podcast somewhere."
Reference C (score +1.0): "She's been right about this from day one and deserves way more credit than she gets. One of the few people actually worth listening to."

Now score the real comment below using that same scale.
"""

PROMPT_TEMPLATE = ANCHOR_BLOCK + """
You are scoring a comment's STANCE STRENGTH toward a specific entity, for a research project on epistemic credibility in online discussion.

Entity: "{entity}"

Comment text:
\"\"\"{text}\"\"\"

Score how strongly hostile or endorsing this text is toward "{entity}", on a continuous scale:
  -1.0 = extremely hostile/attacking (like Reference A)
  -0.5 = mildly critical or hostile but hedged
   0.0 = no real stance, or perfectly balanced/mixed (like Reference B)
  +0.5 = mildly supportive or approving but hedged
  +1.0 = extremely endorsing/supportive (like Reference C)
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
    base = pd.read_parquet(TRAINING_DATA_PATH)
    scores = pd.read_parquet(SCORES_PATH)
    scores = scores[scores["frontier_score"].notna()].drop_duplicates(subset=["text", "current_label"])

    elig = base[(base["split"] == "train") & (base["label"] != "other")]
    # only unambiguous (non duplicate-text) rows -- avoid the entity-mismatch
    # bug already found and fixed elsewhere this session.
    dup_texts = set(elig[elig.duplicated(subset="text", keep=False)]["text"])
    elig = elig[~elig["text"].isin(dup_texts)]

    merged = elig.merge(
        scores.rename(columns={"current_label": "label"})[["text", "label", "frontier_score"]],
        on=["text", "label"], how="inner",
    )

    sample = pd.concat([
        merged[merged["label"] == "hostile"].sample(n=min(N_PER_LABEL, (merged["label"] == "hostile").sum()), random_state=42),
        merged[merged["label"] == "endorsement"].sample(n=min(N_PER_LABEL, (merged["label"] == "endorsement").sum()), random_state=42),
    ]).reset_index(drop=True)
    print(f"Sampled {len(sample)} rows ({(sample['label']=='hostile').sum()} hostile, {(sample['label']=='endorsement').sum()} endorsement) with existing scores to rescore anchored", flush=True)

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

    for i in range(start_idx, len(sample)):
        if time.time() - last_auth > REAUTH_EVERY_SECONDS:
            print("  refreshing proxy auth...", flush=True)
            last_auth = get_env()
            model = load_model(MODEL_NAME)

        row = sample.iloc[i]
        entity = row["target_entity"] if isinstance(row.get("target_entity"), str) and row["target_entity"].strip() else "the entity mentioned"
        prompt = PROMPT_TEMPLATE.format(entity=entity, text=row["text"])
        try:
            raw = model.prompt(prompt, reasoning="none", extra_api_params={"max_tokens": 200})
            score, reason = parse_response(raw)
        except Exception as e:
            score, reason = None, f"call_error: {type(e).__name__}: {e}"

        results.append({
            "text": row["text"],
            "target_entity": entity,
            "true_label": row["label"],
            "old_score": row["frontier_score"],
            "new_anchored_score": score,
            "new_reason": reason,
        })

        if (i + 1) % CHECKPOINT_EVERY == 0 or (i + 1) == len(sample):
            pd.DataFrame(results).to_parquet(OUT_PATH, index=False)
            print(f"  {i + 1}/{len(sample)} scored, checkpointed", flush=True)

    out = pd.DataFrame(results)
    valid = out[out["new_anchored_score"].notna()]
    print(f"\n{len(valid)}/{len(out)} valid anchored scores", flush=True)

    print("\n=== BEFORE (original, unanchored) ===", flush=True)
    print(valid.groupby("true_label")["old_score"].agg(["mean", "median", "std", "count"]), flush=True)
    print("\n=== AFTER (anchored) ===", flush=True)
    print(valid.groupby("true_label")["new_anchored_score"].agg(["mean", "median", "std", "count"]), flush=True)


if __name__ == "__main__":
    main()
