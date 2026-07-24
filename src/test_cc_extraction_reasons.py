#!/usr/bin/env python
import os
import json
import io
import gzip
import requests
from bs4 import BeautifulSoup

INDEX_PATH = "data/processed/ats_cc_index_complete.json"

def run_diagnostics():
    print("==========================================")
    print("Running Extraction Diagnostics...")
    print("==========================================\n")
    
    with open(INDEX_PATH) as f:
        targets = json.load(f)
        
    print(f"Total targets in complete index: {len(targets):,}")
    
    # Let's sample targets from different crawls to see how they behave
    # Group targets by crawl year to get a diverse sample
    by_year = {}
    for t in targets:
        # Extracted from filename like "crawl-data/CC-MAIN-2024-42/..."
        parts = t['filename'].split('/')
        if len(parts) > 1:
            crawl = parts[1] # e.g. "CC-MAIN-2024-42"
            year = crawl.split('-')[2]
            by_year.setdefault(year, []).append(t)
            
    print(f"Discovered years: {sorted(by_year.keys())}")
    for y, items in sorted(by_year.items()):
        print(f"  - {y}: {len(items):,} pages")
        
    # Sample 1 page from each year and inspect
    print("\n--- Testing 1 Sample Page From Each Available Year ---")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    for year in sorted(by_year.keys()):
        sample = by_year[year][0]
        url = sample['url']
        filename = sample['filename']
        offset = sample['offset']
        length = sample['length']
        
        print(f"\n[{year}] Target URL: {url}")
        print(f"  WARC Filename: {filename}")
        print(f"  Offset: {offset}, Length: {length}")
        
        s3_url = f"https://data.commoncrawl.org/{filename}"
        range_header = {"Range": f"bytes={offset}-{offset+length-1}", **headers}
        
        try:
            res = requests.get(s3_url, headers=range_header, timeout=15)
            print(f"  HTTP Response Status: {res.status_code}")
            
            if res.status_code == 403:
                print("  ❌ AWS S3 returned 403 Forbidden.")
                continue
            elif res.status_code != 206 and res.status_code != 200:
                print(f"  ❌ Unexpected status: {res.status_code}")
                continue
                
            # Decompress
            try:
                warc_record = gzip.GzipFile(fileobj=io.BytesIO(res.content)).read()
                print(f"  Decompressed Size: {len(warc_record):,} bytes")
            except Exception as decomp_err:
                print(f"  ❌ Decompression Failed: {decomp_err}")
                continue
                
            parts = warc_record.split(b"\r\n\r\n")
            if len(parts) < 3:
                print(f"  ❌ Invalid WARC record parts (found {len(parts)})")
                continue
                
            html_content = b"\r\n\r\n".join(parts[2:]).decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Check title
            title = soup.title.string.strip() if soup.title else "No Title"
            print(f"  Page Title: '{title}'")
            
            # Let's count threadposts and other indicators
            threadposts = soup.find_all(class_='threadpost')
            kona_bodies = soup.find_all(class_='KonaBody')
            all_divs = len(soup.find_all('div'))
            
            print(f"  Found Elements: threadpost={len(threadposts)}, KonaBody={len(kona_bodies)}, total_divs={all_divs}")
            
            # Let's inspect some of the raw text if no threadposts found
            if len(threadposts) == 0:
                print("  ⚠️ ZERO threadposts found. Let's inspect structure...")
                # Is it an error page or custom page?
                text_snippet = soup.get_text()[:400].replace('\n', ' ')
                print(f"  Raw Text Snippet (first 400 chars): {text_snippet}")
                
        except Exception as e:
            print(f"  ❌ Connection/Request Error: {e}")

if __name__ == "__main__":
    run_diagnostics()
