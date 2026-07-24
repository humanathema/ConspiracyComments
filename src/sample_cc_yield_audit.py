#!/usr/bin/env python
import os
import json
import io
import gzip
import requests
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

INDEX_PATH = "data/processed/ats_cc_index_complete.json"

def audit_sample():
    print("==========================================")
    print("Running Parallel Sample Yield Audit...")
    print("==========================================\n")
    
    with open(INDEX_PATH) as f:
        targets = json.load(f)
        
    print(f"Total targets: {len(targets):,}")
    
    # Take a random sample of 200 targets
    random.seed(42)
    sample_targets = random.sample(targets, 200)
    
    success_count = 0
    zero_post_count = 0
    warc_part_err = 0
    s3_err_403 = 0
    conn_err = 0
    
    # Store zero post titles
    zero_post_titles = []
    success_titles = []
    
    def test_one(target):
        nonlocal success_count, zero_post_count, warc_part_err, s3_err_403, conn_err
        url = target['url']
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
            if res.status_code == 403:
                s3_err_403 += 1
                return ("403", url, None)
            if res.status_code not in [200, 206]:
                conn_err += 1
                return (f"HTTP {res.status_code}", url, None)
                
            warc_record = gzip.GzipFile(fileobj=io.BytesIO(res.content)).read()
            parts = warc_record.split(b"\r\n\r\n")
            if len(parts) < 3:
                warc_part_err += 1
                return ("warc_parts_less_3", url, None)
                
            html_content = b"\r\n\r\n".join(parts[2:]).decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html_content, 'html.parser')
            
            title = soup.title.string.strip() if soup.title else "No Title"
            threadposts = soup.find_all(class_='threadpost')
            
            if len(threadposts) > 0:
                success_count += 1
                return ("success", url, f"Posts: {len(threadposts)} | Title: {title}")
            else:
                zero_post_count += 1
                return ("zero_posts", url, f"Title: {title} | Divs: {len(soup.find_all('div'))}")
                
        except Exception as e:
            conn_err += 1
            return ("error", url, str(e))

    print(f"Auditing a diverse sample of 200 thread-page targets...")
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(test_one, t) for t in sample_targets]
        for fut in as_completed(futures):
            status, url, detail = fut.result()
            if status == "zero_posts":
                zero_post_titles.append((url, detail))
            elif status == "success":
                success_titles.append((url, detail))
                
    print("\n--- Audit Summary ---")
    print(f"  - Total Audited: 200")
    print(f"  - Success (Posts > 0): {success_count} ({success_count/2:.1f}%)")
    print(f"  - Zero Posts Extracted: {zero_post_count} ({zero_post_count/2:.1f}%)")
    print(f"  - AWS S3 403 Forbidden: {s3_err_403} ({s3_err_403/2:.1f}%)")
    print(f"  - WARC Parts < 3: {warc_part_err} ({warc_part_err/2:.1f}%)")
    print(f"  - Connection/HTTP Errors: {conn_err} ({conn_err/2:.1f}%)")
    
    if zero_post_titles:
        print("\n--- Sample Zero Post Targets (first 10) ---")
        for u, d in zero_post_titles[:10]:
            print(f"  - {u} -> {d}")
            
    if success_titles:
        print("\n--- Sample Success Targets (first 10) ---")
        for u, d in success_titles[:10]:
            print(f"  - {u} -> {d}")

if __name__ == "__main__":
    audit_sample()
