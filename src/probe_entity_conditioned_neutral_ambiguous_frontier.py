"""score_silver_other_neutral_ambiguous.py

Splits the AI-silver "other"-labeled rows (3,416 as of 2026-08-04) into
neutral/ambiguous/hostile/endorsement via a real frontier judge call --
the cheap TF-IDF and small-scale entity-conditioned-roberta heuristics
both failed (kappa 0.056-0.19 and 0.08 respectively) on our
hand+Gemini-corrected human labels, so this reuses the same
Vertex/gemini-3.5-flash pattern already validated in
score_boundary_candidates_vertex.py (thinking disabled, single-word-only
output to keep cost down, resumable-by-identity checkpointing).

Prompt is the calibrated version that got the Gemini chat-batch pass's
flag rate up from 14.4% to ~50% (matching hand-review), reused directly
-- see handoff for the calibration examples' provenance.

Cost estimate (computed from real text lengths, 2026-08-04): ~$3.89
total for all 3,416 rows. Explicit sign-off given by Nash same day.

Input: stance_classifier_training_data.parquet, filtered to
  is_human==False & label=='other'
Output: data/processed/silver_other_neutral_ambiguous_scored.parquet
  (text, target_entity, source_file, verdict)
"""
import argparse
import os
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
TRAINING_DATA_PATH = "data/processed/stance_classifier_training_data.parquet"
OUT_PATH = "data/processed/silver_other_neutral_ambiguous_scored.parquet"
CHECKPOINT_EVERY = 50
MAX_WORKERS = 15

PROMPT_TEMPLATE = """Judge whether this comment expresses a stance toward the specific named entity below -- not toward the topic, a theory involving them, or anyone else mentioned.

Entity: "{entity}"

Comment text:
\"\"\"{text}\"\"\"

Categories:
- neutral: genuinely nothing to read into it toward the entity. Reserve this ONLY for truly zero evaluative content -- a bare factual mention, a direct quote with no commentary, or using the entity purely as an incidental example.
- ambiguous: there's SOME evaluative or suspicion-toned content, but you can't confidently tell which direction it leans, OR the text is too garbled/unclear to make any call. If unsure whether something is neutral or ambiguous, default to ambiguous.
- hostile: clearly negative toward the entity.
- endorsement: clearly positive toward the entity.

Calibration:
- "Jones is not Bill Hicks" [+ photo evidence debunking an identity theory] -> neutral toward Bill Hicks (debunking a claim about someone's identity isn't evaluating the person being compared).
- "If Bill Hicks hadn't died, he'd have been replaced with Alex Jones... the real Alex Jones would have been wiped from the records" -> ambiguous toward Bill Hicks (engaging with/entertaining a real claim about his fate, not just background).
- "Coffee with Assange would be a good start, although..." -> ambiguous, leaning positive (a warm/friendly framing is real evaluative content, even mild and incomplete).
- "he is at best moderate social democrat... he is also an opinion writer, not a reporter" -> ambiguous (a subtle, mildly dismissive framing that downgrades legitimacy still counts, even without explicit hostility).

Respond with ONLY one word: neutral, ambiguous, hostile, or endorsement. No explanation, no punctuation.
"""

VALID = {"neutral", "ambiguous", "hostile", "endorsement"}

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
    cleaned = raw.strip().lower().strip(".").strip()
    if cleaned in VALID:
        return cleaned
    for v in VALID:
        if v in cleaned:
            return v
    return None


def score_one(row):
    entity = row["target_entity"]
    prompt = PROMPT_TEMPLATE.format(entity=entity, text=row["text"])
    client = get_client()

    verdict = None
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
            verdict = parse_response(resp.text)
            break
        except Exception as e:
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                time.sleep(10 * (attempt + 1))
                continue
            break

    return {
        "row_key": row["row_key"], "target_entity": entity, "text": row["text"],
        "source_file": row["source_file"], "verdict": verdict,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    args = parser.parse_args()

    df = pd.read_parquet(TRAINING_DATA_PATH)
    rows = df[(df["is_human"] == False) & (df["label"] == "other") & df["target_entity"].notna()].copy()
    rows = rows.reset_index(drop=True)
    rows["row_key"] = rows.index.astype(str) + "_" + rows["text"].str[:40]
    if args.limit:
        rows = rows.head(args.limit).copy()

    done_keys = set()
    results = []
    if os.path.exists(OUT_PATH) and not args.limit:
        done = pd.read_parquet(OUT_PATH)
        succeeded = done[done["verdict"].notna()]
        done_keys = set(succeeded["row_key"])
        results = succeeded.to_dict("records")
        print(f"Resuming: {len(succeeded)} rows already scored.", flush=True)

    todo = [r for _, r in rows.iterrows() if r["row_key"] not in done_keys]
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
                n_valid = sum(1 for r in results if r["verdict"] is not None)
                print(f"  {len(results)}/{len(rows)} total scored ({n_valid} valid), checkpointed", flush=True)

    out = pd.DataFrame(results)
    valid = out[out["verdict"].notna()]
    print(f"\nDone. {len(valid)}/{len(out)} valid verdicts.", flush=True)
    print(valid["verdict"].value_counts())


if __name__ == "__main__":
    main()
