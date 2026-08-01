"""score_ats_lexical.py

Epistemic lexicon scoring for the ATS (AboveTopSecret) corpus, mirroring
src/score_comparisons.py's approach (same 11-category utils/epistemic_lexicon.py
word lists, same SIMD-friendly `contains(clean_text, ' word ')` pattern) so ATS
scores are directly comparable to the r/conspiracy corpus's empath_scores_full*
parquets -- same method, same categories, no reinvention.

Schema differences from the reddit scorer this adapts:
  - Input is data/processed/ats_comments_final.parquet (already deduplicated,
    7,147,196 rows), not raw reddit JSONL.
  - No numeric "upvotes"/"score" -- ATS has `starred` (boolean, 0/1). Kept as
    its own column, not force-mapped onto "upvotes"; cross-corpus normalization
    (z-scoring stars vs upvotes) is a separate later step, not done here.
  - No `controversiality`/`link_id` (reddit-specific engagement/threading
    fields ATS doesn't have).
  - `raw_timestamp` is a free-text string with at least 3 observed formats
    (e.g. "apr, 3 2014 @ 08:27 am", "7:28 am on Sep. 22, 2001",
    "12-12-2005 @ 10:23 AM", the last sometimes suffixed "(ID:12345)").
    Best-effort parsed into `parsed_timestamp` via the 3 formats found so far
    (covers ~90% of rows) -- raw_timestamp is kept alongside it either way, and
    the ~10% that don't match any known format are left NULL rather than
    guessing at further formats not yet seen.

Output: data/processed/ats_empath_scores.parquet
"""
import duckdb
import os
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from utils.epistemic_lexicon import lex
except ImportError:
    print("Error: Could not import utils.epistemic_lexicon.lex")
    sys.exit(1)

INPUT_PATH = "data/processed/ats_comments_final.parquet"
OUTPUT_PATH = "data/processed/ats_empath_scores.parquet"

def main():
    if os.path.exists(OUTPUT_PATH):
        print(f"{OUTPUT_PATH} already exists, skipping. Delete it first to re-run.")
        return

    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='4GB'")

    print("Building SIMD string search query for 11 lexicon dimensions...")
    category_columns = []
    for cat, words in lex.items():
        term_checks = []
        for word in words:
            clean_word = word.replace('-', ' ').replace("'", "''").lower()
            term_checks.append(f"contains(clean_text, ' {clean_word} ')::INT")
        cat_sum_sql = " + \n            ".join(term_checks)
        category_columns.append(f"({cat_sum_sql}) as {cat}_count")
    category_sql = ",\n        ".join(category_columns)

    query = f"""
        WITH raw_comments AS (
            SELECT
                post_id AS id,
                thread_id,
                thread_title,
                page_num,
                author,
                starred,
                reply_to_authors,
                reply_to_post_ids,
                raw_timestamp,
                COALESCE(
                    try_strptime(raw_timestamp, '%b, %d %Y @ %I:%M %p'),
                    try_strptime(raw_timestamp, '%I:%M %p on %b. %d, %Y'),
                    try_strptime(regexp_replace(raw_timestamp, ' \\(ID:[0-9]+\\)', ''), '%d-%m-%Y @ %I:%M %p')
                ) AS parsed_timestamp,
                length(body) as char_length,
                CASE WHEN body LIKE '%http%' THEN 1 ELSE 0 END as has_link,
                body as text,
                ' ' || regexp_replace(lower(body), '[^a-z0-9]', ' ', 'g') || ' ' as clean_text
            FROM read_parquet('{INPUT_PATH}')
            WHERE body IS NOT NULL
              AND length(body) > 50
        )
        SELECT
            id,
            thread_id,
            thread_title,
            page_num,
            author,
            starred,
            reply_to_authors,
            reply_to_post_ids,
            raw_timestamp,
            parsed_timestamp,
            char_length,
            has_link,
            text,
            {category_sql}
        FROM raw_comments
    """

    print(f"Scoring {INPUT_PATH} -> {OUTPUT_PATH}...")
    start = time.time()
    con.execute(f"COPY ({query}) TO '{OUTPUT_PATH}' (FORMAT PARQUET, COMPRESSION 'zstd')")
    elapsed = time.time() - start
    n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{OUTPUT_PATH}')").fetchone()[0]
    print(f"Done in {elapsed:.1f}s -- {n:,} rows scored, saved to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
