"""Build ats_comments_thread_view.parquet: the browse export enriched with
per-thread ordering (page_num, post sequence) and reply_to_post_ids, so the
server can serve a scrollable, threaded forum view instead of single
isolated comments.

ats_comments_browse.parquet has hs_prob (scored) but was flattened without
page_num/reply_to_post_ids. ats_comments_final.parquet has those but not
hs_prob. Same row count (7,147,196) and comment_id == post_id 1:1, so this
is a straight join.
"""
import duckdb

BROWSE = "data/processed/ats_comments_browse.parquet"
FINAL = "data/processed/ats_comments_final.parquet"
OUT = "data/processed/ats_comments_thread_view.parquet"


def main():
    con = duckdb.connect()
    con.execute("PRAGMA preserve_insertion_order=false")
    con.execute(f"""
        COPY (
            SELECT
                b.comment_id,
                b.thread_id,
                b.thread_title,
                b.author,
                b.starred,
                b.raw_timestamp,
                b.text,
                b.hs_prob,
                f.page_num,
                f.reply_to_post_ids,
                ROW_NUMBER() OVER (
                    PARTITION BY b.thread_id
                    ORDER BY f.page_num, b.comment_id
                ) - 1 AS thread_seq
            FROM read_parquet('{BROWSE}') b
            JOIN read_parquet('{FINAL}') f ON f.post_id = CAST(b.comment_id AS VARCHAR)
            ORDER BY b.thread_id, thread_seq
        ) TO '{OUT}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    total = con.execute(f"SELECT COUNT(*) FROM read_parquet('{OUT}')").fetchone()[0]
    threads = con.execute(f"SELECT COUNT(DISTINCT thread_id) FROM read_parquet('{OUT}')").fetchone()[0]
    print(f"Wrote {OUT}: {total:,} rows across {threads:,} threads")


if __name__ == "__main__":
    main()
