"""score_escalation_cascade_frontier_gemini.py

Sends ~9.9k escalation candidates to Gemini API for hostile/endorsement re-scoring.
Uses google-generativeai library (direct Gemini API).

Input: batch_escalation_candidates_round8.csv
Output: escalation_cascade_frontier_scored.csv
"""
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import google.generativeai as genai

INPUT_PATH = "batch_escalation_candidates_round8.csv"
OUT_PATH = "escalation_cascade_frontier_scored.csv"
CHECKPOINT_EVERY = 50
MAX_WORKERS = 10

# Updated prompt to remove the hardcoded "epistemic credibility" reference
PROMPT_TEMPLATE = """You are scoring a comment's STANCE toward a specific entity.

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
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")
        genai.configure(api_key=api_key)
        _thread_local.client = genai.GenerativeModel("gemini-2.0-flash")
    return _thread_local.client

def parse_response(raw):
    try:
        m = SCORE_RE.search(raw.strip())
        score = float(m.group(0))
        return max(-1.0, min(1.0, score))
    except Exception:
        return None

def score_one(record_id, text, entity):
    prompt = PROMPT_TEMPLATE.format(
        entity=entity if isinstance(entity, str) and entity.strip() else "the subject",
        text=str(text)[:2000]
    )
    client = get_client()

    score = None
    for attempt in range(3):
        try:
            resp = client.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0,
                    max_output_tokens=10,
                )
            )
            score = parse_response(resp.text)
            break
        except Exception as e:
            msg = str(e)
            if "429" in msg or "resource_exhausted" in msg.lower():
                import time
                time.sleep(10 * (attempt + 1))
                continue
            break

    return {"id": record_id, "frontier_score": score}

def main():
    # 1. Load the new escalation candidates CSV
    candidates = pd.read_csv(INPUT_PATH)
    print(f"Loaded {len(candidates)} escalation candidates", flush=True)

    # Note: If your CSV has a specific target entity column, change 'target_entity' to match it.
    # Otherwise, it defaults to 'the subject'.
    escalation_data = []
    for _, row in candidates.iterrows():
        escalation_data.append({
            'id': row['id'], 
            'text': row['text'],
            'entity': row.get('target_entity', 'the subject') 
        })

    # 2. Check for existing results to resume if it crashes
    done_ids = set()
    results = []
    if os.path.exists(OUT_PATH):
        done = pd.read_csv(OUT_PATH)
        if 'id' in done.columns:
            done_ids = set(done['id'])
            results = done.to_dict('records')
            print(f"Resuming: {len(done)} rows already scored", flush=True)

    todo = [r for r in escalation_data if r['id'] not in done_ids]
    print(f"\nScoring {len(todo)} remaining rows via Gemini API...", flush=True)

    # 3. Process via API
    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [
            pool.submit(score_one, r['id'], r['text'], r['entity'])
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
    print(f"\nDone. {len(valid)}/{len(out)} valid scores.")
    print(f"Saved to {OUT_PATH}")

if __name__ == "__main__":
    main()