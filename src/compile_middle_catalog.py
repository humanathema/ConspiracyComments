#!/usr/bin/env python
"""compile_middle_catalog.py

Queries the Wayback Machine CDX API for thread captures (/forum/thread[ID]/pg[N])
specifically captured during the 2008-2012 "Middle Era".
Then, runs our high-performance thread-level pruning algorithm against the master
Common Crawl dataset to isolate ONLY the "dead threads" that are completely missing
from Common Crawl. Saves the targeted index.
"""

import os
import sys
import json
import re
import requests

OUTPUT_PATH = "data/processed/ats_metadata_middle_complete.json"
CC_COMMENTS_PATH = "data/processed/ats_comments_cc_complete.jsonl"
THREAD_REGEX = re.compile(r'/forum/thread(\d+)/pg(\d+|lastpost)?')


def compile_middle_catalog():
    print("=================================================================")
    print("Compiling 2008-2012 Middle-Era AboveTopSecret Catalog...")
    print("=================================================================\n")

    # 1. Fetch raw CDX records year-by-year with caching and retries
    import time
    cache_dir = "data/processed/cdx_raw_cache"
    os.makedirs(cache_dir, exist_ok=True)
    
    records = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for year in range(2008, 2013):
        cache_file = os.path.join(cache_dir, f"year_{year}.json")
        
        # Check cache
        if os.path.exists(cache_file):
            print(f"Loading raw CDX records for {year} from local cache...")
            with open(cache_file, "r", encoding="utf-8") as f:
                yearly_records = json.load(f)
            records.extend(yearly_records)
            print(f"  -> Successfully loaded {len(yearly_records):,} captures from cache.")
            continue
            
        print(f"Querying Wayback CDX API for {year} thread captures...")
        api_url = (
            "https://web.archive.org/cdx/search/cdx"
            "?url=abovetopsecret.com/forum/thread"
            "&matchType=prefix"
            "&output=json"
            f"&from={year}0101"
            f"&to={year}1231"
        )
        
        # Robust Retry loop
        max_attempts = 3
        success = False
        
        for attempt in range(max_attempts):
            try:
                # Use a generous 180s timeout
                response = requests.get(api_url, headers=headers, timeout=180)
                response.raise_for_status()
                data = response.json()
                
                if data and len(data) > 1:
                    yearly_records = data[1:]
                else:
                    yearly_records = []
                    
                # Cache results immediately
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(yearly_records, f)
                    
                records.extend(yearly_records)
                print(f"  -> Successfully retrieved and cached {len(yearly_records):,} captures for {year}.")
                success = True
                break
            except Exception as e:
                print(f"  Warning: Attempt {attempt+1}/{max_attempts} failed for {year}: {e}")
                if attempt < max_attempts - 1:
                    sleep_time = (attempt + 1) * 15
                    print(f"  Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    print(f"Error: All {max_attempts} attempts failed for {year}.")
                    sys.exit(1)

    if not records:
        print("No middle-era captures found!")
        sys.exit(0)

    print(f"\nRetrieved {len(records):,} total raw middle-era captures across 2008-2012 from Wayback.")

    # 2. Extract unique (thread_id, page_num) pairs
    raw_catalog = []
    malformed_count = 0

    for row in records:
        timestamp = row[1]
        original_url = row[2]
        mimetype = row[3]
        statuscode = row[4]
        digest = row[5]

        # Filter for HTML text pages only
        if mimetype and "text/html" not in mimetype.lower():
            continue
        if statuscode != "200":
            continue

        # Prevent special character glitched URLs
        if '%' in original_url or ' ' in original_url or '<' in original_url:
            continue

        match = THREAD_REGEX.search(original_url)
        if not match:
            malformed_count += 1
            continue

        try:
            tid = int(match.group(1))
            pg_str = match.group(2)
            if pg_str == 'lastpost' or not pg_str:
                pg_num = 1
            else:
                pg_num = int(pg_str)
        except ValueError:
            malformed_count += 1
            continue

        raw_catalog.append({
            'thread_id': tid,
            'page_num': pg_num,
            'timestamp': timestamp,
            'original_url': original_url,
            'statuscode': statuscode,
            'mimetype': mimetype,
            'digest': digest
        })

    print(f"Discovered {len(raw_catalog):,} valid thread page captures.")

    # 3. Load Common Crawl thread IDs for pruning
    cc_tids = set()
    if os.path.exists(CC_COMMENTS_PATH):
        print("\nScanning Common Crawl comments for unique thread IDs to prune...")
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
        print(f"Loaded {len(cc_tids):,} unique thread IDs from Common Crawl.")
    else:
        print(f"\nWarning: Common Crawl comments not found at: {CC_COMMENTS_PATH}. Pruning skipped.")

    # 4. Perform Thread-Level Pruning & Deduplication
    print("\nDeduplicating index and pruning thread IDs present in Common Crawl...")
    seen = {}
    skipped_cc_count = 0
    skipped_cc_tids = set()

    for item in raw_catalog:
        tid = item['thread_id']
        pg_num = item['page_num']

        # Prune if thread ID is already fully parsed in Common Crawl
        if tid in cc_tids:
            skipped_cc_count += 1
            skipped_cc_tids.add(tid)
            continue

        # Keep the most stable or latest snapshot for deduplication
        key = (tid, pg_num)
        if key not in seen or int(item['timestamp']) > int(seen[key]['timestamp']):
            seen[key] = item

    final_catalog = list(seen.values())

    print("\n=================================================================")
    print("Middle-Era Index Compilation & Pruning Complete!")
    print(f"Skipped malformed thread URLs:            {malformed_count:,}")
    print(f"Pruned CC-covered targets:                {skipped_cc_count:,} across {len(skipped_cc_tids):,} threads")
    print(f"Net remaining TARGETS to scrape:          {len(final_catalog):,}")
    print(f"Saving compiled index to:                 {OUTPUT_PATH}")
    print("=================================================================")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(final_catalog, f, indent=2)

    return final_catalog


if __name__ == "__main__":
    compile_middle_catalog()
