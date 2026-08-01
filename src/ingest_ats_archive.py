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
import threading
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
# Matches both cache filename conventions: CC downloads use "thread268679_pg1.html",
# Wayback downloads use "thread_268679_pg1_<timestamp>.html".
CACHE_FILENAME_REGEX = re.compile(r'^thread_?(\d+)_pg(\d+|lastpost)', re.IGNORECASE)


def check_tor_available():
    """
    Checks if a local SOCKS5 proxy is listening on Tor's default port 9050 or Tor Browser port 9150.
    Returns the port if available, otherwise None.
    """
    import socket
    for port in [9050, 9150]:
        s = socket.socket()
        try:
            s.settimeout(1.0)
            s.connect(('127.0.0.1', port))
            s.close()
            return port
        except Exception:
            continue
    return None


def rotate_tor_ip(control_port=9051):
    """
    Sends a NEWNYM signal to the Tor CLI ControlPort, requesting a clean exit node / IP.
    """
    try:
        from stem import Signal
        from stem.control import Controller
        # Support both default control port and Tor Browser control port 9151
        for port in [control_port, 9151]:
            try:
                with Controller.from_port(port=port) as controller:
                    controller.authenticate()  # Uses cookie auth or password
                    controller.signal(Signal.NEWNYM)
                    print(f"  [TOR] IP rotation triggered on control port {port}. Requesting new circuit exit node...")
                    time.sleep(2.5)  # Wait for circuit to establish
                    return True
            except Exception:
                continue
        return False
    except Exception as e:
        print(f"  [TOR WARNING] Failed to rotate IP: {e}", file=sys.stderr)
        return False


