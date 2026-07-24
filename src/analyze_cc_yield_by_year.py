#!/usr/bin/env python
import os
import json

MASTER_OUTPUT = "data/processed/ats_comments_master.jsonl"
INDEX_PATH = "data/processed/ats_cc_index_complete.json"

def analyze_yield():
    print("==========================================")
    print("Analyzing Yield and Coverage by Year...")
    print("==========================================\n")
    
    if not os.path.exists(MASTER_OUTPUT):
        print("Master file does not exist yet. Run merge first.")
        return
        
    # Build index dictionary: thread_id -> list of target years
    print("Loading target catalog index...")
    with open(INDEX_PATH) as f:
        targets = json.load(f)
        
    targets_by_year = {}
    for t in targets:
        parts = t['filename'].split('/')
        if len(parts) > 1:
            crawl = parts[1]
            year = crawl.split('-')[2]
            targets_by_year.setdefault(year, 0)
            targets_by_year[year] += 1
            
    print(f"Total target pages indexed: {len(targets):,}")
    for y, count in sorted(targets_by_year.items()):
        print(f"  - Year {y}: {count:,} targets")
        
    # Read master comments and count by post date
    print("\nReading master unified comments database...")
    comments_by_post_year = {}
    comments_by_url_year = {}
    
    total_comments = 0
    with open(MASTER_OUTPUT, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                total_comments += 1
                
                # 1. Analyze by raw timestamp (e.g. "posted on Jul, 20 2004")
                raw_time = record.get('raw_timestamp', '')
                post_year = "Unknown"
                year_match = re.search(r'\b(200\d|201\d|202\d)\b', raw_time)
                if year_match:
                    post_year = year_match.group(1)
                comments_by_post_year.setdefault(post_year, 0)
                comments_by_post_year[post_year] += 1
                
            except Exception as e:
                continue
                
    print(f"\nTotal Unified Comments in Master File: {total_comments:,}")
    print("\nParsed Comments Distributed by Post Year:")
    for y, count in sorted(comments_by_post_year.items()):
        print(f"  - Post Year {y}: {count:,} comments")

import re
if __name__ == "__main__":
    analyze_yield()
