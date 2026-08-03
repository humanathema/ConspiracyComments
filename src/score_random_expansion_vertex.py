"""score_boundary_candidates_vertex.py

Scores the 5,000 boundary-confidence unlabeled candidates (from
boundary_confidence_selection.py's Kaggle kernel, real round2-model
inference, entity_key-filtered to exclude the "merged_*" aggregate rows)
via Vertex AI instead of the kaggle_benchmarks proxy -- rerouted
2026-08-02 per Nash's direction, now that a budgeted, buffered GCP
project (tobiasnash-vertex-frontier, hard-stop budget in place) exists
specifically for this. Replaces score_boundary_candidates_overnight.py's
kaggle_benchmarks path entirely (that script's quota-wait-retry loop
never got past row 1 all night).

Same prompt/scoring convention as every other frontier-judge script
tonight (continuous -1.0 to +1.0 stance strength). Auth via Application
Default Credentials (gcloud auth application-default login).

FIX 2026-08-02 (a): gemini-3.5-flash on Vertex defaults to "thinking"
mode -- confirmed via usage_metadata showing 450 hidden
thoughts_token_count against only 54 visible output tokens on a trivial
test call. Fixed with thinking_config=ThinkingConfig(thinking_budget=0).

FIX 2026-08-02 (b): dropped the "reason" field from the prompt/response
entirely (score-only) -- output tokens are billed at 6x the input rate
($9/M vs $1.50/M), so cutting ~90 output tokens/call to ~2 roughly halves
total cost on top of the thinking fix. Traded away per-row audit text
for this batch (acceptable here since it's feeding training-set
expansion, not a quality-check queue Nash reviews row by row).

FIX 2026-08-02 (c): switched from a serial loop with an artificial
0.5s/call delay to a concurrent thread pool with no delay -- this is a
billed, paid endpoint now (not the free tier's RPM/RPD caps), each call
is I/O-bound (waiting on network/API round-trip, not local CPU), and
per-call latency turned out to be dominated by fixed prefill+routing
overhead rather than output size, so concurrency is the real lever left
for wall-clock time. Resumability changed from positional (row index)
to identity-based (comment_id+entity_key), since concurrent completion
order isn't the input order -- needed to not lose the 50 rows already
scored by the old serial run.

Input: data/processed/boundary_candidates.csv (5,000 rows)
Output: data/processed/boundary_candidates_frontier_scored.parquet
"""
import argparse
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials

PROJECT = "tobiasnash-vertex-frontier"  # switched BACK 2026-08-02 night: the
# nashpncc-vertex-frontier project (switched to for budget-safety reasons)
# turned out to have no real quota for gemini-3.5-flash specifically --
# static quota tables look identical between the two projects, but this one
# empirically lets calls through and the other doesn't (likely an
# account-age/trust factor Google doesn't expose in the quota API). Belongs
# to contact@tobiasnash.co.nz, real billing, NO hard stop yet -- a $500
# budget cap is being set up separately, watch spend until it's confirmed live.
ACCOUNT = "contact@tobiasnash.co.nz"  # tobiasnashpncc@gmail.com has no IAM
# access to this project at all -- must build credentials for this specific
# account explicitly rather than relying on the machine's default ADC
LOCATION = "global"  # gemini-3.5-flash 404s on region-pinned endpoints (tried
# us-central1/us-east1/us-east5/europe-west1), only available via global as
# of this project's current rollout -- confirmed empirically, not documented
INPUT_PATH = "data/processed/random_expansion_candidates.csv"
OUT_PATH = "data/processed/random_expansion_candidates_frontier_scored.parquet"
MODEL_NAME = "gemini-3.5-flash"
CHECKPOINT_EVERY = 50
MAX_WORKERS = 15  # conservative starting point -- this project's real Vertex
# QPS ceiling isn't known yet; ramp up only after confirming this doesn't 429

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

Respond with ONLY the numeric score, nothing else -- no JSON, no words, no explanation. Example valid responses: "-0.7" or "0.3" or "1.0"
"""

SCORE_RE = re.compile(r'-?\d*\.?\d+')

_thread_local = threading.local()


def get_client():
    if not hasattr(_thread_local, "client"):
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token", f"--account={ACCOUNT}"]
        ).decode().strip()
        creds = Credentials(token=token)
        _thread_local.client = genai.Client(
            vertexai=True, project=PROJECT, location=LOCATION, credentials=creds
        )
    return _thread_local.client


def parse_response(raw):
    try:
        m = SCORE_RE.search(raw.strip())
        score = float(m.group(0))
        return max(-1.0, min(1.0, score))
    except Exception:
        return None


def score_one(row):
    entity = row["entity_key"]
    prompt = PROMPT_TEMPLATE.format(entity=entity, text=row["text"])
    client = get_client()

    score = None
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            score = parse_response(resp.text)
            break
        except Exception as e:
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                time.sleep(10 * (attempt + 1))
                continue
            break

    return {
        "comment_id": row["comment_id"], "entity_key": entity, "text": row["text"],
        "margin": row["margin"], "frontier_score": score,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    args = parser.parse_args()

    rows = pd.read_csv(INPUT_PATH)
    if args.limit:
        rows = rows.head(args.limit).copy()

    done_keys = set()
    results = []
    if os.path.exists(OUT_PATH) and not args.limit:
        done = pd.read_parquet(OUT_PATH)
        # only successfully-scored rows count as "done" -- a null score means
        # the call failed, and should be retried on rerun, not silently kept
        # as a permanent gap (found the hard way: 132/5000 failed on the
        # first pass, all needed a second attempt, not exclusion).
        succeeded = done[done["frontier_score"].notna()]
        failed = done[done["frontier_score"].isna()]
        done_keys = set(zip(succeeded["comment_id"], succeeded["entity_key"]))
        results = succeeded.to_dict("records")
        print(f"Resuming: {len(succeeded)} rows already scored, retrying {len(failed)} previously-failed rows.", flush=True)

    todo = [r for _, r in rows.iterrows() if (r["comment_id"], r["entity_key"]) not in done_keys]
    print(f"Scoring {len(todo)} remaining of {len(rows)} rows via Vertex AI "
          f"({MODEL_NAME}, project={PROJECT}, {args.workers} concurrent workers)", flush=True)

    completed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(score_one, row) for row in todo]
        for fut in as_completed(futures):
            results.append(fut.result())
            completed += 1
            if completed % CHECKPOINT_EVERY == 0 or completed == len(todo):
                pd.DataFrame(results).to_parquet(OUT_PATH, index=False)
                n_valid = sum(1 for r in results if r["frontier_score"] is not None)
                print(f"  {len(results)}/{len(rows)} total scored ({n_valid} valid), checkpointed", flush=True)

    out = pd.DataFrame(results)
    valid = out[out["frontier_score"].notna()]
    print(f"\nDone. {len(valid)}/{len(out)} valid scores.", flush=True)


if __name__ == "__main__":
    main()
