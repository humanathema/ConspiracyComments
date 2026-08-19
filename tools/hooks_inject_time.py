"""
UserPromptSubmit hook: injects the real current date/time into context on
every turn, so a session can never lose track of elapsed time without
remembering to run `date` itself -- this is the harness-enforced fix for
the "tonight" problem (see data/live_turn_log.jsonl and CLAUDE.md's
coordination-discipline section for the underlying failure this closes).

Also does a lightweight staleness check against data/live_turn_log.jsonl:
if more than STALE_MINUTES have passed since the last entry, adds a
one-line nudge to consider logging -- not a hard requirement (log_turn.py
needs human/model judgment about what's worth logging), just a periodic
reminder so the discipline doesn't silently lapse over a long session.

Reads nothing from stdin (UserPromptSubmit hooks don't need the payload
for this). Prints one JSON object to stdout per Claude Code's hook
output contract.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

STALE_MINUTES = 20
LOG_PATH = Path("data/live_turn_log.jsonl")


def main():
    now = datetime.now(timezone.utc)
    ctx = (
        f"Current real date/time: {now.strftime('%A, %Y-%m-%d %H:%M:%S UTC')}. "
        "If you're about to say things like today/tonight/earlier/just now, "
        "verify against this rather than assuming."
    )

    if LOG_PATH.exists():
        try:
            lines = LOG_PATH.read_text().strip().splitlines()
            if lines:
                last = json.loads(lines[-1])
                last_ts = datetime.fromisoformat(last["ts"])
                diff_min = int((now - last_ts).total_seconds() / 60)
                if diff_min > STALE_MINUTES:
                    ctx += (
                        f" It's been ~{diff_min} min since the last "
                        "data/live_turn_log.jsonl entry -- if anything substantive "
                        "happened since, consider: python3 tools/log_turn.py "
                        '"<label>" "<note>".'
                    )
        except Exception:
            pass  # never block the turn over a malformed/missing log

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ctx,
        }
    }))


if __name__ == "__main__":
    main()
