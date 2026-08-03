"""score_val_gap_frontier.py

Scores the 618 bigval val rows that lack a frontier-judge score --
needed to redo the cascade threshold sweep (simulate_cascade_validation.py)
on the real 680-row val instead of the stale 212-row one. Only 61 of the
original 212 frontier-scored rows survived into the new val after the
bigval re-split (the rest became eligible for train, by design); the
other 618 were never scored.

Same prompt/scoring convention as score_boundary_candidates_vertex.py:
continuous -1.0 to +1.0 stance strength, thinking disabled, score-only
output (score-only cuts output tokens from ~90 to ~2, most of the cost
saving at $9/M output vs $1.50/M input). Keyed by text (this file has no
id column, matching the convention used throughout this project for
stance_classifier_training_data.parquet).

Input: data/processed/val_rows_needing_frontier_scores.csv (618 rows)
Output: data/processed/val_gap_frontier_scored.parquet
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

PROJECT = "tobiasnash-vertex-frontier"
ACCOUNT = "contact@tobiasnash.co.nz"
LOCATION = "global"
INPUT_PATH = "data/processed/val_rows_needing_frontier_scores.csv"
OUT_PATH = "data/processed/val_gap_frontier_scored.parquet"
MODEL_NAME = "gemini-3.5-flash"
CHECKPOINT_EVERY = 50
MAX_WORKERS = 15

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
    entity = row["target_entity"] if isinstance(row["target_entity"], str) and row["target_entity"].strip() else "the subject of this comment"
    prompt = PROMPT_TEMPLATE.format(entity=entity, text=row["text"])
    client = get_client()

    score = None
    fail_reason = None
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
            # Diagnose before touching resp.text -- the SDK's .text accessor
            # raises when there's no valid Part (e.g. a safety block), which
            # would otherwise land in the except branch below with no detail.
            block_reason = None
            finish_reason = None
            safety_ratings = None
            try:
                pf = getattr(resp, "prompt_feedback", None)
                if pf is not None:
                    block_reason = str(getattr(pf, "block_reason", None))
                cands = getattr(resp, "candidates", None) or []
                if cands:
                    finish_reason = str(getattr(cands[0], "finish_reason", None))
                    sr = getattr(cands[0], "safety_ratings", None)
                    if sr:
                        safety_ratings = ";".join(f"{getattr(r,'category',None)}={getattr(r,'probability',None)}" for r in sr)
            except Exception:
                pass

            try:
                score = parse_response(resp.text)
            except Exception as text_exc:
                fail_reason = f"text_accessor_error: {text_exc} | block_reason={block_reason} | finish_reason={finish_reason} | safety_ratings={safety_ratings}"
                score = None

            if score is None and fail_reason is None:
                fail_reason = f"unparseable_response | block_reason={block_reason} | finish_reason={finish_reason} | safety_ratings={safety_ratings}"
            break
        except Exception as e:
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                time.sleep(10 * (attempt + 1))
                continue
            fail_reason = f"api_exception: {type(e).__name__}: {msg}"
            break

    return {
        "text": row["text"], "target_entity": entity, "true_label": row["label"],
        "frontier_score": score, "fail_reason": fail_reason,
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
        succeeded = done[done["frontier_score"].notna()]
        failed = done[done["frontier_score"].isna()]
        done_keys = set(succeeded["text"])
        results = succeeded.to_dict("records")
        print(f"Resuming: {len(succeeded)} rows already scored, retrying {len(failed)} previously-failed rows.", flush=True)

    todo = [r for _, r in rows.iterrows() if r["text"] not in done_keys]
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
