#!/usr/bin/env python
"""ingest_ats_archive.py

A modular, self-contained data-engineering pipeline to recover historical forum
discussions from AboveTopSecret.com (ATS) via the Wayback Machine.

Provides commands to:
1. fetch-metadata: Query Wayback CDX API for thread captures.
2. download: Caches and downloads raw rewritten-free HTML captures with rate-limiting.
3. parse: Parse HTML to extract posts, filtering advertisements, into clean JSONL.
4. run-pipeline: Run the entire sequence end-to-end for selected thread IDs.
"""

import os
import sys
import re
import json
import time
import argparse
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

# Default paths
DEFAULT_CACHE_DIR = "data/raw/ats_raw_html"
DEFAULT_OUTPUT_FILE = "data/processed/ats_comments.jsonl"
DEFAULT_METADATA_FILE = "data/processed/ats_metadata.json"

# Compile regexes for performance
THREAD_REGEX = re.compile(r'/forum/thread(\d+)/pg(\d+|lastpost)?', re.IGNORECASE)
PID_REGEX = re.compile(r'(?:post|pid)(\d+)', re.IGNORECASE)


def fetch_metadata(limit=1000, clean_only=True, output_path=DEFAULT_METADATA_FILE):
    """
    Queries the Wayback Machine CDX API for clean AboveTopSecret thread captures.
    """
    print(f"Querying Wayback CDX API for prefix 'abovetopsecret.com/forum/thread' (limit={limit})...")
    
    # Prefix-match query
    cdx_url = (
        "http://web.archive.org/cdx/search/cdx"
        "?url=abovetopsecret.com/forum/thread"
        "&matchType=prefix"
        f"&limit={limit}"
        "&output=json"
    )
    
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(cdx_url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error querying CDX API: {e}", file=sys.stderr)
        return []
        
    if not data or len(data) < 2:
        print("No captures found.")
        return []
        
    # First row is headers
    headers_row = data[0]
    rows = data[1:]
    
    metadata_list = []
    print(f"Found {len(rows):,} raw captures. Filtering and mapping...")
    
    for row in rows:
        record = dict(zip(headers_row, row))
        original_url = record.get('original', '')
        statuscode = record.get('statuscode', '-')
        mimetype = record.get('mimetype', '')
        timestamp = record.get('timestamp', '')
        digest = record.get('digest', '')
        
        # Parse thread ID and page
        parsed = urlparse(original_url)
        path = parsed.path
        
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
            
        # Clean-only filter
        if clean_only:
            if statuscode != '200':
                continue
            if 'html' not in mimetype.lower():
                continue
                
        # Filter out obvious malformed URLs containing junk characters in path
        if '%' in path or ' ' in path or '<' in path or '*' in path or '-' in path:
            continue
            
        metadata_list.append({
            'thread_id': thread_id,
            'page_num': page_num,
            'timestamp': timestamp,
            'original_url': original_url,
            'statuscode': statuscode,
            'mimetype': mimetype,
            'digest': digest
        })
        
    print(f"Retained {len(metadata_list):,} clean thread page captures.")
    
    # Save to file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(metadata_list, f, indent=2)
    print(f"Saved metadata to {output_path}")
    
    return metadata_list


def download_captures(metadata_list, cache_dir=DEFAULT_CACHE_DIR, delay=1.5, limit=None):
    """
    Downloads raw rewritten-free HTML captures from the Wayback Machine.
    """
    os.makedirs(cache_dir, exist_ok=True)
    downloaded_count = 0
    cached_count = 0
    
    # Apply limit if specified
    targets = metadata_list[:limit] if limit else metadata_list
    total = len(targets)
    
    print(f"Beginning download phase for {total} captures (delay={delay}s)...")
    
    for i, item in enumerate(targets):
        thread_id = item['thread_id']
        page_num = item['page_num']
        timestamp = item['timestamp']
        original_url = item['original_url']
        
        # Local cache filename
        filename = f"thread_{thread_id}_pg{page_num}_{timestamp}.html"
        file_path = os.path.join(cache_dir, filename)
        
        if os.path.exists(file_path):
            cached_count += 1
            continue
            
        # Construct raw raw HTML Wayback URL
        wayback_url = f"https://web.archive.org/web/{timestamp}id_/{original_url}"
        
        print(f"[{i+1}/{total}] Downloading thread {thread_id} page {page_num}...")
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            res = requests.get(wayback_url, headers=headers, timeout=20)
            if res.status_code == 200:
                with open(file_path, 'w', encoding='utf-8', errors='ignore') as f:
                    f.write(res.text)
                downloaded_count += 1
            else:
                print(f"  Warning: HTTP status {res.status_code} for {wayback_url}", file=sys.stderr)
        except Exception as e:
            print(f"  Error downloading {wayback_url}: {e}", file=sys.stderr)
            
        # Respect rate limits
        if i < total - 1:
            time.sleep(delay)
            
    print(f"Download phase completed. New downloads: {downloaded_count}, Already cached: {cached_count}")
    return downloaded_count


def parse_html_file(file_path, thread_id=None, page_num=None):
    """
    Parses a single AboveTopSecret thread HTML file, returning extracted posts.
    """
    posts_extracted = []
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            html_content = f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}", file=sys.stderr)
        return []
        
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. Extract thread title
    title_text = "Unknown Title"
    if soup.title and soup.title.string:
        title_text = soup.title.string.strip()
        # Clean title (e.g. remove page suffixes)
        if ', page' in title_text:
            title_text = title_text.split(', page')[0].strip()
            
    # 2. Extract thread ID and page from filename if not provided
    if thread_id is None or page_num is None:
        basename = os.path.basename(file_path)
        parts = basename.replace('.html', '').split('_')
        for part in parts:
            if part.startswith('thread'):
                try:
                    thread_id = int(part.replace('thread', ''))
                except ValueError:
                    pass
            elif part.startswith('pg'):
                page_num_val = part.replace('pg', '')
                try:
                    page_num = int(page_num_val)
                except ValueError:
                    page_num = page_num_val
                    
    # Default to placeholders if extraction failed
    thread_id = thread_id or 0
    page_num = page_num or 1
    
    # 3. Locate all post containers
    posts_elements = soup.find_all(class_='threadpost')
    
    for post in posts_elements:
        # Filter out mid-thread advertisements
        classes = post.get('class', [])
        if 'midAd' in classes:
            continue
            
        # A. Extract Author
        author = 'Unknown'
        author_el = post.find(class_='membr')
        if author_el:
            author = author_el.text.strip()
        else:
            # Fallback check for unregistered guest profiles
            miniprofile = post.find(class_='miniprofile')
            if miniprofile:
                author = miniprofile.text.strip()
                # Clean up spacing/newlines
                author = ' '.join(author.split())
                
        # B. Extract Post ID
        post_id = 'Unknown'
        post_div = post.find(class_='threadpostC')
        if post_div and post_div.get('id'):
            raw_id = post_div.get('id')
            pid_match = PID_REGEX.search(raw_id)
            if pid_match:
                post_id = pid_match.group(1)
        else:
            # Fallback to pid anchor
            anchor = post.find('a', attrs={'name': True})
            if anchor and anchor.get('name'):
                pid_match = PID_REGEX.search(anchor.get('name'))
                if pid_match:
                    post_id = pid_match.group(1)
                    
        # C. Extract Timestamp
        raw_timestamp = 'Unknown'
        time_div = post.find(class_='posttopL')
        if time_div:
            raw_timestamp = time_div.text.strip()
            # Clean up spacing
            raw_timestamp = ' '.join(raw_timestamp.split())
            if 'posted on' in raw_timestamp.lower():
                raw_timestamp = raw_timestamp.lower().split('posted on')[-1].strip()
                
        # D. Extract Post Body
        body_text = ""
        body_div = post.find(class_='KonaBody')
        if not body_div:
            body_div = post.find(class_='threadpostC')
            
        if body_div:
            # Strip out inline scripts/styles if any
            for s in body_div(['script', 'style']):
                s.decompose()
            body_text = body_div.text.strip()
            # Clean up vertical space
            body_text = re.sub(r'\n{3,}', '\n\n', body_text)
            
        posts_extracted.append({
            'thread_id': thread_id,
            'thread_title': title_text,
            'page_num': page_num,
            'post_id': post_id,
            'author': author,
            'raw_timestamp': raw_timestamp,
            'body': body_text
        })
        
    return posts_extracted


