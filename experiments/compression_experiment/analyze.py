"""
Aggregate log.jsonl once enough rounds exist: mean fidelity scores by
budget level, and a dump of encoding_notes grouped by score band (high
vs low semantic_cosine) so a human/session can eyeball which tricks
correlate with high fidelity at high compression.

Usage: python3 analyze.py
"""
import json
from collections import defaultdict
from pathlib import Path

LOG = Path(__file__).parent / "log.jsonl"


def main():
    rounds = defaultdict(dict)  # (message_id, budget_level) -> merged fields
    with open(LOG) as f:
        for line in f:
            row = json.loads(line)
            if "_schema" in row:
                continue
            key = (row.get("message_id"), row.get("budget_level"))
            rounds[key].update({k: v for k, v in row.items() if v is not None})

    scored = [r for r in rounds.values() if r.get("scores")]
    if not scored:
        print("No scored rounds yet. Run score.py on some completed rounds first.")
        return

    print(f"{len(scored)} scored rounds out of {len(rounds)} total rounds logged.\n")

    by_budget = defaultdict(list)
    for r in scored:
        by_budget[r["budget_level"]].append(r["scores"]["semantic_cosine"])

    print("Mean semantic_cosine by budget_level (higher budget = less compression):")
    for budget in sorted(by_budget, key=lambda b: float(b), reverse=True):
        vals = by_budget[budget]
        print(f"  budget={budget}: mean={sum(vals)/len(vals):.3f}  n={len(vals)}")

    scored.sort(key=lambda r: r["scores"]["semantic_cosine"], reverse=True)
    top = scored[:5]
    bottom = scored[-5:]

    print("\nTop 5 rounds by fidelity (what worked):")
    for r in top:
        print(f"  [{r['message_id']} @ {r['budget_level']}] score={r['scores']['semantic_cosine']:.3f}")
        print(f"    notes: {r.get('encoding_notes', '(none)')}")

    print("\nBottom 5 rounds by fidelity (what didn't):")
    for r in bottom:
        print(f"  [{r['message_id']} @ {r['budget_level']}] score={r['scores']['semantic_cosine']:.3f}")
        print(f"    notes: {r.get('encoding_notes', '(none)')}")


if __name__ == "__main__":
    main()
