#!/usr/bin/env python
"""ingest_ats_common_crawl.py

A high-performance, multi-threaded extraction pipeline to recover historical AboveTopSecret
forum discussions from Common Crawl archive indexes using HTTP Range Requests on raw WARC files.

Provides commands to:
1. query-index: Query the public Common Crawl index for ATS thread captures.
2. extract-threads: Extract, decompress, and parse thread pages in parallel.
"""

import os
import sys
import re
import io
import gzip
import json
import time
import argparse
import threading
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

# Defaults
DEFAULT_INDEX_FILE = "data/processed/ats_cc_index.json"
DEFAULT_OUTPUT_FILE = "data/processed/ats_comments_cc.jsonl"
DEFAULT_CC_INDEX = "CC-MAIN-2022-49"

# Compile Regexes for performance
THREAD_REGEX = re.compile(r'/forum/thread(\d+)/pg(\d+|lastpost)?', re.IGNORECASE)
PID_REGEX = re.compile(r'(?:post|pid)(\d+)', re.IGNORECASE)


def query_cc_index(index_name=DEFAULT_CC_INDEX, limit=1000, output_path=DEFAULT_INDEX_FILE):
    """
    Queries the public Common Crawl Index API for AboveTopSecret thread captures.
    """
    print(f"Querying Common Crawl index '{index_name}' for 'abovetopsecret.com/forum/thread*' (limit={limit})...")
    
    api_url = (
        f"https://index.commoncrawl.org/{index_name}-index"
        "?url=abovetopsecret.com/forum/thread*"
        "&output=json"
    )
    if limit:
        api_url += f"&limit={limit}"
        
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        # Stream the response to avoid bloating memory
        response = requests.get(api_url, headers=headers, stream=True, timeout=60)
        
        if response.status_code == 404:
            print(f"No captures found for the specified crawl index: {index_name}")
            return []
        response.raise_for_status()
    except Exception as e:
        print(f"Error querying Common Crawl Index: {e}", file=sys.stderr)
        return []
        
    target_catalog = []
    seen_keys = set()
    
    # Process line-by-line
    print("Streaming and parsing index response...")
    for line in response.iter_lines():
        if not line:
            continue
        try:
            record = json.loads(line.decode('utf-8'))
            
            # Filters
            if record.get('status') != '200':
                continue
            if 'text/html' not in record.get('mime', '').lower():
                continue
                
            original_url = record.get('url', '')
            parsed = urlparse(original_url)
            path = parsed.path
            
            # Avoid malformed or glitched paths
            if '%' in path or ' ' in path or '<' in path or '*' in path or '-' in path:
                continue
                
            match = THREAD_REGEX.search(path)
            if not match:
                continue
                
            thread_id = int(match.group(1))
            page_val = match.group(2)
            
            # Standardize page number
            if not page_val:
                page_num = 1
            elif page_val.lower() == 'lastpost':
                page_num = 'lastpost'
            else:
                page_num = int(page_val)
                
            # Deduplicate by (thread_id, page_num)
            dedup_key = (thread_id, page_num)
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            
            target_catalog.append({
                'thread_id': thread_id,
                'page_num': page_num,
                'timestamp': record.get('timestamp', ''),
                'url': original_url,
                'filename': record.get('filename', ''),
                'offset': int(record.get('offset', 0)),
                'length': int(record.get('length', 0))
            })
        except Exception as e:
            # Skip invalid lines
            continue
            
    print(f"Retained {len(target_catalog):,} unique, clean page captures.")
    
    # Save index to local file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(target_catalog, f, indent=2)
    print(f"Saved local Common Crawl target catalog index to {output_path}")
    
    return target_catalog