def get_http_session(use_tor_if_available=True):
    """
    Returns a requests.Session, routing traffic through Tor if Tor is active.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Encoding": "identity",
        })
    
    tor_port = check_tor_available() if use_tor_if_available else None
    if tor_port:
        print(f"  [TOR] Local Tor SOCKS5 proxy detected on port {tor_port}. Enabling targeted proxy routing!")
        session.proxies = {
            'http': f'socks5h://127.0.0.1:{tor_port}',
            'https': f'socks5h://127.0.0.1:{tor_port}'
        }
    else:
        if use_tor_if_available:
            print("  [INFO] No Tor proxy detected on port 9050/9150. Proceeding with a direct connection.")
    return session


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
        session = get_http_session()
        response = session.get(cdx_url, timeout=30)
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
    
class AdaptiveRateController:
    def __init__(self, initial_concurrency=3, min_concurrency=1, max_concurrency=8,
                 initial_delay=0.5, min_delay=0.0, max_delay=10.0):
        self.lock = threading.Lock()
        self.concurrency = initial_concurrency
        self.min_concurrency = min_concurrency
        self.max_concurrency = max_concurrency
        self.delay = initial_delay
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.semaphore = threading.Semaphore(initial_concurrency)
        self._sem_count = initial_concurrency  # tracked manually since Semaphore has no public counter

        # rolling outcome tracking
        self.recent_results = []  # True=success, False=failure(403/etc)
        self.window_size = 40
        self.since_last_adjust = 0
        self.adjust_every = 20  # re-evaluate every N completions

    def acquire(self):
        self.semaphore.acquire()
        time.sleep(self.delay)

    def release(self):
        self.semaphore.release()

    def report(self, success):
        with self.lock:
            self.recent_results.append(success)
            if len(self.recent_results) > self.window_size:
                self.recent_results.pop(0)
            self.since_last_adjust += 1

            # Fast reaction: any failure immediately increases delay a bit,
            # independent of the periodic batch adjustment below.
            if not success:
                self.delay = min(self.max_delay, self.delay * 1.5 + 0.1)

            if self.since_last_adjust >= self.adjust_every and len(self.recent_results) >= 10:
                self.since_last_adjust = 0
                fail_rate = self.recent_results.count(False) / len(self.recent_results)

                if fail_rate == 0:
                    # healthy: probe upward - add concurrency, shrink delay
                    self._change_concurrency(+1)
                    self.delay = max(self.min_delay, self.delay * 0.85)
                elif fail_rate > 0.15:
                    # struggling: back off hard - cut concurrency, grow delay
                    self._change_concurrency(-2)
                    self.delay = min(self.max_delay, self.delay * 2.0 + 0.2)
                # else: fail_rate between 0 and 0.15 - hold steady, let the
                # per-failure delay bump above do the fine-tuning

    def _change_concurrency(self, delta):
        new_count = max(self.min_concurrency, min(self.max_concurrency, self._sem_count + delta))
        diff = new_count - self._sem_count
        if diff > 0:
            for _ in range(diff):
                self.semaphore.release()
        elif diff < 0:
            for _ in range(-diff):
                self.semaphore.acquire(blocking=False)  # may not shrink immediately if all permits in use
        self._sem_count = new_count

    def status(self):
        with self.lock:
            return self._sem_count, round(self.delay, 3)


def download_captures(metadata_list, cache_dir=DEFAULT_CACHE_DIR, delay=1.5, limit=None, threads=1):
    """
    Downloads raw rewritten-free HTML captures from the Wayback Machine.
    Supports multi-threaded parallel downloads and Tor IP rotation.
    """
    from threading import Lock
    from concurrent.futures import ThreadPoolExecutor
    import concurrent.futures

    os.makedirs(cache_dir, exist_ok=True)
    
    # Apply limit if specified
    targets = metadata_list[:limit] if limit else metadata_list
    total = len(targets)
    
    # Detect if Tor is active
    test_session = get_http_session()
    is_using_tor = bool(test_session.proxies)
    
    print(f"Beginning download phase for {total} captures (threads={threads}, delay={delay}s, tor_rotation={is_using_tor})...")
    
    # Filter out already cached targets first to prevent threading overhead on cached files
    remaining_targets = []
    cached_count = 0
    
    for item in targets:
        thread_id = item['thread_id']
        page_num = item['page_num']
        timestamp = item['timestamp']
        
        filename = f"thread_{thread_id}_pg{page_num}_{timestamp}.html"
        file_path = os.path.join(cache_dir, filename)
        
        if os.path.exists(file_path):
            cached_count += 1
        else:
            remaining_targets.append(item)
            
    print(f"Already cached: {cached_count:,}. Remaining to download: {len(remaining_targets):,}")
    
    if not remaining_targets:
        print("All target captures are already cached on disk!")
        return 0
        
    downloaded_count = 0
    global_download_lock = Lock()
    last_rotation_time = [0.0]  # Use mutable list to allow updates within nested closures

    # Adaptive Rate Controller setup
    # Wayback is a replay endpoint, so we use a conservative ceiling of max(threads, 8) and default delay
    controller = AdaptiveRateController(
        initial_concurrency=min(3, threads),
        max_concurrency=max(threads, 8),
        initial_delay=delay
    )

    def rotate_tor_ip_throttled():
        with global_download_lock:
            now = time.time()
            if now - last_rotation_time[0] > 15.0:
                rotate_tor_ip()
                last_rotation_time[0] = now
                return True
        return False

    def worker_thread(worker_items, thread_id_num):
        nonlocal downloaded_count
        session = get_http_session()
        
        for idx, item in enumerate(worker_items):
            thread_id_val = item['thread_id']
            page_num = item['page_num']
            timestamp = item['timestamp']
            original_url = item['original_url']
            
            filename = f"thread_{thread_id_val}_pg{page_num}_{timestamp}.html"
            file_path = os.path.join(cache_dir, filename)
            
            wayback_url = f"https://web.archive.org/web/{timestamp}id_/{original_url}"
            
            with global_download_lock:
                conc, curr_delay = controller.status()
                print(f"[Thread-{thread_id_num}] [{idx+1}/{len(worker_items)}] Downloading thread {thread_id_val} page {page_num}... (concurrency={conc}, delay={curr_delay}s)")
                
            max_attempts = 3 
            success = False
            
            controller.acquire()
            try:
                for attempt in range(max_attempts):
                    try:
                        res = session.get(wayback_url, timeout=20, stream=True)
                        if res.status_code == 200:
                            # Read raw content to bypass requests automatic decompression errors
                            # when IA serves uncompressed text with a 'Content-Encoding: gzip' header.
                            raw_bytes = res.raw.read(decode_content=False)
                            
                            # Detect if the payload is actually gzip-compressed (magic bytes 1f 8b)
                            if raw_bytes.startswith(b"\x1f\x8b"):
                                try:
                                    import gzip
                                    html_bytes = gzip.decompress(raw_bytes)
                                except Exception:
                                    html_bytes = raw_bytes # Fallback
                            else:
                                html_bytes = raw_bytes
                                
                            html_text = html_bytes.decode('utf-8', errors='ignore')
                            
                            with open(file_path, 'w', encoding='utf-8', errors='ignore') as f:
                                f.write(html_text)
                            with global_download_lock:
                                downloaded_count += 1
                            
                            success = True
                            controller.report(True)
                            break
                        elif res.status_code in [429, 403, 503]:
                            with global_download_lock:
                                print(f"  [Thread-{thread_id_num}] -> HTTP status {res.status_code} (Blocked/Throttled) on attempt {attempt+1}/{max_attempts}.", file=sys.stderr)
                            controller.report(False)
                            if is_using_tor:
                                rotate_tor_ip_throttled()
                                time.sleep(3)
                            else:
                                if attempt < max_attempts - 1:
                                    time.sleep(2 * (attempt + 1))
                                    continue
                                break
                        else:
                            with global_download_lock:
                                print(f"  [Thread-{thread_id_num}] Warning: HTTP status {res.status_code} for {wayback_url}", file=sys.stderr)
                            controller.report(False)
                            break
                    except Exception as e:
                        with global_download_lock:
                            print(f"  [Thread-{thread_id_num}] Connection error/Timeout: {e} on attempt {attempt+1}/{max_attempts}.", file=sys.stderr)
                        controller.report(False)
                        if is_using_tor:
                            rotate_tor_ip_throttled()
                            time.sleep(3)
                        else:
                            if attempt < max_attempts - 1:
                                time.sleep(2 * (attempt + 1))
                                continue
                            break
            finally:
                controller.release()
                        
    # Split the remaining targets across worker threads
    chunks = [[] for _ in range(threads)]
    for i, item in enumerate(remaining_targets):
        chunks[i % threads].append(item)
        
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = []
        for i in range(threads):
            if chunks[i]:
                futures.append(executor.submit(worker_thread, chunks[i], i + 1))
        concurrent.futures.wait(futures)
        
    print(f"Download phase completed. New downloads: {downloaded_count}, Already cached: {cached_count}")
    return downloaded_count


PID_NAME_REGEX = re.compile(r'^pid(\d+)$', re.IGNORECASE)
STAR_IMG_REGEX = re.compile(r'staron\.png', re.IGNORECASE)
# Some skins wrap each token of the "posted on <date> by <name>" line in its
# own inline tag, so get_text('\n') injects a newline between "on", the
# date, "by", and the name. `(?:[^\n]|\n(?!\s*\n))` tolerates those single
# embedded newlines while still stopping at a genuine blank-line break
# (double newline), which reliably follows the header before the body.
_TOKEN_SPANNING_NEWLINES = r'(?:[^\n]|\n(?!\s*\n))'
POSTED_TIMESTAMP_REGEX = re.compile(
    r'(?:posted on|started on)\s+'
    rf'({_TOKEN_SPANNING_NEWLINES}+?)'
    rf'(?:\s+by\s+({_TOKEN_SPANNING_NEWLINES}+?))?'
    r'\s*\n\s*\n',
    re.IGNORECASE,
)
QUOTE_AUTHOR_REGEX = re.compile(r'originally posted by\s*:?\s*([^\n]{1,60})', re.IGNORECASE)
REPLY_TO_REGEX = re.compile(r'reply to\s+(?:this\s+)?post by\s*:?\s*([^\n]{1,60})', re.IGNORECASE)
QUOTE_PREFIX_REGEX = re.compile(r'^(?:originally posted by|reply to (?:this )?post by)\s*:?\s*', re.IGNORECASE)


MAX_PLAUSIBLE_USERNAME_LEN = 40


def _extract_quote_author_and_text(quotebox_text):
    """Splits a <div class="quotebox"> element's flattened text into (author,
    quoted_text). Across every ATS skin generation checked (2004 image-icon
    style: '<i>Originally posted by X</i>', 2018 font-icon style: bare '<i>
    X</i>' with no prefix phrase), the first non-blank line is usually the
    quoted author -- with or without an 'Originally posted by' / 'reply to
    (this) post by' prefix. But not every quotebox quotes a member post --
    some quote a site disclaimer/footer with no author line at all, in which
    case the "first line" heuristic would wrongly grab a chunk of that quoted
    prose as if it were a username. Only trust the first line as an author
    when it either had an explicit prefix phrase, or is short/plain enough to
    plausibly be a bare username (no sentence-ending punctuation, under
    MAX_PLAUSIBLE_USERNAME_LEN chars) -- otherwise treat the whole block as
    author-less quoted text rather than guessing."""
    lines = [_clean_ws(ln) for ln in str(quotebox_text).split('\n')]
    lines = [ln for ln in lines if ln]
    if not lines:
        return None, ''
    had_prefix = bool(QUOTE_PREFIX_REGEX.match(lines[0]))
    candidate = QUOTE_PREFIX_REGEX.sub('', lines[0]).strip()
    looks_like_username = (
        candidate
        and len(candidate) <= MAX_PLAUSIBLE_USERNAME_LEN
        and not re.search(r'[.!?]\s+\S', candidate)
    )
    if had_prefix or looks_like_username:
        return candidate or None, ' '.join(lines[1:]).strip()
    return None, ' '.join(lines).strip()
PROFILE_TD_SIGNATURE_REGEX = re.compile(r'authors/|registered:|ats points|mediumtxt', re.IGNORECASE)


def _clean_ws(s):
    return re.sub(r'\s+', ' ', s).strip()


def _looks_like_profile_td(td):
    """Identifies a post's author/profile column vs. its content column.

    ATS's HTML skin changed several times across ~2003-2018 archive captures;
    none of these markers are universal, so this checks several signatures
    accumulated by direct inspection of the actual captured HTML (class
    names, and the 'mediumtxt' font wrapper family-A-era skins use to bold
    the username before a plain-text member blurb).
    """
    cls = ' '.join(td.get('class') or [])
    if re.search(r'postprofile|membr|miniprofile', cls, re.IGNORECASE):
        return True
    return bool(PROFILE_TD_SIGNATURE_REGEX.search(str(td)))


def _is_profile_row(tr):
    tds = tr.find_all('td', recursive=False)
    return len(tds) >= 2 and any(_looks_like_profile_td(td) for td in tds)


def _author_from_profile_td(td):
    text = td.get_text('\n')
    for line in (_clean_ws(l) for l in text.split('\n')):
        if not line:
            continue
        low = line.lower()
        if low.startswith('registered') or low.startswith('location') or low.startswith('mood') \
                or 'ats points' in low or 'member is' in low:
            break
        return line
    return None


POST_CONTAINER_MARKERS = re.compile(r'guestpost|threadpost', re.IGNORECASE)
ICON_STAR_REGEX = re.compile(r'icon-star', re.IGNORECASE)


def _is_quotebox(tag):
    """Matches ATS's quote wrapper across skins: <div class="quotebox"> in
    older/font-icon skins, <blockquote id="quotebox"> in the 2014+ skin
    seen alongside 'threadpost'/'KonaBody' class names. Structure (a div or
    blockquote flagged as a quote) matters here, not the specific tag/attr
    combination, since that varies by skin generation."""
    if tag.name not in ('div', 'blockquote'):
        return False
    return 'quotebox' in (tag.get('class') or []) or tag.get('id') == 'quotebox'


def _find_div_post_container(anchor, next_anchor):
    """For skins with no <tr> structure at all (found 2026-07-27: a 'guestpost'
    div-based skin and a 'threadpost' div-based skin, both post-~2010,
    neither using the table layout every skin up to that point used -- see
    handoff/task_ats_topic_modeling.md's sibling audit for how this was
    found and how much of the corpus it affects). Climbs the anchor's div
    ancestors looking for a known post-container marker first; falls back to
    the smallest ancestor div that doesn't also contain the NEXT post's
    anchor, so an unrecognized future skin still gets a sane per-post
    boundary instead of silently producing nothing."""
    for div in anchor.find_parents('div'):
        marker_text = (div.get('id') or '') + ' ' + ' '.join(div.get('class') or [])
        if POST_CONTAINER_MARKERS.search(marker_text):
            return div
    for div in anchor.find_parents('div'):
        if next_anchor is not None and any(
            a is next_anchor for a in div.find_all('a', attrs={'name': PID_NAME_REGEX})
        ):
            continue
        return div
    return None


def _author_from_div_container(div):
    link = div.find('a', class_=re.compile(r'membr', re.IGNORECASE))
    return _clean_ws(link.get_text()) if link else None


def _build_post_dict(content_parts, post_id, author, thread_id, page_num, title_text):
    """Shared field-extraction logic for one post, given the BeautifulSoup
    element(s) that make up its header+body. Used by both the table-row-based
    primary path and the div-based fallback path for skins with no <tr>
    structure -- everything past 'find this post's elements' is identical
    regardless of which skin produced them, since it all operates on
    flattened text/regex from here on. Returns None for degenerate/corrupted
    captures that shouldn't become a fake comment."""
    starred = (
        any(part.find('img', src=STAR_IMG_REGEX) for part in content_parts)
        or any(part.find(class_=ICON_STAR_REGEX) for part in content_parts)
    )

    # Extract quoted content BEFORE flattening to text. ATS wraps quotes in a
    # quotebox element (div or blockquote, see _is_quotebox) in every skin
    # generation checked -- a reliable structural marker that's invisible to
    # a regex run on already-flattened text, since get_text() has no way to
    # signal where a quote block started/ended by that point. Only the
    # OUTERMOST quotebox per occurrence is extracted (a quote-of-a-quote's
    # own nested quotebox belongs to what the outer quote's author was
    # themselves quoting, not to this post's own direct reply target);
    # decomposing the outer one removes its nested descendants from the tree
    # too, so the cleaned body never contains any of it.
    quoted_authors, quoted_texts = [], []
    for part in content_parts:
        for qbox in part.find_all(_is_quotebox):
            if qbox.find_parent(_is_quotebox) is not None:
                continue
            qauthor, qtext = _extract_quote_author_and_text(qbox.get_text('\n'))
            if qauthor:
                quoted_authors.append(qauthor)
            quoted_texts.append(qtext)
            qbox.decompose()

    full_text = '\n'.join(part.get_text('\n') for part in content_parts)

    ts_match = POSTED_TIMESTAMP_REGEX.search(full_text)
    raw_timestamp = _clean_ws(ts_match.group(1)) if ts_match else 'Unknown'
    if ts_match and ts_match.group(2) and not author:
        author = _clean_ws(ts_match.group(2))

    # Fallback regex pass, now colon-tolerant ("originally posted by: X", not
    # just "originally posted by X" -- the earlier version silently matched
    # nothing on the colon variant). This only fires on whatever text remains
    # after quotebox removal above, so it's a residual catch for quote markup
    # that isn't wrapped in a proper quotebox element (rare, but seen in a
    # handful of malformed/edge-case captures), not the primary path anymore.
    # REPLY_TO_REGEX's "reply to (this) post by X" also directly matches the
    # 'guestpost' skin's inline hyperlinked reply marker, no extra handling
    # needed for that skin beyond finding its post boundary correctly.
    reply_to_authors = list(quoted_authors)
    reply_to_authors += [_clean_ws(m) for m in QUOTE_AUTHOR_REGEX.findall(full_text)]
    reply_to_authors += [_clean_ws(m) for m in REPLY_TO_REGEX.findall(full_text)]

    body_text = re.sub(r'\s*\n\s*', '\n', full_text).strip()
    body_text = re.sub(r'\n{3,}', '\n\n', body_text)

    # A handful of captures have genuinely malformed/unclosed HTML that
    # confuses table-structure parsing regardless of skin, landing the
    # anchor's row on the page's own nav-bar chrome instead of the real post
    # row. That's source corruption, not a parseable template - skip rather
    # than emit nav text as a fake comment body.
    if 'BelowTopSecret.com' in body_text:
        return None

    return {
        'thread_id': thread_id,
        'thread_title': title_text,
        'page_num': page_num,
        'post_id': post_id,
        'author': author or 'Unknown',
        'raw_timestamp': raw_timestamp,
        'body': body_text,
        'starred': starred,
        'reply_to_authors': reply_to_authors,
        'quoted_texts': quoted_texts,
    }


def _find_anchor_row(anchor, max_climb=2):
    """Returns the <tr> that structurally 'owns' a pid anchor.

    Some captures nest the anchor inside a malformed/unclosed <td> that
    BeautifulSoup's lenient parsing turns into a 0-<td> <tr>; climb past a
    couple of those before accepting whatever row we land on.
    """
    climbed = 0
    for tr in anchor.find_parents('tr'):
        tds = tr.find_all('td', recursive=False)
        if len(tds) == 0:
            climbed += 1
            if climbed > max_climb:
                return tr
            continue
        return tr
    return None


def parse_html_file(file_path, thread_id=None, page_num=None):
    """
    Parses a single AboveTopSecret thread HTML file, returning extracted posts.

    Posts are located via their `<a name="pidNNNN">` anchor, which is the one
    structural marker that held up across ATS's several HTML skin generations
    (unlike fixed class names such as 'threadpost'/'membr', which only matched
    a small fraction of the actual archive captures on inspection). Each
    post's row is walked structurally (profile column vs. content column,
    merging forward sibling rows for skins that split a post's header/body/
    footer into separate <tr>s) rather than sliced by raw character offset,
    to avoid bleeding the next post's profile blurb into this post's body.
    """
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
        if ', page' in title_text:
            title_text = title_text.split(', page')[0].strip()

    # 2. Extract thread ID and page from filename if not provided
    if thread_id is None or page_num is None:
        basename = os.path.basename(file_path)
        m = CACHE_FILENAME_REGEX.match(basename)
        if m:
            thread_id = int(m.group(1))
            page_num = int(m.group(2)) if m.group(2).isdigit() else m.group(2)

    thread_id = thread_id or 0
    page_num = page_num or 1

    # 3. Locate all posts via their pid anchor
    anchors = soup.find_all('a', attrs={'name': PID_NAME_REGEX})
    rows = [_find_anchor_row(a) for a in anchors]

    posts_extracted = []
    for idx, anchor in enumerate(anchors):
        post_id = PID_NAME_REGEX.match(anchor.get('name', '')).group(1)
        tr = rows[idx]
        if tr is None:
            continue

        tds = tr.find_all('td', recursive=False)
        author = None
        if len(tds) >= 2 and _is_profile_row(tr):
            profile_td = next((td for td in tds if _looks_like_profile_td(td)), None)
            if profile_td is not None:
                author = _author_from_profile_td(profile_td)
        elif len(tds) <= 1:
            # Header-only row (skins that split header/body/footer into
            # separate <tr>s) - the profile column, if any, is the preceding
            # sibling row rather than a sibling <td>.
            prev = tr.find_previous_sibling('tr')
            if prev is not None and not prev.find('a', attrs={'name': PID_NAME_REGEX}) and _is_profile_row(prev):
                ptd = next((td for td in prev.find_all('td', recursive=False) if _looks_like_profile_td(td)), None)
                if ptd is not None:
                    author = _author_from_profile_td(ptd)

        # Merge forward sibling rows until the next post's row, so that
        # skins which split one post's header/content/footer across several
        # <tr>s are captured in full, without swallowing the next post's
        # profile column.
        content_parts = [tr]
        next_tr = rows[idx + 1] if idx + 1 < len(rows) else None
        sib = tr.find_next_sibling('tr')
        hops = 0
        while sib is not None and sib is not next_tr and hops < 10:
            if sib.find('a', attrs={'name': PID_NAME_REGEX}) or _is_profile_row(sib):
                break
            content_parts.append(sib)
            sib = sib.find_next_sibling('tr')
            hops += 1

        post = _build_post_dict(content_parts, post_id, author, thread_id, page_num, title_text)
        if post is not None:
            posts_extracted.append(post)

    # Fallback for skins with no <tr> structure at all (found 2026-07-27: a
    # 'guestpost' div-based skin and a 'threadpost' div-based skin, both
    # concentrated post-~2010 but also seen scattered in earlier Common-
    # Crawl-sourced captures -- see handoff/task_ats_topic_modeling.md's
    # sibling audit). The primary loop above finds zero posts for these,
    # since _find_anchor_row never locates an enclosing <tr>. Only runs when
    # anchors exist but the table-based pass found nothing, so it never
    # touches (or risks regressing) the already-working table-based skins.
    if anchors and not posts_extracted:
        for idx, anchor in enumerate(anchors):
            post_id = PID_NAME_REGEX.match(anchor.get('name', '')).group(1)
            next_anchor = anchors[idx + 1] if idx + 1 < len(anchors) else None
            div = _find_div_post_container(anchor, next_anchor)
            if div is None:
                continue
            author = _author_from_div_container(div)
            post = _build_post_dict([div], post_id, author, thread_id, page_num, title_text)
            if post is not None:
                posts_extracted.append(post)

    return posts_extracted


def resolve_reply_edges(posts):
    """
    Turns each post's `reply_to_authors` (quoted usernames, parsed from
    "Originally posted by X" / "reply to post by X" text) into a best-effort
    `reply_to_post_ids` list of actual post IDs.

    This is necessarily a heuristic, not an exact reference: ATS's quote
    markup only names the quoted *author*, not their specific post. Within
    each thread (across all its pages), posts are ordered by post_id (which
    increases monotonically with time on ATS), and each quoted name is
    resolved to the nearest *preceding* post by that author in the same
    thread. If an author posted more than once earlier in the thread, this
    picks the most recent candidate, which is usually but not always the
    one actually being quoted.
    """
    by_thread = {}
    for post in posts:
        by_thread.setdefault(post['thread_id'], []).append(post)

    for thread_posts in by_thread.values():
        thread_posts.sort(key=lambda p: int(p['post_id']) if str(p['post_id']).isdigit() else 0)
        last_post_id_by_author = {}
        for post in thread_posts:
            reply_ids = []
            for name in post.get('reply_to_authors', []):
                key = name.strip().lower()
                match_id = last_post_id_by_author.get(key)
                if match_id is not None:
                    reply_ids.append(match_id)
            post['reply_to_post_ids'] = reply_ids
            author_key = (post.get('author') or '').strip().lower()
            if author_key and author_key != 'unknown':
                last_post_id_by_author[author_key] = post['post_id']

    return posts


def parse_and_export_directory(cache_dir=DEFAULT_CACHE_DIR, output_path=DEFAULT_OUTPUT_FILE):
    """
    Parses all cached HTML files and exports them to a unified JSONLines file.
    Utilizes multi-processing to speed up CPU-bound BeautifulSoup parsing by 4x to 8x!
    Implements a resilient, append-only checkpoint ledger to allow instant resume.
    """
    if not os.path.exists(cache_dir):
        print(f"Cache directory {cache_dir} does not exist.")
        return

    all_html_files = [f for f in os.listdir(cache_dir) if f.endswith('.html')]
    if not all_html_files:
        print(f"No cached HTML files found in {cache_dir}.")
        return

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    parsed_tracker_path = os.path.join(os.path.dirname(output_path), "ats_parsed_files.txt")
    
    # If the main output file does not exist, reset the parsed ledger
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

    # Only process files that have not been parsed yet
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

    # Determine optimal worker count
    import multiprocessing
    cores = min(multiprocessing.cpu_count(), 8)
    print(f"Spawning {cores} parallel parsing processes...")

    from concurrent.futures import ProcessPoolExecutor, as_completed
    
    # Process files in chunks of 5,000 to periodically flush them to disk and ledger
    chunk_size = 5000
    parsed_files_count = 0
    empty_files = 0
    start_time = time.time()
    last_print_time = start_time

    # We open the files in append mode if we are resuming, otherwise write mode
    mode = 'a' if len(parsed_files) > 0 else 'w'
    
    with ProcessPoolExecutor(max_workers=cores) as executor:
        for chunk_idx in range(0, total_to_parse, chunk_size):
            chunk_filenames = html_files_to_parse[chunk_idx:chunk_idx + chunk_size]
            chunk_paths = [os.path.join(cache_dir, f) for f in chunk_filenames]
            
            # Map future to filename so we can track ledger writes
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
                
                # Print real-time progress dashboard
                now = time.time()
                if now - last_print_time >= 1.0 or parsed_files_count == total_to_parse:
                    last_print_time = now
                    elapsed = now - start_time
                    speed = parsed_files_count / elapsed if elapsed > 0 else 0
                    percent = (parsed_files_count / total_to_parse) * 100
                    eta_sec = (total_to_parse - parsed_files_count) / speed if speed > 0 else 0
                    
                    if eta_sec > 60:
                        eta_str = f"{int(eta_sec // 60)}m {int(eta_sec % 60)}s"
                    else:
                        eta_str = f"{int(eta_sec)}s"
                        
                    print(f"  Progress: {parsed_files_count:,}/{total_to_parse:,} parsed ({percent:.1f}%) | "
                          f"Speed: {speed:.1f} files/sec | "
                          f"ETA: {eta_str} | "
                          f"New Posts: {len(chunk_posts):,}", end="\r", flush=True)

            # Flush this chunk to disk and update ledger!
            if chunk_posts:
                resolve_reply_edges(chunk_posts)
                with open(output_path, mode, encoding='utf-8') as outfile:
                    for post in chunk_posts:
                        outfile.write(json.dumps(post) + '\n')
            
            # Write to ledger append-only
            with open(parsed_tracker_path, "a", encoding="utf-8") as ledger_f:
                for fn in chunk_processed_files:
                    ledger_f.write(fn + "\n")
                    
            # Subsequent chunks always append
            mode = 'a'

    duration = time.time() - start_time
    print(f"\n\nParsing completed in {duration:.1f} seconds.")
    print(f"Chunked files parsed: {total_to_parse:,} ({empty_files:,} empty).")
    print(f"All parsed entries have been written to {output_path} & checkpoint ledger updated.")



def convert_jsonl_to_parquet(input_path, output_path):
    """
    Converts the JSONLines comments export to a compressed Parquet file.

    Uses DuckDB rather than pandas.read_json: the comments file is several
    GB, and pandas' line-delimited JSON reader loads and parses the whole
    thing in Python before it can write anything, which is both slow and a
    real OOM risk on this 8GB dev machine. DuckDB streams the read/write
    instead. reply_to_authors / reply_to_post_ids stay as native Parquet
    LIST columns (this project's other analysis code already reads Parquet
    via DuckDB, which handles LIST columns natively).
    """
    import duckdb

    if not os.path.exists(input_path):
        print(f"Error: {input_path} does not exist. Run 'parse' first.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    print(f"Converting {input_path} -> {output_path} via DuckDB...")
    con = duckdb.connect()
    # A small number of source lines have malformed unicode escapes (from
    # old forum HTML with broken/legacy encoding artifacts) that DuckDB's
    # stricter JSON parser rejects outright, unlike Python's `json`. Skip
    # those rather than fail the whole conversion, and report how many.
    con.execute(f"""
        COPY (SELECT * FROM read_json_auto('{input_path}', format='newline_delimited', ignore_errors=true))
        TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    row_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{output_path}')").fetchone()[0]

    with open(input_path, 'rb') as f:
        input_line_count = sum(1 for _ in f)
    skipped = input_line_count - row_count
    if skipped:
        print(f"Skipped {skipped:,} malformed line(s) out of {input_line_count:,} during conversion.")

    in_size = os.path.getsize(input_path)
    out_size = os.path.getsize(output_path)
    print(f"Wrote {row_count:,} rows to {output_path}")
    print(f"{in_size/1e6:.1f} MB -> {out_size/1e6:.1f} MB ({out_size/in_size:.1%} of original)")


def compress_cache(cache_dir=DEFAULT_CACHE_DIR, delete_raw=False):
    """
    Compresses the entire raw HTML cache directory into a highly-compressed .tar.gz archive.
    Once successfully written and verified, optionally deletes the raw HTML directory.
    """
    import tarfile
    import shutil
    
    if not os.path.exists(cache_dir):
        print(f"Error: Cache directory {cache_dir} does not exist.", file=sys.stderr)
        return
        
    archive_path = cache_dir + ".tar.gz"
    print(f"Compressing cache directory {cache_dir} -> {archive_path}...")
    
    html_files = [f for f in os.listdir(cache_dir) if f.endswith('.html')]
    if not html_files:
        print(f"No HTML files found in {cache_dir} to compress.")
        return
        
    print(f"Packaging and compressing {len(html_files):,} HTML files using Gzip...")
    start_time = time.time()
    
    try:
        # Create tar.gz using buffered stream
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(cache_dir, arcname=os.path.basename(cache_dir))
            
        duration = time.time() - start_time
        orig_size_gb = sum(os.path.getsize(os.path.join(cache_dir, f)) for f in html_files) / (1024 * 1024 * 1024)
        comp_size_gb = os.path.getsize(archive_path) / (1024 * 1024 * 1024)
        
        print(f"\nSuccess! Archive created in {duration:.1f} seconds.")
        print(f"Original Size: {orig_size_gb:.3f} GB")
        print(f"Compressed Size: {comp_size_gb:.3f} GB ({comp_size_gb/orig_size_gb:.1%} of original!)")
        
        if delete_raw:
            print(f"\nDeleting uncompressed raw HTML folder {cache_dir} to free up disk space...")
            shutil.rmtree(cache_dir)
            print("Successfully removed raw directory! Disk space reclaimed.")
        else:
            print(f"\nNote: Raw HTML folder remains intact. To delete it and reclaim space, run with --delete-raw flag.")
            
    except Exception as e:
        print(f"Error during compression: {e}", file=sys.stderr)
        if os.path.exists(archive_path):
            os.remove(archive_path)



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
    dl_parser.add_argument("--threads", type=int, default=1, help="Number of concurrent worker threads")
    dl_parser.add_argument("--shard-count", type=int, default=1, help="Total number of parallel scraper instances (shards)")
    dl_parser.add_argument("--shard-id", type=int, default=0, help="Zero-indexed ID of this shard instance (0 to shard-count - 1)")
    
    # Subcommand: parse
    parse_parser = subparsers.add_parser("parse", help="Parse cached HTML files into structured comments")
    parse_parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR, help="Directory containing cached HTML files")
    parse_parser.add_argument("--local-file", default=None, help="Parse a single specified HTML file instead of directory")
    parse_parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE, help="Path to save structured JSONLines comments")
    
    # Subcommand: to-parquet
    parquet_parser = subparsers.add_parser("to-parquet", help="Convert the JSONLines comments export to Parquet")
    parquet_parser.add_argument("--input", default=DEFAULT_OUTPUT_FILE, help="Path to the JSONLines comments file")
    parquet_parser.add_argument("--output", default=None, help="Path to write the Parquet file (default: input with .parquet extension)")

    # Subcommand: compress
    compress_parser = subparsers.add_parser("compress", help="Compress raw HTML cache into a tar.gz archive to save disk space")
    compress_parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR, help="Directory containing cached HTML files")
    compress_parser.add_argument("--delete-raw", action="store_true", help="Delete raw uncompressed HTML directory upon successful compression")


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
            
        # Apply sharding/partitioning if specified
        if args.shard_count > 1:
            if args.shard_id < 0 or args.shard_id >= args.shard_count:
                print(f"Error: --shard-id must be between 0 and {args.shard_count - 1}", file=sys.stderr)
                sys.exit(1)
            metadata_list = [
                item for idx, item in enumerate(metadata_list)
                if idx % args.shard_count == args.shard_id
            ]
            print(f"[SHARDING] Running as Shard {args.shard_id} of {args.shard_count}. Retained {len(metadata_list):,} targets.")
            
        download_captures(metadata_list, cache_dir=args.cache_dir, delay=args.delay, limit=args.limit, threads=args.threads)
        
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

    elif args.command == "to-parquet":
        output_path = args.output or (os.path.splitext(args.input)[0] + '.parquet')
        convert_jsonl_to_parquet(args.input, output_path)

    elif args.command == "compress":
        compress_cache(cache_dir=args.cache_dir, delete_raw=args.delete_raw)


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
