"""build_canonical_entity_mentions.py

Per-name-variant mention counts for the CANONICAL_EXPERTS list
(src/refine_thesis_models.py) -- historical/philosophical figures used as
a `has_canonical_expert` regression flag, but never broken out per-entity
the way maverick/consensus entities were. Mention counts only, same
regex convention as the regression scripts (word-boundary, case-insensitive)
-- no stance classification exists for this list.

Output: data/processed/canonical_entity_mentions.csv
  entity, mention_count
"""
import duckdb

sys_path_note = None
import sys
sys.path.insert(0, 'src')
from refine_thesis_models import CANONICAL_EXPERTS

CORPUS = 'data/processed/empath_scores_full_mapped.parquet'
OUT_PATH = 'data/processed/canonical_entity_mentions.csv'

con = duckdb.connect()
con.execute("PRAGMA memory_limit='4GB'")

rows = []
for name in CANONICAL_EXPERTS:
    pattern = r'\b' + name.replace(' ', r'\s+') + r'\b'
    n = con.execute(
        f"SELECT count(*) FROM '{CORPUS}' WHERE regexp_matches(text, ?, 'i')",
        [pattern]
    ).fetchone()[0]
    rows.append((n, name))
    print(f"  {name}: {n:,}")

rows.sort(reverse=True)
with open(OUT_PATH, 'w', newline='', encoding='utf-8') as f:
    f.write("entity,mention_count\n")
    for n, name in rows:
        f.write(f"{name},{n}\n")

print(f"Saved {len(rows)} rows to {OUT_PATH}")
