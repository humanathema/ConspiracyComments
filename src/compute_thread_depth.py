"""compute_thread_depth.py

Nash's correction 2026-08-02: "thread size" for the graph pilot should
be the LONGEST REPLY CHAIN (deepest sequence of people replying to each
other), not raw comment count per post (which just picks the WIDEST
posts). Second correction, same conversation: don't pull all 44M rows
into pandas to compute this -- threads are fully independent (Reddit
replies never cross post boundaries), so this is a pure DuckDB
recursive-CTE job, out-of-core, no Python-side string objects for 44M
rows. No text needed either -- pure id/parent_id/link_id structure from
reddit_thread_metadata.parquet.

Output: data/processed/thread_depth.parquet (link_id, max_depth, n_comments)
"""
import duckdb

META_PATH = "data/processed/reddit_thread_metadata.parquet"
OUT_THREAD = "data/processed/thread_depth.parquet"


def main():
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='5GB'")
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA enable_progress_bar=false")

    print("Computing per-comment depth via recursive CTE (all in DuckDB, no pandas)...", flush=True)
    con.execute(f"""
        CREATE TEMP TABLE meta AS
        SELECT id, parent_id, link_id FROM read_parquet('{META_PATH}')
    """)

    con.execute("""
        CREATE TEMP TABLE chain AS
        WITH RECURSIVE depth_chain(id, link_id, depth) AS (
            SELECT id, link_id, 1 AS depth
            FROM meta
            WHERE parent_id = link_id  -- top-level: replies directly to the post

            UNION ALL

            SELECT m.id, m.link_id, d.depth + 1
            FROM meta m
            JOIN depth_chain d ON m.parent_id = 't1_' || d.id
        )
        SELECT * FROM depth_chain
    """)

    n_chain = con.execute("SELECT COUNT(*) FROM chain").fetchone()[0]
    n_meta = con.execute("SELECT COUNT(*) FROM meta").fetchone()[0]
    print(f"  {n_chain:,}/{n_meta:,} comments resolved into the chain "
          f"({n_meta - n_chain:,} unresolved -- broken/orphaned parent refs, expected to be small)", flush=True)

    con.execute(f"""
        COPY (
            SELECT link_id, MAX(depth) AS max_depth, COUNT(*) AS n_comments
            FROM chain
            GROUP BY link_id
            ORDER BY max_depth DESC
        ) TO '{OUT_THREAD}' (FORMAT PARQUET)
    """)

    top = con.execute(f"SELECT * FROM read_parquet('{OUT_THREAD}') LIMIT 20").df()
    print("\nTop 20 threads by longest reply chain (max_depth):", flush=True)
    print(top.to_string(), flush=True)

    stats = con.execute(f"""
        SELECT MIN(max_depth), MAX(max_depth), AVG(max_depth), MEDIAN(max_depth)
        FROM read_parquet('{OUT_THREAD}')
    """).fetchone()
    print(f"\nmax_depth: min={stats[0]} max={stats[1]} mean={stats[2]:.2f} median={stats[3]}", flush=True)


if __name__ == "__main__":
    main()
