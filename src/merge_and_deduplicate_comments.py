#!/usr/bin/env python
"""merge_and_deduplicate_comments.py

Consolidates all parsed AboveTopSecret comments from different extraction runs
into a single, unified, and deduplicated master JSONLines file.
"""

import os
import json
import glob

PROCESSED_DIR = "data/processed"
MASTER_OUTPUT = os.path.join(PROCESSED_DIR, "ats_comments_master.jsonl")


def merge_and_deduplicate():
    print("===============================================================")
    print("Consolidating & Deduplicating All Recovered AboveTopSecret Comments...")
    print("===============================================================\n")
    
    # Locate all jsonl files in processed directory
    jsonl_files = glob.glob(os.path.join(PROCESSED_DIR, "ats_comments_*.jsonl"))
    
    # Filter out master file if it already exists
    jsonl_files = [f for f in jsonl_files if os.path.basename(f) != "ats_comments_master.jsonl"]
    
    if not jsonl_files:
        print("No comments files found to merge.")
        return
        
    print(f"Discovered {len(jsonl_files)} files to merge:")
    for f in jsonl_files:
        size_mb = os.path.getsize(f) / (1024 * 1024)
        print(f"  - {os.path.basename(f)} ({size_mb:.2f} MB)")
        
    unique_posts = {}  # post_id -> record dict
    total_loaded = 0
    
    for file_path in jsonl_files:
        print(f"\nProcessing {os.path.basename(file_path)}...")
        file_loaded = 0
        file_added = 0
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as infile:
            for line in infile:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    post_id = record.get('post_id')
                    if not post_id:
                        continue
                        
                    total_loaded += 1
                    file_loaded += 1
                    
                    # Deduplication check: Keep the one with body or longest text if conflict
                    if post_id not in unique_posts:
                        unique_posts[post_id] = record
                        file_added += 1
                    else:
                        # If duplicate, keep the one with longer text block
                        existing_body_len = len(unique_posts[post_id].get('body', ''))
                        new_body_len = len(record.get('body', ''))
                        if new_body_len > existing_body_len:
                            unique_posts[post_id] = record
                except Exception:
                    continue
                    
        print(f"  -> Loaded {file_loaded:,} posts | Retained {file_added:,} new unique posts.")
        
    # Sort posts chronologically or by thread_id and post_id to make it analytical
    print("\nSorting unified database chronologically...")
    try:
        # Sort by thread_id and post_id (or post_id numeric conversion if possible)
        sorted_posts = sorted(
            unique_posts.values(),
            key=lambda x: (int(x.get('thread_id', 0)), int(x.get('post_id', 0)) if str(x.get('post_id', '')).isdigit() else 0)
        )
    except Exception:
        sorted_posts = list(unique_posts.values())
        
    print(f"Writing {len(sorted_posts):,} unique deduplicated comments to {MASTER_OUTPUT}...")
    
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    with open(MASTER_OUTPUT, 'w', encoding='utf-8') as outfile:
        for post in sorted_posts:
            outfile.write(json.dumps(post) + '\n')
            
    print("\n===============================================================")
    print("Consolidation Completed Successfully!")
    print(f"Grand Total Loaded Across All Runs: {total_loaded:,} comments.")
    print(f"Total Unique Deduplicated Comments Saved: {len(sorted_posts):,} comments.")
    print(f"Final Master File Size: {os.path.getsize(MASTER_OUTPUT) / (1024 * 1024):.2f} MB")
    print("===============================================================")


if __name__ == "__main__":
    merge_and_deduplicate()
