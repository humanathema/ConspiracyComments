"""build_local_context_db.py

hitl_rater.py's context-lookup ("Load surrounding context") falls back
to querying EMPATH_PATH (data/processed/empath_scores_full_mapped.parquet)
via DuckDB when a comment isn't in the pre-built CONTEXT_CACHE -- but
that parquet was never downloaded locally (only exists on Kaggle, same
"deliberately never downloaded locally" pattern as everything else this
session), so the lookup has been silently returning empty context this
whole time regardless of whether parent_id was actually populated.

Nash confirmed the raw comment shards ARE available locally
(data/raw/r_conspiracy_comments*.jsonl.gz, ~7.6GB compressed). This
builds a small, indexed local DuckDB file from just the columns needed
for context lookup (id, parent_id, link_id, body) -- not the full
comment schema -- so hitl_rater.py can query it directly, fast, fully
offline.

Machine has 8GB RAM (real OOM risk, established constraint this
project) -- explicit memory_limit set below, and only 4 narrow columns
are extracted rather than materializing full comment records, to keep
this safely out-of-core.

Output: data/processed/local_context.duckdb (table: comments)
"""
import glob
import os
import time

import duckdb

RAW_DIR = "data/raw"
OUT_DB = "local_context.duckdb"  # local disk — thumb drive lacks space for 14GB file
MEMORY_LIMIT = "4GB"


def main():
    shards = sorted(glob.glob(os.path.join(RAW_DIR, "r_conspiracy_comments*.jsonl.gz")))
    shards = [s for s in shards if os.path.getsize(s) > 1024]  # skip the known-empty comments8 shard
    print(f"Found {len(shards)} shards, total {sum(os.path.getsize(s) for s in shards) / 1e9:.2f}GB compressed:", flush=True)
    for s in shards:
        print(f"  {s} ({os.path.getsize(s)/1e6:.0f}MB)", flush=True)

    if os.path.exists(OUT_DB):
        os.remove(OUT_DB)

    con = duckdb.connect(OUT_DB)
    con.execute(f"PRAGMA memory_limit='{MEMORY_LIMIT}'")
    con.execute("PRAGMA threads=4")

    con.execute("CREATE TABLE comments (id VARCHAR, parent_id VARCHAR, link_id VARCHAR, text VARCHAR)")

    for i, shard in enumerate(shards):
        t0 = time.time()
        print(f"\n[{i+1}/{len(shards)}] loading {shard}...", flush=True)
        con.execute(f"""
            INSERT INTO comments
            SELECT id, parent_id, link_id, body AS text
            FROM read_ndjson(
                '{shard}',
                columns={{'id':'VARCHAR','parent_id':'VARCHAR','link_id':'VARCHAR','body':'VARCHAR'}},
                ignore_errors=true
            )
            WHERE id IS NOT NULL
        """)
        n = con.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
        print(f"  done in {time.time()-t0:.1f}s, running total: {n:,} rows", flush=True)

    print("\nBuilding indexes on id and parent_id...", flush=True)
    con.execute("CREATE INDEX idx_comments_id ON comments(id)")
    con.execute("CREATE INDEX idx_comments_parent_id ON comments(parent_id)")

    total = con.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
    print(f"\nDone. {total:,} comments indexed in {OUT_DB}", flush=True)
    con.close()


if __name__ == "__main__":
    main()
