import re
import urllib.parse
import requests
import time
import json
from bs4 import BeautifulSoup

def translate_wikipedia_url(url: str) -> str:
    """Extracts a readable title from a Wikipedia URL."""
    try:
        if "wikipedia.org/wiki/" in url:
            title_part = url.split("wikipedia.org/wiki/")[-1]
            # Remove any fragment (e.g., #History)
            title_part = title_part.split("#")[0]
            # Decode URL encoding (e.g., %20 -> space)
            title = urllib.parse.unquote(title_part)
            # Replace underscores with spaces
            title = title.replace("_", " ")
            return title
    except Exception:
        pass
    return url

def fetch_pubmed_metadata(pubmed_id: str) -> dict:
    """Fetches title + author list from the NCBI E-utilities API using a PubMed ID."""
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pubmed_id}&retmode=json"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            result = data["result"][pubmed_id]
            title = result.get("title", pubmed_id)
            authors = [a.get("name", "") for a in result.get("authors", [])]
            return {"title": title, "authors": ", ".join(a for a in authors if a)}
    except Exception as e:
        print(f"Failed to fetch PubMed ID {pubmed_id}: {e}")
    return {"title": pubmed_id, "authors": ""}

def fetch_pubmed_title(pubmed_id: str) -> str:
    """Fetches just the article title from the NCBI E-utilities API using a PubMed ID."""
    return fetch_pubmed_metadata(pubmed_id)["title"]

def translate_pubmed_url(url: str) -> str:
    """Extracts PubMed ID from a URL and fetches the article title."""
    try:
        # Match pubmed.ncbi.nlm.nih.gov/123456/
        match = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", url)
        if match:
            pubmed_id = match.group(1)
            title = fetch_pubmed_title(pubmed_id)
            # Add a slight delay to respect rate limits
            time.sleep(0.34)
            return title
    except Exception:
        pass
    return url

def _clean_youtube_title(raw_title: str) -> str:
    """Strip the ' - YouTube' suffix and reject generic placeholder titles
    (deleted/private videos, or a Wayback wrapper page slipping through)."""
    if not raw_title:
        return ""
    title = re.sub(r"\s*-\s*YouTube\s*$", "", raw_title).strip()
    if title.lower() in ("", "youtube", "wayback machine"):
        return ""
    return title

def fetch_youtube_metadata(video_id: str, timeout: float = 5) -> dict:
    """
    Fetches title + channel name for a YouTube video via the free, keyless
    oEmbed endpoint. Falls back to the Wayback Machine for deleted/private
    videos oEmbed can't resolve -- specifically the mobile
    (m.youtube.com) URL, since archived desktop YouTube pages are
    JS-rendered and don't carry the title in static HTML, while archived
    mobile pages do. Channel name isn't recoverable via this fallback.
    """
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            data = response.json()
            return {"title": data.get("title", video_id), "channel": data.get("author_name", "")}
    except Exception:
        pass

    try:
        mobile_url = f"https://m.youtube.com/watch?v={video_id}"
        avail = requests.get(f"http://archive.org/wayback/available?url={mobile_url}", timeout=timeout)
        if avail.status_code == 200:
            snapshot = avail.json().get("archived_snapshots", {}).get("closest", {}).get("url")
            if snapshot:
                raw_snap_ts = snapshot.split("/web/")[1].split("/")[0]
                raw_snap_url = snapshot.replace(f"/web/{raw_snap_ts}/", f"/web/{raw_snap_ts}id_/")
                snap_response = requests.get(
                    raw_snap_url, timeout=timeout,
                    headers={"User-Agent": "Mozilla/5.0 (research corpus citation resolver)"}
                )
                if snap_response.status_code == 200:
                    match = re.search(r"<title[^>]*>(.*?)</title>", snap_response.text, re.IGNORECASE | re.DOTALL)
                    if match:
                        title = _clean_youtube_title(re.sub(r"\s+", " ", match.group(1)).strip())
                        if title:
                            return {"title": title, "channel": ""}
    except Exception:
        pass

    return {"title": video_id, "channel": ""}

