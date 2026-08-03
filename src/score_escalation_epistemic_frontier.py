"""score_escalation_epistemic_frontier.py

The final rung of the escalation ladder, flagged "not yet done" since
2026-08-01: the 50 "epistemic" rows (thread context measurably improved
the classifier's own confidence, confirming more information could
plausibly resolve them -- the aleatoric/no-context rows go to direct
human review instead, since more automated escalation won't help those)
finally get the actual frontier-judge call, with context baked into the
prompt this time.

Same scoring convention/pricing as every other frontier script tonight
(continuous -1.0 to +1.0, thinking disabled, score-only output). Only
difference: the prompt includes context_text (parent comment + original
post, already gathered by the original escalation-context-check kernel)
alongside the comment itself.

Input: data/processed/escalation_epistemic_needs_frontier.csv (50 rows)
Output: data/processed/escalation_epistemic_frontier_scored.parquet
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
INPUT_PATH = "data/processed/escalation_epistemic_needs_frontier.csv"
OUT_PATH = "data/processed/escalation_epistemic_frontier_scored.parquet"
MODEL_NAME = "gemini-3.5-flash"
CHECKPOINT_EVERY = 25
MAX_WORKERS = 15

PROMPT_TEMPLATE = """You are scoring a comment's STANCE STRENGTH toward a specific entity, for a research project on epistemic credibility in online discussion.

Entity: "{entity}"

Thread context (original post and/or parent comment, for background only -- score the COMMENT below, not the context):
\"\"\"{context}\"\"\"

Comment text (this is what you are scoring):
\"\"\"{text}\"\"\"

Score how strongly hostile or endorsing the COMMENT is toward "{entity}", using the thread context to help resolve ambiguity where relevant, on a continuous scale:
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
    context = row["context_text"] if isinstance(row["context_text"], str) and row["context_text"].strip() else "(no context available)"
    prompt = PROMPT_TEMPLATE.format(entity=entity, context=context[:3000], text=row["text"])
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
        "id": row["id"], "text": row["text"], "target_entity": entity,
        "current_label": row["label"], "frontier_score_with_context": score,
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
        succeeded = done[done["frontier_score_with_context"].notna()]
        failed = done[done["frontier_score_with_context"].isna()]
        done_keys = set(succeeded["id"])
        results = succeeded.to_dict("records")
        print(f"Resuming: {len(succeeded)} rows already scored, retrying {len(failed)} previously-failed rows.", flush=True)

    todo = [r for _, r in rows.iterrows() if r["id"] not in done_keys]
    print(f"Scoring {len(todo)} remaining of {len(rows)} rows via Vertex AI "
          f"({MODEL_NAME}, project={PROJECT}, {args.workers} concurrent workers, WITH context)", flush=True)

    completed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(score_one, row) for row in todo]
        for fut in as_completed(futures):
            results.append(fut.result())
            completed += 1
            if completed % CHECKPOINT_EVERY == 0 or completed == len(todo):
                pd.DataFrame(results).to_parquet(OUT_PATH, index=False)
                n_valid = sum(1 for r in results if r["frontier_score_with_context"] is not None)
                print(f"  {len(results)}/{len(rows)} total scored ({n_valid} valid), checkpointed", flush=True)

    out = pd.DataFrame(results)
    valid = out[out["frontier_score_with_context"].notna()]
    print(f"\nDone. {len(valid)}/{len(out)} valid scores.", flush=True)


if __name__ == "__main__":
    main()
