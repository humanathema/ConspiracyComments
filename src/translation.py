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

def fetch_youtube_metadata(video_id: str) -> dict:
    """Fetches title + channel name for a YouTube video via the free, keyless oEmbed endpoint."""
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return {"title": data.get("title", video_id), "channel": data.get("author_name", "")}
    except Exception as e:
        print(f"Failed to fetch YouTube video {video_id}: {e}")
    return {"title": video_id, "channel": ""}

def fetch_article_title(url: str, timeout: float = 5) -> str:
    """
    Best-effort <title> tag fetch for an arbitrary article URL (news sites,
    WikiLeaks pages, etc). No universal API for this like PubMed/YouTube
    have, so it's a direct page fetch -- expect a nontrivial failure rate
    from paywalls, 404s, and bot-blocking on some domains.
    """
    try:
        response = requests.get(
            url, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (research corpus citation resolver)"}
        )
        if response.status_code == 200:
            match = re.search(r"<title[^>]*>(.*?)</title>", response.text, re.IGNORECASE | re.DOTALL)
            if match:
                title = re.sub(r"\s+", " ", match.group(1)).strip()
                if title:
                    return title
    except Exception:
        pass
    return url

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
