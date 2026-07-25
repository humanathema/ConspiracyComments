"""build_author_topic_engagement.py

Per-author topic engagement (which granular topics an author posts about
most), across the full corpus (long + short populations combined).

Restricted to authors with >=20 total comments in the combined corpus
(190,001 of 1,217,880 distinct authors as of 2026-07-24) -- an explicit,
documented sparsity floor, not a silent default. Below this floor an
author's topic distribution is mostly noise (1-2 comments landing in
whatever topic they happen to match). Matches the sparsity-threshold
discipline already used elsewhere in this project (e.g. the elasticity/
insider-presence grid in run_integrated_regressions.py).

Outputs two files:
  data/processed/author_topic_engagement.csv (long format):
    author, assigned_topic, topic_name, super_topic,
    n_comments, author_total_comments, share_of_author_comments
  data/processed/author_top_topic_summary.csv (one row per author):
    author, author_total_comments, top_topic, top_topic_name,
    top_topic_n_comments, top_topic_share
"""
import os
import duckdb

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_AUTHOR_COMMENTS = 20


def main():
    long_path = os.path.join(REPO_ROOT, 'data/processed/empath_scores_full_mapped.parquet')
    short_path = os.path.join(REPO_ROOT, 'data/processed/conspiracy_comments_short_lte100chars_mapped.parquet')
    engagement_path = os.path.join(REPO_ROOT, 'data/processed/author_topic_engagement.csv')
    summary_path = os.path.join(REPO_ROOT, 'data/processed/author_top_topic_summary.csv')

    con = duckdb.connect()
    con.execute("SET memory_limit='3GB'; SET threads=3;")

    print("Aggregating author x topic engagement across long + short populations...")
    con.execute(f"""
        CREATE TEMP TABLE combined AS
        SELECT author, assigned_topic, topic_name, super_topic
        FROM '{long_path}'
        WHERE author IS NOT NULL AND author != '[deleted]'
        UNION ALL
        SELECT author, assigned_topic, topic_name, super_topic
        FROM '{short_path}'
        WHERE author IS NOT NULL AND author != '[deleted]'
    """)

    con.execute(f"""
        CREATE TEMP TABLE author_totals AS
        SELECT author, count(*) AS author_total_comments
        FROM combined
        GROUP BY author
        HAVING count(*) >= {MIN_AUTHOR_COMMENTS}
    """)
    n_authors = con.execute("SELECT count(*) FROM author_totals").fetchone()[0]
    print(f"{n_authors:,} authors clear the >= {MIN_AUTHOR_COMMENTS}-comment floor")

    print("Building long-format engagement table...")
    engagement = con.execute("""
        SELECT c.author, c.assigned_topic, c.topic_name, c.super_topic,
               count(*) AS n_comments,
               t.author_total_comments,
               round(count(*)::DOUBLE / t.author_total_comments, 6) AS share_of_author_comments
        FROM combined c
        JOIN author_totals t USING (author)
        GROUP BY c.author, c.assigned_topic, c.topic_name, c.super_topic, t.author_total_comments
        ORDER BY t.author_total_comments DESC, c.author, n_comments DESC
    """).df()
    engagement.to_csv(engagement_path, index=False)
    print(f"Saved {len(engagement):,} rows to {engagement_path}")

    print("Building per-author top-topic summary...")
    summary = con.execute("""
        SELECT author, assigned_topic AS top_topic, topic_name AS top_topic_name,
               author_total_comments, n_comments AS top_topic_n_comments,
               share_of_author_comments AS top_topic_share
        FROM (
            SELECT *, row_number() OVER (PARTITION BY author ORDER BY n_comments DESC) AS rn
            FROM (
                SELECT c.author, c.assigned_topic, c.topic_name,
                       count(*) AS n_comments,
                       t.author_total_comments,
                       round(count(*)::DOUBLE / t.author_total_comments, 6) AS share_of_author_comments
                FROM combined c
                JOIN author_totals t USING (author)
                GROUP BY c.author, c.assigned_topic, c.topic_name, t.author_total_comments
            )
        )
        WHERE rn = 1
        ORDER BY author_total_comments DESC
    """).df()
    summary.to_csv(summary_path, index=False)
    print(f"Saved {len(summary):,} rows to {summary_path}")


if __name__ == '__main__':
    main()
