"""
Patches the star-icon-count ceiling found in `recount_ats_stars.py`'s
output: ATS's UI caps the number of `staron.png` icons actually rendered
at 24, and shows a `+N more` label for any stars beyond that (confirmed
directly -- thread 398033 pg1 pid5079699 renders exactly 24 icons followed
by `<span class='vsmalltxt' ...><b>+36 more</b></span>`, i.e. 60 real
stars, not 24). `recount_ats_stars.py` only counted icons, so every post
that hit the 24 cap is undercounted.

Only files containing at least one post at exactly 24 (the confirmed cap)
can possibly have a `+N more` label, so this only re-opens that narrow
subset (~2,010 files, not the full ~89K `recount_ats_stars.py` touched) --
same one-more-sequential-pass-over-the-tar tradeoff as before, but with a
much smaller file target so the parse-heavy portion is proportionally
cheap.

Usage:
    python3 src/patch_ats_star_overflow.py
"""
import os
import re
import sys
import tarfile
import time

import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(__file__))
from ingest_ats_archive import PID_NAME_REGEX, STAR_IMG_REGEX, _find_anchor_row, _is_profile_row

ARCHIVE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw', 'ats_raw_html.tar.gz')
STAR_COUNTS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'ats_star_counts.csv')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'ats_star_counts.csv')

OVERFLOW_REGEX = re.compile(r'\+\s*(\d+)\s*more', re.IGNORECASE)
CAP = 24


def load_capped_targets(path):
    df = pd.read_csv(path)
    capped = df[df['star_count'] == CAP]
    targets_by_file = {}
    for fname, post_id in zip(capped['source_file'], capped['post_id']):
        targets_by_file.setdefault(fname, set()).add(str(post_id))
    return targets_by_file


def get_overflow_counts(html_bytes, wanted_post_ids):
    soup = BeautifulSoup(html_bytes, 'html.parser')
    anchors = soup.find_all('a', attrs={'name': PID_NAME_REGEX})
    rows = [_find_anchor_row(a) for a in anchors]

    overflow = {}
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

        combined_html = ''.join(str(part) for part in content_parts)
        m = OVERFLOW_REGEX.search(combined_html)
        if m:
            overflow[post_id] = int(m.group(1))

    return overflow


def main():
    print("Loading posts capped at 24 stars...")
    targets_by_file = load_capped_targets(STAR_COUNTS_PATH)
    total_posts = sum(len(v) for v in targets_by_file.values())
    print(f"  {len(targets_by_file)} distinct files to re-check, covering {total_posts} capped posts")

    overflow_results = {}  # post_id -> extra stars beyond the 24 cap
    files_matched = 0
    files_seen = 0
    start = time.time()

    print(f"Streaming {ARCHIVE_PATH} (single sequential pass)...")
    with tarfile.open(ARCHIVE_PATH, 'r|gz') as tar:
        for member in tar:
            if not member.isfile():
                continue
            files_seen += 1
            basename = os.path.basename(member.name)
            wanted = targets_by_file.get(basename)
            if not wanted:
                continue

            files_matched += 1
            f = tar.extractfile(member)
            if f is None:
                continue
            html_bytes = f.read()
            overflow_results.update(get_overflow_counts(html_bytes, wanted))

            if files_matched % 200 == 0:
                elapsed = time.time() - start
                print(f"  matched {files_matched}/{len(targets_by_file)} files, "
                      f"{len(overflow_results)} overflow labels found, {elapsed:.0f}s elapsed")

    elapsed = time.time() - start
    print(f"Done: {files_seen} files scanned, {files_matched} matched target files, "
          f"{len(overflow_results)} posts had a '+N more' label in {elapsed:.0f}s")
    print(f"  {total_posts - len(overflow_results)} capped posts had no overflow label "
          f"(their true count is exactly 24, not undercounted)")

    df = pd.read_csv(STAR_COUNTS_PATH)
    df['post_id_str'] = df['post_id'].astype(str)
    extra = df['post_id_str'].map(overflow_results)
    patched = (df['star_count'] == CAP) & extra.notna()
    df.loc[patched, 'star_count'] = CAP + extra[patched]
    df = df.drop(columns=['post_id_str'])

    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Patched {patched.sum()} rows, wrote {len(df)} total rows to {OUTPUT_PATH}")


if __name__ == '__main__':
    main()
