"""
build_ordinal_targets.py

Converts raw per-rater stance votes (irr_stance_shared__tobias_copy.csv) into a
continuous, disagreement-aware training target, instead of collapsing straight
to a majority-vote 3-class label.

Rationale
---------
The current pipeline collapses 3 raters' votes into a single nominal label
(hostile / other / endorsement) and throws away *how much* the raters agreed.
An item where 2/3 raters said "hostile" is not the same signal as an item
where 3/3 said "hostile" -- but both currently collapse to the identical
training label. This script recovers that lost signal as a continuous score
on the hostile <-> endorsing axis, usable directly as a regression target
or as soft labels for an ordinal-loss (CORAL/CORN) head.

Scoring scheme
--------------
Each individual vote is mapped onto a [-1, +1] axis:
    hostile      -> -1.0
    ambiguous    ->  0.0   (collapsed into "other", matching irr_summary.md's
    neutral      ->  0.0    3-class scheme, which is the more reliable one --
                             Fleiss' kappa 0.484 vs 0.402 for the 4-class split)
    endorsement  -> +1.0

target_score = mean(individual scores)               in [-1, +1]
target_std   = population std of individual scores    (0 = unanimous)

target_score is a directly usable continuous regression target. target_std
(or n_raters / agreement_level) can be used as a per-item confidence weight
in the loss function, so noisy/disputed items contribute less than clean,
unanimous ones -- rather than being silently treated as equally trustworthy
as a 3/3 unanimous item.

Usage
-----
    python3 build_ordinal_targets.py \
        --input irr_stance_shared__tobias_copy.csv \
        --output ordinal_targets.csv

The output has one row per item (per id, note: two rows share a base comment
id when a comment mentions two tracked entities, e.g. "ceg4rgh__greenwald" /
"ceg4rgh__snowden" -- these are kept as distinct items, since they are
distinct (comment, entity) stance judgments).
"""

import argparse
import csv
import statistics
import sys

LABEL_SCORES = {
    "hostile": -1.0,
    "ambiguous": 0.0,
    "neutral": 0.0,
    "endorsement": 1.0,
}


def load_rater_columns(header):
    """Rater columns are every named column after 'id' up to the first blank
    header (the source file has trailing empty columns from spreadsheet
    scratch work)."""
    raters = []
    for col in header[1:]:
        if col.strip() == "":
            break
        raters.append(col)
    return raters


def process(input_path, output_path):
    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        raters = load_rater_columns(header)
        rows = [row for row in reader if row and row[0].strip()]

    out_rows = []
    skipped = 0
    for row in rows:
        item_id = row[0].strip()
        votes = {}
        for i, rater in enumerate(raters, start=1):
            val = row[i].strip().lower() if i < len(row) else ""
            if val:
                votes[rater] = val

        if len(votes) < 2:
            # Need at least 2 raters to say anything about agreement.
            skipped += 1
            continue

        scores = []
        unmapped = False
        for v in votes.values():
            if v not in LABEL_SCORES:
                unmapped = True
                break
            scores.append(LABEL_SCORES[v])
        if unmapped:
            skipped += 1
            continue

        target_score = sum(scores) / len(scores)
        target_std = statistics.pstdev(scores) if len(scores) > 1 else 0.0

        n_hostile = sum(1 for s in scores if s == -1.0)
        n_other = sum(1 for s in scores if s == 0.0)
        n_endorse = sum(1 for s in scores if s == 1.0)
        n_raters = len(scores)

        counts = {"hostile": n_hostile, "other": n_other, "endorsement": n_endorse}
        majority_label = max(counts, key=counts.get)
        majority_count = counts[majority_label]

        if majority_count == n_raters:
            agreement_level = "unanimous"
        elif majority_count > n_raters / 2:
            agreement_level = "majority"
        else:
            agreement_level = "split"  # e.g. 1/1/1 on a 3-rater item

        out_rows.append(
            {
                "id": item_id,
                "n_raters": n_raters,
                **{f"vote_{r}": votes.get(r, "") for r in raters},
                "target_score": round(target_score, 4),
                "target_std": round(target_std, 4),
                "n_hostile": n_hostile,
                "n_other": n_other,
                "n_endorsement": n_endorse,
                "majority_label": majority_label,
                "agreement_level": agreement_level,
            }
        )

    fieldnames = list(out_rows[0].keys()) if out_rows else []
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Wrote {len(out_rows)} items to {output_path} ({skipped} skipped: <2 raters or unmapped label)")

    if out_rows:
        by_level = {}
        for r in out_rows:
            by_level[r["agreement_level"]] = by_level.get(r["agreement_level"], 0) + 1
        print("Agreement breakdown:", by_level)
        mean_std = statistics.mean(r["target_std"] for r in out_rows)
        print(f"Mean target_std across items: {mean_std:.3f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    process(args.input, args.output)
