#!/usr/bin/env python
import json
import os

COMMENTS_PATH = "data/processed/ats_comments_cc_complete.jsonl"
INDEX_PATH = "data/processed/ats_cc_index_complete.json"

def compare_succeed_fail():
    print("==========================================")
    print("Comparing Succeeding and Failing 2016 Targets...")
    print("==========================================\n")
    
    # 1. Load succeeded pages from 2016
    succeeded_pages = set()
    with open(COMMENTS_PATH) as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                succeeded_pages.add((r['thread_id'], r['page_num']))
                
    # 2. Load all targets from index and find 2016 succeeded/failed targets
    with open(INDEX_PATH) as f:
        targets = json.load(f)
        
    succeeded_targets_2016 = []
    failed_targets_2016 = []
    
    for t in targets:
        if "CC-MAIN-2016" in t['filename']:
            key = (t['thread_id'], t['page_num'])
            if key in succeeded_pages:
                succeeded_targets_2016.append(t)
            else:
                failed_targets_2016.append(t)
                
    print(f"2016 Targets Summary:")
    print(f"  - Total: {len(succeeded_targets_2016) + len(failed_targets_2016):,}")
    print(f"  - Succeeded: {len(succeeded_targets_2016):,}")
    print(f"  - Failed: {len(failed_targets_2016):,}")
    
    # Print 3 succeeded sample targets
    print("\n--- 3 Succeeded 2016 Targets ---")
    for t in succeeded_targets_2016[:3]:
        print(f"  URL: {t['url']} | Offset: {t['offset']} | Length: {t['length']} | WARC: {t['filename']}")
        
    # Print 3 failed sample targets
    print("\n--- 3 Failed 2016 Targets ---")
    for t in failed_targets_2016[:3]:
        print(f"  URL: {t['url']} | Offset: {t['offset']} | Length: {t['length']} | WARC: {t['filename']}")

if __name__ == "__main__":
    compare_succeed_fail()
