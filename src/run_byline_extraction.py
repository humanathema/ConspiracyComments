import os
import re
import urllib.parse
import pandas as pd
import requests
import time
from bs4 import BeautifulSoup

from src.translation import _extract_title, _extract_byline

# Set of domains to exclude from byline extraction (reference, platforms, institutional, etc.)
EXCLUDE_DOMAINS = {
    "wikipedia.org", "en.wikipedia.org", "en.m.wikipedia.org", "youtube.com", "youtu.be",
    "twitter.com", "mobile.twitter.com", "reddit.com", "imgur.com", "archive.org",
    "web.archive.org", "github.com", "facebook.com", "instagram.com", "t.me",
    "amazon.com", "google.com", "patents.google.com", "patentscope.wipo.int",
    "vaers.hhs.gov", "openvaers.com", "phmpt.org", "bit.ly", "tinyurl.com",
    "fda.gov", "cdc.gov", "who.int", "nih.gov", "ncbi.nlm.nih.gov", "justice.gov",
    "whitehouse.gov", "ons.gov.uk", "ourworldindata.org", "documentcloud.org"
}

def get_domain(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""

def is_homepage(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.strip("/")
        if not path or path.lower() in ("index.html", "index.php", "index.htm", "home"):
            return True
        return False
    except Exception:
        return True

def load_curated_urls(filepath="handoff/cited_content_curation_step2.md"):
    if not os.path.exists(filepath):
        print(f"Curated file {filepath} not found.")
        return set()
    curated = set()
    with open(filepath, "r") as f:
        content = f.read()
    in_table = False
    for line in content.split("\n"):
        if line.startswith("|") and "url" in line and "authors" in line:
            in_table = True
            continue
        if in_table:
            if not line.strip() or not line.startswith("|"):
                in_table = False
                continue
            if "---|---|---|---|---" in line:
                continue
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 1:
                url_part = parts[0].lower()
                curated.add(url_part)
    return curated

def fetch_byline_and_title(url: str, timeout: float = 5) -> tuple[str | None, str, str | None]:
    """
    Combined fetcher to retrieve both byline and title from a single request,
    with Wayback fallback if the direct request fails or is blocked.
    Returns: (byline, method, title)
    """
    byline, method, title = None, "failed", None
    
    # Try Direct Fetch
    try:
        response = requests.get(
            url, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (research corpus citation resolver)"}
        )
        if response.status_code == 200:
            byline, method = _extract_byline(response.text, url)
            title = _extract_title(response.text, url)
            if byline or title:
                return byline, method, title
    except Exception:
        pass

    # Wayback Machine Fallback
    try:
        avail = requests.get(
            f"http://archive.org/wayback/available?url={url}", timeout=timeout
        )
        if avail.status_code == 200:
            snapshot = avail.json().get("archived_snapshots", {}).get("closest", {}).get("url")
            if snapshot:
                snap_response = requests.get(
                    snapshot, timeout=timeout,
                    headers={"User-Agent": "Mozilla/5.0 (research corpus citation resolver)"}
                )
                if snap_response.status_code == 200:
                    byline, method = _extract_byline(snap_response.text, url)
                    title = _extract_title(snap_response.text, url)
                    return byline, method, title
    except Exception:
        pass

    return byline, method, title

def run_extraction():
    curated_urls = load_curated_urls()
    print(f"Loaded {len(curated_urls)} curated URLs to exclude.")
    
    ranked_path = "data/processed/cited_urls_ranked.csv"
    if not os.path.exists(ranked_path):
        raise FileNotFoundError(f"Ranked CSV file not found at {ranked_path}")
        
    df_ranked = pd.read_csv(ranked_path)
    print(f"Total ranked URLs in dataset: {len(df_ranked)}")
    
    # Filter candidates
    candidates = []
    skipped_stats = {"curated": 0, "domain": 0, "extension": 0, "homepage": 0}
    
    for idx, row in df_ranked.iterrows():
        url = str(row["url"])
        url_lower = url.lower()
        
        # 1. Check if in curated urls (check substring or exact)
        is_curated = False
        for c_url in curated_urls:
            if c_url in url_lower or url_lower in c_url:
                is_curated = True
                break
        if is_curated:
            skipped_stats["curated"] += 1
            continue
            
        # 2. Check domain exclusions
        domain = get_domain(url)
        if domain in EXCLUDE_DOMAINS or any(d in domain for d in EXCLUDE_DOMAINS if len(d) > 4):
            skipped_stats["domain"] += 1
            continue
            
        # 3. Check extension
        if re.search(r"\.(pdf|jpg|jpeg|png|gif|mp4|mp3|zip|txt|xml)$", url_lower):
            skipped_stats["extension"] += 1
            continue
            
        # 4. Check homepage
        if is_homepage(url):
            skipped_stats["homepage"] += 1
            continue
            
        # Add to candidates
        candidates.append({
            "url": url,
            "distinct_authors": row["distinct_authors"],
            "domain": domain
        })
        
        if len(candidates) >= 500:
            break
            
    print(f"Selected {len(candidates)} candidate URLs after filtering.")
    print(f"Skipped stats: {skipped_stats}")
    
    results = []
    success_count = 0
    start_time = time.time()
    
    for i, cand in enumerate(candidates, 1):
        url = cand["url"]
        print(f"[{i}/500] Fetching: {url} (rank-distinct: {cand['distinct_authors']})")
        
        byline, method, title = fetch_byline_and_title(url)
        
        if byline:
            success_count += 1
            print(f"  -> Extracted Byline: '{byline}' ({method})")
        else:
            print(f"  -> Extraction failed ({method})")
            
        results.append({
            "url": url,
            "distinct_authors": cand["distinct_authors"],
            "extracted_byline": byline,
            "extraction_method": method,
            "domain": cand["domain"],
            "title": title or "",
            "verified": False  # Will update for manual sample later
        })
        
        # Polite delay to prevent rate-limiting
        time.sleep(0.4)
        
    duration = time.time() - start_time
    print(f"\nExtraction complete. Time taken: {duration:.1f}s")
    print(f"Success rate: {success_count}/{len(candidates)} ({success_count/len(candidates)*100:.1f}%)")
    
    # Save as CSV
    df_results = pd.DataFrame(results)
    out_csv = "data/processed/byline_extraction_results.csv"
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    df_results.to_csv(out_csv, index=False)
    print(f"Saved CSV results to {out_csv}")
    
    # We will generate a draft results markdown file as well.
    # Manual verification will be handled in a separate script or manual step.
    write_initial_markdown(df_results, success_count)

def write_initial_markdown(df, success_count):
    md_path = "handoff/byline_extraction_results.md"
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    
    method_counts = df["extraction_method"].value_counts().to_dict()
    
    # Choose 30 random successful extractions for manual verification if possible
    df_success = df[df["extracted_byline"].notna()]
    if len(df_success) >= 30:
        df_sample = df_success.sample(n=30, random_state=42)
    else:
        df_sample = df_success
        
    with open(md_path, "w") as f:
        f.write("# Author Byline Extraction Results\n\n")
        f.write(f"Executed on: {time.strftime('%Y-%m-%d')}\n\n")
        f.write("## Extraction Metrics\n\n")
        f.write(f"- **Total URLs Attempted**: {len(df)}\n")
        f.write(f"- **Successful Extractions**: {success_count} ({success_count/len(df)*100:.1f}%)\n")
        f.write("- **Extraction Methods Breakdown**:\n")
        for method, count in method_counts.items():
            f.write(f"  - `{method}`: {count}\n")
        f.write("\n")
        
        f.write("## Hand-Verified Sample (30 URLs)\n\n")
        f.write("> [!NOTE]\n")
        f.write("> Below is a draft sample of 30 extracted bylines. We will manually check these against the live pages and verify their correctness to measure extractor precision.\n\n")
        
        f.write("| url | distinct_authors | extracted_byline | extraction_method | domain | title | live_byline_check | verified |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        for _, row in df_sample.iterrows():
            url_trunc = row["url"] if len(row["url"]) < 50 else row["url"][:47] + "..."
            title_trunc = row["title"] if len(str(row["title"])) < 40 else str(row["title"])[:37] + "..."
            title_esc = str(title_trunc).replace("|", "\\|")
            f.write(f"| [{url_trunc}]({row['url']}) | {row['distinct_authors']} | {row['extracted_byline']} | {row['extraction_method']} | {row['domain']} | {title_esc} | | [ ] |\n")
            
        f.write("\n## Complete Extraction Results\n\n")
        f.write("| url | distinct_authors | extracted_byline | extraction_method | domain |\n")
        f.write("|---|---|---|---|---|\n")
        for _, row in df.iterrows():
            url_trunc = row["url"] if len(row["url"]) < 60 else row["url"][:57] + "..."
            byline = row["extracted_byline"] if row["extracted_byline"] else "*failed*"
            f.write(f"| [{url_trunc}]({row['url']}) | {row['distinct_authors']} | {byline} | {row['extraction_method']} | {row['domain']} |\n")
            
    print(f"Saved initial Markdown report to {md_path}")

if __name__ == "__main__":
    run_extraction()
