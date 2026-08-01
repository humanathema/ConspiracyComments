"""
Builds a SQLite FTS5 full-text search database for ATS comments, to be
served from the VM (not Cloud Run) -- see
handoff/task_ats_search_sqlite_fts5_on_vm.md for why: DuckDB's remote
`gs://` ATTACH for the earlier DuckDB-based FTS index was confirmed (via
two isolated tests, not just repeated failures) to be a genuine
architectural mismatch -- BM25 scoring does many small scattered lookups
across a large postings table, and DuckDB's httpfs reader is built for
large sequential/columnar reads, not that access pattern. SQLite FTS5
sidesteps this entirely: the file is opened as an ordinary local file (no
remote-attach, no catalog aliasing), and SQLite's mmap-based I/O means the
OS pages in only the blocks a query actually touches -- low real memory
use even for a large index, well suited to the VM's small RAM budget.

Output: data/processed/ats_search_fts5.db -- copy this to the VM's local
disk (NOT GCS -- the whole point is local file access), served by
src/serve_ats_search_fts5.py.

Usage:
    python3 src/build_ats_search_sqlite_fts5.py
"""
import os
import sqlite3
import time

import duckdb

SRC_PARQUET = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'ats_comments_thread_view.parquet')
OUTPUT_DB = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'ats_search_fts5.db')


def main():
    if os.path.exists(OUTPUT_DB):
        os.remove(OUTPUT_DB)

    t0 = time.time()
    print("Reading source parquet via DuckDB...", flush=True)
    con = duckdb.connect()
    rows = con.execute(f"""
        SELECT comment_id, thread_title, text, starred
        FROM read_parquet('{SRC_PARQUET}')
    """).fetchall()
    print(f"Loaded {len(rows)} rows, {time.time()-t0:.0f}s elapsed", flush=True)
    con.close()

    db = sqlite3.connect(OUTPUT_DB)
    db.execute("PRAGMA journal_mode=WAL")
    # FTS5 virtual table: comment_id/starred stored as UNINDEXED columns
    # (retrievable but not tokenized/searched) -- only text+thread_title
    # get indexed. starred is kept for the same reason it's kept in the
    # DuckDB attempt: ranking needs it, and it's cheap (one int per row).
    db.execute("""
        CREATE VIRTUAL TABLE ats_comments_fts USING fts5(
            comment_id UNINDEXED,
            thread_title,
            text,
            starred UNINDEXED,
            tokenize = 'porter unicode61'
        )
    """)
    print("Inserting rows into FTS5 table (this is the slow part)...", flush=True)
    db.executemany(
        "INSERT INTO ats_comments_fts (comment_id, thread_title, text, starred) VALUES (?, ?, ?, ?)",
        rows,
    )
    db.commit()
    print(f"Inserted, {time.time()-t0:.0f}s elapsed", flush=True)

    print("Optimizing FTS5 index...", flush=True)
    db.execute("INSERT INTO ats_comments_fts(ats_comments_fts) VALUES ('optimize')")
    db.commit()
    db.execute("VACUUM")

    check = db.execute(
        "SELECT comment_id FROM ats_comments_fts WHERE ats_comments_fts MATCH ? LIMIT 1",
        ("chemtrails",),
    ).fetchone()
    print(f"Sanity check (a MATCH query returns results): {check is not None}", flush=True)
    db.close()

    size_mb = os.path.getsize(OUTPUT_DB) / 1e6
    print(f"Done in {time.time()-t0:.0f}s total. Wrote {OUTPUT_DB} ({size_mb:.0f}MB)", flush=True)


if __name__ == '__main__':
    main()
