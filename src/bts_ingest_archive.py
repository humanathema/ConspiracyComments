#!/usr/bin/env python
"""bts_ingest_archive.py

Wayback Machine ingestion pipeline for BelowTopSecret.com (BTS), ATS's
official off-topic/chitchat sister board (same operator, "The Above
Network" - see handoff/bts_ingestion_scoping_findings.md for the
verification and archive-coverage scoping that preceded this script).

Reuses the generic, skin-tolerant download/parse machinery from
src/ingest_ats_archive.py (imported, not modified - keeps this ingest
fully separate from the concurrent ATS-parity work touching that file).
Only the CDX querying and default paths are BTS-specific, because BTS's
own archive spans two different URL/template generations:
  - pre-2007: belowtopsecret.com/thread<ID>/pg<N>            (no /forum/)
  - 2007-2010: belowtopsecret.com/forum/thread<ID>/pg<N>      (/forum/, matches
    ATS's current URL shape)
`fetch_metadata` below queries both prefixes and merges them; a single
CDX prefix query cannot span both since the Wayback CDX API's
matchType=prefix only matches URLs that literally start with the given
string.

Commands: fetch-metadata, download, parse, to-parquet, run-pipeline
(same shape as ingest_ats_archive.py).
"""

import os
import sys
import re
import json
import time
import argparse
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_ats_archive import (
    get_http_session,
    download_captures,
    parse_html_file,
    resolve_reply_edges,
    convert_jsonl_to_parquet,
    CACHE_FILENAME_REGEX,
)

DEFAULT_CACHE_DIR = "data/raw/bts_raw_html"
DEFAULT_OUTPUT_FILE = "data/processed/bts_comments.jsonl"
DEFAULT_METADATA_FILE = "data/processed/bts_metadata.json"
PARSED_LEDGER_NAME = "bts_parsed_files.txt"

# Matches thread pages with or without a leading /forum/ segment - BTS's
# two archive-era URL schemes (see module docstring).
THREAD_REGEX = re.compile(r'(?:/forum)?/thread(\d+)/pg(\d+|lastpost)?', re.IGNORECASE)

CDX_URL_PREFIXES = [
    "belowtopsecret.com/forum/thread",
    "belowtopsecret.com/thread",
]


