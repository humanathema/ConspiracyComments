"""validate_frontier_prompt_against_ground_truth.py

Direct quality gate for the frontier judge used to split the AI-silver
"other" rows (probe_entity_conditioned_neutral_ambiguous_frontier.py):
scores the SAME 446-row hand-corrected ground-truth set (joint
hand-review + Gemini-calibrated batch pass) with the identical
prompt/model, and computes Cohen's kappa against known-good labels.
This is the direct test -- whether the downstream retrain's kappa
improves is a confounded, slow, indirect signal on its own.

Input: /tmp/neutral_ambiguous_corrected.csv (text, target_entity, corrected)
Output: prints kappa + classification report against ground truth.
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

First, in ONE short sentence, identify any evaluative or suspicion-toned language directed at the entity specifically (or note there is none). Then, on a new line by itself, write "VERDICT: " followed by exactly one word: neutral, ambiguous, hostile, or endorsement.
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


def parse_response(raw):
    text = raw.strip().lower()
    # look for "verdict: <word>" specifically first, on its own line
    for line in text.splitlines():
        if "verdict" in line:
            for v in VALID:
                if v in line:
                    return v
    # fallback: last word-shaped match anywhere in the response
    for v in VALID:
        if v in text:
            return v
    return None


def score_one(row):
    prompt = PROMPT_TEMPLATE.format(entity=row["target_entity"], text=row["text"])
    client = get_client()
    verdict = None
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME, contents=prompt,
                config=types.GenerateContentConfig(temperature=0, thinking_config=types.ThinkingConfig(thinking_budget=200)),
            )
            verdict = parse_response(resp.text)
            break
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(10 * (attempt + 1))
                continue
            break
    return {"text": row["text"], "true_label": row["corrected"], "frontier_verdict": verdict}


def main():
    df = pd.read_csv("/tmp/neutral_ambiguous_corrected.csv")
    print(f"Scoring {len(df)} ground-truth rows with the production frontier prompt...", flush=True)

    results = []
    with ThreadPoolExecutor(max_workers=15) as pool:
        futures = [pool.submit(score_one, row) for _, row in df.iterrows()]
        for i, fut in enumerate(as_completed(futures), 1):
            results.append(fut.result())
            if i % 50 == 0 or i == len(futures):
                print(f"  {i}/{len(futures)} scored", flush=True)

    out = pd.DataFrame(results)
    out.to_csv("/tmp/frontier_ground_truth_validation.csv", index=False)
    valid = out[out["frontier_verdict"].notna()]
    print(f"\n{len(valid)}/{len(out)} valid verdicts.")

    kappa = cohen_kappa_score(valid["true_label"], valid["frontier_verdict"])
    print(f"\n=== Frontier judge vs ground-truth kappa: {kappa:.4f} ===")
    print(classification_report(valid["true_label"], valid["frontier_verdict"]))


if __name__ == "__main__":
    main()
