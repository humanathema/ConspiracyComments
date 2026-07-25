"""build_citation_drilldown_samples.py

Bounded example-comment samples for the corpus explorer's Domains and Top
cited sources tabs, matching the pattern already used for topics/entities
(src/build_explorer_drilldown_samples.py). Truncated + newline-stripped,
same as that script -- this is still the static interim solution, full text
is deferred to the live backend.

Coverage is capped, not universal: domains beyond the top N by citation
count won't have examples yet (the explorer should say so rather than show
nothing silently).

Output:
  data/processed/domain_example_comments.csv
  data/processed/url_example_comments.csv
"""
import duckdb

CORPUS = 'data/processed/empath_scores_full_mapped.parquet'
CITATIONS = 'data/processed/citations_cache.parquet'
DOMAIN_ROLLUP = 'data/processed/domain_source_quality_rollup.csv'
TOP_URLS = 'data/processed/top_cited_urls_with_quality.csv'

DOMAIN_OUT = 'data/processed/domain_example_comments.csv'
URL_OUT = 'data/processed/url_example_comments.csv'

TOP_N_DOMAINS = 300
PER_KEY = 4
SNIPPET_LEN = 180

con = duckdb.connect()
con.execute("PRAGMA memory_limit='4GB'")

print("=== Building domain example comments (top 300 domains by citations) ===")
con.execute(f"""
COPY (
  WITH top_domains AS (
    SELECT domain FROM read_csv_auto('{DOMAIN_ROLLUP}')
    ORDER BY total_citations DESC
    LIMIT {TOP_N_DOMAINS}
  ),
  ranked AS (
    SELECT
      cc.domain,
      c.upvotes,
      regexp_replace(substr(c.text, 1, {SNIPPET_LEN}), '[\\r\\n\\t]+', ' ', 'g') AS snippet,
      ROW_NUMBER() OVER (PARTITION BY cc.domain ORDER BY c.upvotes DESC) AS rn
    FROM '{CITATIONS}' cc
    JOIN top_domains td ON td.domain = cc.domain
    JOIN '{CORPUS}' c ON c.id = cc.comment_id
    WHERE c.char_length >= 40
  )
  SELECT domain, upvotes, snippet FROM ranked WHERE rn <= {PER_KEY}
  ORDER BY domain, upvotes DESC
) TO '{DOMAIN_OUT}' (FORMAT CSV, HEADER)
""")
n = con.execute(f"SELECT COUNT(*) FROM '{DOMAIN_OUT}'").fetchone()[0]
print(f"  Saved {n:,} rows to {DOMAIN_OUT}")

print("=== Building URL example comments (all 300 top-cited URLs) ===")
con.execute(f"""
COPY (
  WITH ranked AS (
    SELECT
      cc.url,
      c.upvotes,
      regexp_replace(substr(c.text, 1, {SNIPPET_LEN}), '[\\r\\n\\t]+', ' ', 'g') AS snippet,
      ROW_NUMBER() OVER (PARTITION BY cc.url ORDER BY c.upvotes DESC) AS rn
    FROM '{CITATIONS}' cc
    JOIN read_csv_auto('{TOP_URLS}') tu ON tu.url = cc.url
    JOIN '{CORPUS}' c ON c.id = cc.comment_id
    WHERE c.char_length >= 40
  )
  SELECT url, upvotes, snippet FROM ranked WHERE rn <= {PER_KEY}
  ORDER BY url, upvotes DESC
) TO '{URL_OUT}' (FORMAT CSV, HEADER)
""")
n = con.execute(f"SELECT COUNT(*) FROM '{URL_OUT}'").fetchone()[0]
print(f"  Saved {n:,} rows to {URL_OUT}")

print("=== Done ===")
