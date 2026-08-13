"""run_frontier_calibration_tests.py

Step 1: Join target_entity onto the 25k batch from entity_mentions_cache_2stage_pooled.
Step 2: Re-run frontier scoring on escalation candidates with entity column.
Step 3: Save merged results ready for Round 8 training data merge.

This fixes the missing entity column that affected the original frontier scoring run.
"""
import os
import re
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials

PROJECT = "tobiasnash-vertex-frontier"
ACCOUNT = "contact@tobiasnash.co.nz"
LOCATION = "global"
MODEL_NAME = "gemini-3.5-flash"

CANDIDATES_PATH = 'data/processed/batch_escalation_candidates_round8.csv'
ENTITY_CACHE_PATH = 'data/processed/entity_mentions_cache_2stage_pooled.parquet'
OUT_PATH = 'data/processed/round8_frontier_scored_with_entity.csv'
CHECKPOINT_EVERY = 50
MAX_WORKERS = 15

PROMPT_TEMPLATE = """You are scoring a comment's STANCE toward a specific entity for academic research on epistemic credibility in online communities.

Entity: {entity}
Comment: {text}

This comment has been identified as expressing a stance (either hostile or endorsing) toward the entity. Your task: determine whether this comment is HOSTILE or ENDORSING.

You MUST choose between hostile and endorsing — forced binary choice.

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


def parse_score(raw):
    try:
        m = SCORE_RE.search(raw.strip())
        score = float(m.group(0))
        return max(-1.0, min(1.0, score))
    except Exception:
        return None


def score_one(row_id, text, entity):
    prompt = PROMPT_TEMPLATE.format(
        entity=entity if isinstance(entity, str) and entity.strip() else "the subject",
        text=str(text)[:2000]
    )
    client = get_client()
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                )
            )
            return {"id": row_id, "frontier_score": parse_score(resp.text)}
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                import time; time.sleep(10 * (attempt + 1))
                continue
            return {"id": row_id, "frontier_score": None}
    return {"id": row_id, "frontier_score": None}


def main():
    print("=== Step 1: Join entity onto escalation candidates ===\n")

    cands = pd.read_csv(CANDIDATES_PATH)
    print(f"Loaded {len(cands)} escalation candidates")

    if os.path.exists(ENTITY_CACHE_PATH):
        print("Loading entity mentions cache for entity join...")
        entity_cache = pd.read_parquet(ENTITY_CACHE_PATH, columns=['comment_id', 'entity_text'])
        entity_cache = entity_cache.drop_duplicates('comment_id')
        cands = cands.merge(entity_cache.rename(columns={'comment_id': 'id', 'entity_text': 'target_entity'}),
                            on='id', how='left')
        print(f"  Entity join coverage: {cands['target_entity'].notna().sum()}/{len(cands)}")
    else:
        print(f"  Entity cache not found locally ({ENTITY_CACHE_PATH})")
        print("  Falling back to regex detection from text...")
        # Regex fallback
        ENTITY_PATTERNS = [
            (r'\bwikileaks?\b', 'WikiLeaks'),
            (r'\bjulian\s+assange\b|\bassange\b', 'Julian Assange'),
            (r'\bedward\s+snowden\b|\bsnowden\b', 'Edward Snowden'),
            (r'\baaron\s+swartz\b|\bswartz\b', 'Aaron Swartz'),
            (r'\bglenn\s+greenwald\b|\bgreenwald\b', 'Glenn Greenwald'),
            (r'\bdr\.?\s*fauci\b|\banthony\s+fauci\b|\bfauci\b', 'Anthony Fauci'),
            (r'\bbill\s+gates\b', 'Bill Gates'),
            (r'\b(?:the\s+)?cdc\b', 'CDC'),
            (r'\bjulian\s+assange\b|\bassange\b', 'Julian Assange'),
            (r'\balex\s+jones\b|\binfowars\b', 'Alex Jones'),
            (r'\btucker\s+carlson\b', 'Tucker Carlson'),
            (r'\broger\s+stone\b', 'Roger Stone'),
            (r'\bmatt\s+gaetz\b|\bgaetz\b', 'Matt Gaetz'),
        ]
        compiled = [(re.compile(pat, re.IGNORECASE), canonical) for pat, canonical in ENTITY_PATTERNS]
        def detect(text):
            for pattern, canonical in compiled:
                if pattern.search(str(text)):
                    return canonical
            return None
        cands['target_entity'] = cands['text'].apply(detect)
        print(f"  Regex coverage: {cands['target_entity'].notna().sum()}/{len(cands)}")

    # Drop rows with no entity (can't score meaningfully)
    cands_with_entity = cands[cands['target_entity'].notna()].copy()
    print(f"\nRows with entity for frontier scoring: {len(cands_with_entity)}")
    print("\nEntity distribution:")
    print(cands_with_entity['target_entity'].value_counts().head(15))

    print("\n=== Step 2: Frontier scoring with entity ===\n")

    done_ids = set()
    results = []
    if os.path.exists(OUT_PATH):
        done = pd.read_csv(OUT_PATH)
        done_ids = set(done[done['frontier_score'].notna()]['id'])
        results = done[done['frontier_score'].notna()].to_dict('records')
        print(f"Resuming: {len(results)} already scored")

    todo = cands_with_entity[~cands_with_entity['id'].isin(done_ids)].to_dict('records')
    print(f"Scoring {len(todo)} rows via Gemini frontier...\n")

    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(score_one, r['id'], r['text'], r['target_entity']) for r in todo]
        for fut in as_completed(futures):
            result = fut.result()
            results.append(result)
            completed += 1
            if completed % CHECKPOINT_EVERY == 0 or completed == len(todo):
                pd.DataFrame(results).to_csv(OUT_PATH, index=False)
                n_valid = sum(1 for r in results if r['frontier_score'] is not None)
                print(f"  {completed}/{len(todo)} scored ({n_valid} valid), checkpointed")

    # Merge entity + frontier scores back onto candidates
    scored_df = pd.DataFrame(results)
    final = cands_with_entity.merge(scored_df, on='id', how='left')
    final.to_csv(OUT_PATH.replace('.csv', '_merged.csv'), index=False)

    n_valid = final['frontier_score'].notna().sum()
    print(f"\nDone. {n_valid}/{len(final)} valid frontier scores.")
    print(f"Saved to {OUT_PATH.replace('.csv', '_merged.csv')}")


if __name__ == "__main__":
    main()
