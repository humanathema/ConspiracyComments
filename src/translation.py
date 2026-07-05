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

def fetch_pubmed_title(pubmed_id: str) -> str:
    """Fetches the article title from the NCBI E-utilities API using a PubMed ID."""
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pubmed_id}&retmode=json"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            title = data["result"][pubmed_id]["title"]
            return title
    except Exception as e:
        print(f"Failed to fetch PubMed ID {pubmed_id}: {e}")
    return pubmed_id

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