def extract_record_from_cc(record):
    """
    Performs an HTTP Range Request, decompresses raw Gzip member,
    isolates the HTML payload, and parses AboveTopSecret posts.
    """
    filename = record['filename']
    offset = record['offset']
    length = record['length']
    thread_id = record['thread_id']
    page_num = record['page_num']
    original_url = record['url']
    
    # 1. Fetch raw gzipped member from Common Crawl CDN via Range GET (with robust exponential backoff retries)
    cdn_url = f"https://data.commoncrawl.org/{filename}"
    headers = {
        "Range": f"bytes={offset}-{offset + length - 1}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    max_retries = 3
    backoff_factor = 2.0
    res = None
    
    for attempt in range(max_retries):
        try:
            res = requests.get(cdn_url, headers=headers, timeout=15)
            if res.status_code in [200, 206]:
                break
            elif res.status_code in [429, 503]:
                # Server throttled or rate-limited; back off and retry
                if attempt == max_retries - 1:
                    res.raise_for_status()
                import random
                sleep_time = (backoff_factor ** attempt) + random.uniform(0.5, 1.5)
                time.sleep(sleep_time)
            else:
                res.raise_for_status()
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise e
            import random
            sleep_time = (backoff_factor ** attempt) + random.uniform(0.5, 1.5)
            time.sleep(sleep_time)
            
    if not res:
        return []
        
    # 2. Decompress Gzip member
    warc_record = gzip.GzipFile(fileobj=io.BytesIO(res.content)).read()
    
    # 3. Separate WARC headers, HTTP headers, and HTML payload
    # WARC records are structured as: [WARC Headers]\r\n\r\n[HTTP Response Headers]\r\n\r\n[HTML Body]
    parts = warc_record.split(b"\r\n\r\n")
    if len(parts) < 3:
        return []
        
    html_content = b"\r\n\r\n".join(parts[2:]).decode('utf-8', errors='ignore')
    
    # 4. Parse the isolated HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    title_text = "Unknown Title"
    if soup.title and soup.title.string:
        title_text = soup.title.string.strip()
        if ', page' in title_text:
            title_text = title_text.split(', page')[0].strip()
            
    posts_extracted = []
    posts_elements = soup.find_all(class_='threadpost')
    
    for post in posts_elements:
        classes = post.get('class', [])
        if 'midAd' in classes:
            continue
            
        # A. Author
        author = 'Unknown'
        author_el = post.find(class_='membr')
        if author_el:
            author = author_el.text.strip()
        else:
            miniprofile = post.find(class_='miniprofile')
            if miniprofile:
                author = miniprofile.text.strip()
                author = ' '.join(author.split())
                
        # B. Post ID
        post_id = 'Unknown'
        post_div = post.find(class_='threadpostC')
        if post_div and post_div.get('id'):
            raw_id = post_div.get('id')
            pid_match = PID_REGEX.search(raw_id)
            if pid_match:
                post_id = pid_match.group(1)
        else:
            anchor = post.find('a', attrs={'name': True})
            if anchor and anchor.get('name'):
                pid_match = PID_REGEX.search(anchor.get('name'))
                if pid_match:
                    post_id = pid_match.group(1)
                    
        # C. Timestamp
        raw_timestamp = 'Unknown'
        time_div = post.find(class_='posttopL')
        if time_div:
            raw_timestamp = time_div.text.strip()
            raw_timestamp = ' '.join(raw_timestamp.split())
            if 'posted on' in raw_timestamp.lower():
                raw_timestamp = raw_timestamp.lower().split('posted on')[-1].strip()
                
        # D. Post Body
        body_text = ""
        body_div = post.find(class_='KonaBody')
        if not body_div:
            body_div = post.find(class_='threadpostC')
            
        if body_div:
            for s in body_div(['script', 'style']):
                s.decompose()
            body_text = body_div.text.strip()
            body_text = re.sub(r'\n{3,}', '\n\n', body_text)
            
        posts_extracted.append({
            'thread_id': thread_id,
            'thread_title': title_text,
            'page_num': page_num,
            'post_id': post_id,
            'author': author,
            'raw_timestamp': raw_timestamp,
            'body': body_text,
            'original_url': original_url
        })
        
    return posts_extracted


def extract_threads_parallel(index_path, max_workers=10, limit=None, output_path=DEFAULT_OUTPUT_FILE):
    """
    Main orchestrator that executes multi-threaded concurrent range requests to Common Crawl,
    parsing comments in parallel and writing to output in a thread-safe manner.
    """
    if not os.path.exists(index_path):
        print(f"Error: Target catalog index {index_path} does not exist. Run query-index first.", file=sys.stderr)
        return
        
    with open(index_path) as f:
        targets = json.load(f)
        
    if limit:
        targets = targets[:limit]
        
    total_pages = len(targets)
    if total_pages == 0:
        print("No target captures to parse.")
        return
        
    print(f"Starting multi-threaded Common Crawl extraction (workers={max_workers}, pages={total_pages})...")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Initialize locks and statistics
    write_lock = threading.Lock()
    total_comments_extracted = 0
    pages_processed = 0
    start_time = time.time()
    
    def worker(record):
        nonlocal total_comments_extracted, pages_processed
        try:
            posts = extract_record_from_cc(record)
            if posts:
                with write_lock:
                    # Append records to JSONLines output
                    with open(output_path, 'a', encoding='utf-8') as outfile:
                        for p in posts:
                            outfile.write(json.dumps(p) + '\n')
                    total_comments_extracted += len(posts)
            with write_lock:
                pages_processed += 1
                # Show periodic real-time statistics
                if pages_processed % 10 == 0 or pages_processed == total_pages:
                    elapsed = time.time() - start_time
                    speed = pages_processed / elapsed if elapsed > 0 else 0
                    print(f"Progress: [{pages_processed}/{total_pages}] pages processed | "
                          f"Extracted {total_comments_extracted:,} comments | Speed: {speed:.1f} pages/sec")
        except Exception as e:
            print(f"Warning: Failed to extract {record.get('url')}: {e}", file=sys.stderr)

    # Launch parallel thread pool
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(worker, r) for r in targets]
        # Wait for all threads to complete
        for future in as_completed(futures):
            pass
            
    total_time = time.time() - start_time
    avg_speed = total_pages / total_time if total_time > 0 else 0
    print(f"\n=======================================================")
    print(f"Common Crawl Parallel Extraction Completed!")
    print(f"Total Pages Processed: {pages_processed:,}")
    print(f"Total Comments Saved: {total_comments_extracted:,}")
    print(f"Output File: {output_path}")
    print(f"Total Time Taken: {total_time:.1f} seconds")
    print(f"Average System Throughput: {avg_speed:.1f} pages/second")
    print(f"=======================================================")


