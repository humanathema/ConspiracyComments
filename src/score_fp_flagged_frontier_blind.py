"""score_fp_flagged_frontier_blind.py

Sends the 5,159 rows the FP-detector flagged (excluding explicitly
frontier-sourced and human-labeled rows -- pure classifier/ensemble
output only) to Vertex AI Gemini for an INDEPENDENT, BLIND 3-way
classification (hostile/endorsement/other).

Deliberately does NOT show the judge the row's current label or mention
that a detector flagged it -- this is the exact anchoring/sycophancy
mistake retracted from the 2026-07-28 crisis (a judge shown the
classifier's predicted label and asked to "confirm" it anchored and
rationalized rather than judging independently). This prompt only ever
shows text + entity, nothing about what any prior system decided.

Auth/batching/checkpointing pattern reused from
score_escalation_cascade_frontier_gemini.py (proven working code).

Input: /tmp/fp_detector_frontier_batch.csv (row_id, text, target_entity,
label, confidence, fp_detector_score, source_file)
Output: outputs/reinfer_probs/fp_flagged_frontier_blind_scored.csv
"""
import argparse
import os
import threading
import time
import subprocess
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal
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

INPUT_PATH = os.environ.get("INPUT_PATH", "/tmp/fp_detector_frontier_batch.csv")
OUT_PATH = os.environ.get("OUT_PATH", "/Users/nash/Projects/ConspiracyComments/outputs/reinfer_probs/fp_flagged_frontier_blind_scored.csv")
CHECKPOINT_EVERY = 50
MAX_WORKERS = 15
BATCH_SIZE = 10
THINKING_BUDGET = 2048
TEXT_TRUNCATE = 1500


class StancePrediction(BaseModel):
    id: str
    classification: Literal["hostile", "endorsement", "other"]


class BatchPrediction(BaseModel):
    predictions: list[StancePrediction]


# Deliberately blind: no mention of any existing label, classifier, or
# detector flag anywhere in this prompt.
PROMPT_HEADER_JSON = """You are classifying comments for their STANCE toward a specific target entity.

For each comment, determine whether it expresses:
  "hostile" = a critical, attacking, or negative stance toward the entity
  "endorsement" = a supportive, approving, or positive stance toward the entity
  "other" = no clear stance toward the entity -- the entity is not really the subject being
            evaluated, the comment is neutral/factual with no evaluative language toward the
            entity, the comment is off-topic relative to the entity, or the comment is a bare
            citation/link with no discernible stance

Instructions:
- Judge the comment as written. If the entity is merely mentioned in passing while the comment
  evaluates something else, and there is no real evaluative language directed at the entity, use
  "other" even if the comment expresses opinions about other things.
- If the entity is cited approvingly as a source/evidence for a claim the comment is making, that
  DOES count as endorsement of the entity (an implicit epistemic endorsement), even if the entity
  is not the grammatical subject of the sentence.
- Make a forced choice among the three categories -- always pick one, do not add other labels.

Comments to evaluate:
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
        f"Row ID: {row['row_id']}\nEntity: {row['target_entity']}\nText: \"\"\"{str(row['text'])[:TEXT_TRUNCATE]}\"\"\"\n---"
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
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                    ],
                ),
            )
            import json
            data = json.loads(resp.text)
            predictions = data.get("predictions", [])
            return [{"row_id": p.get("id"), "frontier_classification": p.get("classification")} for p in predictions]
        except Exception as e:
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg.upper() or "quota" in msg.lower():
                time.sleep(5 * (attempt + 1))
                continue
            print(f"\n[Error scoring batch of size {len(batch_rows)}]: {msg}")
            time.sleep(2)
    return [{"row_id": r["row_id"], "frontier_classification": None} for r in batch_rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    candidates = pd.read_csv(INPUT_PATH)
    candidates["row_id"] = candidates["row_id"].astype(str)
    print(f"Loaded {len(candidates)} rows to judge", flush=True)

    data = candidates[["row_id", "text", "target_entity"]].to_dict("records")

    done_ids = set()
    results = []
    if os.path.exists(OUT_PATH):
        done = pd.read_csv(OUT_PATH, dtype={"row_id": str})
        if "row_id" in done.columns:
            done_valid = done[done["frontier_classification"].notna()]
            done_ids = set(done_valid["row_id"])
            results = done_valid.to_dict("records")
            print(f"Resuming: {len(results)} valid rows already scored", flush=True)

    todo = [r for r in data if r["row_id"] not in done_ids]
    if args.limit:
        todo = todo[:args.limit]
    print(f"\nScoring {len(todo)} remaining rows in batches of {BATCH_SIZE}...", flush=True)
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
                n_valid = sum(1 for r in results if r["frontier_classification"] is not None)
                print(f"  {len(results)}/{len(data)} total scored ({n_valid} valid), checkpointed", flush=True)

    out = pd.DataFrame(results)
    valid = out[out["frontier_classification"].notna()]
    print(f"\nDone. {len(valid)}/{len(out)} valid scores.", flush=True)
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
