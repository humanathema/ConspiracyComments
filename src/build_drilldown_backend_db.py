# src/build_drilldown_backend_db.py
"""build_drilldown_backend_db.py

Builds the SQLite index behind the corpus explorer's live drill-down API
(src/serve_drilldown_api.py). Unlike the static-artifact examples this
replaces, this is not size-constrained by embedding -- full comment text,
no truncation, generous per-key caps (not "top 300 domains only").

Output: data/processed/drilldown.sqlite

Tables:
  topic_examples(comment_id, topic_name, upvotes, char_length, date, text) -- up to 300/topic, all topics
  entity_examples(comment_id, entity_key, construct, predicted_label,      -- up to 300/entity, all real entities
                   p_hostile, p_endorsement, upvotes, text)
  domain_examples(comment_id, domain, predicted_label, p_hostile,          -- up to 100/domain, all domains >=20 citations
                   p_endorsement, upvotes, text)
  url_examples(comment_id, url, predicted_label, p_hostile,                -- up to 100/url, top 2000 URLs by distinct authors
               p_endorsement, upvotes, text)
  comment_context(comment_id, post_id, thread_title, thread_domain,         -- precomputed thread context + parent texts
                  thread_score, parent_id, parent_comment_id, parent_text)
  entity_monthly(entity_key, construct, month, mentions,       -- monthly series for all real entities
                  n_hostile, n_endorsement, n_other)
  domain_monthly(domain, month, mentions,                      -- monthly series for all covered domains
                  n_hostile, n_endorsement, n_other)
  url_monthly(url, month, mentions,                            -- monthly series for all top-2000 URLs
              n_hostile, n_endorsement, n_other)

Run locally (needs the full parquets); scp the resulting .sqlite to the
backend VM afterward -- this script does not touch the VM.
"""
import os
import duckdb

TOPIC_CORPUS = 'data/processed/empath_scores_full_mapped.parquet'
ENTITY_CACHE_LONG = 'data/processed/entity_mentions_cache_2stage_pooled.parquet'
ENTITY_CACHE_SHORT = 'data/processed/entity_mentions_cache_short.parquet'
ENTITY_CACHE_EXTENDED = 'data/processed/entity_mentions_cache_extended.parquet'
SHORT_CORPUS = 'data/processed/conspiracy_comments_short_lte100chars_mapped.parquet'
SOURCE_CACHE = 'data/processed/source_mentions_cache.parquet'
THREAD_SYNTHESIS = 'data/processed/master_thread_synthesis.parquet'

OUT_PATH = 'data/processed/drilldown.sqlite'
PER_TOPIC = 300
PER_ENTITY = 300
PER_DOMAIN = 100
PER_URL = 100

if os.path.exists(OUT_PATH):
    os.remove(OUT_PATH)

con = duckdb.connect()
con.execute("PRAGMA memory_limit='5GB'")
con.execute("INSTALL sqlite")
con.execute("LOAD sqlite")
con.execute(f"ATTACH '{OUT_PATH}' AS sq (TYPE sqlite)")

print("=== topic_examples (Outliers included -- it's a real, inspectable bucket) ===")
con.execute(f"""
CREATE TABLE sq.topic_examples AS
WITH ranked AS (
  SELECT id AS comment_id, topic_name, upvotes, char_length,
    strftime(to_timestamp(created_utc), '%Y-%m-%d') AS date,
    regexp_replace(text, '[\\r\\n\\t]+', ' ', 'g') AS text,
    ROW_NUMBER() OVER (PARTITION BY topic_name ORDER BY upvotes DESC) AS rn
  FROM '{TOPIC_CORPUS}'
  WHERE topic_name IS NOT NULL AND char_length >= 20
)
SELECT comment_id, topic_name, upvotes, char_length, date, text FROM ranked WHERE rn <= {PER_TOPIC}
""")
n = con.execute("SELECT COUNT(*) FROM sq.topic_examples").fetchone()[0]
print(f"  {n:,} rows")

print("=== topic_fit_ratings (empty, populated live via the API) ===")
con.execute("""
CREATE TABLE sq.topic_fit_ratings (
  comment_id VARCHAR, topic_name VARCHAR, rating VARCHAR, note VARCHAR, rater VARCHAR, rated_at VARCHAR,
  UNIQUE(comment_id, topic_name, rater)
)
""")

