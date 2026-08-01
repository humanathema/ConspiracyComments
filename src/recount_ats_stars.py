"""
Recounts AboveTopSecret star markers as an integer per post instead of the
boolean `starred` flag `ingest_ats_archive.py` currently produces.

`starred` was computed via `any(part.find('img', src=STAR_IMG_REGEX) ...)`,
which stops at the first match -- a post with multiple `staron.png` images
(confirmed to occur in the raw archive, e.g. thread 391745 pg5 pid4984910
has two) collapses to the same `starred=1` as a post with exactly one.
Re-parsing the full ~4.5GB tar.gz to fix this is wasteful: only files that
already contain at least one `starred==1` post (16.8% of the archive, verified
against `ats_comments_final.parquet`) can possibly contain a multi-star post,
so this script narrows the target set from the existing parquet first, then
does a single sequential stream over the tar.gz (gzip has no random access,
so a full pass is unavoidable, but skipping the BeautifulSoup parse on the
other 83% of files is not).

A (thread_id, page_num) key isn't always a single file -- ~8.75% of keys have
more than one archived capture (different Wayback snapshot timestamps of the
same page). Stars only accrue over a thread's life, they don't get removed,
so the latest-timestamped capture of a page is the most complete one -- rather
than opening every capture of an ambiguous key, `ats_parsed_files.txt` (the
list of files the archive actually contains) is used to pick the single
latest-timestamped filename per key up front, and only that exact file is
matched during the tar stream.

Usage:
    python3 src/recount_ats_stars.py
"""
import os
import sys
import re
import tarfile
import time

import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(__file__))
from ingest_ats_archive import (
    CACHE_FILENAME_REGEX,
    PID_NAME_REGEX,
    STAR_IMG_REGEX,
    _find_anchor_row,
    _is_profile_row,
)

ARCHIVE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw', 'ats_raw_html.tar.gz')
COMMENTS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'ats_comments_final.parquet')
PARSED_FILES_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'ats_parsed_files.txt')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'ats_star_counts.csv')

TIMESTAMP_SUFFIX_REGEX = re.compile(r'_(\d{14})\.html$', re.IGNORECASE)


def build_target_keys(comments_path):
    """(thread_id, page_num) keys for files that can possibly contain a
    multi-star post, plus the set of post_ids we expect to find inside each."""
    df = pd.read_parquet(comments_path, columns=['thread_id', 'page_num', 'post_id', 'starred'])
    starred = df[(df['starred'] == 1) & df['page_num'].notna()].copy()
    starred['page_num'] = starred['page_num'].astype(int)

    target_post_ids_by_key = {}
    for thread_id, page_num, post_id in zip(starred['thread_id'], starred['page_num'], starred['post_id']):
        key = (int(thread_id), int(page_num))
        target_post_ids_by_key.setdefault(key, set()).add(str(post_id))

    return target_post_ids_by_key


def build_latest_filenames(parsed_files_path, wanted_keys):
    """For each (thread_id, page_num) key we actually need, picks the
    filename with the latest timestamp suffix among all archived captures
    of that page. Filenames without a timestamp suffix sort last (empty
    string), so a timestamped capture is always preferred when one exists."""
    best = {}  # key -> (timestamp_str, filename)
    with open(parsed_files_path) as f:
        for line in f:
            fname = line.strip()
            if not fname:
                continue
            m = CACHE_FILENAME_REGEX.match(fname)
            if not m or not m.group(2).isdigit():
                continue
            key = (int(m.group(1)), int(m.group(2)))
            if key not in wanted_keys:
                continue
            ts_m = TIMESTAMP_SUFFIX_REGEX.search(fname)
            ts = ts_m.group(1) if ts_m else ''
            current = best.get(key)
            if current is None or ts > current[0]:
                best[key] = (ts, fname)

    return {key: fname for key, (ts, fname) in best.items()}


def count_stars_in_file(html_bytes, wanted_post_ids):
    """Same post-boundary logic as ingest_ats_archive.parse_html_file
    (merge-forward sibling rows), but counts staron.png occurrences per
    post instead of a boolean any()."""
    soup = BeautifulSoup(html_bytes, 'html.parser')
    anchors = soup.find_all('a', attrs={'name': PID_NAME_REGEX})
    rows = [_find_anchor_row(a) for a in anchors]

    counts = {}
    for idx, anchor in enumerate(anchors):
        post_id = PID_NAME_REGEX.match(anchor.get('name', '')).group(1)
        if post_id not in wanted_post_ids:
            continue
        tr = rows[idx]
        if tr is None:
            continue

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

        star_count = sum(len(part.find_all('img', src=STAR_IMG_REGEX)) for part in content_parts)
        counts[post_id] = star_count

    return counts


def main():
    print("Loading target (thread_id, page_num) keys from existing starred posts...")
    target_post_ids_by_key = build_target_keys(COMMENTS_PATH)
    print(f"  {len(target_post_ids_by_key)} distinct files to open "
          f"(covering {sum(len(v) for v in target_post_ids_by_key.values())} starred posts)")

    print("Picking the latest-timestamped capture per key from ats_parsed_files.txt...")
    target_filename_by_key = build_latest_filenames(PARSED_FILES_PATH, set(target_post_ids_by_key.keys()))
    filename_to_key = {fname: key for key, fname in target_filename_by_key.items()}
    unresolved_keys = set(target_post_ids_by_key.keys()) - set(target_filename_by_key.keys())
    if unresolved_keys:
        print(f"  WARNING: {len(unresolved_keys)} keys from the parquet have no matching entry in "
              f"ats_parsed_files.txt at all (can't be recounted, will show star_count=None)")
    print(f"  {len(target_filename_by_key)} exact files targeted")

    results = {}  # post_id -> star_count
    files_matched = 0
    files_seen = 0
    start = time.time()

    print(f"Streaming {ARCHIVE_PATH} (single sequential pass, gzip has no random access)...")
    with tarfile.open(ARCHIVE_PATH, 'r|gz') as tar:
        for member in tar:
            if not member.isfile():
                continue
            files_seen += 1
            basename = os.path.basename(member.name)
            key = filename_to_key.get(basename)
            if key is None:
                continue

            files_matched += 1
            f = tar.extractfile(member)
            if f is None:
                continue
            html_bytes = f.read()
            counts = count_stars_in_file(html_bytes, target_post_ids_by_key[key])
            results.update(counts)

            if files_matched % 5000 == 0:
                elapsed = time.time() - start
                print(f"  matched {files_matched} files, {files_seen} scanned, "
                      f"{len(results)} posts recounted, {elapsed:.0f}s elapsed")

    elapsed = time.time() - start
    print(f"Done: {files_seen} files scanned, {files_matched} matched target files, "
          f"{len(results)} posts recounted in {elapsed:.0f}s")

    expected = set()
    for wanted in target_post_ids_by_key.values():
        expected |= wanted
    missing = expected - set(results.keys())
    if missing:
        print(f"WARNING: {len(missing)} expected starred post_ids were never found in their target file "
              f"(post_id anchor missing/malformed capture -- worth spot-checking a few)")

    out_rows = []
    for key, wanted in target_post_ids_by_key.items():
        thread_id, page_num = key
        for post_id in wanted:
            out_rows.append({
                'thread_id': thread_id,
                'page_num': page_num,
                'post_id': post_id,
                'star_count': results.get(post_id),
                'source_file': target_filename_by_key.get(key),
            })

    out_df = pd.DataFrame(out_rows)
    out_df.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(out_df)} rows to {OUTPUT_PATH}")


if __name__ == '__main__':
    main()
