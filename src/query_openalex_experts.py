"""query_openalex_experts.py

Queries the free OpenAlex API to programmatically discover and extract
citation-elite academic consensus experts across target domains.
"""
import os
import requests
import pandas as pd

OUT_PATH = "data/processed/openalex_experts.csv"

DOMAINS = {
    "climate": ("Climate", 5000),
    "health": ("Public Health", 5000),
    "economics": ("Economics", 5000),
    "aerospace": ("Aerospace", 1000)
}

def query_openalex_domain(query, domain_name, min_citations):
    print(f"Querying OpenAlex for {query} ({domain_name}) with citations > {min_citations}...")
    url = f"https://api.openalex.org/authors"
    params = {
        "filter": f"cited_by_count:>{min_citations},works_count:>50",
        "search": query,
        "select": "display_name,works_count,cited_by_count,summary_stats,last_known_institutions",
        "per_page": 100
    }
    
    r = requests.get(url, params=params)
    if r.status_code != 200:
        print(f"Error: OpenAlex API returned status {r.status_code}")
        return []
        
    results = r.json().get("results", [])
    records = []
    for x in results:
        name = x.get("display_name")
        if not name:
            continue
        
        # Check if name is initials-only
        tokens = name.strip().split()
        if len(tokens) > 1:
            all_except_last_are_initials = True
            for t in tokens[:-1]:
                clean_t = t.replace(".", "")
                if not (len(clean_t) == 1 and clean_t.isupper()):
                    all_except_last_are_initials = False
                    break
            if all_except_last_are_initials:
                print(f"Filtering out initials-only OpenAlex profile: {name}")
                continue

        citations = x.get("cited_by_count", 0)
        h_index = x.get("summary_stats", {}).get("h_index", 0)
        
        inst_list = x.get("last_known_institutions", [])
        inst_name = inst_list[0].get("display_name", "") if inst_list else ""
        country_code = inst_list[0].get("country_code", "") if inst_list else ""
        
        records.append({
            "name": name,
            "domain": domain_name,
            "basis_type": "citation_elite",
            "basis_detail": f"OpenAlex Citation Elite (h-index: {h_index}, citations: {citations})",
            "source_url": f"https://openalex.org/authors?search={name}",
            "tenure_start": "",
            "tenure_end": "",
            "in_corpus_window": "Y",
            "h_index": h_index,
            "citation_count": citations,
            "institution": inst_name,
            "country": country_code,
            "notes": f"OpenAlex Academic Citation Sweep ({domain_name})"
        })
        
    print(f"Retrieved {len(records)} records for {query}")
    return records

def main():
    print("=== Querying OpenAlex Citation-Elite Experts ===")
    
    all_records = []
    for query, (domain_name, min_citations) in DOMAINS.items():
        records = query_openalex_domain(query, domain_name, min_citations)
        all_records.extend(records)
        
    df = pd.DataFrame(all_records)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    print(f"Saved {len(df)} OpenAlex experts to {OUT_PATH}")

if __name__ == "__main__":
    main()
