"""score_stage2_errors_frontier.py

Scores only stage2 errors (true=stance, ensemble predicted wrong) via frontier judge.
Uses forced-choice prompt: hostile vs endorsement only, no "other" option.

Input: escalation_candidates_stage2_only.csv
       stance_classifier_training_data_round7_bigval_split.parquet
Output: stage2_frontier_scored.csv
"""
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
import subprocess

PROJECT = "tobiasnash-vertex-frontier"
ACCOUNT = "contact@tobiasnash.co.nz"
LOCATION = "global"
INPUT_PATH = "escalation_candidates_stage2_only.csv"
OUT_PATH = "stage2_frontier_scored.csv"
MODEL_NAME = "gemini-3.5-flash"
CHECKPOINT_EVERY = 10
MAX_WORKERS = 10

PROMPT_TEMPLATE = """You are scoring a comment's STANCE toward a specific entity for research on epistemic credibility.

Entity: {entity}
Comment: {text}

This comment has been identified as expressing a stance (either hostile or endorsing) toward the entity. Your task: determine whether this comment is HOSTILE or ENDORSING.

You MUST choose between hostile and endorsing — this is a forced binary choice.

Scale:
  -1.0 = extremely hostile/attacking
  -0.5 = mildly critical/hostile
  +0.5 = mildly supportive/approving
  +1.0 = extremely endorsing/supportive

Respond with ONLY the numeric score. No explanation."""

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
                import time
                time.sleep(10 * (attempt + 1))
                continue
            break

    return {"row_idx": row_idx, "frontier_score": score}


def main():
    # Load stage2 errors only
    candidates = pd.read_csv(INPUT_PATH)
    print(f"Loaded {len(candidates)} stage2 errors", flush=True)

    # Load training data for text + entity
    train = pd.read_parquet("data/processed/stance_classifier_training_data_round7_bigval_split.parquet")
    val_data = train[train['split'] == 'val'].reset_index(drop=True)
    print(f"Loaded {len(val_data)} validation rows with text", flush=True)

    # Match candidates to validation rows
    escalation_data = []
    for idx, cand_row in candidates.iterrows():
        row_idx = int(cand_row['row_idx'])
        if row_idx < len(val_data):
            val_row = val_data.iloc[row_idx]
            escalation_data.append({
                'row_idx': row_idx,
                'text': val_row['text'],
                'entity': val_row.get('target_entity', 'the subject'),
                'true_label': cand_row['true_label'],
                'pred_label': cand_row['pred_label'],
            })

    print(f"Matched {len(escalation_data)} stage2 errors", flush=True)

    # Check for existing results
    done_idxs = set()
    results = []
    if os.path.exists(OUT_PATH):
        done = pd.read_csv(OUT_PATH)
        done_idxs = set(done['row_idx'])
        results = done.to_dict('records')
        print(f"Resuming: {len(done)} rows already scored", flush=True)

    todo = [r for r in escalation_data if r['row_idx'] not in done_idxs]
    print(f"\nScoring {len(todo)} remaining stage2 errors via Vertex Gemini...", flush=True)

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
