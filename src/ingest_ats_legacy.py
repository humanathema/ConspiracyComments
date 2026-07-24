#!/usr/bin/env python
"""ingest_ats_legacy.py

Downloads and parses pre-2003 legacy Ikonboard pages from AboveTopSecret
using Wayback Machine archived snapshots.
Uses multi-threading and handles Tor-based proxy IP rotation.
"""

import os
import sys
import json
import re
import time
import argparse
from threading import Thread, Lock
from urllib.parse import urlparse, parse_qs
import requests
from bs4 import BeautifulSoup

# Define colors for command line visibility
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"


def print_log(level, msg):
    timestamp = time.strftime("%H:%M:%S")
    if level == "INFO":
        print(f"[{timestamp}] {GREEN}[INFO]{RESET} {msg}")
    elif level == "WARNING":
        print(f"[{timestamp}] {YELLOW}[WARNING]{RESET} {msg}")
    elif level == "ERROR":
        print(f"[{timestamp}] {RED}[ERROR]{RESET} {msg}")
    elif level == "TOR":
        print(f"[{timestamp}] {CYAN}[TOR]{RESET} {msg}")


def rotate_tor_ip():
    """Request a new Tor circuit/IP from the local Tor control port (9051)."""
    from socks import SOCKS5Error
    import socks
    import socket

    print_log("TOR", "Triggering Tor IP rotation... Requesting new circuit...")
    try:
        # Connect to Tor Control Port
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(("127.0.0.1", 9051))
        s.send(b'AUTHENTICATE ""\r\n')
        response = s.recv(1024)
        if b"250" in response:
            s.send(b"SIGNAL NEWNYM\r\n")
            response = s.recv(1024)
            if b"250" in response:
                print_log("TOR", "Tor SOCKS circuit rotated successfully!")
                time.sleep(3.0)  # Wait for circuit to establish
                return True
            else:
                print_log("WARNING", f"Signal response failed: {response}")
        else:
            print_log("WARNING", f"Auth response failed: {response}")
        s.close()
    except Exception as e:
        print_log("WARNING", f"Could not connect to Tor control port 9051: {e}")
    return False


def parse_legacy_html(html_content, target):
    """Parses legacy Ikonboard HTML and returns a list of comments."""
    soup = BeautifulSoup(html_content, "html.parser")
    posts = []

    # Thread Title is usually in the title tag
    thread_title = "Unknown Thread"
    if soup.title:
        title_text = soup.title.string or ""
        # Remove AboveTopSecret.com Message Board - prefix
        thread_title = title_text.replace("AboveTopSecret.com Message Board - ", "").strip()

    forum_id = target.get("forum_id")
    topic_id = target.get("topic_id")

    bottomlines = soup.find_all("td", class_="bottomline")

    for meta_td in bottomlines:
        table = meta_td.find_parent("table")
        if not table:
            continue

        author_td = table.find("td", rowspan="2")
        body_td = table.find("td", width="80%")

        if author_td and body_td:
            # Extract Author
            author_b = author_td.find("b")
            author = author_b.get_text(strip=True) if author_b else "Unknown"

            # Extract Post ID (postno)
            post_id = "Unknown"
            reply_link = body_td.find("a", href=lambda href: href and "postno=" in href)
            if reply_link:
                match = re.search(r"postno=(\d+)", reply_link["href"])
                if match:
                    post_id = match.group(1)

            # Extract Timestamp
            posted_on_text = "Unknown"
            for b in meta_td.find_all("b"):
                prev_sibling = b.previous_sibling
                if prev_sibling and "Posted on:" in prev_sibling:
                    posted_on_text = b.get_text(strip=True)
                    break

            # Extract Body - gather content after the first hr tag
            body = ""
            hr = body_td.find("hr")
            if hr:
                siblings = list(hr.next_siblings)
                clean_siblings = []
                for s in siblings:
                    if s.name == "font":
                        clean_siblings.append(s.get_text())
                    elif isinstance(s, str):
                        clean_siblings.append(s)
                body = "".join(clean_siblings).strip()
            else:
                body_font = body_td.find("font", size="2")
                body = body_font.get_text(strip=True) if body_font else body_td.get_text(strip=True)

            posts.append({
                "thread_id": topic_id,
                "forum_id": forum_id,
                "thread_title": thread_title,
                "post_id": f"{topic_id}_{post_id}",
                "author": author,
                "raw_timestamp": posted_on_text,
                "body": body,
                "source": "wayback_legacy",
            })

    return posts


