"""build_ats_citations_cache.py

Domain/URL extraction for the ATS (AboveTopSecret) corpus. Reuses the same
URL extraction + normalization logic as src/build_citations_cache.py
(extract_urls/normalize_url -- imported directly, not reimplemented) so URLs
are cleaned identically to the r/conspiracy pipeline.

Deliberately does NOT replicate build_citations_cache.py's curated exact-URL
taxonomy system (handoff/cited_content_curation_step2.md) -- that's hand-
curated specifically against r/conspiracy/politics/askreddit citations and
wouldn't transfer meaningfully to ATS without its own curation pass. Instead
this applies only the general, corpus-agnostic domain-level lookup
(data/processed/domain_classification_lookup.csv, 269 domains) where a
domain happens to already be in it -- most ATS-cited domains won't be, and
are left uncategorized rather than guessed at.

Outputs:
  data/processed/ats_citations_cache.parquet  -- one row per (comment_id, url)
  data/processed/ats_cited_domains_ranked.csv -- domain-level rollup, ranked by mentions
"""
import os
import re
import sys
import pandas as pd
import duckdb

sys.path.insert(0, os.path.dirname(__file__))
from build_citations_cache import extract_urls, normalize_url

INPUT_PATH = "data/processed/ats_comments_final.parquet"
DOMAIN_LOOKUP_PATH = "data/processed/domain_classification_lookup.csv"
OUT_PARQUET = "data/processed/ats_citations_cache.parquet"
OUT_DOMAINS_CSV = "data/processed/ats_cited_domains_ranked.csv"


def main():
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='4GB'")

    print("Loading domain classification lookup (general, corpus-agnostic)...")
    domain_lookup = {}
    if os.path.exists(DOMAIN_LOOKUP_PATH):
        df_lookup = pd.read_csv(DOMAIN_LOOKUP_PATH)
        domain_lookup = df_lookup.set_index('domain').to_dict(orient='index')
        print(f"  {len(domain_lookup)} known domains loaded.")
    else:
        print(f"  {DOMAIN_LOOKUP_PATH} not found -- proceeding with no categorization.")

    print("\nStreaming ATS comments containing 'http'...")
    df = con.execute(f"""
        SELECT post_id AS comment_id, body AS text
        FROM read_parquet('{INPUT_PATH}')
        WHERE body LIKE '%http%'
    """).df()
    print(f"  {len(df):,} comments to scan for URLs.")

    print("\nExtracting and normalizing URLs...")
    records = []
    domain_re = re.compile(r'^https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,4})')
    for cid, text in zip(df['comment_id'], df['text']):
        for url in extract_urls(text):
            m = domain_re.match(url)
            if not m:
                continue
            domain = m.group(1).lower()
            records.append({'comment_id': cid, 'url': url, 'domain': domain})

    citations_df = pd.DataFrame(records)
    print(f"  {len(citations_df):,} citation records extracted.")

    print("\nApplying domain-level classification where known...")
    def lookup_row(domain):
        rec = domain_lookup.get(domain)
        if not rec:
            return pd.Series({'category': None, 'mbfc_reliability_label': None, 'is_platform': None})
        return pd.Series({
            'category': rec.get('category'),
            'mbfc_reliability_label': rec.get('mbfc_reliability_label'),
            'is_platform': rec.get('is_platform'),
        })

    unique_domains = citations_df['domain'].drop_duplicates()
    domain_meta = unique_domains.apply(lookup_row)
    domain_meta['domain'] = unique_domains.values
    citations_df = citations_df.merge(domain_meta, on='domain', how='left')

    citations_df.to_parquet(OUT_PARQUET, compression='zstd', index=False)
    print(f"  Saved {OUT_PARQUET}")

    print("\nBuilding ranked domain rollup...")
    domain_ranked = (
        citations_df.groupby('domain')
        .agg(mentions=('comment_id', 'count'), unique_comments=('comment_id', 'nunique'),
             category=('category', 'first'), mbfc_reliability_label=('mbfc_reliability_label', 'first'),
             is_platform=('is_platform', 'first'))
        .sort_values('mentions', ascending=False)
        .reset_index()
    )
    domain_ranked.to_csv(OUT_DOMAINS_CSV, index=False)
    print(f"  Saved {OUT_DOMAINS_CSV} ({len(domain_ranked):,} distinct domains)")

    known_pct = domain_ranked['category'].notna().mean() * 100
    print(f"\n{known_pct:.1f}% of distinct domains matched the existing lookup table "
          f"(rest are ATS-specific/uncategorized, not guessed at).")


if __name__ == "__main__":
    main()