def parse_and_export_directory(cache_dir=DEFAULT_CACHE_DIR, output_path=DEFAULT_OUTPUT_FILE):
    """
    Parses all cached HTML files and exports them to a unified JSONLines file.
    """
    if not os.path.exists(cache_dir):
        print(f"Cache directory {cache_dir} does not exist.")
        return
        
    html_files = [f for f in os.listdir(cache_dir) if f.endswith('.html')]
    if not html_files:
        print(f"No cached HTML files found in {cache_dir}.")
        return
        
    print(f"Parsing {len(html_files):,} cached HTML files...")
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    total_posts = 0
    with open(output_path, 'w', encoding='utf-8') as outfile:
        for fname in sorted(html_files):
            file_path = os.path.join(cache_dir, fname)
            posts = parse_html_file(file_path)
            
            for post in posts:
                outfile.write(json.dumps(post) + '\n')
                total_posts += 1
                
    print(f"Successfully exported {total_posts:,} structured comments to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="AboveTopSecret Wayback Machine Ingestion Pipeline")
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")
    
    # Subcommand: fetch-metadata
    meta_parser = subparsers.add_parser("fetch-metadata", help="Fetch clean thread capture metadata from CDX API")
    meta_parser.add_argument("--limit", type=int, default=1000, help="Maximum number of CDX records to query")
    meta_parser.add_argument("--output", default=DEFAULT_METADATA_FILE, help="Path to save metadata JSON")
    
    # Subcommand: download
    dl_parser = subparsers.add_parser("download", help="Download raw HTML captures from Wayback")
    dl_parser.add_argument("--metadata", default=DEFAULT_METADATA_FILE, help="Path to metadata JSON file")
    dl_parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR, help="Directory to store cached HTML files")
    dl_parser.add_argument("--delay", type=float, default=1.5, help="Delay (seconds) between sequential downloads")
    dl_parser.add_argument("--limit", type=int, default=None, help="Limit the number of threads to download")
    
    # Subcommand: parse
    parse_parser = subparsers.add_parser("parse", help="Parse cached HTML files into structured comments")
    parse_parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR, help="Directory containing cached HTML files")
    parse_parser.add_argument("--local-file", default=None, help="Parse a single specified HTML file instead of directory")
    parse_parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE, help="Path to save structured JSONLines comments")
    
    # Subcommand: run-pipeline
    pipe_parser = subparsers.add_parser("run-pipeline", help="Run end-to-end extraction for specific thread IDs")
    pipe_parser.add_argument("--threads", required=True, help="Comma-separated list of target thread IDs to extract")
    pipe_parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR, help="Directory to cache raw HTML files")
    pipe_parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE, help="Path to save output JSONLines comments")
    pipe_parser.add_argument("--delay", type=float, default=1.5, help="Delay (seconds) between downloads")
    
    args = parser.parse_args()
    
    if args.command == "fetch-metadata":
        fetch_metadata(limit=args.limit, output_path=args.output)
        
    elif args.command == "download":
        if not os.path.exists(args.metadata):
            print(f"Error: Metadata file {args.metadata} does not exist. Run fetch-metadata first.", file=sys.stderr)
            sys.exit(1)
        with open(args.metadata) as f:
            metadata_list = json.load(f)
        download_captures(metadata_list, cache_dir=args.cache_dir, delay=args.delay, limit=args.limit)
        
    elif args.command == "parse":
        if args.local_file:
            # Parse single file for testing
            posts = parse_html_file(args.local_file)
            print(f"Parsed single file {args.local_file}. Found {len(posts)} posts.")
            os.makedirs(os.path.dirname(args.output), exist_ok=True)
            with open(args.output, 'w', encoding='utf-8') as f:
                for post in posts:
                    f.write(json.dumps(post) + '\n')
            print(f"Saved parsed test results to {args.output}")
        else:
            parse_and_export_directory(cache_dir=args.cache_dir, output_path=args.output)
            
    elif args.command == "run-pipeline":
        thread_ids = [int(t.strip()) for t in args.threads.split(',')]
        print(f"Executing prototype pipeline for thread IDs: {thread_ids}")
        
        # 1. Fetch metadata specifically for these threads
        temp_meta_list = []
        for tid in thread_ids:
            # Query CDX for this specific thread to ensure clean metadata capture
            cdx_url = (
                "http://web.archive.org/cdx/search/cdx"
                f"?url=abovetopsecret.com/forum/thread{tid}/pg"
                "&matchType=prefix"
                "&output=json"
            )
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                res = requests.get(cdx_url, headers=headers, timeout=20)
                res.raise_for_status()
                data = res.json()
                if len(data) > 1:
                    headers_row = data[0]
                    for row in data[1:]:
                        record = dict(zip(headers_row, row))
                        if record.get('statuscode') == '200' and 'html' in record.get('mimetype', '').lower():
                            original_url = record.get('original', '')
                            # Ensure clean URL with no special char glitches
                            if '%' in original_url or ' ' in original_url or '<' in original_url:
                                continue
                            match = THREAD_REGEX.search(original_url)
                            if match:
                                pg_num = int(match.group(2)) if match.group(2) and match.group(2).isdigit() else 1
                                temp_meta_list.append({
                                    'thread_id': tid,
                                    'page_num': pg_num,
                                    'timestamp': record.get('timestamp', ''),
                                    'original_url': original_url
                                })
            except Exception as e:
                print(f"Warning: Failed to fetch metadata for thread {tid}: {e}", file=sys.stderr)
                
        # Deduplicate metadata by (thread_id, page_num) keeping the earliest or latest timestamp
        seen = {}
        for item in temp_meta_list:
            key = (item['thread_id'], item['page_num'])
            if key not in seen or int(item['timestamp']) > int(seen[key]['timestamp']):
                seen[key] = item
        final_meta = list(seen.values())
        
        print(f"Discovered {len(final_meta)} clean page captures to recover.")
        
        # 2. Download the captures
        download_captures(final_meta, cache_dir=args.cache_dir, delay=args.delay)
        
        # 3. Parse and export
        parse_and_export_directory(cache_dir=args.cache_dir, output_path=args.output)
        
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
