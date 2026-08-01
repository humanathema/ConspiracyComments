"""add_context_ids_to_active_learning_queue.py

Fixes a gap in build_active_learning_requeue.py: it never carried
parent_id/link_id through, so hitl_rater.py's "load surrounding context"
button (parent comment + sibling replies) never appears for this queue
(the button's JS is gated on `row.parent_id` being truthy).

Recovers parent_id/link_id by matching each queued row's full_text back
to its original source_file (same convention as every other cross-file
join tonight -- id is not reliable across variants, text is). Where the
source_file is a "*_REVIEW.csv" variant that itself lacks parent_id/
link_id (checked directly: the REVIEW quality-check variants drop these
columns), falls back to the corresponding base file -- same comments,
confirmed by build_stance_classifier_training_data.py's own PREFER_VARIANT
mapping ("checked by hand: same ids, same texts").
"""
import os

import pandas as pd

QUEUE_PATH = "data/hitl/queue_active_learning_requeue.csv"
HITL_DIR = "data/hitl"

# REVIEW variant -> base file with the same comments but real parent_id/link_id.
REVIEW_TO_BASE = {
    "queue_snowden_stance_quality_check_REVIEW.csv": "queue_snowden_stance_quality_check.csv",
    "queue_assange_stance_quality_check_REVIEW.csv": "queue_assange_stance_quality_check.csv",
    "queue_jones_short_stance_quality_check_REVIEW.csv": "queue_jones_short_stance_quality_check.csv",
    "queue_wikileaks_stance_quality_check_REVIEW.csv": "queue_wikileaks_stance_quality_check.csv",
    "queue_greenwald_stance_quality_check_REVIEW.csv": "queue_greenwald_stance_quality_check.csv",
}


def main():
    queue = pd.read_csv(QUEUE_PATH)
    n_already_rated = queue["human_stance"].notna().sum()
    if n_already_rated:
        raise RuntimeError(
            f"{n_already_rated} rows already rated -- replacing the id column now would orphan those "
            "responses (hitl_rater.py matches by id). Merge/back up existing ratings first."
        )

    queue["real_id"] = None
    queue["parent_id"] = None
    queue["link_id"] = None

    for source_file in queue["source_file"].unique():
        lookup_file = REVIEW_TO_BASE.get(source_file, source_file)
        path = os.path.join(HITL_DIR, lookup_file)
        if not os.path.exists(path):
            print(f"  [skip] {source_file} -> {lookup_file}: file not found")
            continue
        src = pd.read_csv(path, low_memory=False)
        if "parent_id" not in src.columns:
            print(f"  [skip] {lookup_file}: no parent_id column even in the fallback")
            continue

        mask = queue["source_file"] == source_file
        text_to_row = src.drop_duplicates(subset="full_text").set_index("full_text")[["id", "parent_id", "link_id"]]
        matched = queue.loc[mask, "full_text"].map(lambda t: text_to_row.loc[t] if t in text_to_row.index else None)
        n_matched = matched.notna().sum()
        for idx, vals in zip(queue.loc[mask].index, matched):
            if vals is not None:
                queue.at[idx, "real_id"] = vals["id"]
                queue.at[idx, "parent_id"] = vals["parent_id"]
                queue.at[idx, "link_id"] = vals["link_id"]
        print(f"  {source_file} (via {lookup_file}): {n_matched}/{mask.sum()} matched")

    # Swap the synthetic al_XXXX id for the real comment id (recovered
    # above) -- this is what lets the context cache (keyed by real ids)
    # and any future cross-referencing actually work. Safe: confirmed
    # above that nothing has been rated under the synthetic id yet.
    n_recovered = queue["real_id"].notna().sum()
    queue["id"] = queue["real_id"].where(queue["real_id"].notna(), queue["id"])
    queue = queue.drop(columns=["real_id"])

    queue.to_csv(QUEUE_PATH, index=False)
    n_total_matched = queue["parent_id"].notna().sum()
    print(f"\n{n_total_matched}/{len(queue)} rows now have parent_id/link_id.")
    print(f"{n_recovered}/{len(queue)} rows now use their real original id instead of the synthetic al_XXXX one.")
    print(f"Saved to {QUEUE_PATH}")


if __name__ == "__main__":
    main()
