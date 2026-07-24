#!/usr/bin/env python
"""compile_legacy_catalog.py

Queries the Wayback Machine CDX API for legacy Ikonboard thread captures
(/cgi-bin/ikonboard/topic.cgi) from the pre-2003 era of AboveTopSecret.
Deduplicates them by (forum_id, topic_id, start_offset) to create a clean legacy catalog.
"""

import os
import sys
import json
import re
from urllib.parse import urlparse, parse_qs
import requests

OUTPUT_PATH = "data/processed/ats_legacy_index_complete.json"


def compile_legacy_catalog():
    print("=================================================================")
    print("Compiling Pre-2003 Legacy Ikonboard AboveTopSecret Catalog...")
    print("=================================================================\n")

    # We use matchType=prefix which is highly optimized on the Wayback backend
    # This queries all captures starting with the topic.cgi script
    api_url = (
        "https://web.archive.org/cdx/search/cdx"
        "?url=abovetopsecret.com/cgi-bin/ikonboard/topic.cgi"
        "&matchType=prefix"
        "&output=json"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    print(f"Querying Wayback CDX API for legacy forum paths...")
    try:
        # Increase timeout to 120s as prefix index scanning can take some time
        response = requests.get(api_url, headers=headers, timeout=120)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error querying CDX: {e}")
        sys.exit(1)

    if not data or len(data) <= 1:
        print("No legacy captures found!")
        sys.exit(0)

    # data[0] is headers: ['urlkey', 'timestamp', 'original', 'mimetype', 'statuscode', 'digest', 'length']
    records = data[1:]
    print(f"Retrieved {len(records):,} total raw captures from Wayback.")

    legacy_catalog = {}  # (forum_id, topic_id, start) -> record dict
    malformed_count = 0

    for row in records:
        timestamp = row[1]
        original_url = row[2]
        mimetype = row[3]
        statuscode = row[4]
        digest = row[5]

        # Filter for HTML text pages only
        if mimetype and "text/html" not in mimetype.lower():
            continue
        if statuscode != "200":
            continue

        # Parse query parameters from URL
        parsed_url = urlparse(original_url)
        query_params = parse_qs(parsed_url.query)

        # Handle ampersand entity escaping in Wayback URLs (e.g. &amp;topic=18)
        if not query_params and "amp;" in parsed_url.query:
            clean_query = parsed_url.query.replace("amp;", "")
            query_params = parse_qs(clean_query)

        forum_list = query_params.get("forum") or query_params.get("f")
        topic_list = query_params.get("topic") or query_params.get("t")
        start_list = query_params.get("start") or query_params.get("s")

        if not forum_list or not topic_list:
            malformed_count += 1
            continue

        try:
            forum_id = int(forum_list[0])
            topic_id = int(topic_list[0])
            # If 'start' is not present, it is page 1 (startoffset = 0)
            start_offset = int(start_list[0]) if start_list else 0
        except ValueError:
            malformed_count += 1
            continue

        key = f"{forum_id}_{topic_id}_start{start_offset}"

        # Deduplication: Keep the earliest or most stable capture of each page
        if key not in legacy_catalog:
            legacy_catalog[key] = {
                "forum_id": forum_id,
                "topic_id": topic_id,
                "start_offset": start_offset,
                "timestamp": timestamp,
                "url": original_url,
                "digest": digest,
            }
        else:
            # Keep the oldest snapshot to get original text in case of edits/archiving glitches
            if timestamp < legacy_catalog[key]["timestamp"]:
                legacy_catalog[key]["timestamp"] = timestamp
                legacy_catalog[key]["url"] = original_url
                legacy_catalog[key]["digest"] = digest

    flat_catalog = list(legacy_catalog.values())

    print("\n=================================================================")
    print("Legacy Catalog Compilation Complete!")
    print(f"Skipped {malformed_count:,} malformed legacy query parameters.")
    print(f"Deduplicated Unique Legacy Page Targets: {len(flat_catalog):,}")
    print(f"Saving compiled legacy index to: {OUTPUT_PATH}")
    print("=================================================================")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(flat_catalog, f, indent=2)

    return flat_catalog


if __name__ == "__main__":
    compile_legacy_catalog()
