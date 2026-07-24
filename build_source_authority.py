import os
import csv
import re

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

def normalize_name(name):
    if not name:
        return ""
    name = name.lower().strip()
    # Remove leading "the "
    if name.startswith("the "):
        name = name[4:].strip()
    # Remove non-alphanumeric characters
    name = re.sub(r'[^a-z0-9]', '', name)
    return name

def is_individual(wp_desc, name):
    if not wp_desc:
        return False
    desc = wp_desc.lower()
    # Words indicating a person/individual
    individual_keywords = [
        "journalist", "author", "writer", "novelist", "physicist", "professor",
        "activist", "politician", "founder", "born 19", "born 20", "whistleblower",
        "conspiracy theorist", "broadcaster", "columnist", "reporter", "economist",
        "sociologist", "philosopher", "commentator", "editor"
    ]
    for kw in individual_keywords:
        if kw in desc:
            # Exceptions for things like "weekly news magazine" which might contain "writer"
            if "magazine" in desc or "newspaper" in desc or "journal" in desc or "agency" in desc:
                continue
            return True
    return False

def build_source_authority():
    candidates_path = os.path.join(REPO_ROOT, "data/processed/institutional_source_candidates.csv")
    mbfc_path = os.path.join(REPO_ROOT, "data/raw/mbfc.csv")
    sjr_path = os.path.join(REPO_ROOT, "data/raw/scimagojr 2025.csv")
    output_path = os.path.join(REPO_ROOT, "data/processed/source_authority_scores.csv")

    print("Loading institutional source candidates...")
    candidates = []
    with open(candidates_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            candidates.append(row)
    print(f"Loaded {len(candidates)} candidates.")

    # Load MBFC
    print("Loading MBFC data...")
    mbfc_data = {}
    with open(mbfc_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            domain = row['source'].strip().lower()
            mbfc_data[domain] = {
                "bias": row['bias'].strip(),
                "factual_reporting": row['factual_reporting'].strip()
            }
    print(f"Loaded {len(mbfc_data)} MBFC outlets.")

    # Load SJR
    print("Loading SJR 2025 data...")
    sjr_data = {}
    with open(sjr_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
        # Use ';' as delimiter
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            title = row.get('Title', '').strip()
            if title:
                sjr_data[title.lower()] = {
                    "title": title,
                    "sjr": row.get('SJR', '0').replace(',', '.'),
                    "quartile": row.get('SJR Best Quartile', ''),
                    "h_index": row.get('H index', '0'),
                    "categories": row.get('Categories', '')
                }
    print(f"Loaded {len(sjr_data)} SJR journals.")

    # Explicit manual mapping dictionary for top outlets/journals
    manual_news_map = {
        "washingtonpost": "washingtonpost.com",
        "wapo": "washingtonpost.com",
        "thewashingtonpost": "washingtonpost.com",
        "guardian": "theguardian.com",
        "theguardian": "theguardian.com",
        "nytimes": "nytimes.com",
        "newyorktimes": "nytimes.com",
        "thenewyorktimes": "nytimes.com",
        "nytimes": "nytimes.com",
        "wsj": "wsj.com",
        "wallstreetjournal": "wsj.com",
        "thewallstreetjournal": "wsj.com",
        "dailymail": "dailymail.co.uk",
        "thedailymail": "dailymail.co.uk",
        "associatedpress": "apnews.com",
        "theassociatedpress": "apnews.com",
        "ap": "apnews.com",
        "reuters": "reuters.com",
        "bbc": "bbc.co.uk",
        "cnn": "cnn.com",
        "politico": "politico.com",
        "forbes": "forbes.com",
        "newsweek": "newsweek.com",
        "foxnews": "foxnews.com",
        "fox": "foxnews.com",
        "npr": "npr.org",
        "msnbc": "msnbc.com",
        "huffpost": "huffpost.com",
        "huffingtonpost": "huffpost.com",
        "breitbart": "breitbart.com",
        "infowars": "infowars.com",
        "rt": "rt.com",
        "russiatoday": "rt.com",
        "time": "time.com",
        "atlantic": "theatlantic.com",
        "intercept": "theintercept.com",
        "salon": "salon.com",
        "slate": "slate.com",
        "vice": "vice.com",
        "vox": "vox.com"
    }

    manual_journal_map = {
        "nejm": "new england journal of medicine",
        "bmj": "bmj",
        "britishmedicaljournal": "bmj",
        "thebritishmedicaljournal": "bmj",
        "jama": "jama",
        "pnas": "proceedings of the national academy of sciences of the united states of america"
    }

    results = []
    matched_counts = {"gov": 0, "journal": 0, "news": 0, "none": 0}

    for cand in candidates:
        entity = cand['entity'].strip()
        doc_count = float(cand['doc_count']) if cand['doc_count'] else 0.0
        wp_desc = cand['wp_description'].strip() if cand['wp_description'] else ""

        # Default fields
        category = "none"
        matched_name = ""
        dataset = "none"
        reliability_label = ""
        rank_or_score = ""
        bias_label = ""

        wp_desc_lower = wp_desc.lower()

        # 1. Filter out individuals/persons to keep construct strictly institutional
        if is_individual(wp_desc, entity):
            category = "none"
        # 2. Check if .gov agency (improved US vs U.S. and executive department checks)
        elif "federal government agency" in wp_desc_lower or \
             "executive department of the u.s." in wp_desc_lower or \
             "executive department of the us" in wp_desc_lower or \
             "federal agency" in wp_desc_lower or \
             "u.s. federal agency" in wp_desc_lower or \
             "us federal agency" in wp_desc_lower or \
             "government agency" in wp_desc_lower or \
             "independent agency of the united states" in wp_desc_lower or \
             "agency of the united states" in wp_desc_lower or \
             "u.s. federal government" in wp_desc_lower or \
             "us federal government" in wp_desc_lower or \
             "executive department of the federal government" in wp_desc_lower or \
             entity.lower() in ["epa", "state department", "tsa", "fda", "gao", "cdc", "nasa", "cia", "fbi", "nsa", "irs", "doj", "nih", "pentagon", "department of defense", "defense department", "department of justice", "department of homeland security"]:
            category = "gov"
            matched_name = entity
            dataset = "gov"
            reliability_label = "Maximum Authority"
            rank_or_score = "1.0"
            bias_label = "neutral"
        else:
            norm_entity = normalize_name(entity)

            # 3. Check for Academic Journal match
            journal_match = None
            # Check manual journal abbreviations first
            if norm_entity in manual_journal_map:
                journal_match = sjr_data.get(manual_journal_map[norm_entity])
            else:
                # Direct match
                journal_match = sjr_data.get(entity.lower())
                if not journal_match:
                    # Normalized match
                    for title_lower, info in sjr_data.items():
                        norm_title = normalize_name(info['title'])
                        if norm_entity == norm_title:
                            journal_match = info
                            break

            if journal_match:
                category = "journal"
                matched_name = journal_match['title']
                dataset = "sjr"
                reliability_label = journal_match['quartile']
                rank_or_score = journal_match['sjr']
                bias_label = "neutral"
            else:
                # 4. Check for News/Media outlet match
                news_match_domain = None
                # Check manual news map first
                if norm_entity in manual_news_map:
                    news_match_domain = manual_news_map[norm_entity]
                else:
                    # Try to find a matching domain in MBFC
                    for domain, info in mbfc_data.items():
                        norm_dom = normalize_name(domain.split('.')[0])
                        if norm_entity == norm_dom:
                            news_match_domain = domain
                            break
                        elif norm_entity in norm_dom and len(norm_entity) >= 4:
                            news_match_domain = domain
                            break

                if news_match_domain and news_match_domain in mbfc_data:
                    mbfc_info = mbfc_data[news_match_domain]
                    category = "news"
                    matched_name = news_match_domain
                    dataset = "mbfc"
                    reliability_label = mbfc_info['factual_reporting']
                    # Map factual reporting to numerical score
                    fact_map = {
                        "very high": "5.0",
                        "high": "4.5",
                        "mostly factual": "4.0",
                        "mixed": "3.0",
                        "low": "1.5",
                        "very low": "0.0"
                    }
                    rank_or_score = fact_map.get(mbfc_info['factual_reporting'].lower(), "3.0")
                    bias_label = mbfc_info['bias']
                # Substring check for other media indications in wp_description
                elif "newspaper" in wp_desc.lower() or "magazine" in wp_desc.lower() or "broadcaster" in wp_desc.lower() or "news website" in wp_desc.lower():
                    category = "news"
                    matched_name = entity
                    dataset = "none"
                    reliability_label = "Unclassified news"
                    rank_or_score = "3.0"
                    bias_label = "unknown"

        matched_counts[category] += 1

        results.append({
            "entity": entity,
            "doc_count": doc_count,
            "category": category,
            "matched_name": matched_name,
            "dataset": dataset,
            "reliability_label": reliability_label,
            "rank_or_score": rank_or_score,
            "bias_label": bias_label,
            "wp_description": wp_desc
        })

    # Sort results by doc_count descending
    results.sort(key=lambda x: -x['doc_count'])

    # Write output CSV
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        fieldnames = ["entity", "doc_count", "category", "matched_name", "dataset", "reliability_label", "rank_or_score", "bias_label", "wp_description"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    print("\nMatching Summary:")
    for k, v in matched_counts.items():
        print(f"  - {k}: {v} matches")
    print(f"\nSuccessfully generated {output_path}!")

if __name__ == "__main__":
    build_source_authority()
