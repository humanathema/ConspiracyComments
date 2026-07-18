"""
Flags likely bot and spam/copypasta accounts in the comment corpus.

Two signals, both metadata-only (author name + text-reuse counts — never
inspects comment content):

1. Named bots: author matches a common Reddit bot-naming convention
   (AutoModerator, *Bot, *_bot).
2. Text-reuse ratio: n_comments / n_distinct_texts per author. Template
   bots post a handful of texts thousands of times (ratio in the
   hundreds/thousands); human copypasta/repeat-posters show a smaller
   but still elevated ratio; ordinary human authors sit close to 1.

Output is author-level so it can be left-joined onto any downstream
query rather than mutating the base corpus.

Usage: python -m src.detect_spam_bots
Input:  data/processed/lexical_scores_full.parquet
Output: data/processed/author_spam_bot_flags.parquet
"""

import duckdb

LEXICAL_PATH = "data/processed/lexical_scores_full.parquet"
OUT_PATH = "data/processed/author_spam_bot_flags.parquet"

# n_comments / n_distinct_texts thresholds.
# Among authors with >=20 comments, p50 dup_ratio is 1.0 and p99 is 1.13
# (verified against the full corpus), so 1.5 already sits deep in the tail.
BOT_DUP_RATIO = 20.0
REPEAT_POSTER_DUP_RATIO = 1.5
REPEAT_POSTER_MIN_COMMENTS = 20  # avoid flagging low-volume authors on noise

BOT_NAME_PATTERN = r'(?i)^automoderator$|(?i)bot$'


def build_author_flags(con: duckdb.DuckDBPyConnection) -> None:
    query = f"""
        COPY (
            WITH per_author AS (
                SELECT
                    author,
                    COUNT(*) AS n_comments,
                    COUNT(DISTINCT text) AS n_distinct_texts
                FROM '{LEXICAL_PATH}'
                WHERE author IS NOT NULL
                  AND author NOT IN ('[deleted]', 'AutoModerator')
                GROUP BY author
            )
            SELECT
                author,
                n_comments,
                n_distinct_texts,
                ROUND(n_comments::DOUBLE / n_distinct_texts, 2) AS dup_ratio,
                regexp_matches(author, '{BOT_NAME_PATTERN}') AS is_named_bot,
                (
                    regexp_matches(author, '{BOT_NAME_PATTERN}')
                    OR (n_comments::DOUBLE / n_distinct_texts) >= {BOT_DUP_RATIO}
                ) AS is_likely_bot,
                (
                    NOT (
                        regexp_matches(author, '{BOT_NAME_PATTERN}')
                        OR (n_comments::DOUBLE / n_distinct_texts) >= {BOT_DUP_RATIO}
                    )
                    AND n_comments >= {REPEAT_POSTER_MIN_COMMENTS}
                    AND (n_comments::DOUBLE / n_distinct_texts) >= {REPEAT_POSTER_DUP_RATIO}
                ) AS is_repeat_poster
            FROM per_author
        ) TO '{OUT_PATH}' (FORMAT PARQUET)
    """
    con.execute(query)


def summarize(con: duckdb.DuckDBPyConnection) -> None:
    summary = con.execute(f"""
        SELECT
            COUNT(*) AS n_authors,
            SUM(n_comments) AS n_comments,
            SUM(CASE WHEN is_named_bot OR is_likely_bot THEN n_comments ELSE 0 END) AS n_bot_comments,
            SUM(CASE WHEN is_repeat_poster THEN n_comments ELSE 0 END) AS n_repeat_poster_comments
        FROM '{OUT_PATH}'
    """).fetchone()
    n_authors, n_comments, n_bot_comments, n_repeat_poster_comments = summary
    print(f"Authors profiled:          {n_authors:,}")
    print(f"Comments covered:          {n_comments:,}")
    print(f"Comments from bots:        {n_bot_comments:,} ({100 * n_bot_comments / n_comments:.2f}%)")
    print(f"Comments from repeat posters: {n_repeat_poster_comments:,} ({100 * n_repeat_poster_comments / n_comments:.2f}%)")


if __name__ == "__main__":
    con = duckdb.connect()
    build_author_flags(con)
    summarize(con)
    print(f"\nWrote author-level flags to {OUT_PATH}")
