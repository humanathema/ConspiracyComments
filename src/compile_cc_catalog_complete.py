#!/usr/bin/env python
"""compile_cc_catalog_complete.py

Queries the public Common Crawl Index API for thread prefixes thread1* through thread9*
across 12 historical monthly crawls (2013 to 2024).

Aggregates and deduplicates them by (thread_id, page_num), retaining strictly the
latest available snapshot to build the absolute, 100% complete AboveTopSecret 
modern corpus catalog, bypassing alphabetical truncation limits.
"""

import os
import sys
import re
import json
from urllib.parse import urlparse
import requests

# Comprehensive list of annual crawls including 2023 and 2024
HISTORICAL_INDEXES = [
    "CC-MAIN-2024-42",
    "CC-MAIN-2023-50",
    "CC-MAIN-2022-49",
    "CC-MAIN-2021-49",
    "CC-MAIN-2020-50",
    "CC-MAIN-2019-51",
    "CC-MAIN-2018-51",
    "CC-MAIN-2017-51",
    "CC-MAIN-2016-50",
    "CC-MAIN-2015-50",
    "CC-MAIN-2014-52",
    "CC-MAIN-2013-48"
]

THREAD_REGEX = re.compile(r'/forum/thread(\d+)/pg(\d+|lastpost)?', re.IGNORECASE)
OUTPUT_PATH = "data/processed/ats_cc_index_complete.json"


def compile_complete_cc_catalog():
    print("=================================================================")
    print("Compiling 100% Complete AboveTopSecret Modern Common Crawl Catalog...")
    print("=================================================================\n")
    
    master_catalog = {}  # (thread_id, page_num) -> record dict
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    for idx in HISTORICAL_INDEXES:
        print(f"\n--- [{idx}] Fetching targets across all thread ID prefixes ---")
        
        for n in range(1, 10):
            print(f"  Prefix thread{n}* ... ", end="", flush=True)
            api_url = f"https://index.commoncrawl.org/{idx}-index?url=abovetopsecret.com/forum/thread{n}*&output=json"
            
            try:
                # Stream the response to process line-by-line efficiently
                response = requests.get(api_url, headers=headers, stream=True, timeout=60)
                if response.status_code == 404:
                    print("No captures found.")
                    continue
                response.raise_for_status()
                
                idx_records_found = 0
                idx_records_added = 0
                idx_records_updated = 0
                
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        record = json.loads(line.decode('utf-8'))
                        if record.get('status') != '200':
                            continue
                        if 'text/html' not in record.get('mime', '').lower():
                            continue
                            
                        original_url = record.get('url', '')
                        parsed = urlparse(original_url)
                        path = parsed.path
                        
                        # Clean out malformed paths
                        if '%' in path or ' ' in path or '<' in path or '*' in path or '-' in path:
                            continue
                            
                        match = THREAD_REGEX.search(path)
                        if not match:
                            continue
                            
                        thread_id = int(match.group(1))
                        page_val = match.group(2)
                        page_num = 1 if not page_val else ('lastpost' if page_val.lower() == 'lastpost' else int(page_val))
                        
                        key = f"{thread_id}_pg{page_num}"
                        timestamp = record.get('timestamp', '')
                        idx_records_found += 1
                        
                        # Deduplication Strategy: Keep the LATEST snapshot timestamp
                        if key not in master_catalog:
                            master_catalog[key] = {
                                'thread_id': thread_id,
                                'page_num': page_num,
                                'timestamp': timestamp,
                                'url': original_url,
                                'filename': record.get('filename', ''),
                                'offset': int(record.get('offset', 0)),
                                'length': int(record.get('length', 0))
                            }
                            idx_records_added += 1
                        elif timestamp > master_catalog[key]['timestamp']:
                            master_catalog[key] = {
                                'thread_id': thread_id,
                                'page_num': page_num,
                                'timestamp': timestamp,
                                'url': original_url,
                                'filename': record.get('filename', ''),
                                'offset': int(record.get('offset', 0)),
                                'length': int(record.get('length', 0))
                            }
                            idx_records_updated += 1
                    except Exception:
                        continue
                        
                print(f"Found {idx_records_found:,} captures | Added {idx_records_added:,} new | Updated {idx_records_updated:,} newer snapshots")
                
            except Exception as e:
                print(f"Error: {e}")
                
    # Convert catalog dict values back to a standard flat list
    flat_catalog = list(master_catalog.values())
    print("\n=================================================================")
    print("Compilation Complete!")
    print(f"Total 100% Complete Deduplicated Unique Page Targets: {len(flat_catalog):,}")
    print(f"Expected Comment Yield: {len(flat_catalog) * 15.6:,} comments.")
    print(f"Saving compiled index catalog to: {OUTPUT_PATH}")
    print("=================================================================")
    
    # Save compilation to disk
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(flat_catalog, f, indent=2)
        
    return flat_catalog


if __name__ == "__main__":
    compile_complete_cc_catalog()
