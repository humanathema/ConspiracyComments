"""query_petscan_experts.py

Pulls academy membership lists from Wikipedia Category API as a robust,
reproducible alternative to flaky web-scraped PetScan pulls.
Fetches Fellows of the Royal Society and Members of the United States National
Academy of Sciences.
"""
import os
import requests
import pandas as pd

OUT_PATH = "data/processed/petscan_experts.csv"

CATEGORIES = {
    "Fellow of the Royal Society": "Category:Fellows_of_the_Royal_Society",
    "NAS Member": "Category:Members_of_the_United_States_National_Academy_of_Sciences"
}

def fetch_category_members(category_name, limit=1000):
    print(f"Fetching members for {category_name}...")
    url = "https://en.wikipedia.org/w/api.php"
    headers = {"User-Agent": "HonoursThesisAcademicPipeline/1.0 (nash@example.com)"}
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": category_name,
        "cmlimit": 500,
        "format": "json"
    }
    
    members = []
    while len(members) < limit:
        r = requests.get(url, params=params, headers=headers)
        if r.status_code != 200:
            print(f"Error: Wikipedia API returned status {r.status_code}")
            break
            
        data = r.json()
        results = data.get("query", {}).get("categorymembers", [])
        for m in results:
            # Skip subcategories or files
            if m.get("ns") == 0:
                members.append(m.get("title"))
                
        if len(results) < 500 or "continue" not in data:
            break
            
        params["cmcontinue"] = data["continue"]["cmcontinue"]
        
    print(f"Retrieved {len(members)} pages for {category_name}")
    return members[:limit]

def is_valid_person_name(name):
    name_lower = name.lower().strip()
    # Skip Wikipedia list pages
    if name_lower.startswith("list of"):
        return False
    # Skip category metadata pages or explanatory articles
    if name_lower in [
        "fellow of the royal society",
        "fellows of the royal society",
        "member of the national academy of sciences",
        "members of the national academy of sciences",
        "national academy of sciences",
        "royal society",
    ]:
        return False
    return True

def main():
    print("=== Querying Wikipedia Category Experts ===")
    
    all_records = []
    for detail, cat_title in CATEGORIES.items():
        names = fetch_category_members(cat_title, limit=1000)
        for name in names:
            # Reformat or clean names if needed (e.g., stripping post-nominals or parentheses)
            clean_name = name.split("(")[0].strip()
            if not is_valid_person_name(clean_name):
                print(f"Filtering out non-person category page: {clean_name}")
                continue
            all_records.append({
                "name": clean_name,
                "domain": "Science/Academy",
                "basis_type": "academy",
                "basis_detail": detail,
                "source_url": f"https://en.wikipedia.org/wiki/{cat_title}",
                "tenure_start": "",
                "tenure_end": "",
                "in_corpus_window": "Y",
                "notes": "Pulled from Wikipedia Academy Category"
            })
            
    df = pd.DataFrame(all_records)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    print(f"Saved {len(df)} category experts to {OUT_PATH}")

if __name__ == "__main__":
    main()
