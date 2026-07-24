#!/usr/bin/env python
"""compile_pre_2008_wayback_index.py

Queries the Wayback Machine CDX API specifically for thread ID prefixes 1 through 9
from 1999 to December 31, 2007.

Aggregates, filters, and deduplicates the results by (thread_id, page_num), 
retaining ONLY the latest timestamp snapshot for each unique page to maximize
reply history while minimizing unnecessary download overhead.
"""

import os
import sys
import re
import json
from urllib.parse import urlparse
import requests

THREAD_REGEX = re.compile(r'/forum/thread(\d+)/pg(\d+|lastpost)?', re.IGNORECASE)
OUTPUT_PATH = "data/processed/ats_metadata_pre_2008_complete.json"


def compile_complete_pre_2008_index():
    print("=======================================================")
    print("Compiling Complete Pre-2008 Wayback Historical Index...")
    print("=======================================================\n")
    
    raw_captures_count = 0
    unique_catalog = {}  # (thread_id, page_num) -> record dict
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    # Query prefixes thread1 to thread9
    for n in range(1, 10):
        print(f"[Prefix thread{n}*] Fetching CDX metadata up to Dec 31, 2007...")
        cdx_url = (
            f"https://web.archive.org/cdx/search/cdx"
            f"?url=abovetopsecret.com/forum/thread{n}"
            f"&matchType=prefix"
            f"&output=json"
            f"&to=20071231235959"
        )
        
        try:
            response = requests.get(cdx_url, headers=headers, timeout=60)
            if response.status_code == 404:
                print(f"  -> No captures found. Skipping.")
                continue
            response.raise_for_status()
            
            data = response.json()
            if not data or len(data) < 2:
                print(f"  -> No captures found.")
                continue
                
            headers_row = data[0]
            rows = data[1:]
            print(f"  -> Found {len(rows):,} raw captures. Filtering and deduplicating...")
            
            prefix_added = 0
            prefix_updated = 0
            
            for row in rows:
                record = dict(zip(headers_row, row))
                statuscode = record.get('statuscode', '-')
                mimetype = record.get('mimetype', '')
                original_url = record.get('original', '')
                timestamp = record.get('timestamp', '')
                digest = record.get('digest', '')
                
                raw_captures_count += 1
                
                # Filter strictly for clean status-200 HTML pages
                if statuscode != '200' or 'html' not in mimetype.lower():
                    continue
                    
                parsed = urlparse(original_url)
                path = parsed.path
                
                match = THREAD_REGEX.search(path)
                if not match:
                    continue
                    
                thread_id = int(match.group(1))
                page_val = match.group(2)
                page_num = 1 if not page_val else ('lastpost' if page_val.lower() == 'lastpost' else int(page_val))
                
                key = f"{thread_id}_pg{page_num}"
                
                # Deduplication logic: Retain only the latest snapshot before 2008
                if key not in unique_catalog:
                    unique_catalog[key] = {
                        'thread_id': thread_id,
                        'page_num': page_num,
                        'timestamp': timestamp,
                        'original_url': original_url,
                        'statuscode': statuscode,
                        'mimetype': mimetype,
                        'digest': digest
                    }
                    prefix_added += 1
                elif timestamp > unique_catalog[key]['timestamp']:
                    unique_catalog[key] = {
                        'thread_id': thread_id,
                        'page_num': page_num,
                        'timestamp': timestamp,
                        'original_url': original_url,
                        'statuscode': statuscode,
                        'mimetype': mimetype,
                        'digest': digest
                    }
                    prefix_updated += 1
                    
            print(f"  -> Unique pages added: {prefix_added:,} | Upgraded to newer snapshot: {prefix_updated:,}")
            
        except Exception as e:
            print(f"  -> Error fetching Prefix thread{n}*: {e}", file=sys.stderr)
            
    # Flat list of deduplicated target page snapshots
    flat_catalog = list(unique_catalog.values())
    
    print("\n=======================================================")
    print("Compilation and Deduplication Complete!")
    print(f"Total Raw Captures Fetched: {raw_captures_count:,}")
    print(f"Total Deduplicated Target Pages: {len(flat_catalog):,}")
    if raw_captures_count > 0:
        reduction = (1 - len(flat_catalog) / raw_captures_count) * 100
        print(f"Data Reduction Ratio: {reduction:.2f}% (Saved {raw_captures_count - len(flat_catalog):,} duplicate downloads!)")
    print(f"Saved complete pre-2008 deduplicated index to: {OUTPUT_PATH}")
    print("=======================================================")
    
    # Write to disk
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(flat_catalog, f, indent=2)
        
    return flat_catalog


if __name__ == "__main__":
    compile_complete_pre_2008_index()
