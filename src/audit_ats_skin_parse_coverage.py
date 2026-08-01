"""audit_ats_skin_parse_coverage.py

Checks how much of the cached ATS raw-HTML archive (data/raw/ats_raw_html.tar.gz,
453,330 files) the current parser (src/ingest_ats_archive.py) actually converts
into posts, broken down by year. Raised 2026-07-27 after a single 2018-era test
file was found to parse to ZERO posts despite having real <a name="pidNNNN">
anchors present -- suspected cause: a later ATS skin generation doesn't use the
table-based <tr>/<td> layout every other checked skin does, so `_find_anchor_row`
never finds an enclosing row and every anchor in the file is silently skipped.

This does a single sequential streaming pass through the tar (gzip doesn't
support cheap random access, so this reads it once start to finish rather than
seeking per file) -- cheap regex anchor-counting on every file, full
BeautifulSoup-based parsing (the real conversion path) only on a systematic
1-in-N sample to keep runtime reasonable across 453K files.

Output: data/processed/ats_skin_coverage_audit.csv (per-sampled-file stats)
and a year-bucketed summary printed to stdout.
"""
import os
import re
import sys
import tarfile
import random

sys.path.insert(0, os.path.dirname(__file__))
from ingest_ats_archive import parse_html_file, PID_NAME_REGEX

TAR_PATH = 'data/raw/ats_raw_html.tar.gz'
OUTPUT_CSV = 'data/processed/ats_skin_coverage_audit.csv'
SAMPLE_EVERY_N = 25  # full-parse 1 in 25 files (~18K files)
RNG_SEED = 42

FILENAME_TS_REGEX = re.compile(r'_(\d{4})\d{10}\.html$')          # thread_X_pgY_TIMESTAMP.html (Wayback)
FILENAME_NO_TS_REGEX = re.compile(r'^thread\d+_pg')                # thread100021_pg1.html (Common Crawl, no timestamp)


def year_from_filename(name):
    base = os.path.basename(name)
    m = FILENAME_TS_REGEX.search(base)
    if m:
        return int(m.group(1))
    return None  # no-timestamp (CC-era) filenames handled separately


def main():
    random.seed(RNG_SEED)
    if not os.path.exists(TAR_PATH):
        print(f"Error: {TAR_PATH} not found.", file=sys.stderr)
        sys.exit(1)

    rows = []
    total_files = 0
    total_html_files = 0
    sampled = 0

    print(f"Streaming through {TAR_PATH} (single sequential pass, sampling 1-in-{SAMPLE_EVERY_N})...")
    with tarfile.open(TAR_PATH, 'r:gz') as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith('.html'):
                continue
            total_files += 1
            total_html_files += 1

            if total_html_files % SAMPLE_EVERY_N != 0:
                if total_html_files % 20000 == 0:
                    print(f"  ...scanned {total_html_files:,} files, sampled {sampled:,}", end='\r', flush=True)
                continue

            f = tar.extractfile(member)
            if f is None:
                continue
            try:
                content = f.read().decode('utf-8', errors='ignore')
            except Exception:
                continue

            n_anchors = len(re.findall(r'<a name="pid\d+"', content, re.IGNORECASE))
            year = year_from_filename(member.name)

            n_posts = 0
            if n_anchors > 0:
                try:
                    # parse_html_file expects a file path; write to a temp buffer instead
                    import io
                    from bs4 import BeautifulSoup
                    # Reuse the real parser logic via a temp file to stay faithful to production behavior
                    tmp_path = f"/tmp/_ats_audit_tmp_{os.getpid()}.html"
                    with open(tmp_path, 'w', encoding='utf-8') as tf:
                        tf.write(content)
                    posts = parse_html_file(tmp_path)
                    n_posts = len(posts)
                    os.remove(tmp_path)
                except Exception as e:
                    n_posts = -1  # parse error

            rows.append({
                'file': member.name,
                'year': year,
                'n_anchors': n_anchors,
                'n_posts_parsed': n_posts,
                'zero_despite_anchors': int(n_anchors > 0 and n_posts == 0),
            })
            sampled += 1

    print(f"\nDone. Total .html files in archive: {total_html_files:,}. Sampled: {sampled:,}.")

    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    import csv
    with open(OUTPUT_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['file', 'year', 'n_anchors', 'n_posts_parsed', 'zero_despite_anchors'])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote per-file sample results to {OUTPUT_CSV}")

    # Year-bucketed summary
    print("\n=== Coverage by year (sampled files with >=1 anchor) ===")
    by_year = {}
    no_ts = {'n': 0, 'zero': 0, 'anchors': 0}
    for r in rows:
        if r['n_anchors'] == 0:
            continue
        y = r['year']
        if y is None:
            no_ts['n'] += 1
            no_ts['anchors'] += r['n_anchors']
            no_ts['zero'] += r['zero_despite_anchors']
            continue
        d = by_year.setdefault(y, {'n': 0, 'zero': 0, 'anchors': 0})
        d['n'] += 1
        d['anchors'] += r['n_anchors']
        d['zero'] += r['zero_despite_anchors']

    print(f"{'Year':<8}{'Files w/ anchors':<20}{'Zero-post files':<18}{'Zero rate':<12}")
    for y in sorted(by_year):
        d = by_year[y]
        rate = d['zero'] / d['n'] if d['n'] else 0
        print(f"{y:<8}{d['n']:<20}{d['zero']:<18}{rate:.1%}")
    if no_ts['n']:
        rate = no_ts['zero'] / no_ts['n']
        print(f"{'no-ts':<8}{no_ts['n']:<20}{no_ts['zero']:<18}{rate:.1%}  (Common-Crawl-era filenames, no embedded timestamp)")


if __name__ == '__main__':
    main()
