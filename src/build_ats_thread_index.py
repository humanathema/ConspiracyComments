"""Build ats_thread_index: one row per AboveTopSecret thread (all 339k, not
just the top 50 by engagement), so the explorer can offer a real browsable
forum index -- sortable, paginated -- rather than a search-only view.

Written into drilldown.sqlite (species it's tiny -- one row per thread,
not per comment) so the API can ORDER BY / LIMIT / OFFSET / LIKE-filter it
cheaply without re-aggregating 7.1M parquet rows on every request.
"""
import sqlite3
import duckdb

THREAD_VIEW = "data/processed/ats_comments_thread_view.parquet"
DB_PATH = "data/processed/drilldown.sqlite"


def main():
    con = duckdb.connect()
    con.execute("PRAGMA preserve_insertion_order=false")
    df = con.execute(f"""
        SELECT
            thread_id,
            any_value(thread_title) AS thread_title,
            COUNT(*) AS total_comments,
            SUM(starred) AS starred_comments,
            MIN(raw_timestamp) FILTER (WHERE thread_seq = 0) AS first_post_ts
        FROM read_parquet('{THREAD_VIEW}')
        GROUP BY thread_id
    """).fetchdf()

    sconn = sqlite3.connect(DB_PATH, timeout=30.0)
    try:
        sconn.execute("DROP TABLE IF EXISTS ats_thread_index")
        sconn.execute("""
            CREATE TABLE ats_thread_index (
                thread_id BIGINT PRIMARY KEY,
                thread_title VARCHAR,
                total_comments BIGINT,
                starred_comments BIGINT,
                first_post_ts VARCHAR
            )
        """)
        sconn.executemany(
            "INSERT INTO ats_thread_index (thread_id, thread_title, total_comments, starred_comments, first_post_ts) VALUES (?, ?, ?, ?, ?)",
            df[["thread_id", "thread_title", "total_comments", "starred_comments", "first_post_ts"]].itertuples(index=False, name=None),
        )
        sconn.execute("CREATE INDEX idx_ats_thread_index_title ON ats_thread_index(thread_title)")
        sconn.execute("CREATE INDEX idx_ats_thread_index_comments ON ats_thread_index(total_comments)")
        sconn.commit()
        n = sconn.execute("SELECT COUNT(*) FROM ats_thread_index").fetchone()[0]
        print(f"Wrote ats_thread_index: {n:,} threads")
    finally:
        sconn.close()


if __name__ == "__main__":
    main()