def _extract_title(html: str, url: str) -> str:
    """Pull <title> text, rejecting bot-challenge pages that just echo the bare domain."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    domain = re.sub(r"^https?://(?:www\.)?", "", url).split("/")[0]
    if not title or title.lower() == domain.lower():
        return ""
    return title

def fetch_article_title(url: str, timeout: float = 5) -> str:
    """
    Best-effort <title> tag fetch for an arbitrary article URL (news sites,
    WikiLeaks pages, etc). No universal API for this like PubMed/YouTube
    have, so it's a direct page fetch first -- some domains (Reuters,
    NYTimes) run bot-detection that returns a 401/403 challenge page
    instead of the article, so this falls back to the Wayback Machine's
    free, keyless availability API, which isn't bot-blocked.
    """
    try:
        response = requests.get(
            url, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (research corpus citation resolver)"}
        )
        if response.status_code == 200:
            title = _extract_title(response.text, url)
            if title:
                return title
    except Exception:
        pass

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
                    title = _extract_title(snap_response.text, url)
                    if title:
                        return title
    except Exception:
        pass

    return url

def fetch_article_titles_batch(urls, delay: float = 0.3):
    """
    fetch_article_title over a list of URLs with a small delay between
    each -- calling it in a tight loop/apply() without this reliably
    triggers Wayback Machine rate-limiting on batches bigger than ~10.
    """
    titles = []
    for url in urls:
        titles.append(fetch_article_title(url))
        time.sleep(delay)
    return titles

def clean_author_name(name: str) -> str:
    """Clean and normalize raw extracted author strings, filtering out boilerplate."""
    if not isinstance(name, str):
        return ""
    # Normalize whitespace
    name = re.sub(r"\s+", " ", name).strip()
    # Strip leading "by " or "By " (case-insensitive)
    name = re.sub(r"(?i)^by\s+", "", name).strip()
    # Handle concatenated "ByName" (e.g. "ByIan Lee")
    name = re.sub(r"^By([A-Z])", r"\1", name).strip()
    
    # Reject if empty, too long, too short, or contains HTML tags
    if not name or len(name) > 100 or len(name) < 2 or "<" in name or ">" in name:
        return ""
        
    # Reject common boilerplate words or terms indicating non-authors
    blacklist = [
        "share", "subscribe", "comments", "comment", "email", "print", "follow", 
        "facebook", "twitter", "instagram", "login", "register", "posted", "published", 
        "updated", "modified", "click here", "read more", "about the author", "about us",
        "home", "news", "homepage", "contact us"
    ]
    name_lower = name.lower()
    for word in blacklist:
        if word == name_lower or f" {word} " in f" {name_lower} ":
            return ""
            
    # Also ignore purely numeric/date strings
    if re.match(r"^\d+[\s\d\-:/]*$", name):
        return ""
        
    return name

def _extract_names_from_author_val(author_val):
    """Recursively extract name(s) from a schema.org JSON-LD author value."""
    if not author_val:
        return None
        
    if isinstance(author_val, str):
        cleaned = clean_author_name(author_val)
        return [cleaned] if cleaned else None
        
    if isinstance(author_val, dict):
        name_val = author_val.get("name")
        if name_val:
            if isinstance(name_val, str):
                cleaned = clean_author_name(name_val)
                return [cleaned] if cleaned else None
            elif isinstance(name_val, list):
                names = []
                for n in name_val:
                    if isinstance(n, str):
                        c = clean_author_name(n)
                        if c:
                            names.append(c)
                return names if names else None
                
    if isinstance(author_val, list):
        names = []
        for item in author_val:
            res = _extract_names_from_author_val(item)
            if res:
                names.extend(res)
        return names if names else None
        
    return None

def _find_author_in_json(obj):
    """Recursively search for 'author' field in JSON-LD objects."""
    if isinstance(obj, dict):
        if 'author' in obj:
            authors = _extract_names_from_author_val(obj['author'])
            if authors:
                return authors
        for k, v in obj.items():
            res = _find_author_in_json(v)
            if res:
                return res
    elif isinstance(obj, list):
        for item in obj:
            res = _find_author_in_json(item)
            if res:
                return res
    return None

def _extract_byline(html: str, url: str) -> tuple[str | None, str]:
    """
    Extract author byline from HTML content using JSON-LD, meta tags,
    and common HTML selector patterns in order of reliability.
    """
    soup = BeautifulSoup(html, "html.parser")
    
    # Method 1: JSON-LD
    ld_scripts = soup.find_all("script", type="application/ld+json")
    for script in ld_scripts:
        if not script.string:
            continue
        try:
            data = json.loads(script.string.strip())
            authors = _find_author_in_json(data)
            if authors:
                return ", ".join(authors), "json-ld"
        except Exception:
            continue
            
    # Method 2: Meta Tags
    meta_keys = ["author", "article:author", "twitter:creator", "dc.creator", "sailthru.author", "byl"]
    for key in meta_keys:
        meta = soup.find("meta", attrs={"name": re.compile(f"^{re.escape(key)}$", re.IGNORECASE)})
        if not meta:
            meta = soup.find("meta", attrs={"property": re.compile(f"^{re.escape(key)}$", re.IGNORECASE)})
        if meta and meta.get("content"):
            cleaned = clean_author_name(meta["content"])
            if cleaned:
                return cleaned, "meta-tag"
                
    selectors = [
        "a[rel='author']",
        ".byline",
        ".author-name",
        ".author__name",
        ".entry-author",
        ".article-author",
        ".author",
    ]
    for selector in selectors:
        try:
            elements = soup.select(selector)
            for elem in elements:
                text = elem.get_text(strip=True)
                cleaned = clean_author_name(text)
                if cleaned and len(cleaned) > 2 and len(cleaned) < 80:
                    return cleaned, "html-pattern"
        except Exception:
            continue
            
    return None, "failed"

def fetch_article_byline(url: str, timeout: float = 5) -> tuple[str | None, str]:
    """
    Best-effort author byline extraction for an arbitrary article URL.
    Attempts direct fetch first, and falls back to Wayback Machine snapshot
    if blocked or unavailable. Returns (extracted_byline, extraction_method).
    """
    try:
        response = requests.get(
            url, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (research corpus citation resolver)"}
        )
        if response.status_code == 200:
            byline, method = _extract_byline(response.text, url)
            if byline:
                return byline, method
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
                    if byline:
                        return byline, method
    except Exception:
        pass

    return None, "failed"


def resolve_titles_with_reddit_first(urls, reddit_title_lookup, delay: float = 0.3):
    """
    Resolve titles for a list of URLs, preferring Reddit's own submitted
    post title (free, deterministic, already in the corpus, and often
    more informative than the raw page title) over an external fetch.
    Only falls through to fetch_article_title -- direct page fetch, then
    Wayback Machine -- for URLs that were never themselves submitted as
    a link post.

    Args:
        urls: iterable of URLs needing a title.
        reddit_title_lookup: dict {url: title} built from the corpus's
            own posts (see the `post_titles_query` cell).
        delay: seconds between external-fetch calls (only applied when
            actually falling through, not for Reddit-title hits).
    """
    titles = []
    for url in urls:
        reddit_title = reddit_title_lookup.get(url)
        if reddit_title:
            titles.append(reddit_title)
        else:
            titles.append(fetch_article_title(url))
            time.sleep(delay)
    return titles

def translate_url(url: str) -> str:
    """Master translation function that routes to specific parsers based on domain."""
    if not isinstance(url, str):
        return url

    if "wikipedia.org" in url.lower():
        return translate_wikipedia_url(url)
    elif "pubmed.ncbi.nlm.nih.gov" in url.lower():
        return translate_pubmed_url(url)
    else:
        return url
