"""extract_thread_metadata.py

Metadata-only extraction for thread-structure graph reconstruction
(handoff/task_graph_based_topic_structure.md) -- id/parent_id/link_id
(the reply-tree topology) plus author/created_utc/subreddit/score, with
NO comment body text. Nash's point 2026-08-02: thread topology doesn't
need full text at all, so this can be a small, cheap, local-machine-safe
file instead of requiring the full-text corpus (which only lives on
Kaggle, multi-GB, would OOM this 8GB RAM machine -- see
machine_constraints memory).

Reads directly from the raw archive (same read_json_auto + glob pattern
as build_sample_id_map.py), NOT from any already-built corpus parquet --
avoids depending on ATS-specific indexing (index_all_comments_sqlite.py
turned out to be the ATS/forum indexer, different data model, not
reusable here). Dedup on 'id' applied directly in this script (the
known duplicate-id bug, see dedup_root_cause_lexical_scores memory, was
about full-text corpus parquets; this script sidesteps it by deduping
itself rather than trusting any prebuilt file).

Output: data/processed/reddit_thread_metadata.parquet
  columns: id, parent_id, link_id, author, created_utc, subreddit, score
"""
import duckdb

RAW_GLOB = "data/raw/r_conspiracy_comments*.jsonl*"
OUT_PATH = "data/processed/reddit_thread_metadata.parquet"


def main():
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='5GB'")
    con.execute("PRAGMA threads=4")

    print("Extracting thread-topology metadata (no body text) from raw archive...", flush=True)
    con.execute(f"""
        COPY (
            SELECT DISTINCT ON (id)
                id, parent_id, link_id, author, created_utc, subreddit, score
            FROM read_json_auto('{RAW_GLOB}', maximum_object_size=50000000, union_by_name=True)
            WHERE id IS NOT NULL
            ORDER BY id, retrieved_on DESC NULLS LAST
        ) TO '{OUT_PATH}' (FORMAT PARQUET)
    """)

    n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{OUT_PATH}')").fetchone()[0]
    n_top_level = con.execute(f"SELECT COUNT(*) FROM read_parquet('{OUT_PATH}') WHERE parent_id = link_id").fetchone()[0]
    n_unique_threads = con.execute(f"SELECT COUNT(DISTINCT link_id) FROM read_parquet('{OUT_PATH}')").fetchone()[0]
    print(f"\nWrote {n:,} rows to {OUT_PATH}", flush=True)
    print(f"  {n_top_level:,} top-level comments (parent_id == link_id)", flush=True)
    print(f"  {n_unique_threads:,} unique threads (distinct link_id)", flush=True)


if __name__ == "__main__":
    main()
