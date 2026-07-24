#!/usr/bin/env python
import os
import json
import io
import gzip
import requests

INDEX_PATH = "data/processed/ats_cc_index_complete.json"
COMMENTS_PATH = "data/processed/ats_comments_cc_complete.jsonl"

def debug_zero_yields():
    print("==========================================")
    print("Debugging Zero-Yield Pages...")
    print("==========================================\n")
    
    # 1. Load parsed pages
    parsed_pages = set()
    if os.path.exists(COMMENTS_PATH):
        with open(COMMENTS_PATH) as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    parsed_pages.add((r['thread_id'], r['page_num']))
                    
    print(f"Loaded {len(parsed_pages):,} successfully parsed thread pages.")
    
    # 2. Load all target pages
    with open(INDEX_PATH) as f:
        targets = json.load(f)
        
    print(f"Loaded {len(targets):,} target pages.")
    
    # 3. Find target pages that yielded 0 comments
    zero_yield_targets = []
    for t in targets:
        if (t['thread_id'], t['page_num']) not in parsed_pages:
            zero_yield_targets.append(t)
            
    print(f"Found {len(zero_yield_targets):,} zero-yield targets.")
    
    # 4. Pull 5 samples from different crawls and print their raw WARC headers
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    for i, t in enumerate(zero_yield_targets[:10]):
        url = t['url']
        filename = t['filename']
        offset = t['offset']
        length = t['length']
        
        print(f"\n--- [Sample {i+1}] Zero-Yield Thread: {url} ---")
        print(f"  WARC: {filename} (Offset: {offset}, Length: {length})")
        
        s3_url = f"https://data.commoncrawl.org/{filename}"
        range_header = {"Range": f"bytes={offset}-{offset+length-1}", **headers}
        
        try:
            res = requests.get(s3_url, headers=range_header, timeout=10)
            print(f"  S3 Status: {res.status_code}")
            
            if res.status_code in [200, 206]:
                warc_record = gzip.GzipFile(fileobj=io.BytesIO(res.content)).read()
                print(f"  Decompressed Size: {len(warc_record):,} bytes")
                
                # Print WARC headers (everything before the first double CRLF)
                parts = warc_record.split(b"\r\n\r\n")
                print(f"  Number of double-CRLF parts: {len(parts)}")
                
                warc_header = parts[0].decode('utf-8', errors='ignore')
                print("  --- WARC Headers ---")
                for line in warc_header.split('\n')[:10]:
                    print(f"    {line.strip()}")
                    
                if len(parts) > 1:
                    http_header = parts[1].decode('utf-8', errors='ignore')
                    print("  --- HTTP Headers ---")
                    for line in http_header.split('\n')[:10]:
                        print(f"    {line.strip()}")
                        
                if len(parts) > 2:
                    payload = b"\r\n\r\n".join(parts[2:])
                    print(f"  --- Payload Preview ({min(300, len(payload))} bytes) ---")
                    print(payload[:300].decode('utf-8', errors='ignore').replace('\n', ' '))
            else:
                print(f"  S3 status code not 200/206: {res.status_code}")
        except Exception as e:
            print(f"  Error fetching: {e}")

if __name__ == "__main__":
    debug_zero_yields()
