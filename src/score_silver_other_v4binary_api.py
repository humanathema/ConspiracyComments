"""score_silver_other_v4binary_api.py

Re-scores the 3,388 AI-silver "other" rows that were NOT already corrected
to a genuine hostile/endorsement label by the v2 pass
(silver_other_neutral_ambiguous_scored_v2.parquet: 10 hostile, 18
endorsement corrections, kept as-is) -- replaces their neutral/ambiguous
split using v4's validated binary framing (kappa 0.3202 against the
446-row human ground truth, the best of 13 prompt variants tested
2026-08-04), instead of the original 4-way categorical prompt that
produced an 85.1%/14.1% neutral/ambiguous split later found to have
kappa only ~0.16 against the same ground truth.

Output: data/processed/silver_other_neutral_ambiguous_scored_v3.parquet
  (row_uid, text, target_entity, source_file, verdict)
"""
import glob
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
V2_PATH = "data/processed/silver_other_neutral_ambiguous_scored_v2.parquet"
OUT_PATH = "data/processed/silver_other_neutral_ambiguous_scored_v3.parquet"

PROMPT_HEADER = """For each numbered row below, a comment mentions a specific named entity. Answer one question only: does the comment contain ANY trace of evaluative content, framing, suspicion, dismissal, tone, or implied judgment pointing toward that entity -- in either direction -- however subtle?

Answer "1" if there is any such trace at all, even a mild or ambiguous one you can't fully pin down the direction of.
Answer "0" only if the comment is purely factual/descriptive with truly nothing to read into -- a bare mention, a plain quote, an incidental example.

This is a detection task, not a direction task -- you are NOT being asked whether the trace is positive or negative, just whether one exists.

Rows:
{rows_block}

Respond with exactly {n} lines, one per row, in the format:
N: 0
or
N: 1
No other text.
"""

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
        verdict_part = verdict_part.strip()
        if not num_part.isdigit():
            continue
        num = int(num_part)
        if "1" in verdict_part:
            verdicts[num] = 1
        elif "0" in verdict_part:
            verdicts[num] = 0
    return verdicts


def score_one_batch_file(key_path, exclude_uids):
    key = pd.read_csv(key_path).sort_values("batch_position").reset_index(drop=True)
    key = key[~key["row_uid"].isin(exclude_uids)].reset_index(drop=True)
    if len(key) == 0:
        return []
    rows_block = "\n".join(
        f'{i+1}. Entity: "{row["target_entity"]}"\n   Text: """{row["text"]}"""'
        for i, row in key.iterrows()
    )
    prompt = PROMPT_HEADER.format(rows_block=rows_block, n=len(key))
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
    for i, row in key.iterrows():
        bit = verdicts.get(i + 1)
        verdict = {0: "neutral", 1: "ambiguous"}.get(bit)
        results.append({
            "row_uid": row["row_uid"], "text": row["text"], "target_entity": row["target_entity"],
            "source_file": row["source_file"], "verdict": verdict,
        })
    return results


def main():
    v2 = pd.read_parquet(V2_PATH)
    keep_v2 = v2[v2["verdict"].isin(["hostile", "endorsement"])]
    exclude_uids = set(keep_v2["row_uid"])
    print(f"Keeping {len(keep_v2)} existing hostile/endorsement corrections from v2 as-is.", flush=True)

    key_files = sorted(
        glob.glob("data/hitl/gemini_silver_other_batch*_KEY_do_not_paste.csv"),
        key=lambda p: int(p.split("batch")[1].split("_")[0]),
    )
    print(f"Re-scoring remaining rows across {len(key_files)} batches via v4 binary framing (thinking_budget={THINKING_BUDGET})...", flush=True)

    all_results = list(keep_v2.to_dict("records"))
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(score_one_batch_file, f, exclude_uids): f for f in key_files}
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
