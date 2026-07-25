"""export_domain_source_quality_encyclopedia.py

Export script to build and save:
  1. data/processed/domain_source_quality_rollup.csv
  2. data/processed/top_cited_urls_with_quality.csv

These outputs serve as the "encyclopedia of source quality" for the corpus explorer.
Processes the large citation cache and ranked URLs safely using DuckDB.
"""
import os
import sys
import duckdb

# Determine repo root directory relative to this script
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Define input paths
RANKED_PATH = os.path.join(REPO_ROOT, 'data/processed/cited_urls_ranked.csv')
CACHE_PATH = os.path.join(REPO_ROOT, 'data/processed/citations_cache.parquet')
BYLINE_PATH = os.path.join(REPO_ROOT, 'data/processed/byline_extraction_results.csv')

# Define output paths
DOMAIN_OUT = os.path.join(REPO_ROOT, 'data/processed/domain_source_quality_rollup.csv')
URL_OUT = os.path.join(REPO_ROOT, 'data/processed/top_cited_urls_with_quality.csv')


def export_domain_rollup(con, min_citations=20):
    """Build and export domain-level source quality rollup."""
    print(f"\nBuilding domain rollup with total_citations >= {min_citations}...")
    
    query = f"""
        WITH url_domains AS (
            SELECT 
                url,
                lower(regexp_extract(url, '^https?://(?:www\\.)?([a-zA-Z0-9.-]+\\.[a-zA-Z]{{2,4}})', 1)) as domain,
                mention_count,
                distinct_authors
            FROM '{RANKED_PATH}'
        ),
        domain_sums AS (
            SELECT 
                domain,
                count(*) as n_distinct_urls,
                sum(mention_count) as total_citations,
                sum(distinct_authors) as total_distinct_authors
            FROM url_domains
            WHERE domain IS NOT NULL AND domain != ''
            GROUP BY domain
            HAVING total_citations >= {min_citations}
        ),
        domain_attrs AS (
            SELECT 
                domain,
                mode(credentials_taxonomy_tier) as credentials_taxonomy_tier,
                mode(link_source_tier) as link_source_tier,
                mode(mbfc_reliability_label) as mbfc_reliability_label,
                mode(sjr_quartile) as sjr_quartile
            FROM '{CACHE_PATH}'
            GROUP BY domain
        )
        SELECT 
            ds.domain,
            ds.n_distinct_urls,
            ds.total_citations,
            ds.total_distinct_authors,
            coalesce(da.credentials_taxonomy_tier, 'other') as credentials_taxonomy_tier,
            coalesce(da.link_source_tier, 'unmatched_link') as link_source_tier,
            da.mbfc_reliability_label,
            da.sjr_quartile
        FROM domain_sums ds
        LEFT JOIN domain_attrs da ON ds.domain = da.domain
        ORDER BY ds.total_citations DESC
    """
    
    df = con.execute(query).df()
    
    # Save output
    df.to_csv(DOMAIN_OUT, index=False)
    
    # Show stats
    file_size_kb = os.path.getsize(DOMAIN_OUT) / 1024.0
    print(f"  Successfully exported {len(df):,} domains.")
    print(f"  Saved to: {DOMAIN_OUT}")
    print(f"  File size: {file_size_kb:.2f} KB")
    return len(df), file_size_kb


def export_top_urls(con, limit_urls=300):
    """Build and export individual top cited URLs with quality and bylines."""
    print(f"\nBuilding top {limit_urls} cited URLs...")
    
    query = f"""
        WITH top_ranked AS (
            SELECT url, distinct_authors, mention_count
            FROM '{RANKED_PATH}'
            ORDER BY distinct_authors DESC
            LIMIT {limit_urls}
        ),
        distinct_cache AS (
            SELECT 
                url,
                domain,
                mode(credentials_taxonomy_tier) as credentials_taxonomy_tier,
                mode(link_source_tier) as link_source_tier,
                mode(mbfc_reliability_label) as mbfc_reliability_label,
                mode(sjr_quartile) as sjr_quartile
            FROM '{CACHE_PATH}'
            GROUP BY url, domain
        ),
        bylines AS (
            SELECT url, extracted_byline, title
            FROM '{BYLINE_PATH}'
        )
        SELECT 
            tr.url,
            coalesce(dc.domain, lower(regexp_extract(tr.url, '^https?://(?:www\\.)?([a-zA-Z0-9.-]+\\.[a-zA-Z]{{2,4}})', 1))) as domain,
            tr.distinct_authors,
            tr.mention_count,
            coalesce(dc.credentials_taxonomy_tier, 'other') as credentials_taxonomy_tier,
            coalesce(dc.link_source_tier, 'unmatched_link') as link_source_tier,
            dc.mbfc_reliability_label,
            dc.sjr_quartile,
            b.extracted_byline,
            b.title
        FROM top_ranked tr
        LEFT JOIN distinct_cache dc ON tr.url = dc.url
        LEFT JOIN bylines b ON tr.url = b.url
    """
    
    df = con.execute(query).df()
    
    # Save output
    df.to_csv(URL_OUT, index=False)
    
    # Show stats
    file_size_kb = os.path.getsize(URL_OUT) / 1024.0
    print(f"  Successfully exported {len(df):,} URLs.")
    print(f"  Saved to: {URL_OUT}")
    print(f"  File size: {file_size_kb:.2f} KB")
    
    # Count available bylines/titles
    n_bylines = df['extracted_byline'].notna().sum()
    n_titles = df['title'].notna().sum()
    print(f"  Bylines populated: {n_bylines} / {len(df)}")
    print(f"  Titles populated: {n_titles} / {len(df)}")
    
    return len(df), file_size_kb


def main():
    print("=== EXPORTING SOURCE QUALITY DATA FOR CORPUS EXPLORER ===")
    
    # Ensure inputs exist
    for path in [RANKED_PATH, CACHE_PATH, BYLINE_PATH]:
        if not os.path.exists(path):
            print(f"Error: Required input missing at {path}")
            sys.exit(1)
            
    con = duckdb.connect()
    
    # Configure connection resource limits to prevent OOM
    con.execute("SET memory_limit='3GB'; SET threads=3;")
    
    # Export domain rollup
    export_domain_rollup(con, min_citations=20)
    
    # Export top URLs
    export_top_urls(con, limit_urls=300)
    
    print("\nAll exports completed successfully!")


if __name__ == '__main__':
    main()
