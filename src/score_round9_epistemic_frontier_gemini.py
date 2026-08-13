"""score_escalation_cascade_frontier_gemini.py

Sends unlabeled escalation candidates to Vertex AI (Gemini) for hostile/endorsement scoring.
Uses google.genai library (Vertex AI endpoint) in batches of 10 with thinking budget enabled.

Input: batch_escalation_candidates_round8.csv
Output: escalation_cascade_frontier_scored.csv
"""
import argparse
import os
import threading
import time
import subprocess
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydantic import BaseModel

import pandas as pd
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials

# Set global socket timeout to prevent indefinite hangs on Vertex API calls
socket.setdefaulttimeout(60)

# Vertex AI Settings
PROJECT = "conspiracycomments-gce"
ACCOUNT = "tobiasnash@gmail.com"  
LOCATION = "global"
MODEL_NAME = "gemini-3.5-flash"

INPUT_PATH = "/Users/nash/Projects/ConspiracyComments/data/processed/round9/round9_epistemic_for_frontier.csv"
OUT_PATH = "/Users/nash/Projects/ConspiracyComments/data/processed/round9/round9_epistemic_frontier_scored.csv"
CHECKPOINT_EVERY = 50  # Checkpoint results frequently
MAX_WORKERS = 15       # Up to 15 concurrent threads for fast execution
BATCH_SIZE = 10
THINKING_BUDGET = 2048

class StancePrediction(BaseModel):
    id: str
    score: float

class BatchPrediction(BaseModel):
    predictions: list[StancePrediction]

PROMPT_HEADER_JSON = """You are scoring a set of comments for their STANCE toward specific target entities.
Each comment has already been identified as stance-bearing (either hostile or endorsing).
Your task is to determine whether the comment is HOSTILE or ENDORSING toward the entity, and assign a numeric score.

Scale:
  -1.0 = extremely hostile/attacking toward the entity
  -0.5 = mildly critical/hostile
  +0.5 = mildly supportive/approving
  +1.0 = extremely endorsing/supportive

Instructions:
- For each comment, identify the stance and output a score from the scale above (choose from -1.0, -0.5, +0.5, +1.0).
- Do not use 0.0. You must make a forced choice between hostile (negative) and endorsing (positive).

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
        f"Row ID: {row['id']}\nEntity: {row['entity']}\nText: \"\"\"{str(row['text'])[:1500]}\"\"\"\n---"
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
                row_id = pred.get("id")
                score = pred.get("score", 0.0)
                results.append({"id": row_id, "frontier_score": score})
            return results
        except Exception as e:
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg.upper() or "quota" in msg.lower():
                time.sleep(5 * (attempt + 1))
                continue
            print(f"\n[Error scoring batch of size {len(batch_rows)}]: {msg}")
            time.sleep(2)
            
    # Fallback: return None scores for all if batch failed completely
    return [{"id": r["id"], "frontier_score": None} for r in batch_rows]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    # Load escalation candidates
    candidates = pd.read_csv(INPUT_PATH)
    print(f"Loaded {len(candidates)} escalation candidates", flush=True)

    escalation_data = []
    for _, row in candidates.iterrows():
        escalation_data.append({
            'id': row['id'],
            'text': row['text'],
            'entity': row['target_entity'] if 'target_entity' in row else 'the subject',
        })

    # Check for existing results to resume cleanly
    done_ids = set()
    results = []
    if os.path.exists(OUT_PATH):
        done = pd.read_csv(OUT_PATH)
        if 'id' in done.columns:
            # Only count as done if the score is not null/empty
            done_valid = done[done['frontier_score'].notna()]
            done_ids = set(done_valid['id'])
            results = done_valid.to_dict('records')
            print(f"Resuming: {len(results)} valid rows already scored (re-queuing null/failed rows)", flush=True)

    todo = [r for r in escalation_data if r['id'] not in done_ids]
    if args.limit:
        todo = todo[:args.limit]
    
    print(f"\nScoring {len(todo)} remaining rows in batches of {BATCH_SIZE} via Vertex AI Gemini...", flush=True)
    if len(todo) == 0:
        print("Nothing to do!")
        return

    # Partition todo into batches
    batches = [todo[i:i + BATCH_SIZE] for i in range(0, len(todo), BATCH_SIZE)]
    
    completed_batches = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(score_batch, b) for b in batches]
        
        for fut in as_completed(futures):
            batch_results = fut.result()
            results.extend(batch_results)
            completed_batches += 1
            
            # Checkpoint results
            if completed_batches % (CHECKPOINT_EVERY // BATCH_SIZE + 1) == 0 or completed_batches == len(batches):
                pd.DataFrame(results).to_csv(OUT_PATH, index=False)
                n_valid = sum(1 for r in results if r['frontier_score'] is not None)
                print(f"  {len(results)}/{len(escalation_data)} total scored ({n_valid} valid), checkpointed", flush=True)

    out = pd.DataFrame(results)
    valid = out[out['frontier_score'].notna()]
    print(f"\nDone. {len(valid)}/{len(out)} valid scores.", flush=True)
    print(f"Saved to {OUT_PATH}")

if __name__ == "__main__":
    main()