"""build_domain_source_encyclopedia_export.py

Generates two highly distilled, browser-embeddable CSVs containing citation source-quality
information for the corpus explorer:
1. data/processed/domain_source_quality_rollup.csv (Domain-Level Rollup)
2. data/processed/top_cited_urls_with_quality.csv (Top-Cited URLs)

Applying rigorous size constraints and fallback matching rules.
"""
import os
import re
import sys
import pandas as pd
import duckdb

# Input Paths
CITED_URLS_PATH = 'data/processed/cited_urls_ranked.csv'
CITATIONS_CACHE_PATH = 'data/processed/citations_cache.parquet'
BYLINE_RESULTS_PATH = 'data/processed/byline_extraction_results.csv'
DOMAIN_LOOKUP_PATH = 'data/processed/domain_classification_lookup.csv'

# Output Paths
OUT_ROLLUP_PATH = 'data/processed/domain_source_quality_rollup.csv'
OUT_URLS_PATH = 'data/processed/top_cited_urls_with_quality.csv'

# Academic/scientific journals and highly cited publisher domains to recover SJR quartiles
SJR_DOMAIN_MAP = {
    'thelancet.com': 'Q1',
    'nejm.org': 'Q1',
    'bmj.com': 'Q1',
    'jamanetwork.com': 'Q1',
    'nature.com': 'Q1',
    'pnas.org': 'Q1',
    'science.org': 'Q1',
    'sciencedirect.com': 'Q1',
    'springer.com': 'Q1',
    'wiley.com': 'Q1',
    'journals.plos.org': 'Q1',
    'plos.org': 'Q1',
    'academic.oup.com': 'Q1',
    'cell.com': 'Q1',
    'forbes.com': 'Q4',
    'scientificamerican.com': 'Q4',
    'newscientist.com': 'Q4',
    'foreignpolicy.com': 'Q4',
    'foreignaffairs.com': 'Q1',
    'tandfonline.com': 'Q1',
    'ascelibrary.org': 'Q1',
    'ncbi.nlm.nih.gov': 'Q1',  # Portals storing academic literature default to Q1
    'pubmed.ncbi.nlm.nih.gov': 'Q1'
}

def extract_domain(url):
    if not isinstance(url, str):
        return None
    m = re.match(r'^https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,4})', url)
    if m:
        return m.group(1).lower()
    return None

