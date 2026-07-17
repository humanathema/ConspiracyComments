import re
import urllib.parse
import requests
import time

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
