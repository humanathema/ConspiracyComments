#!/usr/bin/env python
"""prune_pre_2008_by_thread.py

Prunes the pre-2008 Wayback index targets (ats_metadata_pre_2008_complete.json)
at the THREAD ID level. If a thread ID is present anywhere in our Common Crawl
dataset, we already have its modern complete crawl (which is a cumulative superset
of any pre-2008 posts). Therefore, we can safely prune all page-level targets
for that thread ID, preventing the local Wayback scraper from downloading them.
"""

import os
import json

INDEX_PATH = "data/processed/ats_metadata_pre_2008_complete.json"
CC_COMMENTS_PATH = "data/processed/ats_comments_cc_complete.jsonl"


def prune_by_thread_id():
    print("=================================================================")
    print("Pruning Pre-2008 Index at the Thread ID Level...")
    print("=================================================================\n")

    if not os.path.exists(INDEX_PATH):
        print(f"Error: Pre-2008 index not found at: {INDEX_PATH}")
        return

    if not os.path.exists(CC_COMMENTS_PATH):
        print(f"Error: Common Crawl comments not found at: {CC_COMMENTS_PATH}")
        return

    # 1. Load current Wayback index targets
    print("Loading remaining pre-2008 index targets...")
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        targets = json.load(f)
    print(f"Total targets in current index: {len(targets):,}")

    # 2. Extract unique thread IDs from CC
    print("\nScanning Common Crawl comments for unique thread IDs...")
    cc_tids = set()
    count = 0
    with open(CC_COMMENTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                cc_tids.add(int(r["thread_id"]))
                count += 1
                if count % 1000000 == 0:
                    print(f"  Processed {count:,} CC comments...")
            except Exception:
                continue
    print(f"Found {len(cc_tids):,} unique thread IDs in Common Crawl.")

    # 3. Filter targets
    print("\nPruning targets whose Thread ID is already covered in CC...")
    pruned_targets = []
    skipped_count = 0
    skipped_tids = set()

    for t in targets:
        try:
            tid = int(t["thread_id"])
            if tid in cc_tids:
                skipped_count += 1
                skipped_tids.add(tid)
            else:
                pruned_targets.append(t)
        except Exception:
            pruned_targets.append(t)

    print(f"Skipped {skipped_count:,} targets across {len(skipped_tids):,} thread IDs.")
    print(f"Net remaining targets to scrape: {len(pruned_targets):,}")

    # 4. Overwrite index file
    print(f"\nSaving pruned index to: {INDEX_PATH} ...")
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(pruned_targets, f, indent=2)

    print("=================================================================")
    print(f"Pruning Complete! Successfully removed {skipped_count:,} redundant page downloads.")
    print("=================================================================")


if __name__ == "__main__":
    prune_by_thread_id()
