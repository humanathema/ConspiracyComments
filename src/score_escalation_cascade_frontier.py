"""score_escalation_cascade_frontier.py

Sends 136 escalation candidates (identified by cascade_sweep) to frontier judge
for hostile/endorsement re-scoring. Uses Vertex Gemini frontier API.

Input: escalation_candidates_for_frontier.csv (row indices, predictions)
       preds_*.csv files (text content)
Output: escalation_cascade_frontier_scored.csv (frontier scores)

The frontier judge is validated at ~0.81 accuracy on hostile/endorsement
(stage2-only, not stage1 "other" calls). We only escalate rows where the
ensemble was uncertain on that axis.
"""
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
INPUT_PATH = "escalation_candidates_for_frontier.csv"
OUT_PATH = "escalation_cascade_frontier_scored.csv"
MODEL_NAME = "gemini-3.5-flash"
CHECKPOINT_EVERY = 25
MAX_WORKERS = 15

PROMPT_TEMPLATE = """You are scoring a comment's STANCE toward a specific entity for research on epistemic credibility.

Entity: {entity}
Comment: {text}

The comment has already been identified as stance-related (not neutral/other). Your task: is this comment HOSTILE or ENDORSING toward the entity?

Scale:
  -1.0 = extremely hostile/attacking
  -0.5 = mildly critical/hostile
   0.0 = balanced/mixed
  +0.5 = mildly supportive/approving
  +1.0 = extremely endorsing/supportive

Respond with ONLY the numeric score (e.g., "-0.7" or "0.3"). No explanation."""

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


def score_one(row_idx, text, entity):
    prompt = PROMPT_TEMPLATE.format(
        entity=entity if isinstance(entity, str) and entity.strip() else "the subject",
        text=text[:2000]
    )
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

    return {"row_idx": row_idx, "frontier_score": score}


def main():
    # Load escalation candidates
    candidates = pd.read_csv(INPUT_PATH)
    print(f"Loaded {len(candidates)} escalation candidates", flush=True)

    # Load training data for text + entity
    train = pd.read_parquet("data/processed/stance_classifier_training_data_round7_bigval_split.parquet")
    val_data = train[train['split'] == 'val'].reset_index(drop=True)
    print(f"Loaded {len(val_data)} validation rows with text", flush=True)

    # Candidates are in the same order as val_data (cascade_sweep didn't reorder)
    # Just match by index
    escalation_data = []
    for idx, cand_row in candidates.iterrows():
        if idx < len(val_data):
            val_row = val_data.iloc[idx]
            escalation_data.append({
                'row_idx': idx,
                'text': val_row['text'],
                'entity': val_row.get('target_entity', 'the subject'),
                'true_label': cand_row['true_label'],
                'pred_label': cand_row['pred_label'],
                'margin': cand_row['margin']
            })

    print(f"Matched {len(escalation_data)}/{len(candidates)} candidates to validation rows", flush=True)

    # Check for existing results
    done_idxs = set()
    results = []
    if os.path.exists(OUT_PATH):
        done = pd.read_csv(OUT_PATH)
        done_idxs = set(done['row_idx'])
        results = done.to_dict('records')
        print(f"Resuming: {len(done)} rows already scored", flush=True)

    todo = [r for r in escalation_data if r['row_idx'] not in done_idxs]
    print(f"\nScoring {len(todo)} remaining rows via Vertex Gemini frontier...", flush=True)

    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [
            pool.submit(score_one, r['row_idx'], r['text'], r['entity'])
            for r in todo
        ]
        for fut in as_completed(futures):
            result = fut.result()
            results.append(result)
            completed += 1
            if completed % CHECKPOINT_EVERY == 0 or completed == len(todo):
                pd.DataFrame(results).to_csv(OUT_PATH, index=False)
                n_valid = sum(1 for r in results if r['frontier_score'] is not None)
                print(f"  {len(results)}/{len(escalation_data)} total scored ({n_valid} valid), checkpointed", flush=True)

    out = pd.DataFrame(results)
    valid = out[out['frontier_score'].notna()]
    print(f"\nDone. {len(valid)}/{len(out)} valid scores.", flush=True)
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