def worker_thread(targets, output_file, thread_id, delay, use_tor, write_lock):
    """Worker thread that processes the target pages sequentially."""
    session = requests.Session()
    proxies = None
    if use_tor:
        proxies = {
            "http": "socks5h://127.0.0.1:9050",
            "https": "socks5h://127.0.0.1:9050",
        }

    for idx, target in enumerate(targets):
        url = target["url"]
        timestamp = target["timestamp"]
        # Format the direct/raw Wayback URL
        wayback_url = f"https://web.archive.org/web/{timestamp}id_/{url}"

        forum_id = target["forum_id"]
        topic_id = target["topic_id"]
        start_offset = target["start_offset"]

        success = False
        retries = 3

        for attempt in range(1, retries + 1):
            try:
                if delay > 0:
                    time.sleep(delay)

                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                res = session.get(wayback_url, headers=headers, proxies=proxies, timeout=20)

                if res.status_code == 200:
                    html_content = res.text
                    posts = parse_legacy_html(html_content, target)

                    if posts:
                        with write_lock:
                            with open(output_file, "a", encoding="utf-8") as f:
                                for post in posts:
                                    f.write(json.dumps(post) + "\n")

                        print_log(
                            "INFO",
                            f"[Thread-{thread_id}] [{idx+1}/{len(targets)}] "
                            f"Successfully parsed {len(posts)} posts from F{forum_id} T{topic_id} "
                            f"(start={start_offset})",
                        )
                    else:
                        print_log(
                            "WARNING",
                            f"[Thread-{thread_id}] No posts extracted from F{forum_id} T{topic_id} "
                            f"at {wayback_url}",
                        )

                    success = True
                    break
                elif res.status_code == 503 or res.status_code == 429:
                    print_log(
                        "WARNING",
                        f"[Thread-{thread_id}] Blocked/Throttled (Status {res.status_code}) on "
                        f"attempt {attempt}/{retries}. URL: {wayback_url}",
                    )
                    if use_tor:
                        with write_lock:
                            rotate_tor_ip()
                else:
                    print_log(
                        "WARNING",
                        f"[Thread-{thread_id}] HTTP {res.status_code} on attempt {attempt}/{retries} "
                        f"for URL: {wayback_url}",
                    )

            except Exception as e:
                print_log(
                    "WARNING",
                    f"[Thread-{thread_id}] Network error: {e} on attempt {attempt}/{retries} "
                    f"for URL: {wayback_url}",
                )
                if use_tor:
                    with write_lock:
                        rotate_tor_ip()

        if not success:
            print_log(
                "ERROR",
                f"[Thread-{thread_id}] Failed to download F{forum_id} T{topic_id} after {retries} attempts.",
            )


def load_completed_pages(output_file):
    """Loads already processed pages from the output file to support resuming."""
    completed = set()
    if os.path.exists(output_file):
        print_log("INFO", f"Reading existing progress from: {output_file}")
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    forum_id = data.get("forum_id")
                    thread_id = data.get("thread_id")
                    # Deduplicate completed pages
                    # Extract start offset from post_id or parsing logic
                    # To be perfectly safe, we can match completed page keys
                    completed.add(f"{forum_id}_{thread_id}")
                except Exception:
                    continue
        print_log("INFO", f"Found {len(completed):,} already completed target threads/forums.")
    return completed


def main():
    parser = argparse.ArgumentParser(description="Ingest ATS Legacy Pre-2003 Ikonboard Comments.")
    parser.add_argument(
        "--index",
        default="data/processed/ats_legacy_index_complete.json",
        help="Path to the compiled legacy catalog index.",
    )
    parser.add_argument(
        "--output",
        default="data/processed/ats_comments_legacy_complete.jsonl",
        help="Path to output the scraped comments JSONL file.",
    )
    parser.add_argument(
        "--threads", type=int, default=2, help="Number of concurrent worker threads."
    )
    parser.add_argument(
        "--delay", type=float, default=1.0, help="Delay (in seconds) between requests."
    )
    parser.add_argument(
        "--tor", action="store_true", default=True, help="Use Tor SOCKS5 proxy on port 9050."
    )

    args = parser.parse_args()

    print("=================================================================")
    print("🚀  ATS Legacy Pre-2003 Comment Ingestion Crawler")
    print("=================================================================")
    print(f"Index File:   {args.index}")
    print(f"Output File:  {args.output}")
    print(f"Threads:      {args.threads}")
    print(f"Delay:        {args.delay}s")
    print(f"Tor Rotation: {'Enabled (Port 9050)' if args.tor else 'Disabled'}")
    print("=================================================================\n")

    # Load targets
    if not os.path.exists(args.index):
        print_log("ERROR", f"Legacy index not found at: {args.index}. Please compile it first.")
        sys.exit(1)

    with open(args.index, "r", encoding="utf-8") as f:
        targets = json.load(f)

    print_log("INFO", f"Loaded {len(targets):,} total legacy target pages from index.")

    # Resuming logic
    completed = load_completed_pages(args.output)
    remaining_targets = []
    for t in targets:
        key = f"{t['forum_id']}_{t['topic_id']}"
        if key not in completed:
            remaining_targets.append(t)

    print_log(
        "INFO",
        f"Filtered out completed pages. {len(remaining_targets):,} target pages remaining to scrape.",
    )

    if not remaining_targets:
        print_log("INFO", "All pages have already been successfully scraped! Nothing to do.")
        sys.exit(0)

    # Split targets across worker threads
    chunks = [[] for _ in range(args.threads)]
    for i, t in enumerate(remaining_targets):
        chunks[i % args.threads].append(t)

    write_lock = Lock()
    threads = []

    print_log("INFO", f"Launching {args.threads} worker threads...")
    for i in range(args.threads):
        t = Thread(
            target=worker_thread,
            args=(chunks[i], args.output, i + 1, args.delay, args.tor, write_lock),
        )
        t.start()
        threads.append(t)

    # Wait for all threads to finish
    for t in threads:
        t.join()

    print_log("INFO", "🎉 Legacy Ingestion Sweep Complete!")


if __name__ == "__main__":
    main()