print("=== entity_examples ===")
con.execute(f"""
CREATE TABLE sq.entity_examples AS
WITH real_entities AS (
  SELECT * FROM '{ENTITY_CACHE_LONG}' WHERE entity_key NOT LIKE 'merged_%'
  UNION ALL
  SELECT comment_id, entity_key, construct, p_hostile, p_endorsement, p_other, predicted_label, is_list_dump
  FROM '{ENTITY_CACHE_SHORT}' WHERE entity_key NOT LIKE 'merged_%'
  UNION ALL
  SELECT comment_id, entity_key, construct, p_hostile, p_endorsement, p_other, predicted_label, is_list_dump
  FROM '{ENTITY_CACHE_EXTENDED}'
),
joined AS (
  SELECT
    e.comment_id, e.entity_key, e.construct, e.predicted_label, e.p_hostile, e.p_endorsement,
    c.upvotes, regexp_replace(c.text, '[\\r\\n\\t]+', ' ', 'g') AS text,
    ROW_NUMBER() OVER (PARTITION BY e.entity_key ORDER BY c.upvotes DESC) AS rn
  FROM real_entities e
  JOIN (
    SELECT id, upvotes, text FROM '{TOPIC_CORPUS}'
    UNION ALL
    SELECT id, upvotes, text FROM '{SHORT_CORPUS}'
  ) c ON c.id = e.comment_id
  WHERE e.is_list_dump = 0
)
SELECT comment_id, entity_key, construct, predicted_label, p_hostile, p_endorsement, upvotes, text
FROM joined WHERE rn <= {PER_ENTITY}
""")

# Load unreviewed_entity_examples.csv into entity_examples if it exists
unreviewed_path = 'data/processed/unreviewed_entity_examples.csv'
if os.path.exists(unreviewed_path):
    print("=== Loading unreviewed_entity_examples ===")
    con.execute(f"""
    INSERT INTO sq.entity_examples (comment_id, entity_key, construct, predicted_label, p_hostile, p_endorsement, upvotes, text)
    SELECT comment_id, entity_key, 'unreviewed' AS construct, 'unreviewed' AS predicted_label, 0.0 AS p_hostile, 0.0 AS p_endorsement, upvotes, text
    FROM read_csv_auto('{unreviewed_path}')
    """)
else:
    print("⚠️ unreviewed_entity_examples.csv not found, skipping for now...")

n = con.execute("SELECT COUNT(*) FROM sq.entity_examples").fetchone()[0]
print(f"  entity_examples total: {n:,} rows")

print("=== domain_examples ===")
con.execute(f"""
CREATE TABLE sq.domain_examples AS
WITH ranked AS (
  SELECT s.comment_id, s.source_key AS domain, s.predicted_label, s.p_hostile, s.p_endorsement,
    c.upvotes, regexp_replace(c.text, '[\\r\\n\\t]+', ' ', 'g') AS text,
    ROW_NUMBER() OVER (PARTITION BY s.source_key ORDER BY c.upvotes DESC) AS rn
  FROM '{SOURCE_CACHE}' s
  JOIN '{TOPIC_CORPUS}' c ON c.id = s.comment_id
  WHERE s.level = 'domain' AND s.is_list_dump = 0
)
SELECT comment_id, domain, predicted_label, p_hostile, p_endorsement, upvotes, text FROM ranked WHERE rn <= {PER_DOMAIN}
""")
n = con.execute("SELECT COUNT(*) FROM sq.domain_examples").fetchone()[0]
print(f"  {n:,} rows")

print("=== url_examples ===")
con.execute(f"""
CREATE TABLE sq.url_examples AS
WITH ranked AS (
  SELECT s.comment_id, s.source_key AS url, s.predicted_label, s.p_hostile, s.p_endorsement,
    c.upvotes, regexp_replace(c.text, '[\\r\\n\\t]+', ' ', 'g') AS text,
    ROW_NUMBER() OVER (PARTITION BY s.source_key ORDER BY c.upvotes DESC) AS rn
  FROM '{SOURCE_CACHE}' s
  JOIN '{TOPIC_CORPUS}' c ON c.id = s.comment_id
  WHERE s.level = 'url' AND s.is_list_dump = 0
)
SELECT comment_id, url, predicted_label, p_hostile, p_endorsement, upvotes, text FROM ranked WHERE rn <= {PER_URL}
""")
n = con.execute("SELECT COUNT(*) FROM sq.url_examples").fetchone()[0]
print(f"  {n:,} rows")


