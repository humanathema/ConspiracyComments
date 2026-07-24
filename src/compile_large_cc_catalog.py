#!/usr/bin/env python
"""compile_large_cc_catalog.py

A high-performance script to compile a massive, deduplicated AboveTopSecret target capture catalog
by querying multiple historical Common Crawl monthly indexes from 2013 to 2022.

Ensures that we capture the absolute latest available snapshot for each unique thread page,
maximizing the reply coverage and post counts for each thread in our final corpus.
"""

import os
import sys
import re
import json
from urllib.parse import urlparse
import requests

# Recommended list of comprehensive annual end-of-year crawls
HISTORICAL_INDEXES = [
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
DEFAULT_OUTPUT = "data/processed/ats_cc_index_large.json"


def compile_large_catalog(indexes=HISTORICAL_INDEXES, output_path=DEFAULT_OUTPUT):
    print(f"=======================================================")
    print(f"Compiling Massive ATS Catalog across {len(indexes)} CC Indices...")
    print(f"Target Indices: {', '.join(indexes)}")
    print(f"=======================================================\n")
    
    master_catalog = {}  # (thread_id, page_num) -> record dict
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    for idx in indexes:
        print(f"[{idx}] Fetching thread index targets...")
        api_url = f"https://index.commoncrawl.org/{idx}-index?url=abovetopsecret.com/forum/thread*&output=json"
        
        try:
            # Stream the response to process line-by-line efficiently
            response = requests.get(api_url, headers=headers, stream=True, timeout=60)
            if response.status_code == 404:
                print(f"  -> No captures found or index not available. Skipping.")
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
                        # Found a newer snapshot of the exact same page! Update to maximize reply counts.
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
                    
            print(f"  -> Found {idx_records_found:,} valid captures | Added: {idx_records_added:,} new | Updated: {idx_records_updated:,} newer snapshots")
            
        except Exception as e:
            print(f"  -> Error fetching index {idx}: {e}", file=sys.stderr)
            
    # Convert catalog dict values back to a standard flat list
    flat_catalog = list(master_catalog.values())
    print(f"\n=======================================================")
    print(f"Compilation Complete!")
    print(f"Total Deduplicated Unique Page Targets: {len(flat_catalog):,}")
    print(f"Approximate Potential Post Yield: {len(flat_catalog) * 15:,} to {len(flat_catalog) * 20:,} comments.")
    
    # Save compilation to disk
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(flat_catalog, f, indent=2)
    print(f"Saved master large-scale index catalog to: {output_path}")
    print(f"=======================================================")
    
    return flat_catalog


if __name__ == "__main__":
    compile_large_catalog()