def _query_cdx_prefix(session, url_prefix, limit):
    cdx_url = (
        "http://web.archive.org/cdx/search/cdx"
        f"?url={url_prefix}"
        "&matchType=prefix"
        "&collapse=urlkey"
        f"&limit={limit}"
        "&output=json"
    )
    try:
        response = session.get(cdx_url, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error querying CDX API for prefix '{url_prefix}': {e}", file=sys.stderr)
        return []
    if not data or len(data) < 2:
        return []
    headers_row = data[0]
    return [dict(zip(headers_row, row)) for row in data[1:]]


def fetch_metadata(limit=1000, clean_only=True, output_path=DEFAULT_METADATA_FILE):
    """
    Queries the Wayback CDX API for clean BelowTopSecret thread captures,
    across both URL-scheme eras, deduping by (thread_id, page_num) and
    keeping the earliest capture per page (BTS's real content skews
    2004-2010; earliest captures are least likely to be post-death
    redirect/parking noise).
    """
    session = get_http_session()
    all_records = []
    for prefix in CDX_URL_PREFIXES:
        print(f"Querying Wayback CDX API for prefix '{prefix}' (limit={limit})...")
        recs = _query_cdx_prefix(session, prefix, limit)
        print(f"  -> {len(recs):,} raw records")
        all_records.extend(recs)

    print(f"Found {len(all_records):,} raw captures across both URL schemes. Filtering and mapping...")

    by_key = {}
    for record in all_records:
        original_url = record.get('original', '')
        statuscode = record.get('statuscode', '-')
        mimetype = record.get('mimetype', '')
        timestamp = record.get('timestamp', '')
        digest = record.get('digest', '')

        parsed = urlparse(original_url)
        path = parsed.path

        match = THREAD_REGEX.search(path)
        if not match:
            continue

        thread_id = int(match.group(1))
        page_val = match.group(2)

        if not page_val:
            page_num = 1
        elif page_val.lower() == 'lastpost':
            page_num = 'lastpost'
        else:
            page_num = int(page_val)

        if clean_only:
            if statuscode != '200':
                continue
            if 'html' not in mimetype.lower():
                continue

        if '%' in path or ' ' in path or '<' in path or '*' in path or "'" in path:
            continue

        key = (thread_id, page_num)
        existing = by_key.get(key)
        if existing is None or timestamp < existing['timestamp']:
            by_key[key] = {
                'thread_id': thread_id,
                'page_num': page_num,
                'timestamp': timestamp,
                'original_url': original_url,
                'statuscode': statuscode,
                'mimetype': mimetype,
                'digest': digest,
            }

    metadata_list = list(by_key.values())
    print(f"Retained {len(metadata_list):,} distinct clean thread-page captures (deduped across both schemes).")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(metadata_list, f, indent=2)
    print(f"Saved metadata to {output_path}")
    return metadata_list


def parse_and_export_directory(cache_dir=DEFAULT_CACHE_DIR, output_path=DEFAULT_OUTPUT_FILE):
    """
    Same resumable, multiprocess, checkpointed parse loop as
    ingest_ats_archive.parse_and_export_directory, copied rather than
    imported only because that function hardcodes its ledger filename
    ('ats_parsed_files.txt') - reusing it unmodified against a BTS output
    directory would risk colliding with ATS's own ledger if the two ever
    shared a data/processed/ directory. Everything else about it is
    identical.
    """
    if not os.path.exists(cache_dir):
        print(f"Cache directory {cache_dir} does not exist.")
        return

    all_html_files = [f for f in os.listdir(cache_dir) if f.endswith('.html')]
    if not all_html_files:
        print(f"No cached HTML files found in {cache_dir}.")
        return

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    parsed_tracker_path = os.path.join(os.path.dirname(output_path), PARSED_LEDGER_NAME)

    if not os.path.exists(output_path) and os.path.exists(parsed_tracker_path):
        try:
            os.remove(parsed_tracker_path)
        except Exception:
            pass

    parsed_files = set()
    if os.path.exists(parsed_tracker_path):
        try:
            with open(parsed_tracker_path, "r", encoding="utf-8", errors="ignore") as ledger_f:
                parsed_files = {line.strip() for line in ledger_f if line.strip()}
        except Exception:
            pass

    html_files_to_parse = [f for f in all_html_files if f not in parsed_files]
    total_all_files = len(all_html_files)
    total_to_parse = len(html_files_to_parse)

    if total_to_parse == 0:
        print(f"All {total_all_files:,} cached HTML files have already been parsed!")
        print(f"Comments are preserved in {output_path}")
        return

    if len(parsed_files) > 0:
        print(f"Found {len(parsed_files):,} already parsed files in ledger. Resuming parser...")

    print(f"Parsing remaining {total_to_parse:,} out of {total_all_files:,} files using multi-processing...")

    import multiprocessing
    cores = min(multiprocessing.cpu_count(), 8)
    print(f"Spawning {cores} parallel parsing processes...")

    from concurrent.futures import ProcessPoolExecutor, as_completed

    chunk_size = 5000
    parsed_files_count = 0
    empty_files = 0
    start_time = time.time()
    last_print_time = start_time

    mode = 'a' if len(parsed_files) > 0 else 'w'

    with ProcessPoolExecutor(max_workers=cores) as executor:
        for chunk_idx in range(0, total_to_parse, chunk_size):
            chunk_filenames = html_files_to_parse[chunk_idx:chunk_idx + chunk_size]
            chunk_paths = [os.path.join(cache_dir, f) for f in chunk_filenames]

            futures = {executor.submit(parse_html_file, fp): f for fp, f in zip(chunk_paths, chunk_filenames)}

            chunk_posts = []
            chunk_processed_files = []

            for future in as_completed(futures):
                filename = futures[future]
                parsed_files_count += 1
                chunk_processed_files.append(filename)

                try:
                    posts = future.result()
                    if not posts:
                        empty_files += 1
                    else:
                        chunk_posts.extend(posts)
                except Exception:
                    empty_files += 1

                now = time.time()
                if now - last_print_time >= 1.0 or parsed_files_count == total_to_parse:
                    last_print_time = now
                    elapsed = now - start_time
                    speed = parsed_files_count / elapsed if elapsed > 0 else 0
                    percent = (parsed_files_count / total_to_parse) * 100
                    eta_sec = (total_to_parse - parsed_files_count) / speed if speed > 0 else 0
                    eta_str = f"{int(eta_sec // 60)}m {int(eta_sec % 60)}s" if eta_sec > 60 else f"{int(eta_sec)}s"
                    print(f"  Progress: {parsed_files_count:,}/{total_to_parse:,} parsed ({percent:.1f}%) | "
                          f"Speed: {speed:.1f} files/sec | ETA: {eta_str} | New Posts: {len(chunk_posts):,}",
                          end="\r", flush=True)

            if chunk_posts:
                resolve_reply_edges(chunk_posts)
                with open(output_path, mode, encoding='utf-8') as outfile:
                    for post in chunk_posts:
                        outfile.write(json.dumps(post) + '\n')

            with open(parsed_tracker_path, "a", encoding="utf-8") as ledger_f:
                for fn in chunk_processed_files:
                    ledger_f.write(fn + "\n")

            mode = 'a'

    duration = time.time() - start_time
    print(f"\n\nParsing completed in {duration:.1f} seconds.")
    print(f"Chunked files parsed: {total_to_parse:,} ({empty_files:,} empty).")
    print(f"All parsed entries have been written to {output_path} & checkpoint ledger updated.")


def main():
    parser = argparse.ArgumentParser(description="BelowTopSecret.com Wayback Machine Ingestion Pipeline")
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    meta_parser = subparsers.add_parser("fetch-metadata", help="Fetch clean thread capture metadata from CDX API")
    meta_parser.add_argument("--limit", type=int, default=1000, help="Max CDX records to query per URL scheme")
    meta_parser.add_argument("--output", default=DEFAULT_METADATA_FILE, help="Path to save metadata JSON")

    dl_parser = subparsers.add_parser("download", help="Download raw HTML captures from Wayback")
    dl_parser.add_argument("--metadata", default=DEFAULT_METADATA_FILE, help="Path to metadata JSON file")
    dl_parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR, help="Directory to store cached HTML files")
    dl_parser.add_argument("--delay", type=float, default=1.5, help="Delay (seconds) between sequential downloads")
    dl_parser.add_argument("--limit", type=int, default=None, help="Limit the number of captures to download")
    dl_parser.add_argument("--threads", type=int, default=1, help="Number of concurrent worker threads")
    dl_parser.add_argument("--shard-count", type=int, default=1, help="Total number of parallel scraper instances")
    dl_parser.add_argument("--shard-id", type=int, default=0, help="Zero-indexed ID of this shard instance")

    parse_parser = subparsers.add_parser("parse", help="Parse cached HTML files into structured comments")
    parse_parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR, help="Directory containing cached HTML files")
    parse_parser.add_argument("--local-file", default=None, help="Parse a single specified HTML file instead of directory")
    parse_parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE, help="Path to save structured JSONLines comments")

    parquet_parser = subparsers.add_parser("to-parquet", help="Convert the JSONLines comments export to Parquet")
    parquet_parser.add_argument("--input", default=DEFAULT_OUTPUT_FILE, help="Path to the JSONLines comments file")
    parquet_parser.add_argument("--output", default=None, help="Path to write the Parquet file")

    pipe_parser = subparsers.add_parser("run-pipeline", help="Fetch metadata, download, and parse end-to-end")
    pipe_parser.add_argument("--limit", type=int, default=1000, help="Max CDX records to query per URL scheme")
    pipe_parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR, help="Directory to cache raw HTML files")
    pipe_parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE, help="Path to save output JSONLines comments")
    pipe_parser.add_argument("--delay", type=float, default=1.5, help="Delay (seconds) between downloads")
    pipe_parser.add_argument("--threads", type=int, default=1, help="Number of concurrent download worker threads")
    pipe_parser.add_argument("--download-limit", type=int, default=None, help="Cap number of captures downloaded")

    args = parser.parse_args()

    if args.command == "fetch-metadata":
        fetch_metadata(limit=args.limit, output_path=args.output)

    elif args.command == "download":
        if not os.path.exists(args.metadata):
            print(f"Error: Metadata file {args.metadata} does not exist. Run fetch-metadata first.", file=sys.stderr)
            sys.exit(1)
        with open(args.metadata) as f:
            metadata_list = json.load(f)

        if args.shard_count > 1:
            if args.shard_id < 0 or args.shard_id >= args.shard_count:
                print(f"Error: --shard-id must be between 0 and {args.shard_count - 1}", file=sys.stderr)
                sys.exit(1)
            metadata_list = [item for idx, item in enumerate(metadata_list) if idx % args.shard_count == args.shard_id]
            print(f"[SHARDING] Running as Shard {args.shard_id} of {args.shard_count}. Retained {len(metadata_list):,} targets.")

        download_captures(metadata_list, cache_dir=args.cache_dir, delay=args.delay, limit=args.limit, threads=args.threads)

    elif args.command == "parse":
        if args.local_file:
            posts = parse_html_file(args.local_file)
            print(f"Parsed single file {args.local_file}. Found {len(posts)} posts.")
            os.makedirs(os.path.dirname(args.output), exist_ok=True)
            with open(args.output, 'w', encoding='utf-8') as f:
                for post in posts:
                    f.write(json.dumps(post) + '\n')
            print(f"Saved parsed test results to {args.output}")
        else:
            parse_and_export_directory(cache_dir=args.cache_dir, output_path=args.output)

    elif args.command == "to-parquet":
        output_path = args.output or (os.path.splitext(args.input)[0] + '.parquet')
        convert_jsonl_to_parquet(args.input, output_path)

    elif args.command == "run-pipeline":
        metadata_list = fetch_metadata(limit=args.limit, output_path=DEFAULT_METADATA_FILE)
        download_captures(metadata_list, cache_dir=args.cache_dir, delay=args.delay, limit=args.download_limit, threads=args.threads)
        parse_and_export_directory(cache_dir=args.cache_dir, output_path=args.output)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
