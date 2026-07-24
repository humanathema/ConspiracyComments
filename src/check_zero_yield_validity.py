#!/usr/bin/env python
import os
import json
import requests
import gzip
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

INDEX_PATH = "data/processed/ats_cc_index_complete.json"
COMMENTS_PATH = "data/processed/ats_comments_cc_complete.jsonl"

def check_validity():
    print("==========================================")
    print("Checking Validity of Zero-Yield Pages...")
    print("==========================================\n")
    
    # Load parsed pages
    parsed = set()
    if os.path.exists(COMMENTS_PATH):
        with open(COMMENTS_PATH) as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    parsed.add((r['thread_id'], r['page_num']))
                    
    with open(INDEX_PATH) as f:
        targets = json.load(f)
        
    zero_yield_targets = [t for t in targets if (t['thread_id'], t['page_num']) not in parsed]
    print(f"Total zero-yield targets: {len(zero_yield_targets):,}")
    
    # Take a sample of 100 zero-yield targets
    import random
    random.seed(123)
    sample = random.sample(zero_yield_targets, 100)
    
    success_count = 0
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    def test_target(t):
        filename = t['filename']
        offset = t['offset']
        length = t['length']
        
        s3_url = f"https://data.commoncrawl.org/{filename}"
        r_headers = {"Range": f"bytes={offset}-{offset+length-1}", **headers}
        
        try:
            res = requests.get(s3_url, headers=r_headers, timeout=10)
            if res.status_code in [200, 206]:
                content = gzip.GzipFile(fileobj=io.BytesIO(res.content)).read()
                parts = content.split(b"\r\n\r\n")
                if len(parts) >= 3:
                    html = b"\r\n\r\n".join(parts[2:]).decode('utf-8', errors='ignore')
                    # Search for threadpost elements
                    if 'class="threadpost"' in html or "class='threadpost'" in html:
                        return True
            return False
        except:
            return False

    print("Testing 100 random zero-yield targets in isolation to see if they are actually valid thread pages...")
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(test_target, t) for t in sample]
        for fut in as_completed(futures):
            results.append(fut.result())
            
    valid_count = sum(1 for r in results if r)
    print(f"\nResults of isolated check:")
    print(f"  - Valid thread pages in sample: {valid_count} out of 100 ({valid_count:.1f}%)")
    print(f"  - Invalid/Empty pages in sample: {100 - valid_count} out of 100")

if __name__ == "__main__":
    check_validity()
