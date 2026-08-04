"""validate_frontier_prompt_batched.py

Tests whether batching multiple rows into one API call (mimicking the
manual chat-batch process that got ~50% flag rate, vs. the isolated
per-row calls that only got kappa 0.12-0.17 against ground truth)
actually helps -- batches of 26 rows per call, same calibrated prompt,
scored against the same 446-row hand-corrected ground truth set.
"""
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from sklearn.metrics import cohen_kappa_score, classification_report
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials

PROJECT = "tobiasnash-vertex-frontier"
ACCOUNT = "contact@tobiasnash.co.nz"
LOCATION = "global"
MODEL_NAME = "gemini-3.5-flash"
BATCH_SIZE = 26

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


def parse_batch_response(raw, n):
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
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME, contents=prompt,
                config=types.GenerateContentConfig(temperature=0, thinking_config=types.ThinkingConfig(thinking_budget=500)),
            )
            verdicts = parse_batch_response(resp.text, len(batch_rows))
            break
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(10 * (attempt + 1))
                continue
            break

    results = []
    for i, row in enumerate(batch_rows):
        results.append({
            "text": row["text"], "true_label": row["corrected"],
            "frontier_verdict": verdicts.get(i + 1),
        })
    return results


def main():
    df = pd.read_csv("/tmp/neutral_ambiguous_corrected.csv")
    batches = [df.iloc[i:i + BATCH_SIZE].to_dict("records") for i in range(0, len(df), BATCH_SIZE)]
    print(f"Scoring {len(df)} rows in {len(batches)} batches of up to {BATCH_SIZE}...", flush=True)

    all_results = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(score_batch, b) for b in batches]
        for i, fut in enumerate(as_completed(futures), 1):
            all_results.extend(fut.result())
            print(f"  {i}/{len(batches)} batches done", flush=True)

    out = pd.DataFrame(all_results)
    out.to_csv("/tmp/frontier_batched_validation.csv", index=False)
    valid = out[out["frontier_verdict"].notna()]
    print(f"\n{len(valid)}/{len(out)} valid verdicts (missing = row not found in a batch's response).")

    kappa = cohen_kappa_score(valid["true_label"], valid["frontier_verdict"])
    print(f"\n=== Batched frontier judge vs ground-truth kappa: {kappa:.4f} ===")
    print(classification_report(valid["true_label"], valid["frontier_verdict"]))


if __name__ == "__main__":
    main()
