"""run_byline_extraction_batch2.py

Second batch of byline_extraction_results.csv, per
handoff/task_citation_coverage_expansion.md ranked-next-step #1: "running
it against the next 5,000-10,000 URLs by citation volume (already ranked,
no new labels needed) would take Reddit-side article-author coverage
from ~0.02% of URLs to something defensible, entirely with existing
deterministic code, no LLM calls."

Same extraction code as run_byline_extraction.py (src/translation.py's
_extract_byline/_extract_title, same Wayback fallback) -- this script
only changes which URLs get selected: skips both the curated set AND the
500 URLs already processed in data/processed/byline_extraction_results.csv,
then takes the next N_NEW candidates by citation volume.

Appends to (does not overwrite) byline_extraction_results.csv.
"""
import os
import re
import time

import pandas as pd

from src.run_byline_extraction import (
    EXCLUDE_DOMAINS, get_domain, is_homepage, load_curated_urls, fetch_byline_and_title,
)

N_NEW = 5000
OUT_CSV = "data/processed/byline_extraction_results.csv"


def run_extraction():
    curated_urls = load_curated_urls()
    already_done = set()
    if os.path.exists(OUT_CSV):
        prior = pd.read_csv(OUT_CSV)
        already_done = set(prior["url"].str.lower())
        print(f"{len(already_done)} URLs already processed in a prior batch, will skip.")

    ranked_path = "data/processed/cited_urls_ranked.csv"
    df_ranked = pd.read_csv(ranked_path)
    print(f"Total ranked URLs in dataset: {len(df_ranked)}")

    candidates = []
    skipped_stats = {"curated": 0, "already_done": 0, "domain": 0, "extension": 0, "homepage": 0}

    for _, row in df_ranked.iterrows():
        url = str(row["url"])
        url_lower = url.lower()

        if url_lower in already_done:
            skipped_stats["already_done"] += 1
            continue

        is_curated = False
        for c_url in curated_urls:
            if c_url in url_lower or url_lower in c_url:
                is_curated = True
                break
        if is_curated:
            skipped_stats["curated"] += 1
            continue

        domain = get_domain(url)
        if domain in EXCLUDE_DOMAINS or any(d in domain for d in EXCLUDE_DOMAINS if len(d) > 4):
            skipped_stats["domain"] += 1
            continue

        if re.search(r"\.(pdf|jpg|jpeg|png|gif|mp4|mp3|zip|txt|xml)$", url_lower):
            skipped_stats["extension"] += 1
            continue

        if is_homepage(url):
            skipped_stats["homepage"] += 1
            continue

        candidates.append({"url": url, "distinct_authors": row["distinct_authors"], "domain": domain})
        if len(candidates) >= N_NEW:
            break

    print(f"Selected {len(candidates)} new candidate URLs after filtering.")
    print(f"Skipped stats: {skipped_stats}")

    results = []
    success_count = 0
    start_time = time.time()
    write_header = not os.path.exists(OUT_CSV)

    for i, cand in enumerate(candidates, 1):
        url = cand["url"]
        byline, method, title = fetch_byline_and_title(url)

        if byline:
            success_count += 1

        row = {
            "url": url, "distinct_authors": cand["distinct_authors"], "extracted_byline": byline,
            "extraction_method": method, "domain": cand["domain"], "title": title or "", "verified": False,
        }
        results.append(row)

        if i % 50 == 0 or i == len(candidates):
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            eta_min = (len(candidates) - i) / rate / 60 if rate > 0 else float("inf")
            print(f"[{i}/{len(candidates)}] success so far: {success_count} ({success_count/i*100:.1f}%) | "
                  f"{rate:.1f}/s | ETA {eta_min:.1f} min", flush=True)

        # Flush to disk every 200 rows so a crash/timeout doesn't lose progress.
        if i % 200 == 0:
            pd.DataFrame(results).to_csv(OUT_CSV, mode="a", header=write_header, index=False)
            write_header = False
            results = []

        time.sleep(0.4)

    if results:
        pd.DataFrame(results).to_csv(OUT_CSV, mode="a", header=write_header, index=False)

    duration = time.time() - start_time
    print(f"\nBatch 2 extraction complete. Time taken: {duration:.1f}s")
    print(f"Success rate this batch: {success_count}/{len(candidates)} ({success_count/max(1,len(candidates))*100:.1f}%)")


if __name__ == "__main__":
    run_extraction()
