"""build_explorer_drilldown_samples.py

Builds two small, browser-embeddable CSVs of example comments for the corpus
explorer's topic/entity drill-down panes:
1. data/processed/topic_example_comments.csv
2. data/processed/entity_example_comments.csv

Bounded samples only (a handful of rows per topic/entity) -- not a general
corpus query tool. Full comment text, newline-stripped; author is dropped.
"""
import duckdb
import re

TOPIC_CORPUS = 'data/processed/empath_scores_full_mapped.parquet'
ENTITY_CACHE = 'data/processed/entity_mentions_cache_2stage_pooled.parquet'
TOPIC_OUT = 'data/processed/topic_example_comments.csv'
ENTITY_OUT = 'data/processed/entity_example_comments.csv'

PER_TOPIC = 6
PER_ENTITY_PER_LABEL = 2

con = duckdb.connect()
con.execute(f"PRAGMA memory_limit='4GB'")

print("=== Building topic example comments ===")
con.execute(f"""
COPY (
  WITH ranked AS (
    SELECT
      topic_name,
      upvotes,
      char_length,
      regexp_replace(text, '[\\r\\n\\t]+', ' ', 'g') AS snippet,
      ROW_NUMBER() OVER (PARTITION BY topic_name ORDER BY upvotes DESC) AS rn
    FROM '{TOPIC_CORPUS}'
    WHERE topic_name IS NOT NULL AND topic_name != 'Outliers' AND char_length >= 40
  )
  SELECT topic_name, upvotes, char_length, snippet
  FROM ranked
  WHERE rn <= {PER_TOPIC}
  -- top-upvoted only: a convenience sample for "what does this topic look like",
  -- not a representative/random draw of the topic's full distribution
  ORDER BY topic_name, upvotes DESC
) TO '{TOPIC_OUT}' (FORMAT CSV, HEADER)
""")
n = con.execute(f"SELECT COUNT(*) FROM '{TOPIC_OUT}'").fetchone()[0]
print(f"  Saved {n:,} rows to {TOPIC_OUT}")

print("=== Building entity example comments ===")
con.execute(f"""
COPY (
  WITH real_entities AS (
    SELECT * FROM '{ENTITY_CACHE}'
    WHERE entity_key NOT LIKE 'merged_%'
  ),
  joined AS (
    SELECT
      e.entity_key,
      e.construct,
      e.predicted_label,
      e.p_hostile,
      e.p_endorsement,
      c.upvotes,
      regexp_replace(c.text, '[\\r\\n\\t]+', ' ', 'g') AS snippet,
      -- rank by confidence in the predicted label so examples are illustrative,
      -- not just noise near the decision boundary
      GREATEST(e.p_hostile, e.p_endorsement, e.p_other) AS confidence,
      ROW_NUMBER() OVER (
        PARTITION BY e.entity_key, e.predicted_label
        ORDER BY GREATEST(e.p_hostile, e.p_endorsement, e.p_other) DESC
      ) AS rn
    FROM real_entities e
    JOIN '{TOPIC_CORPUS}' c ON c.id = e.comment_id
    WHERE e.is_list_dump = 0 AND c.char_length >= 40
  )
  SELECT entity_key, construct, predicted_label, p_hostile, p_endorsement, upvotes, snippet
  FROM joined
  WHERE rn <= {PER_ENTITY_PER_LABEL}
  ORDER BY entity_key, predicted_label, confidence DESC
) TO '{ENTITY_OUT}' (FORMAT CSV, HEADER)
""")
n = con.execute(f"SELECT COUNT(*) FROM '{ENTITY_OUT}'").fetchone()[0]
print(f"  Saved {n:,} rows to {ENTITY_OUT}")

print("=== Done ===")
