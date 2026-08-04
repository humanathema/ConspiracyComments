"""score_silver_other_v3_stage2_direction.py

Stage 2 of the v3 re-score, run only on rows score_silver_other_v4binary_api.py
marked "ambiguous" (has some evaluative trace, direction unasked). Mirrors the
trained classifier's own stage1(gate)/stage2(direction) cascade in the
labeling process itself: this is a separate, narrower follow-up question
("is this actually clearly directional?") on top of the validated binary
gate, rather than reintroducing the 4-way categorical frame into the gate
call that caused the original neutral-bias problem.

Input: data/processed/silver_other_neutral_ambiguous_scored_v3.parquet
  (rows with verdict == "ambiguous" only; hostile/endorsement/neutral rows
  are left untouched)
Output: data/processed/silver_other_neutral_ambiguous_scored_v3_final.parquet
  (same schema, verdict updated to hostile/endorsement where stage2 finds a
  clear direction, otherwise stays "ambiguous")
"""
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
MODEL_NAME = "gemini-3.5-flash"
THINKING_BUDGET = 4000
BATCH_SIZE = 40
IN_PATH = "data/processed/silver_other_neutral_ambiguous_scored_v3.parquet"
OUT_PATH = "data/processed/silver_other_neutral_ambiguous_scored_v3_final.parquet"

PROMPT_HEADER = """For each numbered row below, a comment has already been flagged as carrying SOME evaluative trace toward the named entity -- the only question here is whether that trace clearly points in one direction.

Answer "hostile" if the comment is clearly negative toward the entity.
Answer "endorsement" if the comment is clearly positive toward the entity.
Answer "ambiguous" if the trace exists but you cannot confidently tell which direction it leans -- this is the expected answer for most rows here, only pick hostile/endorsement if the direction is genuinely clear.

Rows:
{rows_block}

Respond with exactly {n} lines, one per row, in the format:
N: verdict
where verdict is exactly one word (hostile, endorsement, or ambiguous). No other text.
"""

VALID = {"hostile", "endorsement", "ambiguous"}
_thread_local = threading.local()


def get_client():
    if not hasattr(_thread_local, "client"):
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token", f"--account={ACCOUNT}"]
        ).decode().strip()
        creds = Credentials(token=token)
        _thread_local.client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION, credentials=creds)
    return _thread_local.client


def parse_batch_response(raw):
    verdicts = {}
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        num_part, verdict_part = line.split(":", 1)
        num_part = num_part.strip().lstrip("#").strip()
        verdict_part = verdict_part.strip().lower().strip(".")
        if not num_part.isdigit():
            continue
        num = int(num_part)
        for v in VALID:
            if v in verdict_part:
                verdicts[num] = v
                break
    return verdicts


def score_batch(batch_rows):
    rows_block = "\n".join(
        f'{i+1}. Entity: "{row["target_entity"]}"\n   Text: """{row["text"]}"""'
        for i, row in enumerate(batch_rows)
    )
    prompt = PROMPT_HEADER.format(rows_block=rows_block, n=len(batch_rows))
    client = get_client()

    verdicts = {}
    for attempt in range(4):
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME, contents=prompt,
                config=types.GenerateContentConfig(temperature=0, thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET)),
            )
            verdicts = parse_batch_response(resp.text)
            break
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(15 * (attempt + 1))
                continue
            break

    results = []
    for i, row in enumerate(batch_rows):
        new_verdict = verdicts.get(i + 1, row["verdict"])
        results.append({**row, "verdict": new_verdict})
    return results


def main():
    df = pd.read_parquet(IN_PATH)
    ambiguous = df[df["verdict"] == "ambiguous"].to_dict("records")
    other = df[df["verdict"] != "ambiguous"]
    print(f"stage2 direction-check on {len(ambiguous)} ambiguous rows ({len(other)} rows left untouched)...", flush=True)

    batches = [ambiguous[i:i + BATCH_SIZE] for i in range(0, len(ambiguous), BATCH_SIZE)]
    all_results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(score_batch, b) for b in batches]
        for i, fut in enumerate(as_completed(futures), 1):
            all_results.extend(fut.result())
            print(f"  {i}/{len(batches)} batches done", flush=True)

    updated = pd.DataFrame(all_results)
    final = pd.concat([other, updated], ignore_index=True)
    final.to_parquet(OUT_PATH, index=False)
    print(f"\nDone. Final verdict distribution:")
    print(final["verdict"].value_counts())


if __name__ == "__main__":
    main()