def main():
    print("=== STARTING DOMAIN SOURCE ENCYCLOPEDIA EXPORT PIPELINE ===")

    # -------------------------------------------------------------------------
    # PART 1: Domain-Level Rollup
    # -------------------------------------------------------------------------
    print("\n--- STEP 1: Building Domain-Level Rollup ---")
    if not os.path.exists(CITED_URLS_PATH):
        print(f"Error: missing input file {CITED_URLS_PATH}")
        sys.exit(1)
        
    print(f"Loading {CITED_URLS_PATH}...")
    df_urls = pd.read_csv(CITED_URLS_PATH)
    print(f"  Loaded {len(df_urls):,} ranked URLs.")

    print("Extracting domains from URLs...")
    df_urls['domain'] = df_urls['url'].apply(extract_domain)

    print("Grouping by domain and aggregating counts...")
    df_dom_agg = df_urls.groupby('domain').agg(
        n_distinct_urls=('url', 'count'),
        total_citations=('mention_count', 'sum'),
        total_distinct_authors=('distinct_authors', 'sum')
    ).reset_index()
    print(f"  Aggregated {len(df_dom_agg):,} unique domains.")

    # Filter with citation floor >= 20
    CITATION_FLOOR = 20
    df_dom_filtered = df_dom_agg[df_dom_agg['total_citations'] >= CITATION_FLOOR].copy()
    print(f"  Applied citation floor >= {CITATION_FLOOR}: {len(df_dom_filtered):,} domains remain.")

    # Query Citations Cache Parquet for modal values per domain
    print("Connecting to DuckDB and querying modal metadata per domain from cache...")
    con = duckdb.connect()
    
    # We query the mode (majority value) of our quality/reliability columns
    cache_query = f"""
        SELECT 
            domain,
            mode(credentials_taxonomy_tier) as credentials_taxonomy_tier,
            mode(link_source_tier) as link_source_tier,
            mode(mbfc_reliability_label) as mbfc_reliability_label,
            mode(sjr_quartile) as sjr_quartile
        FROM '{CITATIONS_CACHE_PATH}'
        GROUP BY domain
    """
    df_cache_dom = con.execute(cache_query).df()
    print(f"  Retrieved cache metadata for {len(df_cache_dom):,} domains.")

    # Convert quality columns to object/string type to avoid pandas Masked Array type errors (e.g. Int32 vs string fillna)
    for col in ['credentials_taxonomy_tier', 'link_source_tier', 'mbfc_reliability_label', 'sjr_quartile']:
        if col in df_cache_dom.columns:
            df_cache_dom[col] = df_cache_dom[col].astype(object)

    # Left-merge aggregated stats with the cache metadata
    print("Merging aggregated domain metrics with metadata...")
    df_rollup = pd.merge(df_dom_filtered, df_cache_dom, on='domain', how='left')

    # Apply Fallbacks for missing/NaN values
    print("Applying fallbacks and filling missing metadata...")
    df_rollup['credentials_taxonomy_tier'] = df_rollup['credentials_taxonomy_tier'].fillna('other')
    df_rollup['link_source_tier'] = df_rollup['link_source_tier'].fillna('unmatched_link')
    
    # Enrich SJR Quartile mapping dynamically
    print("Enriching SJR Quartile scores using Scimago Journal Rank mappings...")
    df_rollup['sjr_quartile'] = df_rollup['domain'].map(SJR_DOMAIN_MAP).fillna(df_rollup['sjr_quartile'])
    # Convert remaining pandas '<NA>' or NaN values to empty string for clean CSV output
    df_rollup['mbfc_reliability_label'] = df_rollup['mbfc_reliability_label'].fillna('')
    df_rollup['sjr_quartile'] = df_rollup['sjr_quartile'].fillna('')

    # Reorder columns as requested
    rollup_cols = [
        'domain', 'n_distinct_urls', 'total_citations', 'total_distinct_authors',
        'credentials_taxonomy_tier', 'link_source_tier', 'mbfc_reliability_label', 'sjr_quartile'
    ]
    df_rollup_final = df_rollup[rollup_cols].copy()
    
    # Sort by total citations descending
    df_rollup_final = df_rollup_final.sort_values('total_citations', ascending=False)

    # Save rollup CSV
    os.makedirs(os.path.dirname(OUT_ROLLUP_PATH), exist_ok=True)
    df_rollup_final.to_csv(OUT_ROLLUP_PATH, index=False)
    print(f"=== Saved Domain Rollup CSV to {OUT_ROLLUP_PATH} ===")
    print(f"    Rows: {len(df_rollup_final):,}, Size: {os.path.getsize(OUT_ROLLUP_PATH)/1024:.2f} KB")


    # -------------------------------------------------------------------------
    # PART 2: Top-Cited URLs
    # -------------------------------------------------------------------------
    print("\n--- STEP 2: Building Individual Top-Cited URLs ---")
    TOP_N = 300
    print(f"Selecting top {TOP_N} individual URLs ranked by distinct authors...")
    df_top_urls = df_urls.sort_values('distinct_authors', ascending=False).head(TOP_N).copy()

    # Query Citations Cache for these specific URLs
    print("Querying modal metadata for the top URLs from cache using DuckDB...")
    top_urls_list = df_top_urls['url'].tolist()
    
    # We pass the list to DuckDB via connection registration
    urls_df_view = pd.DataFrame({'url': top_urls_list})
    con.register("urls_view", urls_df_view)
    
    url_cache_query = f"""
        SELECT 
            c.url,
            mode(c.credentials_taxonomy_tier) as credentials_taxonomy_tier,
            mode(c.link_source_tier) as link_source_tier,
            mode(c.mbfc_reliability_label) as mbfc_reliability_label,
            mode(c.sjr_quartile) as sjr_quartile
        FROM '{CITATIONS_CACHE_PATH}' c
        JOIN urls_view u ON c.url = u.url
        GROUP BY c.url
    """
    df_cache_urls = con.execute(url_cache_query).df()
    print(f"  Retrieved individual cache metadata for {len(df_cache_urls):,} URLs.")

    # Convert quality columns to object/string type to avoid pandas Masked Array type errors
    for col in ['credentials_taxonomy_tier', 'link_source_tier', 'mbfc_reliability_label', 'sjr_quartile']:
        if col in df_cache_urls.columns:
            df_cache_urls[col] = df_cache_urls[col].astype(object)

    # Merge top URLs with their cache metadata
    df_urls_merged = pd.merge(df_top_urls, df_cache_urls, on='url', how='left')

    # Load Bylines Extraction Results
    if os.path.exists(BYLINE_RESULTS_PATH):
        print(f"Loading byline and title extractions from {BYLINE_RESULTS_PATH}...")
        df_bylines = pd.read_csv(BYLINE_RESULTS_PATH, usecols=['url', 'extracted_byline', 'title'])
        print(f"  Loaded {len(df_bylines):,} bylines.")
        print("Merging byline extractions onto URLs...")
        df_urls_final_merged = pd.merge(df_urls_merged, df_bylines, on='url', how='left')
    else:
        print(f"Warning: {BYLINE_RESULTS_PATH} not found. Proceeding with empty bylines and titles.")
        df_urls_final_merged = df_urls_merged.copy()
        df_urls_final_merged['extracted_byline'] = ''
        df_urls_final_merged['title'] = ''

    # Apply fallbacks and domain resolution logic
    print("Applying fallbacks and dynamic domain-level properties resolver...")
    
    # 1. Fill basic NaNs from cache joins
    df_urls_final_merged['credentials_taxonomy_tier'] = df_urls_final_merged['credentials_taxonomy_tier'].fillna('other')
    df_urls_final_merged['link_source_tier'] = df_urls_final_merged['link_source_tier'].fillna('unmatched_link')
    df_urls_final_merged['mbfc_reliability_label'] = df_urls_final_merged['mbfc_reliability_label'].fillna('')
    df_urls_final_merged['sjr_quartile'] = df_urls_final_merged['sjr_quartile'].fillna('')
    df_urls_final_merged['extracted_byline'] = df_urls_final_merged['extracted_byline'].fillna('')
    df_urls_final_merged['title'] = df_urls_final_merged['title'].fillna('')

    # 2. Enrich SJR Quartile mapping based on domain
    df_urls_final_merged['sjr_quartile'] = df_urls_final_merged['domain'].map(SJR_DOMAIN_MAP).fillna(df_urls_final_merged['sjr_quartile'])
    df_urls_final_merged['sjr_quartile'] = df_urls_final_merged['sjr_quartile'].fillna('')

    # Reorder columns as requested
    url_cols = [
        'url', 'domain', 'distinct_authors', 'mention_count',
        'credentials_taxonomy_tier', 'link_source_tier', 'mbfc_reliability_label', 'sjr_quartile',
        'extracted_byline', 'title'
    ]
    df_urls_final_out = df_urls_final_merged[url_cols].copy()

    # Save Top-Cited URLs CSV
    df_urls_final_out.to_csv(OUT_URLS_PATH, index=False)
    print(f"=== Saved Top-Cited URLs CSV to {OUT_URLS_PATH} ===")
    print(f"    Rows: {len(df_urls_final_out):,}, Size: {os.path.getsize(OUT_URLS_PATH)/1024:.2f} KB")

    print("\n=== PIPELINE COMPLETED SUCCESSFULLY ===")

if __name__ == '__main__':
    main()