def main():
    parser = argparse.ArgumentParser(description="AboveTopSecret Common Crawl Ingestion Pipeline")
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")
    
    # query-index command
    q_parser = subparsers.add_parser("query-index", help="Query the public CC Index database for thread targets")
    q_parser.add_argument("--index", default=DEFAULT_CC_INDEX, help=f"Crawl index ID (default: {DEFAULT_CC_INDEX})")
    q_parser.add_argument("--limit", type=int, default=1000, help="Maximum index lines to process (0 for no limit)")
    q_parser.add_argument("--output", default=DEFAULT_INDEX_FILE, help="Path to save index targets JSON")
    
    # extract-threads command
    e_parser = subparsers.add_parser("extract-threads", help="Download and parse CC WARC threads in parallel")
    e_parser.add_argument("--index", default=DEFAULT_INDEX_FILE, help="Path to index targets JSON file")
    e_parser.add_argument("--threads", type=int, default=10, help="Number of concurrent thread workers")
    e_parser.add_argument("--limit", type=int, default=None, help="Limit number of thread pages to extract")
    e_parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE, help="Path to output JSONLines comments")
    
    args = parser.parse_args()
    
    if args.command == "query-index":
        limit_val = None if args.limit == 0 else args.limit
        query_cc_index(index_name=args.index, limit=limit_val, output_path=args.output)
        
    elif args.command == "extract-threads":
        extract_threads_parallel(
            index_path=args.index,
            max_workers=args.threads,
            limit=args.limit,
            output_path=args.output
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
