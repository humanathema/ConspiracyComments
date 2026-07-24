#!/usr/bin/env python
"""prune_pre_2008_index.py

Prunes the pre-2008 Wayback index targets (ats_metadata_pre_2008_complete.json)
by removing any (thread_id, page_num) pairs that have ALREADY been successfully
ingested and parsed inside the massive Common Crawl run (ats_comments_cc_complete.jsonl).
This allows the local Tor Wayback scraper to immediately skip 20,000+ pages.
"""

import os
import json

INDEX_PATH = "data/processed/ats_metadata_pre_2008_complete.json"
CC_COMMENTS_PATH = "data/processed/ats_comments_cc_complete.jsonl"


def prune_pre_2008_index():
    print("=================================================================")
    print("Pruning Pre-2008 Index with Common Crawl Ingestion Data...")
    print("=================================================================\n")

    if not os.path.exists(INDEX_PATH):
        print(f"Error: Pre-2008 index not found at: {INDEX_PATH}")
        return

    if not os.path.exists(CC_COMMENTS_PATH):
        print(f"Error: Common Crawl comments not found at: {CC_COMMENTS_PATH}")
        return

    # 1. Load pre-2008 targets
    print("Loading pre-2008 index targets...")
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        targets = json.load(f)
    print(f"Total targets in original pre-2008 index: {len(targets):,}")

    # Helper to format (thread_id, page_num) key safely
    def to_safe_key(tid, pg):
        try:
            tid_int = int(tid)
        except:
            tid_int = str(tid).strip()
        try:
            pg_int = int(pg)
        except:
            pg_int = str(pg).strip()
        return (tid_int, pg_int)

    # 2. Build set of already-ingested CC pages
    print("Scanning Common Crawl comments file for completed page keys...")
    cc_keys = set()
    count = 0
    with open(CC_COMMENTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                key = to_safe_key(r["thread_id"], r["page_num"])
                cc_keys.add(key)
                count += 1
                if count % 1000000 == 0:
                    print(f"  Processed {count:,} CC comments...")
            except Exception:
                continue
    print(f"Found {len(cc_keys):,} unique pages already parsed from Common Crawl.")

    # 3. Filter the pre-2008 targets
    print("\nFiltering pre-2008 targets...")
    pruned_targets = []
    skipped_count = 0

    for t in targets:
        key = to_safe_key(t["thread_id"], t["page_num"])
        if key in cc_keys:
            skipped_count += 1
        else:
            pruned_targets.append(t)

    print(f"Skipped {skipped_count:,} already completed targets.")
    print(f"Remaining targets to scrape: {len(pruned_targets):,}")

    # 4. Save the pruned index back to disk in-place
    print(f"\nSaving pruned index to: {INDEX_PATH} ...")
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(pruned_targets, f, indent=2)

    print("=================================================================")
    print("Pruning Complete! Your terminal scraper will automatically skip")
    print("these 20,000+ completed pages on its next boot!")
    print("=================================================================")


if __name__ == "__main__":
    prune_pre_2008_index()
