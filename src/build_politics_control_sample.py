"""build_politics_control_sample.py

Pulls a temporally-stratified r/politics comment sample via the Arctic
Shift API (https://arctic-shift.photon-reddit.com), to replace
r/TopMindsOfReddit as the external control subreddit in the refined
regression comparison (r/TopMindsOfReddit was confirmed invalid: it's a
mockery/meta-community that quotes and ridicules r/conspiracy content,
not a neutral baseline -- see ANTIGRAVITY_HANDOFF.md). r/AskReddit was
also rejected: that sample was a single-day snapshot, temporally biased.

METHOD (fully deterministic, no judgment calls left open):
  - MONTHS below are 20 evenly-spaced months spanning the exact same
    range as data/processed/monthly_baselines/ (2008-07 through
    2026-06, 216 months total) -- computed once via
    `idx = sorted(set(round(i*(n-1)/19) for i in range(20)))` against
    the sorted month list, then hardcoded here so re-running this
    script never silently drifts to a different sample of months.
  - For each month, page backward from the end of the month using the
    `before` cursor (Arctic Shift returns newest-first), collecting
    comments until either TARGET_PER_MONTH raw comments are collected
    or the month is exhausted (an empty page, or `before` drops below
    the month start).
  - Checkpointed per month: writes to
    data/raw/r_politics_by_month/{month}.jsonl and skips any month
    whose file already exists non-empty -- safe to re-run/resume after
    an interruption (rate limit ban, network drop, out of budget).
  - After all months are present on disk, concatenates them into
    data/raw/r_politics_comments.jsonl (matches the naming convention
    of data/raw/r_askreddit_comments.jsonl / r_topmindsofreddit_comments.jsonl
    so it's a drop-in input to src/score_comparisons.py).

TO RUN standalone:
    python3.12 src/build_politics_control_sample.py

TO RESUME after interruption: just re-run the same command. Completed
months are skipped automatically.

NEXT STEP after this script finishes (not automated here, see
ANTIGRAVITY_HANDOFF.md for the exact commands): run
src/score_comparisons.py with "politics" added to its corpora dict
(already added, see bottom of that file) to produce
data/processed/comparison_politics_scored.parquet, then run
src/rerun_refined_regressions_v2.py.
"""
import json
import os
import time
import calendar
from datetime import datetime, timezone

import requests

MONTHS = [
    "2008-07", "2009-06", "2010-06", "2011-05", "2012-04", "2013-04",
    "2014-03", "2015-02", "2016-02", "2017-01", "2017-12", "2018-11",
    "2019-11", "2020-10", "2021-09", "2022-09", "2023-08", "2024-07",
    "2025-07", "2026-06",
]

SUBREDDIT = "politics"
TARGET_PER_MONTH = 7000
PAGE_LIMIT = 100  # Arctic Shift max allowed
FIELDS = "id,author,score,parent_id,link_id,created_utc,body"
# NOTE: "controversiality" is NOT a valid Arctic Shift field (confirmed via a
# live 400 response on 2026-07-15: "'controversiality' is not a valid
# field"). score_comparisons.py's schema expects a controversiality column
# (defaulted to 0 via COALESCE/try_cast if absent/null), so we inject a
# literal 0 for every row when saving below rather than requesting it from
# the API.
BASE_URL = "https://arctic-shift.photon-reddit.com/api/comments/search"
USER_AGENT = "AcademicDissertationContextAudit/2.0 (Massey University r/politics control sample)"

OUT_DIR = "data/raw/r_politics_by_month"
FINAL_PATH = "data/raw/r_politics_comments.jsonl"

MAX_RETRIES = 5
POLITE_DELAY_SECONDS = 1.0


def month_bounds_utc(month_str):
    year, month = int(month_str[:4]), int(month_str[5:7])
    start = int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp())
    last_day = calendar.monthrange(year, month)[1]
    end = int(datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc).timestamp())
    return start, end


def fetch_page(after_ts, before_ts):
    params = {
        "subreddit": SUBREDDIT,
        "after": after_ts,
        "before": before_ts,
        "limit": PAGE_LIMIT,
        "fields": FIELDS,
    }
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(BASE_URL, params=params, headers=headers, timeout=30)
            if resp.status_code == 200:
                payload = resp.json()
                data = payload.get("data")
                if data is None:
                    print(f"    API error payload: {payload.get('error')}")
                    return []
                return data
            else:
                print(f"    HTTP {resp.status_code}, retrying (attempt {attempt+1}/{MAX_RETRIES})...")
                time.sleep(5 + attempt * 5)
        except requests.exceptions.RequestException as e:
            print(f"    Request failed: {e}, retrying (attempt {attempt+1}/{MAX_RETRIES})...")
            time.sleep(5 + attempt * 5)
    print(f"    Giving up on this page after {MAX_RETRIES} attempts.")
    return []


def pull_month(month_str):
    out_path = os.path.join(OUT_DIR, f"{month_str}.jsonl")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        with open(out_path) as f:
            n = sum(1 for _ in f)
        print(f"[{month_str}] already done ({n} rows) -- skipping")
        return

    month_start, month_end = month_bounds_utc(month_str)
    cursor_before = month_end
    collected = []
    seen_ids = set()

    print(f"[{month_str}] pulling (target {TARGET_PER_MONTH})...")
    while len(collected) < TARGET_PER_MONTH:
        page = fetch_page(month_start, cursor_before)
        if not page:
            print(f"[{month_str}] exhausted at {len(collected)} rows")
            break

        new_this_page = 0
        oldest_ts_this_page = cursor_before
        for row in page:
            ts = row.get("created_utc")
            if ts is not None and ts < oldest_ts_this_page:
                oldest_ts_this_page = ts
            rid = row.get("id")
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            body = row.get("body")
            if not body or body in ("[deleted]", "[removed]") or len(body) <= 50:
                continue
            row["controversiality"] = 0
            collected.append(row)
            new_this_page += 1

        if oldest_ts_this_page >= cursor_before:
            # no forward progress possible, avoid infinite loop
            print(f"[{month_str}] cursor stalled, stopping at {len(collected)} rows")
            break
        cursor_before = oldest_ts_this_page - 1
        if cursor_before < month_start:
            print(f"[{month_str}] reached month start at {len(collected)} rows")
            break

        time.sleep(POLITE_DELAY_SECONDS)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        for row in collected:
            f.write(json.dumps(row) + "\n")
    print(f"[{month_str}] saved {len(collected)} usable comments to {out_path}")


def concatenate_final():
    os.makedirs(os.path.dirname(FINAL_PATH), exist_ok=True)
    total = 0
    with open(FINAL_PATH, "w") as out_f:
        for month_str in MONTHS:
            month_path = os.path.join(OUT_DIR, f"{month_str}.jsonl")
            if not os.path.exists(month_path):
                print(f"WARNING: {month_path} missing, cannot finalize -- run pull_month for all months first")
                return False
            with open(month_path) as in_f:
                for line in in_f:
                    out_f.write(line)
                    total += 1
    print(f"\nConcatenated {total} total comments across {len(MONTHS)} months into {FINAL_PATH}")
    return True


def main():
    print(f"=== Building r/{SUBREDDIT} temporally-stratified control sample ===")
    print(f"Months ({len(MONTHS)}): {MONTHS}")
    for month_str in MONTHS:
        pull_month(month_str)
    ok = concatenate_final()
    if ok:
        print("\nDone. Next: python3.12 src/score_comparisons.py (politics entry already registered)")
    else:
        print("\nIncomplete -- re-run this script to resume the missing months.")


if __name__ == "__main__":
    main()
