#!/usr/bin/env python
import os
import json
import io
import gzip
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

INDEX_PATH = "data/processed/ats_cc_index_complete.json"

def test_rate_limiting():
    print("==========================================")
    print("Testing S3 Rate Limiting / 403 Forbidden Behavior...")
    print("==========================================\n")
    
    with open(INDEX_PATH) as f:
        targets = json.load(f)
        
    # Get 200 targets from 2016
    targets_2016 = [t for t in targets if "CC-MAIN-2016" in t['filename']][:200]
    print(f"Loaded {len(targets_2016)} targets from 2016.")
    
    results = []
    start_time = time.time()
    
    def fetch_one(target):
        filename = target['filename']
        offset = target['offset']
        length = target['length']
        
        s3_url = f"https://data.commoncrawl.org/{filename}"
        headers = {
            "Range": f"bytes={offset}-{offset+length-1}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        
        try:
            res = requests.get(s3_url, headers=headers, timeout=10)
            return res.status_code
        except Exception as e:
            return str(e)
            
    # Run with 15 workers (same as parallel scraper)
    print("Running 200 parallel S3 Range GETs with 15 workers...")
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(fetch_one, t) for t in targets_2016]
        for fut in as_completed(futures):
            results.append(fut.result())
            
    elapsed = time.time() - start_time
    print(f"\nCompleted in {elapsed:.2f} seconds ({len(targets_2016)/elapsed:.1f} req/sec)")
    
    # Print status code counts
    counts = {}
    for r in results:
        counts[r] = counts.get(r, 0) + 1
        
    print("\nStatus Code Counts:")
    for status, count in sorted(counts.items(), key=lambda x: str(x[0])):
        print(f"  - {status}: {count}")

if __name__ == "__main__":
    test_rate_limiting()
