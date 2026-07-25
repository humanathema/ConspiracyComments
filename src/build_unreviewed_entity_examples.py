"""build_unreviewed_entity_examples.py

Comment-linked examples for the "unreviewed" entities (Trump, DNC, Biden,
etc. -- see data/processed/missing_entity_candidates.csv) that were
mined by frequency but never run through any comment-linkage pipeline.
Previously these had only 2 hand-picked example snippets and no real
comment data at all, so the drill-down correctly came up empty. Mention
counts only, no stance -- these entities are still unbucketed, same
regex-scan approach as src/build_canonical_entity_mentions.py.

Output: data/processed/unreviewed_entity_examples.csv
  entity_key, upvotes, text  (up to 300 examples per entity, by upvotes)
"""
import csv
import re
import duckdb
import os

CORPUS = 'data/processed/empath_scores_full_mapped.parquet'
CANDIDATES = 'data/processed/missing_entity_candidates.csv'
OUT_PATH = 'data/processed/unreviewed_entity_examples.csv'
PER_ENTITY = 300

with open(CANDIDATES, newline='', encoding='utf-8') as f:
    entities = [row['entity'] for row in csv.DictReader(f)]

processed = set()
file_exists = os.path.exists(OUT_PATH)

if file_exists:
    try:
        with open(OUT_PATH, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                processed.add(row['entity_key'].lower())
        print(f"🔄 Resuming build. Found {len(processed)} existing entries (grouped into {len(processed)} unique entities).")
    except Exception as e:
        print(f"⚠️ Error reading existing file, starting fresh: {e}")
        file_exists = False

con = duckdb.connect()
con.execute("PRAGMA memory_limit='5GB'")

mode = 'a' if file_exists else 'w'
with open(OUT_PATH, mode, newline='', encoding='utf-8') as out:
    w = csv.writer(out)
    if not file_exists:
        w.writerow(['comment_id', 'entity_key', 'upvotes', 'text'])
    
    skipped = 0
    for i, name in enumerate(entities):
        if name.lower() in processed:
            skipped += 1
            continue
            
        # Escape special regex characters in name
        escaped_name = re.escape(name).replace(r'\ ', r'\s+').replace(' ', r'\s+')
        pattern = r'\b' + escaped_name + r'\b'
        rows = con.execute(f"""
            SELECT id AS comment_id, upvotes, regexp_replace(text, '[\\r\\n\\t]+', ' ', 'g') AS text
            FROM '{CORPUS}'
            WHERE regexp_matches(text, ?, 'i') AND char_length >= 20
            ORDER BY upvotes DESC
            LIMIT {PER_ENTITY}
        """, [pattern]).fetchall()
        for comment_id, upvotes, text in rows:
            w.writerow([comment_id, name.lower(), upvotes, text])
        print(f"  [{i+1}/{len(entities)}] {name}: {len(rows)} examples")

print(f"Saved to {OUT_PATH}")

