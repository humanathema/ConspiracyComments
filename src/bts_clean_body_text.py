"""bts_clean_body_text.py

Post-hoc boilerplate stripper for the BTS / AbovePolitics ingestion
scripts (bts_ingest_archive.py, bts_ingest_abovepolitics.py), adding a
`body_clean` column (original `body` kept for audit) the same way a
concurrent session's src/clean_ats_body_text.py does for ATS.

Why this is needed here too: bts_ingest_archive.py / bts_ingest_abovepolitics.py
both reuse ingest_ats_archive.py's parse_html_file unmodified, which is
the exact function ATS's own cleanup targeted - it records quote/reply
headers into reply_to_authors but never strips the matched text back out
of body, so the same "Originally posted by X" / "reply to post by X" /
site-chrome-footer contamination that hurt ATS's BERTopic run
(collapsed to <5 topics per handoff/task_ats_topic_modeling.md's
context) will be present in body here too, unless cleaned before any
topic modeling on this corpus.

STRIP_PATTERNS is copied from src/clean_ats_body_text.py (2026-07-26),
not imported - that file lives only in the main repo checkout,
uncommitted, and is part of a separate in-flight session's work; copying
avoids a fragile cross-worktree import dependency. Two site-chrome
literals differ (BTS/AbovePolitics's own copyright/ad-supported footer
text, not ATS's) - verify against real samples before trusting this
blindly, same "not a claim of exhaustive cleanup" caveat as the
original.

Usage:
    python src/bts_clean_body_text.py --input data/processed/bts_comments_final.parquet \\
        --output data/processed/bts_comments_final_cleaned.parquet
"""
import argparse
import os
import time
import duckdb

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Same patterns as src/clean_ats_body_text.py, plus BTS/AbovePolitics
# equivalents of the two ATS-branded site-chrome footer lines. Applied in
# order via DuckDB regexp_replace(body, pattern, '', 'gi').
#
# Trailing captures use [^\n"]{0,60} (not [^\n]{0,60}): a real header is
# never inside a quote, but someone discussing another post can write
# e.g. 'reply posted on ... by Anunaki10"' as part of their own quoted
# sentence, and without the '"' stop the capture overran the closing
# quote and ate real follow-on content along with the false-positive
# match. DuckDB's regex engine has no lookaround, so this bounded-class
# approach is the fix rather than a negative lookahead.
STRIP_PATTERNS = [
    r'reply to\s*(this\s*)?post\s+by[^\n"]{0,60}',
    r'originally posted by[^\n"]{0,60}',
    r'a reply to:\s*[^\n"]{0,60}',
    r'reply posted on\s+[0-9./-]{4,12}\s*@?\s*[0-9:]{0,8}\s*(am|pm)?\s*by\s*[\r\n\s]{0,3}[^\n"]{0,60}',
    r'copyright\s*&\s*usage',
    r'AboveTopSecret\.com is advertising supported\.',
    r'BelowTopSecret\.com is advertising supported\.',
    r'AbovePolitics\.com is advertising supported\.',
    r'reply to this post:',
    r'edit on [\s\S]{0,100}?because:\s*(\([^)\n]{0,80}\)|[^\n]{0,80})',
    r'\[edit on [^\]\n]{0,80}\]',
]


def clean_parquet(input_path, output_path):
    con = duckdb.connect()
    con.execute("SET memory_limit='3GB'; SET threads=3;")

    total = con.execute(f"SELECT count(*) FROM '{input_path}'").fetchone()[0]
    print(f"Loaded schema, {total:,} rows in source.")

    columns = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM '{input_path}'").fetchall()]
    other_cols = [c for c in columns if c != 'body']

    expr = "body"
    for pat in STRIP_PATTERNS:
        escaped = pat.replace("'", "''")
        expr = f"regexp_replace({expr}, '{escaped}', '', 'gi')"
    expr = f"trim(regexp_replace(regexp_replace({expr}, '[ \\t]{{2,}}', ' ', 'g'), '\\n{{3,}}', chr(10) || chr(10), 'g'))"

    print("Running full-corpus clean (single streaming DuckDB pass)...")
    t0 = time.time()
    select_cols = ", ".join(other_cols + ["body", f"{expr} AS body_clean"])
    con.execute(f"""
        COPY (
            SELECT {select_cols}
            FROM '{input_path}'
        ) TO '{output_path}' (FORMAT PARQUET)
    """)
    print(f"Wrote {output_path} in {time.time()-t0:.1f}s")

    print("\n--- Verification ---")
    changed = con.execute(f"SELECT count(*) FROM '{output_path}' WHERE body_clean != body").fetchone()[0]
    pct = 100 * changed / total if total else 0.0
    print(f"Rows changed: {changed:,} / {total:,} ({pct:.1f}%)")

    if changed:
        avg_delta = con.execute(f"""
            SELECT avg(length(body) - length(body_clean))
            FROM '{output_path}' WHERE body_clean != body
        """).fetchone()[0]
        print(f"Avg chars stripped per changed row: {avg_delta:.1f}")

    empty_after = con.execute(f"""
        SELECT count(*) FROM '{output_path}'
        WHERE length(trim(body_clean)) = 0 AND length(trim(body)) > 0
    """).fetchone()[0]
    print(f"Rows now EMPTY after cleaning (was non-empty): {empty_after:,}")

    if changed:
        print("\n--- 5 before/after spot checks (rows that changed) ---")
        sample = con.execute(f"""
            SELECT body, body_clean FROM '{output_path}'
            WHERE body_clean != body
            USING SAMPLE 5
        """).fetchdf()
        for i, row in sample.iterrows():
            print(f"\n[{i}] BEFORE: {row['body'][:200]!r}")
            print(f"[{i}] AFTER : {row['body_clean'][:200]!r}")


def main():
    parser = argparse.ArgumentParser(description="Strip forum-chrome boilerplate from a bts_ingest_*.py parquet output")
    parser.add_argument("--input", required=True, help="Path to the *_final.parquet input")
    parser.add_argument("--output", required=True, help="Path to write the *_final_cleaned.parquet output")
    args = parser.parse_args()
    clean_parquet(args.input, args.output)


if __name__ == '__main__':
    main()
