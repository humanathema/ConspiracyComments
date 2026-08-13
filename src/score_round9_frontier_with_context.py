"""score_round9_frontier_with_context.py

Sends round9 escalation candidates (both the not-yet-strongly-resolved
epistemic rows and the aleatoric rows) to Vertex AI (Gemini) for
hostile/endorsement scoring, WITH the same context (parent comment /
thread ancestor / post title+selftext) that was used in the epistemic vs
aleatoric classification test -- context depth chosen per-row: the depth
that resolved it (epistemic), or the deepest depth reached (aleatoric,
never resolved).

Unlike the original score_escalation_cascade_frontier_gemini.py, this is
NOT forced-choice: the model may mark a row "unsure" instead of picking a
stance, so genuinely ambiguous rows (expected mostly among the aleatoric
set) route to a human HITL queue rather than getting a coin-flip label.

Input: round9_all_for_frontier_with_context.csv (id, text, target_entity, context)
Output: round9_frontier_scored_with_context.csv (id, unsure, score)
"""
import argparse
import os
import threading
import time
import subprocess
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from pydantic import BaseModel

import pandas as pd
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials

socket.setdefaulttimeout(60)

PROJECT = "conspiracycomments-gce"
ACCOUNT = "tobiasnash@gmail.com"
LOCATION = "global"
MODEL_NAME = "gemini-3.5-flash"

INPUT_PATH = "/Users/nash/Projects/ConspiracyComments/data/processed/round9/round9_all_for_frontier_with_context.csv"
OUT_PATH = "/Users/nash/Projects/ConspiracyComments/data/processed/round9/round9_frontier_scored_with_context.csv"
CHECKPOINT_EVERY = 50
MAX_WORKERS = 15
BATCH_SIZE = 10
THINKING_BUDGET = 2048
CONTEXT_TRUNCATE = 1500
TEXT_TRUNCATE = 1500


class StancePrediction(BaseModel):
    id: str
    unsure: bool
    score: Optional[float] = None


class BatchPrediction(BaseModel):
    predictions: list[StancePrediction]


PROMPT_HEADER_JSON = """You are scoring a set of comments for their STANCE toward specific target entities.
Each comment has already been flagged by an automated classifier as plausibly stance-bearing (hostile or
endorsing), but the classifier was NOT confident. You are given the comment's surrounding thread context
(the parent comment, an earlier ancestor in the thread, or the post title/body) to help you judge.

Scale (use ONLY if you can confidently determine a stance, with or without the context):
  -1.0 = extremely hostile/attacking toward the entity
  -0.5 = mildly critical/hostile
  +0.5 = mildly supportive/approving
  +1.0 = extremely endorsing/supportive

Instructions:
- Read the context AND the comment together.
- If you can confidently tell whether the comment is hostile or endorsing toward the entity (even a mild
  lean), set unsure=false and give a score from the scale above (choose from -1.0, -0.5, +0.5, +1.0). Do
  not use 0.0.
- If the comment is genuinely ambiguous, sarcastic in a way you can't resolve, off-topic, a bare
  citation/link-dump with no discernible stance, or you genuinely cannot tell hostile from endorsing even
  with the context, set unsure=true and omit score. Do not guess just to avoid saying unsure -- a wrong
  forced guess is worse than an honest "unsure" here, since unsure rows go to human review.

Items to evaluate:
{comments_block}
"""

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


def score_batch(batch_rows):
    comments_block = "\n".join(
        f"Row ID: {row['id']}\n"
        f"Entity: {row['entity']}\n"
        f"Context: \"\"\"{str(row['context'])[:CONTEXT_TRUNCATE] if row['context'] else '(no context available)'}\"\"\"\n"
        f"Comment: \"\"\"{str(row['text'])[:TEXT_TRUNCATE]}\"\"\"\n---"
        for row in batch_rows
    )
    prompt = PROMPT_HEADER_JSON.format(comments_block=comments_block)
    client = get_client()

    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
                    response_mime_type="application/json",
                    response_schema=BatchPrediction,
                    safety_settings=[
                        types.SafetySetting(
                            category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                            threshold=types.HarmBlockThreshold.BLOCK_NONE,
                        ),
                        types.SafetySetting(
                            category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                            threshold=types.HarmBlockThreshold.BLOCK_NONE,
                        ),
                        types.SafetySetting(
                            category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                            threshold=types.HarmBlockThreshold.BLOCK_NONE,
                        ),
                        types.SafetySetting(
                            category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                            threshold=types.HarmBlockThreshold.BLOCK_NONE,
                        ),
                    ]
                )
            )

            import json
            data = json.loads(resp.text)
            predictions = data.get("predictions", [])

            results = []
            for pred in predictions:
                results.append({
                    "id": pred.get("id"),
                    "unsure": pred.get("unsure", False),
                    "frontier_score": pred.get("score"),
                })
            return results
        except Exception as e:
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg.upper() or "quota" in msg.lower():
                time.sleep(5 * (attempt + 1))
                continue
            print(f"\n[Error scoring batch of size {len(batch_rows)}]: {msg}")
            time.sleep(2)

    return [{"id": r["id"], "unsure": None, "frontier_score": None} for r in batch_rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    candidates = pd.read_csv(INPUT_PATH)
    print(f"Loaded {len(candidates)} rows", flush=True)

    data = []
    for _, row in candidates.iterrows():
        data.append({
            "id": row["id"],
            "text": row["text"],
            "entity": row["target_entity"] if "target_entity" in row else "the subject",
            "context": row["context"] if pd.notna(row.get("context")) else None,
        })

    done_ids = set()
    results = []
    if os.path.exists(OUT_PATH):
        done = pd.read_csv(OUT_PATH)
        if "id" in done.columns:
            done_valid = done[done["unsure"].notna()]
            done_ids = set(done_valid["id"])
            results = done_valid.to_dict("records")
            print(f"Resuming: {len(results)} valid rows already scored", flush=True)

    todo = [r for r in data if r["id"] not in done_ids]
    if args.limit:
        todo = todo[:args.limit]

    print(f"\nScoring {len(todo)} remaining rows in batches of {BATCH_SIZE} via Vertex AI Gemini...", flush=True)
    if len(todo) == 0:
        print("Nothing to do!")
        return

    batches = [todo[i:i + BATCH_SIZE] for i in range(0, len(todo), BATCH_SIZE)]

    completed_batches = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(score_batch, b) for b in batches]

        for fut in as_completed(futures):
            batch_results = fut.result()
            results.extend(batch_results)
            completed_batches += 1

            if completed_batches % (CHECKPOINT_EVERY // BATCH_SIZE + 1) == 0 or completed_batches == len(batches):
                pd.DataFrame(results).to_csv(OUT_PATH, index=False)
                n_valid = sum(1 for r in results if r.get("unsure") is not None)
                print(f"  {len(results)}/{len(data)} total scored ({n_valid} valid), checkpointed", flush=True)

    out = pd.DataFrame(results)
    valid = out[out["unsure"].notna()]
    n_unsure = (valid["unsure"] == True).sum()
    print(f"\nDone. {len(valid)}/{len(out)} valid. {n_unsure} marked unsure ({n_unsure/len(valid)*100:.1f}%).", flush=True)
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
