"""
build_domain_source_encyclopedia_export.py

Aggregates and exports domain-level and URL-level source-quality datasets from 
the full r/conspiracy corpus. Generates:
1. data/processed/domain_source_quality_rollup.csv (filtered for total_citations >= 20)
2. data/processed/top_cited_urls_with_quality.csv (top 300 URLs by distinct_authors)

Writes output files atomically using concurrency_utils.py to ensure zero multi-session collisions.
"""
import os
import sys
import duckdb
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from utils.concurrency_utils import atomic_write_dataframe

CITED_URLS_PATH = "data/processed/cited_urls_ranked.csv"
CITATIONS_CACHE_PATH = "data/processed/citations_cache.parquet"
BYLINES_PATH = "data/processed/byline_extraction_results.csv"

def build_domain_rollup(con):
    print("Building Domain-Level Source Quality Rollup...")
    
    # 1. We map each URL to its domain, using a fallback regex if the URL is not in citations_cache
    # 2. Group by domain and sum distinct authors and citations
    # 3. Join with domain-level metadata (taxonomy tiers, MBFC label, SJR quartile)
    query = f"""
        WITH url_to_domain AS (
            SELECT 
                u.url,
                COALESCE(c.domain, lower(regexp_replace(regexp_extract(u.url, 'https?://([^/]+)', 1), '^www\\.', ''))) as domain,
                u.distinct_authors,
                u.mention_count
            FROM read_csv_auto('{CITED_URLS_PATH}') u
            LEFT JOIN (
                SELECT url, any_value(domain) as domain
                FROM read_parquet('{CITATIONS_CACHE_PATH}')
                GROUP BY url
            ) c ON u.url = c.url
        ),
        domain_stats AS (
            SELECT 
                domain,
                count(DISTINCT url) as n_distinct_urls,
                CAST(sum(mention_count) AS BIGINT) as total_citations,
                CAST(sum(distinct_authors) AS BIGINT) as total_distinct_authors
            FROM url_to_domain
            GROUP BY domain
        ),
        domain_metadata AS (
            SELECT 
                domain,
                any_value(credentials_taxonomy_tier) as credentials_taxonomy_tier,
                any_value(link_source_tier) as link_source_tier,
                any_value(mbfc_reliability_label) as mbfc_reliability_label,
                any_value(sjr_quartile) as sjr_quartile
            FROM read_parquet('{CITATIONS_CACHE_PATH}')
            GROUP BY domain
        )
        SELECT 
            s.domain,
            s.n_distinct_urls,
            s.total_citations,
            s.total_distinct_authors,
            m.credentials_taxonomy_tier,
            m.link_source_tier,
            m.mbfc_reliability_label,
            m.sjr_quartile
        FROM domain_stats s
        LEFT JOIN domain_metadata m ON s.domain = m.domain
        WHERE s.total_citations >= 20
        ORDER BY s.total_citations DESC
    """
    
    df = con.execute(query).df()
    print(f"  Successfully aggregated {len(df)} domains with total citations >= 20.")
    return df

def build_top_urls(con):
    print("Building Top-Cited URLs with Quality + Byline...")
    
    # 1. Take the top 300 URLs by distinct_authors
    # 2. Join with URL-level metadata from citations_cache
    # 3. Join with extracted bylines and titles
    query = f"""
        WITH top_urls AS (
            SELECT 
                url,
                distinct_authors,
                mention_count
            FROM read_csv_auto('{CITED_URLS_PATH}')
            ORDER BY distinct_authors DESC
            LIMIT 300
        ),
        url_metadata AS (
            SELECT 
                url,
                any_value(domain) as domain,
                any_value(credentials_taxonomy_tier) as credentials_taxonomy_tier,
                any_value(link_source_tier) as link_source_tier,
                any_value(mbfc_reliability_label) as mbfc_reliability_label,
                any_value(sjr_quartile) as sjr_quartile
            FROM read_parquet('{CITATIONS_CACHE_PATH}')
            GROUP BY url
        ),
        bylines AS (
            SELECT 
                url,
                any_value(extracted_byline) as extracted_byline,
                any_value(title) as title
            FROM read_csv_auto('{BYLINES_PATH}')
            GROUP BY url
        )
        SELECT 
            t.url,
            COALESCE(m.domain, lower(regexp_replace(regexp_extract(t.url, 'https?://([^/]+)', 1), '^www\\.', ''))) as domain,
            t.distinct_authors,
            t.mention_count,
            m.credentials_taxonomy_tier,
            m.link_source_tier,
            m.mbfc_reliability_label,
            m.sjr_quartile,
            b.extracted_byline,
            b.title
        FROM top_urls t
        LEFT JOIN url_metadata m ON t.url = m.url
        LEFT JOIN bylines b ON t.url = b.url
    """
    
    df = con.execute(query).df()
    print(f"  Successfully built {len(df)} top-cited URLs.")
    return df

def main():
    # Initialize DuckDB connection
    con = duckdb.connect()
    
    # Ensure processed directory exists
    os.makedirs("data/processed", exist_ok=True)
    
    # Run the pipelines
    domain_df = build_domain_rollup(con)
    top_urls_df = build_top_urls(con)
    
    # Atomic writes to prevent multi-session race conditions
    domain_output = "data/processed/domain_source_quality_rollup.csv"
    urls_output = "data/processed/top_cited_urls_with_quality.csv"
    
    print(f"\nWriting output files atomically...")
    atomic_write_dataframe(domain_df, domain_output, index=False)
    print(f"  Wrote {domain_output}")
    
    atomic_write_dataframe(top_urls_df, urls_output, index=False)
    print(f"  Wrote {urls_output}")
    
    print("\nAll exports completed successfully!")

if __name__ == '__main__':
    main()
