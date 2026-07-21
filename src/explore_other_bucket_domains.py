"""explore_other_bucket_domains.py

Descriptive-only pass over the "other" citation bucket from
integrate_credentials_problem.py's cross-tab (95.71% of all 4,568,747
citations land here, since the underlying taxonomy in
cited_content_curation_step2.md only hand-reviewed 139 specific URLs --
everything else defaults to `other`, which is NOT the same claim as
"confirmed neutral/mainstream", see that report's caveat).

Nash's request (2026-07-22): don't impose the existing 4-tier taxonomy on
this bucket or guess at categories -- just surface what's actually in
there (frequent domains/subdomains, volume patterns) via DuckDB
aggregation directly over the already-materialized
credentials_integration_results.csv, so a human (or Antigravity) can
decide what's worth curating next, the same way the original ~50-ish
(actually 139, see note below) URL list was built.

Despam convention matches rank_cited_urls_by_author.py: rank by DISTINCT
AUTHOR count, not raw citation count, since raw counts can be dominated
by one prolific poster reposting the same link.

Also cross-checks against cited_content_curation_step2.md's already-
curated domain list, since a domain can be PARTIALLY curated (a few
specific pages reviewed) while still contributing large uncategorized
volume from OTHER pages on the same domain that never got reviewed.

Output: prints top domains by distinct-author count and by raw citation
count; saves data/processed/other_bucket_domain_frequencies.csv (full
domain-level table, not just the printed top N) for further inspection.
"""
import os
import re
import duckdb
import pandas as pd

RESULTS_PATH = 'data/processed/credentials_integration_results.csv'
CURATION_PATH = 'handoff/cited_content_curation_step2.md'
OUT_PATH = 'data/processed/other_bucket_domain_frequencies.csv'


def load_curated_domains():
    """Extracts the root domain/subdomain token from each already-curated
    row in cited_content_curation_step2.md's markdown table (first
    whitespace- or slash-delimited token), so we can flag which of the
    high-volume 'other' domains are already partially reviewed vs
    completely untouched."""
    with open(CURATION_PATH) as f:
        lines = f.readlines()
    domains = set()
    for line in lines:
        if not line.startswith('|') or line.startswith('|---') or line.strip().startswith('| url'):
            continue
        cell = line.split('|')[1].strip()
        if not cell:
            continue
        token = re.split(r'[\s/]', cell, maxsplit=1)[0]
        token = token.lower().lstrip('www.')
        if token:
            domains.add(token)
    return domains


def main():
    curated_domains = load_curated_domains()
    print(f"Curated domain tokens parsed from {CURATION_PATH}: {len(curated_domains)}")

    con = duckdb.connect()
    print("\nAggregating domains within category='other' via DuckDB (streaming, no full load into pandas)...")
    query = f"""
        WITH other_citations AS (
            SELECT
                url,
                author,
                comment_id,
                lower(regexp_replace(regexp_extract(url, '^https?://([^/]+)', 1), '^www\\.', '')) AS domain
            FROM read_csv_auto('{RESULTS_PATH}')
            WHERE category = 'other'
        )
        SELECT
            domain,
            count(*) AS citation_count,
            count(DISTINCT url) AS distinct_urls,
            count(DISTINCT author) AS distinct_authors,
            count(DISTINCT comment_id) AS distinct_comments
        FROM other_citations
        WHERE domain IS NOT NULL AND domain != ''
        GROUP BY domain
        ORDER BY distinct_authors DESC
    """
    domain_df = con.execute(query).df()
    domain_df['already_curated'] = domain_df['domain'].isin(curated_domains)
    domain_df['mentions_per_author'] = domain_df['citation_count'] / domain_df['distinct_authors']
    domain_df.to_csv(OUT_PATH, index=False)
    print(f"Saved full domain-level table ({len(domain_df):,} distinct domains) to {OUT_PATH}")

    print(f"\nTotal distinct domains in 'other' bucket: {len(domain_df):,}")
    print(f"Domains already touched (at least one page reviewed) by the curated taxonomy: "
          f"{domain_df['already_curated'].sum()} / {len(domain_df):,}")
    print(f"  (of which, citations from those PARTIALLY-curated domains still falling into 'other': "
          f"{domain_df.loc[domain_df['already_curated'], 'citation_count'].sum():,})")

    print("\n=== Top 40 domains by DISTINCT AUTHOR count (despam-by-construction) ===")
    top_by_author = domain_df.sort_values('distinct_authors', ascending=False).head(40)
    print(top_by_author[['domain', 'distinct_authors', 'citation_count', 'distinct_urls', 'already_curated']].to_string(index=False))

    print("\n=== Top 40 domains by RAW CITATION count (for comparison -- may surface spam-driven domains) ===")
    top_by_citation = domain_df.sort_values('citation_count', ascending=False).head(40)
    print(top_by_citation[['domain', 'citation_count', 'distinct_authors', 'distinct_urls', 'already_curated']].to_string(index=False))

    print("\n=== High distinct_urls, low mentions_per_author (many DIFFERENT pages each cited once-ish -- "
          "possible platform/hosting domain rather than a specific recurring source) ===")
    diverse = domain_df[domain_df['distinct_urls'] >= 50].sort_values('distinct_urls', ascending=False).head(20)
    print(diverse[['domain', 'distinct_urls', 'citation_count', 'distinct_authors', 'mentions_per_author']].to_string(index=False))

    print("\n=== Already-curated domains with substantial STILL-uncategorized volume "
          "(specific curated pages exist, but the domain has much more beyond those) ===")
    partial = domain_df[domain_df['already_curated'] & (domain_df['distinct_authors'] >= 20)].sort_values('distinct_authors', ascending=False)
    print(partial[['domain', 'distinct_authors', 'citation_count', 'distinct_urls']].to_string(index=False))


if __name__ == "__main__":
    main()
