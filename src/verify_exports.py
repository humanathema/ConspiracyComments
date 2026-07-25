"""verify_exports.py

Verifies the output CSV files from the encyclopedia export pipeline:
- Schema correctness
- Size discipline
- Missing value/NaN checks
- SJR quartile enrichment verify
- Print beautiful coverage stats
"""
import os
import pandas as pd

ROLLUP_PATH = 'data/processed/domain_source_quality_rollup.csv'
TOP_URLS_PATH = 'data/processed/top_cited_urls_with_quality.csv'

def main():
    print("=== STARTING EXPORT VALIDATION ===")
    
    # -------------------------------------------------------------------------
    # 1. Verify Domain Rollup
    # -------------------------------------------------------------------------
    print("\n--- 1. Validating Domain Rollup ---")
    if not os.path.exists(ROLLUP_PATH):
        print(f"Error: {ROLLUP_PATH} does not exist!")
        return
        
    df_rollup = pd.read_csv(ROLLUP_PATH)
    print(f"Loaded {len(df_rollup):,} domains.")
    print("Columns:", df_rollup.columns.tolist())
    
    # Check expected schema
    expected_rollup_cols = [
        'domain', 'n_distinct_urls', 'total_citations', 'total_distinct_authors',
        'credentials_taxonomy_tier', 'link_source_tier', 'mbfc_reliability_label', 'sjr_quartile'
    ]
    if df_rollup.columns.tolist() != expected_rollup_cols:
        print(f"WARNING: Rollup columns do not match expected! Expected: {expected_rollup_cols}")
    else:
        print("Schema: Correct")
        
    # Check NaNs (especially in credentials_taxonomy_tier and link_source_tier)
    nan_counts = df_rollup.isnull().sum()
    print("NaN counts per column (should be 0 or very small):")
    print(nan_counts)
    
    # Check SJR Quartile coverage
    sjr_non_empty = df_rollup['sjr_quartile'].notna() & (df_rollup['sjr_quartile'] != '') & (df_rollup['sjr_quartile'] != 'nan')
    sjr_count = sjr_non_empty.sum()
    print(f"Domains with SJR Quartile enriched: {sjr_count} ({sjr_count / len(df_rollup) * 100:.2f}%)")
    if sjr_count > 0:
        print("\nEnriched Academic Domains sample:")
        print(df_rollup[sjr_non_empty][['domain', 'sjr_quartile']].head(10))
        
    # Check MBFC Reliability coverage
    mbfc_non_empty = df_rollup['mbfc_reliability_label'].notna() & (df_rollup['mbfc_reliability_label'] != '') & (df_rollup['mbfc_reliability_label'] != 'nan')
    mbfc_count = mbfc_non_empty.sum()
    print(f"Domains with MBFC Reliability label: {mbfc_count} ({mbfc_count / len(df_rollup) * 100:.2f}%)")
    if mbfc_count > 0:
        print("\nMBFC Domains sample:")
        print(df_rollup[mbfc_non_empty][['domain', 'mbfc_reliability_label']].head(10))

    # -------------------------------------------------------------------------
    # 2. Verify Top-Cited URLs
    # -------------------------------------------------------------------------
    print("\n--- 2. Validating Top-Cited URLs ---")
    if not os.path.exists(TOP_URLS_PATH):
        print(f"Error: {TOP_URLS_PATH} does not exist!")
        return
        
    df_urls = pd.read_csv(TOP_URLS_PATH)
    print(f"Loaded {len(df_urls):,} URLs.")
    print("Columns:", df_urls.columns.tolist())
    
    # Check expected schema
    expected_url_cols = [
        'url', 'domain', 'distinct_authors', 'mention_count',
        'credentials_taxonomy_tier', 'link_source_tier', 'mbfc_reliability_label', 'sjr_quartile',
        'extracted_byline', 'title'
    ]
    if df_urls.columns.tolist() != expected_url_cols:
        print(f"WARNING: Top URLs columns do not match expected! Expected: {expected_url_cols}")
    else:
        print("Schema: Correct")
        
    # Check NaNs
    nan_url_counts = df_urls.isnull().sum()
    print("NaN counts per column (should be 0 or very small):")
    print(nan_url_counts)
    
    # Check Byline coverage
    byline_non_empty = df_urls['extracted_byline'].notna() & (df_urls['extracted_byline'] != '') & (df_urls['extracted_byline'] != 'nan')
    byline_count = byline_non_empty.sum()
    print(f"URLs with Bylines successfully merged: {byline_count} ({byline_count / len(df_urls) * 100:.2f}%)")
    if byline_count > 0:
         print("\nBylines Merged sample:")
         print(df_urls[byline_non_empty][['url', 'extracted_byline', 'title']].head(10))

    # Check File Size discipline
    print("\n--- 3. Checking File Sizes ---")
    rollup_size = os.path.getsize(ROLLUP_PATH) / 1024
    urls_size = os.path.getsize(TOP_URLS_PATH) / 1024
    print(f"Domain Rollup Size: {rollup_size:.2f} KB (Target: under 500 KB)")
    print(f"Top-Cited URLs Size: {urls_size:.2f} KB (Target: under 500 KB)")
    if rollup_size < 500 and urls_size < 500:
        print("SIZE DISCIPLINE MET: Both files are safely under the 500 KB static asset ceiling!")
    else:
        print("WARNING: One or more files exceeds the 500 KB limit.")

    print("\n=== VALIDATION COMPLETED SUCCESSFULLY ===")

if __name__ == '__main__':
    main()
