"""score_gemini_api_free_tier.py

Real Gemini API access via Google AI Studio's free tier (project
382018412266, confirmed genuinely free-tier, not postpay/prepay --
.freekey, after two earlier keys turned out billing-adjacent). Replaces
both the metered kaggle_benchmarks AI-proxy path (frontier judge,
$10/day, stalled twice tonight) and the manual chat-batch-paste
approach (worked well up to ~60-138 rows, outright failed at 1,543) --
this scores one row per call, same reliable methodology that got
kappa=0.8266 on held-out val via the paid proxy, just against a free,
unmetered endpoint instead.

Input: data/hitl/gemini_chat_fullbatch_KEY_do_not_paste.csv (1,543 rows,
  real human ground truth, the same pool the manual chat-batch attempt
  choked on at full size).
Output: data/processed/gemini_api_free_tier_scored.parquet, checkpointed
  incrementally, resumable.

API key is read from a local file at runtime only, never printed or
logged -- see .gitignore, both .gemini_key and .geminikey are excluded.

Usage:
    python src/score_gemini_api_free_tier.py --limit 10   # smoke test
    python src/score_gemini_api_free_tier.py               # full run
"""
import argparse
import json
import os
import re
import time

import pandas as pd
from google import genai
from google.genai import types

KEY_PATH = os.path.join(os.path.dirname(__file__), "..", ".freekey")
INPUT_PATH = "data/hitl/gemini_chat_fullbatch_KEY_do_not_paste.csv"
OUT_PATH = "data/processed/gemini_api_free_tier_scored.parquet"
MODEL_NAME = "gemini-3.5-flash-lite"
CHECKPOINT_EVERY = 20
# Confirmed via this project's live AI Studio rate-limit dashboard
# (2026-08-02): full Gemini 3.5 Flash on this free project is RPM=5,
# RPD=20 -- far too low for any volume work (we blew through both
# before even finishing a smoke test). Gemini 3.5 Flash Lite / 3.1 Flash
# Lite show RPM=15, RPD=500 on the same project -- switched to
# flash-lite for exactly that reason. 4.5s stays under the 15 RPM cap
# with margin.
SECONDS_BETWEEN_CALLS = 4.5

PROMPT_TEMPLATE = """You are scoring a comment's STANCE STRENGTH toward a specific entity, for a research project on epistemic credibility in online discussion.

Entity: "{entity}"

Comment text:
\"\"\"{text}\"\"\"

Score how strongly hostile or endorsing this text is toward "{entity}", on a continuous scale:
  -1.0 = extremely hostile/attacking
  -0.5 = mildly critical or hostile but hedged
   0.0 = no real stance, or perfectly balanced/mixed
  +0.5 = mildly supportive or approving but hedged
  +1.0 = extremely endorsing/supportive
Use the full range, including intermediate values (e.g. -0.7, 0.3, -0.2) where warranted -- do not default to round numbers.

Respond with ONLY a JSON object, no other text, no markdown code fences: {{"score": <float from -1.0 to 1.0>, "reason": "one short sentence"}}
"""


def load_client():
    with open(KEY_PATH, "r", encoding="utf-8") as f:
        key = f.read().strip()
    return genai.Client(api_key=key)


def parse_response(raw):
    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        obj = json.loads(match.group(0) if match else raw)
        score = float(obj.get("score"))
        score = max(-1.0, min(1.0, score))
        return score, obj.get("reason", "")
    except Exception as e:
        return None, f"{type(e).__name__}: {raw[:200]}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    rows = pd.read_csv(INPUT_PATH)
    if args.limit:
        rows = rows.head(args.limit).copy()
    print(f"Scoring {len(rows)} rows via Gemini API free tier ({MODEL_NAME})", flush=True)

    client = load_client()

    if os.path.exists(OUT_PATH) and not args.limit:
        done = pd.read_parquet(OUT_PATH)
        print(f"Resuming: {len(done)} rows already scored.", flush=True)
        start_idx = len(done)
        results = done.to_dict("records")
    else:
        start_idx = 0
        results = []

    for i in range(start_idx, len(rows)):
        row = rows.iloc[i]
        prompt = PROMPT_TEMPLATE.format(entity=row["target_entity"], text=row["text"])

        score, reason = None, None
        for attempt in range(3):
            try:
                resp = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0),
                )
                score, reason = parse_response(resp.text)
                break
            except Exception as e:
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    backoff = 15 * (attempt + 1)
                    print(f"  rate-limited, backing off {backoff}s (attempt {attempt+1}/3)...", flush=True)
                    time.sleep(backoff)
                    continue
                score, reason = None, f"call_error: {type(e).__name__}: {e}"
                break

        results.append({
            "batch_position": row["batch_position"],
            "target_entity": row["target_entity"],
            "true_label": row["label"],
            "api_score": score,
            "api_reason": reason,
        })

        if (i + 1) % CHECKPOINT_EVERY == 0 or (i + 1) == len(rows):
            pd.DataFrame(results).to_parquet(OUT_PATH, index=False)
            n_valid = sum(1 for r in results if r["api_score"] is not None)
            print(f"  {i + 1}/{len(rows)} scored ({n_valid} valid), checkpointed", flush=True)

        time.sleep(SECONDS_BETWEEN_CALLS)

    out = pd.DataFrame(results)
    valid = out[out["api_score"].notna()].copy()
    print(f"\n{len(valid)}/{len(out)} valid scores", flush=True)

    valid["pred"] = valid["api_score"].apply(lambda s: "endorsement" if s >= 0 else "hostile")
    acc = (valid["pred"] == valid["true_label"]).mean()
    from sklearn.metrics import cohen_kappa_score
    kappa = cohen_kappa_score(valid["true_label"], valid["pred"])
    print(f"Thresholded at 0.0 -- accuracy: {acc:.4f}, kappa: {kappa:.4f}", flush=True)
    print("(reference: kaggle_benchmarks proxy frontier judge on 212 val rows = 0.8266 kappa)", flush=True)


if __name__ == "__main__":
    main()
