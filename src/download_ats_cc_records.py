#!/usr/bin/env python
import os
import sys
import json
import gzip
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

class AdaptiveRateController:
    def __init__(self, initial_concurrency=3, min_concurrency=1, max_concurrency=12,
                 initial_delay=0.15, min_delay=0.0, max_delay=5.0):
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
                self.delay = min(self.max_delay, self.delay * 1.5 + 0.05)

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
                    self.delay = min(self.max_delay, self.delay * 2.0 + 0.1)
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

def download_page(record, controller, output_dir):
    thread_id = record["thread_id"]
    page_num = record["page_num"]
    filename = record["filename"]
    offset = record["offset"]
    length = record["length"]

    if filename.startswith("s3://"):
        filename = filename.replace("s3://aws-publicdatasets/", "")

    url = f"https://data.commoncrawl.org/{filename}"
    headers = {"Range": f"bytes={offset}-{offset + length - 1}"}

    controller.acquire()
    try:
        max_attempts = 3
        r = None
        for attempt in range(max_attempts):
            try:
                r = requests.get(url, headers=headers, timeout=20)
                if r.status_code == 206:
                    controller.report(True)
                    break
                elif r.status_code == 403:
                    controller.report(False)
                    if attempt < max_attempts - 1:
                        time.sleep(2 * (attempt + 1))
                        continue
                    return False, f"HTTP 403 after {max_attempts} attempts"
                else:
                    controller.report(False)
                    return False, f"HTTP {r.status_code} response for range"
            except Exception as e_net:
                controller.report(False)
                if attempt < max_attempts - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                return False, f"Network/IO error after {max_attempts} attempts: {e_net}"
    finally:
        controller.release()

    if r is None or r.status_code != 206:
        return False, "Failed to get valid response after retries"

    outer_data = r.content
    if len(outer_data) != length:
        return False, f"Expected {length} bytes, got {len(outer_data)}"

    try:
        raw_arc_record = gzip.decompress(outer_data)
    except Exception as e:
        return False, f"Outer decompression failed: {e}"

    parts = raw_arc_record.split(b"\n", 1)
    if len(parts) < 2:
        return False, "Malformed ARC record (no metadata line)"

    payload = parts[1]
    header_end = payload.find(b"\r\n\r\n")
    if header_end == -1:
        header_end = payload.find(b"\n\n")
        delim_len = 2
    else:
        delim_len = 4

    if header_end == -1:
        return False, "Could not find HTTP header boundary in payload"

    raw_headers = payload[:header_end]
    body_bytes = payload[header_end + delim_len:]

    headers_str = raw_headers.decode("utf-8", errors="replace").lower()
    is_gzip_encoded = "content-encoding: gzip" in headers_str or "content-encoding:gzip" in headers_str

    if is_gzip_encoded:
        try:
            html_content = gzip.decompress(body_bytes)
        except Exception as e_inner:
            html_content = body_bytes
    else:
        html_content = body_bytes

    out_path = os.path.join(output_dir, f"thread{thread_id}_pg{page_num}.html")
    with open(out_path, "wb") as f_html:
        f_html.write(html_content)

    return True, None

def main():
    metadata_path = "data/processed/ats_cc_index_complete.json"
    output_dir = "data/raw/ats_raw_html"
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(metadata_path):
        print(f"Error: Common Crawl matches file '{metadata_path}' not found.")
        print("Please run the index scanner first to generate this file.")
        sys.exit(1)

    with open(metadata_path) as f:
        records = json.load(f)

    print(f"Loaded {len(records)} verified thread page matches from Common Crawl.")

    # Determine files that are already downloaded to allow incremental resumption
    already_downloaded = set()
    for fname in os.listdir(output_dir):
        if fname.endswith(".html"):
            m = re.match(r"thread(\d+)_pg(\d+)\.html", fname)
            if m:
                already_downloaded.add((int(m.group(1)), int(m.group(2))))

    to_download = [r for r in records if (r["thread_id"], r["page_num"]) not in already_downloaded]
    print(f"Skipping {len(already_downloaded)} already downloaded pages.")
    print(f"Remaining pages to download: {len(to_download)}")

    if not to_download:
        print("All matched pages are already downloaded!")
        sys.exit(0)

    # Use a ThreadPoolExecutor for high-performance concurrent S3 Range downloads
    # Since S3 / CloudFront is a robust CDN, we can safely use 10-15 threads with zero rate limits!
    workers = 12  # ceiling — semaphore controls actual concurrent requests, starts at 3
    print(f"Starting downloader using {workers} concurrent threads...")

    success_count = 0
    failure_count = 0

    controller = AdaptiveRateController(initial_concurrency=3, max_concurrency=12,
                                     initial_delay=0.15)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(download_page, r, controller, output_dir): r for r in to_download}
        
        for count, future in enumerate(as_completed(futures), 1):
            r = futures[future]
            success, err_msg = future.result()
            
            if success:
                success_count += 1
            else:
                failure_count += 1
                print(f"Failed thread {r['thread_id']} pg {r['page_num']}: {err_msg}")
            
            if count % 100 == 0 or count == len(to_download):
                conc, delay = controller.status()
                print(f"Progress: {count}/{len(to_download)} ({success_count} success, {failure_count} failures) — concurrency={conc}, delay={delay}s")

    print(f"\nDownloader execution completed!")
    print(f"Successfully downloaded: {success_count} pages")
    print(f"Failures: {failure_count}")

if __name__ == "__main__":
    main()


