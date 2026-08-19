"""
Append one line to data/live_turn_log.jsonl -- the per-turn, cross-session
live activity log. NOT git-tracked (deliberately: high-frequency and
ephemeral, unlike data/session_registry.jsonl which stays git-tracked for
durable start/wrap-up milestones only). Exists so a session that's been
running for hours/days, or a fresh session picking up mid-stream, can see
what just happened elsewhere on this machine without either (a) scrolling
a bloated context window that isn't theirs to scroll, or (b) re-deriving
state that was already established seconds/minutes ago.

Append after any substantive turn -- a real finding, a file touched, a
decision made, a job started/finished. Skip pure no-ops (re-reading
something with nothing new to report). Err toward writing; a few extra
lines cost nothing, a missed real event costs the next session real time.

Usage:
    python3 tools/log_turn.py "session-label" "short note" [--touching a.py b.py] [--tag stance] [--tag vm]

Read the log directly with `tail -N data/live_turn_log.jsonl` -- no
script needed for reading, only for writing (keeps the schema/timestamp
format consistent across sessions that may not all remember the exact
field names).
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).parent.parent / "data" / "live_turn_log.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session_label", help="your best-known session name/id/title")
    ap.add_argument("note", help="a few words: what just happened this turn")
    ap.add_argument("--touching", nargs="*", default=[], help="files/scripts/VMs touched this turn")
    ap.add_argument("--tag", action="append", default=[], help="short topic tag, repeatable")
    args = ap.parse_args()

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session_label": args.session_label,
        "note": args.note,
        "touching": args.touching,
        "tags": args.tag,
    }

    LOG_PATH.parent.mkdir(exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"logged: {entry['ts']}  {args.session_label}  {args.note}")


if __name__ == "__main__":
    main()
