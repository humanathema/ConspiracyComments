"""build_citations_cache_short.py

Performs URL extraction, normalization, and taxonomy classification for the short-comment
population (18.6M), specifically the 404,019 pre-filtered comments where has_link = 1.

Produces a separate centralized Parquet/CSV cache for short comments:
  - data/processed/citations_cache_short.parquet
  - data/processed/citations_cache_short.csv
"""
import os
import re
import sys
import pandas as pd
import duckdb

sys.path.insert(0, os.path.dirname(__file__))
from build_citations_cache import (
    extract_urls, parse_curated_urls, build_taxonomy_matchers,
    DOMAIN_LOOKUP_PATH, DOMAIN_FALLBACK_EXCLUDED,
)

SHORT_COMMENTS_PATH = 'data/processed/conspiracy_comments_short_lte100chars.parquet'
OUT_PARQUET = 'data/processed/citations_cache_short.parquet'
OUT_CSV = 'data/processed/citations_cache_short.csv'


def main():
    print("=== MATERIALIZING SHORT COMMENT CITATION CACHE ===")
    
    if not os.path.exists(DOMAIN_LOOKUP_PATH):
        print(f"Error: missing domain lookup file {DOMAIN_LOOKUP_PATH}. Build it first.")
        sys.exit(1)
        
    print("Loading domain classification lookup table...")
    df_domain_lookup = pd.read_csv(DOMAIN_LOOKUP_PATH)
    domain_to_rec = df_domain_lookup.set_index('domain').to_dict(orient='index')
    
    print("Parsing curated exact URLs...")
    curated_rows = parse_curated_urls()
    matchers, domain_tax_map = build_taxonomy_matchers(curated_rows)
    print(f"  Parsed {len(curated_rows)} curated exact URLs.")

    con = duckdb.connect()

    print(f"\nStreaming short comments with links from {SHORT_COMMENTS_PATH}...")
    query = f"""
        SELECT id, text
        FROM '{SHORT_COMMENTS_PATH}'
        WHERE has_link = 1
    """
    df_short = con.execute(query).df()
    print(f"  Found {len(df_short):,} short comments with links.")

    print("\nExtracting and normalizing URLs from texts...")
    records = []
    for idx, row in df_short.iterrows():
        cid = row['id']
        urls = extract_urls(row['text'])
        for url in urls:
            m = re.match(r'^https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,4})', url)
            if not m:
                continue
            domain = m.group(1).lower()
            records.append({
                'comment_id': cid,
                'url': url,
                'domain': domain
            })

    citations_df = pd.DataFrame(records)
    print(f"  Extracted {len(citations_df):,} citation records across the short population.")

    if citations_df.empty:
        print("No citations found in short comments. Exiting.")
        return

    print("\nApplying taxonomy classification mapping rules...")
    
    classification_cache = {}

    def classify_single_citation(url, domain):
        cache_key = (url, domain)
        if cache_key in classification_cache:
            return classification_cache[cache_key]
            
        # 1. Exact curated match check
        exact_tax = None
        for orig_str, rx, tax in matchers:
            if rx.match(url):
                exact_tax = tax
                break
                
        # 2. Get domain record
        domain_rec = domain_to_rec.get(domain)
        is_platform = False
        mbfc_rel = None
        sjr_quart = None
        category = 'other'
        
        if domain_rec:
            is_platform = bool(domain_rec['is_platform'])
            mbfc_rel = domain_rec['mbfc_reliability_label'] if pd.notna(domain_rec['mbfc_reliability_label']) else None
            sjr_quart = domain_rec['sjr_quartile'] if pd.notna(domain_rec['sjr_quartile']) else None
            category = domain_rec['category']
            
        # Enforce hard fallback exclusion list constraints
        if domain in DOMAIN_FALLBACK_EXCLUDED:
            is_platform = True

        # Determine Credentials Taxonomy Tier (4-tier)
        cred_tier = 'other'
        conf = 'unreviewed'
        
        if exact_tax:
            cred_tier = exact_tax
            conf = 'curated'
        elif domain in DOMAIN_FALLBACK_EXCLUDED:
            cred_tier = 'other'
            conf = 'unreviewed'
        elif domain in domain_tax_map:
            cred_tier = domain_tax_map[domain]
            conf = 'provisional_heuristic'
        elif domain == 'cia.gov':
            cred_tier = 'credentialed_institutional'
            conf = 'provisional_heuristic'
        elif domain == 'pfizer.com':
            cred_tier = 'other'
            conf = 'provisional_heuristic'
        elif domain.endswith('.gov') or domain.endswith('.mil') or domain in [
            'cdc.gov', 'nih.gov', 'fda.gov', 'who.int', 'ncbi.nlm.nih.gov',
            'pubmed.ncbi.nlm.nih.gov', 'nature.com', 'nejm.org', 'thelancet.com',
            'bmj.com', 'pnas.org', 'sciencedirect.com', 'springer.com',
            'jamanetwork.com', 'science.org', 'biorxiv.org', 'medrxiv.org', 'wiley.com'
        ]:
            cred_tier = 'credentialed_institutional'
            conf = 'provisional_heuristic'
        elif domain in [
            'youtube.com', 'youtu.be', 'twitter.com', 'x.com', 'wikipedia.org',
            'en.wikipedia.org', 'reddit.com', 'old.reddit.com', 'nytimes.com',
            'bbc.com', 'theguardian.com', 'reuters.com', 'npr.org', 'cnn.com'
        ]:
            cred_tier = 'other'
            conf = 'provisional_heuristic'
        else:
            if category in ['government_official', 'academic_scientific']:
                cred_tier = 'credentialed_institutional'
                conf = 'provisional_heuristic'
            elif category == 'alt_media':
                cred_tier = 'movement_internal_anonymous'
                conf = 'provisional_heuristic'
            elif category == 'leak_whistleblower':
                if 'gov' in domain or domain.endswith('.gov') or domain in ['foia.state.gov', 'vault.fbi.gov']:
                    cred_tier = 'credentialed_institutional'
                else:
                    cred_tier = 'movement_internal_anonymous'
                conf = 'provisional_heuristic'
            else:
                cred_tier = 'other'
                conf = 'unreviewed'

        # Determine Link Source Tier (5-tier & 6-tier)
        source_tier = 'unmatched_link'
        
        if is_platform:
            source_tier = 'aggregator_or_platform'
        elif domain.endswith('.gov') or domain.endswith('.mil') or category in ['government_official', 'academic_scientific']:
            source_tier = 'mainstream_reliable'
        elif mbfc_rel:
            m_lower = mbfc_rel.lower()
            if m_lower in ['high', 'very high', 'mostly factual', 'unclassified news']:
                source_tier = 'mainstream_reliable'
            elif m_lower in ['mixed', 'low', 'very low']:
                if category == 'alt_media' or domain in ['zerohedge.com', 'infowars.com', 'breitbart.com', 'rt.com']:
                    source_tier = 'alt_media'
                else:
                    source_tier = 'mainstream_imperfect'
        elif sjr_quart:
            s_lower = sjr_quart.lower()
            if s_lower in ['q1', 'q2']:
                source_tier = 'mainstream_reliable'
            elif s_lower in ['q3', 'q4']:
                source_tier = 'mainstream_imperfect'
        elif category == 'mainstream_news':
            if domain in ['dailymail.co.uk', 'nypost.com']:
                source_tier = 'mainstream_imperfect'
            else:
                source_tier = 'mainstream_reliable'
        elif category == 'alt_media':
            source_tier = 'alt_media'
        else:
            source_tier = 'unmatched_link'

        res = (category, is_platform, cred_tier, source_tier, conf, mbfc_rel, sjr_quart)
        classification_cache[cache_key] = res
        return res

    categories = []
    platforms = []
    cred_tiers = []
    source_tiers = []
    confidences = []
    mbfc_reliability = []
    sjr_quartiles = []

    for idx, row in citations_df.iterrows():
        cat, is_plat, cred, src_tier, conf, mbfc, sjr = classify_single_citation(row['url'], row['domain'])
        categories.append(cat)
        platforms.append(is_plat)
        cred_tiers.append(cred)
        source_tiers.append(src_tier)
        confidences.append(conf)
        mbfc_reliability.append(mbfc)
        sjr_quartiles.append(sjr)

    citations_df['category'] = categories
    citations_df['is_platform'] = platforms
    citations_df['credentials_taxonomy_tier'] = cred_tiers
    citations_df['link_source_tier'] = source_tiers
    citations_df['confidence'] = confidences
    citations_df['mbfc_reliability_label'] = mbfc_reliability
    citations_df['sjr_quartile'] = sjr_quartiles

    print(f"\nShort Comment Citation Mapping Stats:")
    print(f"  Total records: {len(citations_df):,}")
    print(f"  Curated exact URLs: {sum(citations_df['confidence'] == 'curated'):,}")
    print(f"  Fallback/Heuristic matches: {sum(citations_df['confidence'] == 'provisional_heuristic'):,}")
    print(f"  Unreviewed: {sum(citations_df['confidence'] == 'unreviewed'):,}")

    print("\nCredentials 4-tier Taxonomy Distribution (Short):")
    for tier, count in citations_df['credentials_taxonomy_tier'].value_counts().items():
        print(f"  - {tier:27s}: {count:7d}")

    # Output Parquet & CSV
    print(f"\nSaving short citations cache...")
    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    citations_df.to_parquet(OUT_PARQUET, index=False)
    citations_df.to_csv(OUT_CSV, index=False)
    print(f"=== Saved short central Parquet cache to {OUT_PARQUET} ===")


if __name__ == '__main__':
    main()
