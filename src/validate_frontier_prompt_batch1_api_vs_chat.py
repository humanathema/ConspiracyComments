"""validate_frontier_prompt_batch1_api_vs_chat.py

Direct API-vs-chat comparison, isolating delivery mechanism as the
variable (not batch size, not reasoning depth, not ground-truth quality):
same 90 rows (gemini_neutral_audit_batch1), same revised calibrated
prompt, sent as ONE batch API call instead of pasted into a Gemini chat
conversation. Compared directly against the already-recorded chat
verdicts for this exact batch (the "batch 1 revised" pass).
"""
import subprocess

import pandas as pd
from sklearn.metrics import cohen_kappa_score, classification_report
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials

PROJECT = "tobiasnash-vertex-frontier"
ACCOUNT = "contact@tobiasnash.co.nz"
LOCATION = "global"
MODEL_NAME = "gemini-3.5-flash"

# the actual chat verdicts already recorded for gemini_neutral_audit_batch1,
# "revised prompt" pass -- batch_position -> verdict
CHAT_VERDICTS = {
    1: "ambiguous", 2: "ambiguous", 3: "neutral", 4: "ambiguous", 5: "ambiguous",
    6: "neutral", 7: "ambiguous", 8: "neutral", 9: "ambiguous", 10: "ambiguous",
    11: "neutral", 12: "neutral", 13: "ambiguous", 14: "ambiguous", 15: "neutral",
    16: "neutral", 17: "neutral", 18: "ambiguous", 19: "neutral", 20: "neutral",
    21: "endorsement", 22: "neutral", 23: "endorsement", 24: "hostile", 25: "ambiguous",
    26: "ambiguous", 27: "ambiguous", 28: "ambiguous", 29: "ambiguous", 30: "neutral",
    31: "neutral", 32: "neutral", 33: "neutral", 34: "neutral", 35: "ambiguous",
    36: "neutral", 37: "ambiguous", 38: "ambiguous", 39: "neutral", 40: "ambiguous",
    41: "neutral", 42: "endorsement", 43: "neutral", 44: "ambiguous", 45: "ambiguous",
    46: "ambiguous", 47: "ambiguous", 48: "neutral", 49: "neutral", 50: "ambiguous",
    51: "neutral", 52: "ambiguous", 53: "ambiguous", 54: "neutral", 55: "endorsement",
    56: "neutral", 57: "neutral", 58: "ambiguous", 59: "ambiguous", 60: "neutral",
    61: "neutral", 62: "neutral", 63: "neutral", 64: "ambiguous", 65: "neutral",
    66: "ambiguous", 67: "hostile", 68: "ambiguous", 69: "hostile", 70: "neutral",
    71: "neutral", 72: "ambiguous", 73: "neutral", 74: "neutral", 75: "ambiguous",
    76: "neutral", 77: "neutral", 78: "neutral", 79: "neutral", 80: "neutral",
    81: "neutral", 82: "neutral", 83: "ambiguous", 84: "ambiguous", 85: "ambiguous",
    86: "neutral", 87: "ambiguous", 88: "ambiguous", 89: "neutral", 90: "endorsement",
}

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


def get_client():
    token = subprocess.check_output(
        ["gcloud", "auth", "print-access-token", f"--account={ACCOUNT}"]
    ).decode().strip()
    creds = Credentials(token=token)
    return genai.Client(vertexai=True, project=PROJECT, location=LOCATION, credentials=creds)


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


def main():
    key = pd.read_csv("data/hitl/gemini_neutral_audit_batch1_KEY_do_not_paste.csv")
    key = key.sort_values("batch_position").reset_index(drop=True)

    rows_block = "\n".join(
        f'{row["batch_position"]}. Entity: "{row["target_entity"]}"\n   Text: """{row["text"]}"""'
        for _, row in key.iterrows()
    )
    prompt = PROMPT_HEADER.format(rows_block=rows_block, n=len(key))

    client = get_client()
    resp = client.models.generate_content(
        model=MODEL_NAME, contents=prompt,
        config=types.GenerateContentConfig(temperature=0, thinking_config=types.ThinkingConfig(thinking_budget=4000)),
    )
    api_verdicts = parse_batch_response(resp.text)
    print(f"{len(api_verdicts)}/{len(key)} API verdicts parsed", flush=True)

    rows = []
    for _, row in key.iterrows():
        bp = row["batch_position"]
        rows.append({
            "batch_position": bp, "text": row["text"],
            "chat_verdict": CHAT_VERDICTS.get(bp),
            "api_verdict": api_verdicts.get(bp),
        })
    out = pd.DataFrame(rows)
    out.to_csv("/tmp/batch1_api_vs_chat.csv", index=False)

    valid = out[out["api_verdict"].notna() & out["chat_verdict"].notna()]
    print(f"\nAgreement (API vs chat, same 90 rows, same prompt): {(valid['api_verdict']==valid['chat_verdict']).mean()*100:.1f}%")
    kappa = cohen_kappa_score(valid["chat_verdict"], valid["api_verdict"])
    print(f"kappa (chat vs API, treating chat as reference): {kappa:.4f}")
    print("\nAPI verdict distribution:", api_verdicts and pd.Series(list(api_verdicts.values())).value_counts().to_dict())
    print("Chat verdict distribution:", pd.Series(list(CHAT_VERDICTS.values())).value_counts().to_dict())
    print()
    print(classification_report(valid["chat_verdict"], valid["api_verdict"]))


if __name__ == "__main__":
    main()
