"""score_silver_other_batched_api.py

Real run: scores all 3,416 AI-silver "other" rows into
neutral/ambiguous/hostile/endorsement via the Vertex API, using the
config that actually validated well (kappa 0.7110 vs the chat-verdict
reference on batch1's 90 rows) -- 90-row batches per call, same
calibrated prompt, thinking_budget=4000 per batch. Replaces the earlier
weak per-row/zero-thinking-budget pass (kappa 0.12-0.17 against ground
truth) that fed the current (unreliable) split training data.

Reads the same 38 batch files already built for manual chat-pasting
(data/hitl/gemini_silver_other_batch{1..38}_KEY_do_not_paste.csv) --
identical rows, just sent to the API instead of pasted by hand.

Output: data/processed/silver_other_neutral_ambiguous_scored_v2.parquet
  (row_uid, text, target_entity, source_file, verdict)
"""
import glob
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
THINKING_BUDGET = 4000
OUT_PATH = "data/processed/silver_other_neutral_ambiguous_scored_v2.parquet"

PROMPT_HEADER = """For each numbered row below, judge whether the comment expresses a stance toward its specific named entity -- not toward the topic, a theory involving them, or anyone else mentioned.

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

Rows:
{rows_block}

Respond with exactly {n} lines, one per row, in the format:
N: verdict
where N is the row number and verdict is exactly one word (neutral, ambiguous, hostile, or endorsement). No other text.
"""

VALID = {"neutral", "ambiguous", "hostile", "endorsement"}
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


def score_one_batch_file(key_path):
    key = pd.read_csv(key_path).sort_values("batch_position").reset_index(drop=True)
    rows_block = "\n".join(
        f'{row["batch_position"]}. Entity: "{row["target_entity"]}"\n   Text: """{row["text"]}"""'
        for _, row in key.iterrows()
    )
    prompt = PROMPT_HEADER.format(rows_block=rows_block, n=len(key))
    client = get_client()

    verdicts = {}
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME, contents=prompt,
                config=types.GenerateContentConfig(temperature=0, thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET)),
            )
            verdicts = parse_batch_response(resp.text)
            break
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(10 * (attempt + 1))
                continue
            break

    results = []
    for _, row in key.iterrows():
        bp = row["batch_position"]
        results.append({
            "row_uid": row["row_uid"], "text": row["text"], "target_entity": row["target_entity"],
            "source_file": row["source_file"], "verdict": verdicts.get(bp),
        })
    return results


def main():
    key_files = sorted(
        glob.glob("data/hitl/gemini_silver_other_batch*_KEY_do_not_paste.csv"),
        key=lambda p: int(p.split("batch")[1].split("_")[0]),
    )
    print(f"Scoring {len(key_files)} batches via API (thinking_budget={THINKING_BUDGET})...", flush=True)

    all_results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(score_one_batch_file, f): f for f in key_files}
        for i, fut in enumerate(as_completed(futures), 1):
            all_results.extend(fut.result())
            if i % 5 == 0 or i == len(key_files):
                pd.DataFrame(all_results).to_parquet(OUT_PATH, index=False)
                print(f"  {i}/{len(key_files)} batches done, checkpointed", flush=True)

    out = pd.DataFrame(all_results)
    out.to_parquet(OUT_PATH, index=False)
    valid = out[out["verdict"].notna()]
    print(f"\nDone. {len(valid)}/{len(out)} valid verdicts.")
    print(valid["verdict"].value_counts())


if __name__ == "__main__":
    main()
