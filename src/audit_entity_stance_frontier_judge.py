"""audit_entity_stance_frontier_judge.py

Adds a genuinely strong, independent third judge to the existing
entity-stance disagreement audit, via the kaggle_benchmarks model proxy
(Claude Sonnet 5 / Gemini 3.x / etc, confirmed working 2026-08-01,
$10/day quota, tobiasnash account -- see conversation for how this was
discovered and authenticated).

This is a genuine upgrade over the earlier Qwen2.5-1.5B/7B judges (which
found only 33-36% / 24.4% agreement with the production classifier) --
a much more capable model, still free within the daily quota.

Blind by design from the start (never shows predicted_label, bigmodel_label,
or judged_label to the frontier judge) -- this is exactly the fix the
earlier citation-stance anchoring bug needed after the fact (see
job_source_stance_tier2_v2_anchoring_finding_2026-07-28), applied here
from the outset instead of retrofitted.

Input: data/processed/entity_stance_bigmodel_judged.parquet (1,606 rows,
already has: predicted_label [classifier], judged_label [1.5B judge],
bigmodel_label [7B judge], bigmodel_confidence).
Output: data/processed/entity_stance_frontier_judged.parquet -- same
rows, plus frontier_label/frontier_reason, checkpointed incrementally
(every CHECKPOINT_EVERY rows) so a crash mid-run doesn't lose progress
(the exact lesson from mine_other_candidates.py's first, checkpoint-less
run this project already learned the hard way).

Usage:
    python src/audit_entity_stance_frontier_judge.py --limit 20   # smoke test first
    python src/audit_entity_stance_frontier_judge.py              # full 1,606-row run
"""
import argparse
import json
import os
import re
import subprocess
import time

import pandas as pd

INPUT_PATH = "data/processed/entity_stance_bigmodel_judged.parquet"
OUT_PATH = "data/processed/entity_stance_frontier_judged.parquet"
ENV_FILE = "/tmp/kbench_frontier_audit.env"
MODEL_NAME = "google/gemini-3.5-flash"  # cheap-but-capable default for bulk work; see conversation re: budget
CHECKPOINT_EVERY = 25
REAUTH_EVERY_SECONDS = 45 * 60  # refresh well before the 1-hour expiry

JUDGE_PROMPT_TEMPLATE = """You are evaluating a comment for its STANCE toward a specific entity, for a research project measuring epistemic credibility in online discussion.

Entity being evaluated: "{entity}"

Comment text (may be a fragment/window, not necessarily the full comment):
\"\"\"{text}\"\"\"

Classify the stance expressed toward "{entity}" in this text into exactly one of:
- hostile: the text is critical, attacking, or dismissive of this entity
- endorsement: the text is supportive, approving, or credits this entity favorably
- other: no clear stance either way (neutral mention, off-topic, purely factual/informational, or genuinely ambiguous)

Respond with ONLY a JSON object, no other text: {{"label": "hostile" | "endorsement" | "other", "reason": "one short sentence"}}
"""


def get_env():
    os.environ.pop("MODEL_PROXY_URL", None)
    os.environ.pop("MODEL_PROXY_API_KEY", None)
    subprocess.run(
        ["kaggle", "benchmarks", "auth", "-y", "--env-file", ENV_FILE],
        env={**os.environ, "KAGGLE_API_TOKEN": os.path.expanduser("~/.kaggle/access_token0")},
        check=True, capture_output=True, text=True,
    )
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                env[k] = v
    os.environ["MODEL_PROXY_URL"] = env["MODEL_PROXY_URL"]
    os.environ["MODEL_PROXY_API_KEY"] = env["MODEL_PROXY_API_KEY"]
    return time.time()


def parse_judge_response(raw):
    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        obj = json.loads(match.group(0) if match else raw)
        label = obj.get("label", "").strip().lower()
        if label not in ("hostile", "endorsement", "other"):
            return "parse_error", f"unrecognized label: {label!r}"
        return label, obj.get("reason", "")
    except Exception as e:
        return "parse_error", f"{type(e).__name__}: {raw[:200]}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Only judge the first N rows (smoke test)")
    parser.add_argument("--model", type=str, default=MODEL_NAME)
    args = parser.parse_args()

    df = pd.read_parquet(INPUT_PATH)
    if args.limit:
        df = df.head(args.limit).copy()
    print(f"Judging {len(df)} rows with {args.model} (blind -- classifier/small-judge labels never shown)", flush=True)

    last_auth = get_env()
    os.environ["LLM_DEFAULT"] = args.model  # kaggle_benchmarks/__init__.py eagerly loads this on import
    from kaggle_benchmarks.kaggle.models import load_model
    model = load_model(args.model)

    if os.path.exists(OUT_PATH) and not args.limit:
        done = pd.read_parquet(OUT_PATH)
        print(f"Resuming: {len(done)} rows already judged in a prior run.", flush=True)
        start_idx = len(done)
        results = done.to_dict("records")
    else:
        start_idx = 0
        results = []

    for i in range(start_idx, len(df)):
        if time.time() - last_auth > REAUTH_EVERY_SECONDS:
            print("  refreshing proxy auth...", flush=True)
            last_auth = get_env()
            model = load_model(args.model)

        row = df.iloc[i]
        prompt = JUDGE_PROMPT_TEMPLATE.format(entity=row["entity_key"], text=row["text_window"])
        try:
            raw = model.prompt(prompt)
            label, reason = parse_judge_response(raw)
        except Exception as e:
            label, reason = "call_error", f"{type(e).__name__}: {e}"

        rec = row.to_dict()
        rec["frontier_label"] = label
        rec["frontier_reason"] = reason
        results.append(rec)

        if (i + 1) % CHECKPOINT_EVERY == 0 or (i + 1) == len(df):
            pd.DataFrame(results).to_parquet(OUT_PATH, index=False)
            print(f"  {i + 1}/{len(df)} judged, checkpointed to {OUT_PATH}", flush=True)

    out = pd.DataFrame(results)
    out.to_parquet(OUT_PATH, index=False)

    valid = out[out["frontier_label"] != "parse_error"]
    print(f"\n{len(valid)}/{len(out)} valid judgments ({len(out) - len(valid)} parse/call errors)", flush=True)

    print("\n=== Frontier judge vs. classifier's predicted_label ===", flush=True)
    print((valid["frontier_label"] == valid["predicted_label"]).mean(), flush=True)
    print("\n=== Frontier judge vs. 1.5B judge (judged_label) ===", flush=True)
    print((valid["frontier_label"] == valid["judged_label"]).mean(), flush=True)
    print("\n=== Frontier judge vs. 7B judge (bigmodel_label) ===", flush=True)
    print((valid["frontier_label"] == valid["bigmodel_label"]).mean(), flush=True)
    print("\n=== Frontier judge label distribution ===", flush=True)
    print(valid["frontier_label"].value_counts(), flush=True)


if __name__ == "__main__":
    main()