print("=== comment_context (Precomputing parent texts and thread titles) ===")
# Generate comment_context table
con.execute(f"""
CREATE TABLE sq.comment_context AS
WITH all_comment_ids AS (
  SELECT comment_id FROM sq.topic_examples WHERE comment_id IS NOT NULL
  UNION
  SELECT comment_id FROM sq.entity_examples WHERE comment_id IS NOT NULL
  UNION
  SELECT comment_id FROM sq.domain_examples WHERE comment_id IS NOT NULL
  UNION
  SELECT comment_id FROM sq.url_examples WHERE comment_id IS NOT NULL
),
comment_metadata AS (
  SELECT c.id AS comment_id, c.link_id, c.parent_id
  FROM (
    SELECT id, link_id, parent_id FROM '{TOPIC_CORPUS}'
    UNION ALL
    SELECT id, link_id, parent_id FROM '{SHORT_CORPUS}'
  ) c
  WHERE c.id IN (SELECT comment_id FROM all_comment_ids)
),
parent_ids AS (
  SELECT DISTINCT regexp_replace(parent_id, '^t1_', '') AS parent_comment_id
  FROM comment_metadata
  WHERE parent_id LIKE 't1_%'
),
parent_texts AS (
  SELECT c.id AS parent_comment_id, regexp_replace(c.text, '[\\r\\n\\t]+', ' ', 'g') AS parent_text
  FROM (
    SELECT id, text FROM '{TOPIC_CORPUS}'
    UNION ALL
    SELECT id, text FROM '{SHORT_CORPUS}'
  ) c
  WHERE c.id IN (SELECT parent_comment_id FROM parent_ids)
),
joined_threads AS (
  SELECT
    m.comment_id,
    regexp_replace(m.link_id, '^t3_', '') AS post_id,
    t.title AS thread_title,
    t.domain AS thread_domain,
    t.post_score AS thread_score,
    m.parent_id,
    CASE 
      WHEN m.parent_id LIKE 't1_%' THEN regexp_replace(m.parent_id, '^t1_', '')
      ELSE NULL
    END AS parent_comment_id,
    p.parent_text
  FROM comment_metadata m
  LEFT JOIN '{THREAD_SYNTHESIS}' t ON t.post_id = regexp_replace(m.link_id, '^t3_', '')
  LEFT JOIN parent_texts p ON p.parent_comment_id = CASE WHEN m.parent_id LIKE 't1_%' THEN regexp_replace(m.parent_id, '^t1_', '') ELSE NULL END
)
SELECT * FROM joined_threads;
""")
n = con.execute("SELECT COUNT(*) FROM sq.comment_context").fetchone()[0]
print(f"  comment_context: {n:,} rows")


print("=== entity_monthly (all real entities) ===")
# Load unreviewed entities to compute their true monthly timeline
import csv, re
with open('data/processed/missing_entity_candidates.csv', encoding='utf-8') as f:
    unreviewed_entities = [row['entity'].strip() for row in csv.DictReader(f) if row['entity'].strip()]

# Sort descending by length to match longer names first in regex
unreviewed_entities.sort(key=len, reverse=True)
escaped_entities = [re.escape(e) for e in unreviewed_entities]
regex_pattern = r'\b(' + '|'.join(escaped_entities) + r')\b'

# Create a temporary table of true monthly counts for these unreviewed entities (in-memory DuckDB!)
con.execute(f"""
CREATE TABLE unreviewed_raw_monthly AS
WITH extracted AS (
  SELECT 
    regexp_extract(text, ?, 1, 'i') AS matched,
    strftime(to_timestamp(created_utc), '%Y-%m') AS month
  FROM '{TOPIC_CORPUS}'
  UNION ALL
  SELECT 
    regexp_extract(text, ?, 1, 'i') AS matched,
    strftime(to_timestamp(created_utc), '%Y-%m') AS month
  FROM '{SHORT_CORPUS}'
)
SELECT 
  lower(matched) AS entity_key,
  month,
  COUNT(*) AS mentions
FROM extracted
WHERE matched != '' AND (lower(matched) != 'who' OR matched = 'WHO')
GROUP BY 1, 2
""", [regex_pattern, regex_pattern])

