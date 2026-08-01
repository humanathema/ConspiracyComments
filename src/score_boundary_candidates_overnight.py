"""score_boundary_candidates_overnight.py

Unattended overnight orchestration, per conversation 2026-08-02 (Nash's
kaggle_benchmarks AI-proxy budget was showing $0 at 2am, presumably
resets on a different timezone than local -- rather than guess when,
just keep retrying and let it pick up automatically once available):

1. Wait for the boundary-confidence-selection Kaggle kernel to finish,
   pull its output (real round2-model-scored candidates, not the stale
   entity_mentions_cache probabilities -- see that kernel's docstring).
2. Score every candidate via the kaggle_benchmarks frontier judge
   (same prompt/config as score_frontier_continuous_targets.py, already
   fixed for the reasoning-token/quota-reservation bug tonight).
3. On a genuine quota-exceeded error specifically (not other failures),
   wait and retry the SAME row indefinitely rather than skipping it --
   the point is to sit here until budget resets, then just keep going,
   not to give up. Other error types still skip after a few attempts
   (a malformed response isn't going to fix itself by waiting).

Output: data/processed/boundary_candidates_frontier_scored.parquet,
  checkpointed every 25 successes, safe to interrupt/resume.
"""
import json
import os
import re
import subprocess
import time

import pandas as pd

KERNEL_REF = "tobiasnashws/boundary-confidence-selection"
KERNEL_OUTPUT_DIR = "/tmp/boundary_candidates_kernel_output"
CANDIDATES_PATH = "data/processed/boundary_candidates.csv"
OUT_PATH = "data/processed/boundary_candidates_frontier_scored.parquet"
ENV_FILE = "/tmp/kbench_boundary_overnight.env"
MODEL_NAME = "google/gemini-3.5-flash"
CHECKPOINT_EVERY = 25
REAUTH_EVERY_SECONDS = 45 * 60
QUOTA_RETRY_WAIT_SECONDS = 20 * 60  # wait 20 min and retry the same row on quota errors
KAGGLE_CLI = "/Users/nash/miniforge3/bin/kaggle"

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


def wait_for_kernel():
    if os.path.exists(CANDIDATES_PATH):
        print(f"{CANDIDATES_PATH} already exists locally, skipping kernel wait.", flush=True)
        return
    print(f"Waiting for kernel {KERNEL_REF} to complete...", flush=True)
    while True:
        result = subprocess.run([KAGGLE_CLI, "kernels", "status", KERNEL_REF], capture_output=True, text=True)
        status = result.stdout.strip()
        print(f"  {status}", flush=True)
        if "COMPLETE" in status:
            break
        if "ERROR" in status:
            raise RuntimeError(f"Selection kernel failed: {status}")
        time.sleep(60)

    print("Kernel complete, downloading output...", flush=True)
    subprocess.run([KAGGLE_CLI, "kernels", "output", KERNEL_REF, "-p", KERNEL_OUTPUT_DIR], check=True)
    csv_path = os.path.join(KERNEL_OUTPUT_DIR, "boundary_candidates.csv")
    os.makedirs(os.path.dirname(CANDIDATES_PATH), exist_ok=True)
    pd.read_csv(csv_path).to_csv(CANDIDATES_PATH, index=False)
    print(f"Saved candidates to {CANDIDATES_PATH}", flush=True)


def get_env():
    os.environ.pop("MODEL_PROXY_URL", None)
    os.environ.pop("MODEL_PROXY_API_KEY", None)
    result = subprocess.run(
        [KAGGLE_CLI, "benchmarks", "auth", "-y", "--env-file", ENV_FILE],
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
    wait_for_kernel()

    rows = pd.read_csv(CANDIDATES_PATH)
    print(f"Scoring {len(rows)} boundary-confidence candidates", flush=True)

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
        row = rows.iloc[i]
        entity = row["entity_key"]
        prompt = PROMPT_TEMPLATE.format(entity=entity, text=row["text"])

        score, reason = None, None
        while True:
            if time.time() - last_auth > REAUTH_EVERY_SECONDS:
                print("  refreshing proxy auth...", flush=True)
                last_auth = get_env()
                model = load_model(MODEL_NAME)
            try:
                raw = model.prompt(prompt, reasoning="none", extra_api_params={"max_tokens": 150})
                score, reason = parse_response(raw)
                break
            except Exception as e:
                msg = str(e)
                if "quota" in msg.lower() or "PermissionDenied" in msg or "exceeds your available" in msg:
                    print(f"  [{i+1}/{len(rows)}] quota exhausted, waiting {QUOTA_RETRY_WAIT_SECONDS//60} min and retrying this row...", flush=True)
                    time.sleep(QUOTA_RETRY_WAIT_SECONDS)
                    continue
                score, reason = None, f"call_error: {type(e).__name__}: {e}"
                break

        results.append({
            "comment_id": row["comment_id"], "entity_key": entity, "text": row["text"],
            "margin": row["margin"], "frontier_score": score, "frontier_reason": reason,
        })

        if (i + 1) % CHECKPOINT_EVERY == 0 or (i + 1) == len(rows):
            pd.DataFrame(results).to_parquet(OUT_PATH, index=False)
            n_valid = sum(1 for r in results if r["frontier_score"] is not None)
            print(f"  {i + 1}/{len(rows)} processed ({n_valid} valid), checkpointed", flush=True)

    out = pd.DataFrame(results)
    valid = out[out["frontier_score"].notna()]
    print(f"\nDone. {len(valid)}/{len(out)} valid scores.", flush=True)


if __name__ == "__main__":
    main()
