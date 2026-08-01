"""
Builds a pre-indexed DuckDB database for /api/ats_search on Cloud Run.

A plain `LIKE '%term%'` scan over `ats_comments_browse_with_stars.parquet`
(7.15M rows, 1.8GB) has no index to use -- DuckDB has to decompress and
scan the entire `text` column on every request. Measured directly against
the deployed Cloud Run service: ~78s for one query. That's the same
underlying cost that OOM-crashed the old e2-micro VM, just survivable here
instead of fast. DuckDB's `fts` extension builds a real inverted index
(BM25-ranked, same underlying idea as Postgres/Elasticsearch full-text
search) over `text`+`thread_title`, turning search into an index lookup
(measured: 0.67s locally after this build).

The base table indexed only carries `comment_id` + `starred` -- NOT the
full row. First attempt kept every column (thread_id/author/text/etc.) in
the indexed table too, which produced an 11.5GB file (bigger than the
~7GB the ATS corpus would've been as raw sqlite, i.e. worse than the thing
this migration was moving away from -- a real, correctly-called-out
problem). Root cause: once the FTS index is built, match_bm25() scores
off its own internal `fts_main_ats_comments.*` structures, not the
original text column -- keeping a full duplicate copy of `text` in the
base table was pure waste. Dropping the text/thread_title columns and
re-packing (EXPORT DATABASE -> IMPORT DATABASE, since DuckDB doesn't
reclaim space in-place after ALTER TABLE DROP COLUMN) took it to 1.18GB
-- smaller than the source parquet.

`starred` specifically IS kept (a second pass added it back after
dropping it in the first cut) -- ranking needs to sort by starred-first
same as the site's original design, and computing that via a JOIN against
the mounted parquet during ranking (tried first) meant resolving `starred`
for every candidate match before the LIMIT could apply, not just the
final page -- measured 3.2s instead of 0.8s. Keeping one small BIGINT
column costs almost nothing (1.18GB either way) and avoids the join
entirely for ranking. Only the *other* columns (text, thread_title,
author, etc.) are fetched from the mounted parquet, and only for the
already-ranked, already-paginated result set.

Output: data/processed/ats_search_fts.duckdb -- upload this to the GCS
bucket alongside the rest of the migrated data (cloudrun_api/main.py opens
it read-only via the same GCS volume mount as everything else).

Usage:
    python3 src/build_ats_search_fts_index.py
"""
import os
import shutil
import time

import duckdb

SRC_PARQUET = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'ats_comments_thread_view.parquet')
OUTPUT_DB = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'ats_search_fts.duckdb')
TMP_EXPORT_DIR = '/tmp/ats_fts_export'
TMP_DB = OUTPUT_DB + '.tmp'


def main():
    for p in (OUTPUT_DB, TMP_DB):
        if os.path.exists(p):
            os.remove(p)
    if os.path.exists(TMP_EXPORT_DIR):
        shutil.rmtree(TMP_EXPORT_DIR)

    t0 = time.time()
    con = duckdb.connect(TMP_DB)
    # Conservative cap for this machine's 8GB RAM (see handoff's
    # documented OOM history on full-corpus jobs) -- FTS index
    # construction over 7M+ text rows is a real memory operation.
    con.execute("PRAGMA memory_limit='5GB'")
    con.execute("PRAGMA threads=4")
    con.execute("INSTALL fts; LOAD fts;")

    print("Creating table from parquet...", flush=True)
    con.execute(f"""
        CREATE TABLE ats_comments AS
        SELECT comment_id, thread_title, text, starred
        FROM read_parquet('{SRC_PARQUET}')
    """)
    n = con.execute("SELECT COUNT(*) FROM ats_comments").fetchone()[0]
    print(f"Loaded {n} rows into table, {time.time()-t0:.0f}s elapsed", flush=True)

    print("Building FTS index (this is the slow part)...", flush=True)
    con.execute("""
        PRAGMA create_fts_index('ats_comments', 'comment_id', 'text', 'thread_title', stemmer='porter', overwrite=1)
    """)
    print(f"FTS index built, {time.time()-t0:.0f}s elapsed", flush=True)

    print("Dropping the now-redundant text/thread_title columns (score comes from the FTS index, not these; starred is kept)...", flush=True)
    con.execute("ALTER TABLE ats_comments DROP COLUMN text")
    con.execute("ALTER TABLE ats_comments DROP COLUMN thread_title")

    print("Repacking into a fresh file to actually reclaim the dropped columns' space...", flush=True)
    con.execute(f"EXPORT DATABASE '{TMP_EXPORT_DIR}' (FORMAT PARQUET)")
    con.close()

    con2 = duckdb.connect(OUTPUT_DB)
    con2.execute("INSTALL fts; LOAD fts;")
    con2.execute(f"IMPORT DATABASE '{TMP_EXPORT_DIR}'")
    check = con2.execute("""
        SELECT comment_id FROM (
            SELECT comment_id, fts_main_ats_comments.match_bm25(comment_id, 'test') AS score FROM ats_comments
        ) WHERE score IS NOT NULL LIMIT 1
    """).fetchone()
    con2.close()
    print(f"Sanity check (a match_bm25 query still returns results): {check is not None}", flush=True)

    os.remove(TMP_DB)
    shutil.rmtree(TMP_EXPORT_DIR)
    size_gb = os.path.getsize(OUTPUT_DB) / 1e9
    print(f"Done in {time.time()-t0:.0f}s total. Wrote {OUTPUT_DB} ({size_gb:.2f}GB)", flush=True)


if __name__ == '__main__':
    main()