con.execute(f"""
CREATE TABLE sq.entity_monthly AS
WITH real_entities AS (
  SELECT comment_id, entity_key, construct, predicted_label FROM '{ENTITY_CACHE_LONG}' WHERE entity_key NOT LIKE 'merged_%'
  UNION ALL
  SELECT comment_id, entity_key, construct, predicted_label FROM '{ENTITY_CACHE_EXTENDED}'
  UNION ALL
  SELECT comment_id, entity_key, construct, predicted_label FROM '{ENTITY_CACHE_SHORT}'
),
pre_monthly AS (
  SELECT
    e.entity_key, e.construct,
    strftime(to_timestamp(c.created_utc), '%Y-%m') AS month,
    COUNT(*) AS mentions,
    SUM(CASE WHEN e.predicted_label = 'hostile' THEN 1 ELSE 0 END) AS n_hostile,
    SUM(CASE WHEN e.predicted_label = 'endorsement' THEN 1 ELSE 0 END) AS n_endorsement,
    SUM(CASE WHEN e.predicted_label = 'other' THEN 1 ELSE 0 END) AS n_other
  FROM real_entities e
  JOIN (
    SELECT id, created_utc FROM '{TOPIC_CORPUS}'
    UNION ALL
    SELECT id, created_utc FROM '{SHORT_CORPUS}'
  ) c ON c.id = e.comment_id
  GROUP BY 1, 2, 3
)
SELECT entity_key, construct, month, mentions, n_hostile, n_endorsement, n_other FROM pre_monthly
UNION ALL
SELECT entity_key, 'unreviewed' AS construct, month, mentions, 0 AS n_hostile, 0 AS n_endorsement, mentions AS n_other FROM unreviewed_raw_monthly
""")
n = con.execute("SELECT COUNT(*) FROM sq.entity_monthly").fetchone()[0]
print(f"  {n:,} rows")

print("=== domain_monthly / url_monthly ===")
con.execute(f"""
CREATE TABLE sq.domain_monthly AS
SELECT
  s.source_key AS domain,
  strftime(to_timestamp(c.created_utc), '%Y-%m') AS month,
  COUNT(*) AS mentions,
  SUM(CASE WHEN s.predicted_label = 'hostile' THEN 1 ELSE 0 END) AS n_hostile,
  SUM(CASE WHEN s.predicted_label = 'endorsement' THEN 1 ELSE 0 END) AS n_endorsement,
  SUM(CASE WHEN s.predicted_label = 'other' THEN 1 ELSE 0 END) AS n_other
FROM '{SOURCE_CACHE}' s
JOIN '{TOPIC_CORPUS}' c ON c.id = s.comment_id
WHERE s.level = 'domain'
GROUP BY 1, 2
""")
n = con.execute("SELECT COUNT(*) FROM sq.domain_monthly").fetchone()[0]
print(f"  domain_monthly: {n:,} rows")

con.execute(f"""
CREATE TABLE sq.url_monthly AS
SELECT
  s.source_key AS url,
  strftime(to_timestamp(c.created_utc), '%Y-%m') AS month,
  COUNT(*) AS mentions,
  SUM(CASE WHEN s.predicted_label = 'hostile' THEN 1 ELSE 0 END) AS n_hostile,
  SUM(CASE WHEN s.predicted_label = 'endorsement' THEN 1 ELSE 0 END) AS n_endorsement,
  SUM(CASE WHEN s.predicted_label = 'other' THEN 1 ELSE 0 END) AS n_other
FROM '{SOURCE_CACHE}' s
JOIN '{TOPIC_CORPUS}' c ON c.id = s.comment_id
WHERE s.level = 'url'
GROUP BY 1, 2
""")
n = con.execute("SELECT COUNT(*) FROM sq.url_monthly").fetchone()[0]
print(f"  url_monthly: {n:,} rows")

con.close()

print("=== indexes ===")
import sqlite3
sconn = sqlite3.connect(OUT_PATH)
sconn.execute("PRAGMA journal_mode=WAL;")
for stmt in [
    "CREATE INDEX idx_topic_ex ON topic_examples(topic_name)",
    "CREATE INDEX idx_entity_ex ON entity_examples(entity_key)",
    "CREATE INDEX idx_domain_ex ON domain_examples(domain)",
    "CREATE INDEX idx_url_ex ON url_examples(url)",
    "CREATE INDEX idx_entity_monthly ON entity_monthly(entity_key)",
    "CREATE INDEX idx_domain_monthly ON domain_monthly(domain)",
    "CREATE INDEX idx_url_monthly ON url_monthly(url)",
    "CREATE INDEX idx_comment_context ON comment_context(comment_id)",
    "CREATE INDEX idx_topic_ex_comment ON topic_examples(comment_id)",
    "CREATE INDEX idx_entity_ex_comment ON entity_examples(comment_id)",
    "CREATE INDEX idx_domain_ex_comment ON domain_examples(comment_id)",
    "CREATE INDEX idx_url_ex_comment ON url_examples(comment_id)",
]:
    sconn.execute(stmt)
sconn.commit()
sconn.execute("VACUUM")
sconn.close()

size_mb = os.path.getsize(OUT_PATH) / 1e6
print(f"=== Done. {OUT_PATH}: {size_mb:.1f} MB ===")
