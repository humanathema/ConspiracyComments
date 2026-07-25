#!/usr/bin/env python
import os
import sys
import json
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor

def main():
    indexes = [
        'CC-MAIN-2008-2009',
        'CC-MAIN-2009-2010',
        'CC-MAIN-2012',
        'CC-MAIN-2013-20',
        'CC-MAIN-2013-48'
    ]

    target_path = "data/processed/ats_metadata_middle_complete.json"
    output_path = "data/processed/ats_cc_index_complete.json"

    if not os.path.exists(target_path):
        print(f"Error: Targets file '{target_path}' not found.")
        sys.exit(1)

    print("Loading target metadata...")
    with open(target_path) as f:
        targets = json.load(f)

    target_lookup = {(t['thread_id'], t['page_num']): t for t in targets}
    print(f"Loaded {len(targets)} target middle-era pages to match against.")

    re_thread_id = re.compile(r'thread(?:/|)(\d+)')
    re_page_num = re.compile(r'/pg(\d+)')

    deduped_matches = {}

    for index_id in indexes:
        print(f"\nStarting sequential scan of {index_id}...")
        index_matches_count = 0
        
        # Partitioning by thread1 to thread9 to bypass index.commoncrawl.org ASCII space limits
        for digit in range(1, 10):
            for domain in ['www.abovetopsecret.com', 'abovetopsecret.com']:
                prefix = f'{domain}/forum/thread{digit}'
                url = f'https://index.commoncrawl.org/{index_id}-index'
                params = {
                    'url': prefix,
                    'matchType': 'prefix',
                    'output': 'json'
                }
                
                # Retry loop for rate-limiting protection
                for attempt in range(1, 4):
                    try:
                        # Polite delay to prevent connection resets
                        time.sleep(1.0)
                        
                        r = requests.get(url, params=params, stream=True, timeout=30)
                        if r.status_code == 200:
                            for line in r.iter_lines():
                                if line:
                                    try:
                                        record = json.loads(line.decode('utf-8'))
                                        orig_url = record.get('url', '')
                                        m_tid = re_thread_id.search(orig_url)
                                        m_pg = re_page_num.search(orig_url)
                                        if m_tid and m_pg:
                                            tid = int(m_tid.group(1))
                                            pg = int(m_pg.group(1))
                                            if (tid, pg) in target_lookup:
                                                key = (tid, pg)
                                                match_entry = {
                                                    'thread_id': tid,
                                                    'page_num': pg,
                                                    'timestamp': record.get('timestamp'),
                                                    'filename': record.get('filename'),
                                                    'offset': int(record.get('offset')),
                                                    'length': int(record.get('length')),
                                                    'digest': record.get('digest'),
                                                    'cc_index': index_id,
                                                    'cc_url': orig_url
                                                }
                                                if key not in deduped_matches:
                                                    deduped_matches[key] = match_entry
                                                    index_matches_count += 1
                                                else:
                                                    # Keep the earlier capture if duplicates exist
                                                    if record.get('timestamp') < deduped_matches[key]['timestamp']:
                                                        deduped_matches[key] = match_entry
                                    except Exception:
                                        pass
                            break # Succeeded this prefix
                        elif r.status_code == 404:
                            break # Safe to skip: no captures exist for this prefix
                        else:
                            print(f"  [Attempt {attempt}/3] Received status {r.status_code} for prefix {prefix}. Backing off...")
                            time.sleep(3)
                    except Exception as e:
                        print(f"  [Attempt {attempt}/3] Connection failed for prefix {prefix}: {e}. Backing off...")
                        time.sleep(4)
                        
        print(f"Completed {index_id}: Found {index_matches_count} new target page matches.")

    print(f"\nTotal unique target pages found across all 5 Common Crawl indexes: {len(deduped_matches)}")
    pct = (len(deduped_matches) / len(targets)) * 100
    print(f"Actual coverage percentage: {pct:.2f}% of our middle-era gap!")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f_out:
        json.dump(list(deduped_matches.values()), f_out, indent=2)
    print(f"Successfully saved all matched indexes to '{output_path}'!")

if __name__ == "__main__":
    main()
