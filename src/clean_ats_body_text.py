"""src/clean_ats_body_text.py

Strips known forum-chrome boilerplate out of ats_comments_final.parquet's
`body` field into a new `body_clean` column, without touching the original
`body` (kept for audit) or any other column. Anything meaningful in the
stripped text (member role/tagline, edit history) is extracted into its
own column first, not just discarded -- e.g. "Kano\nSuper Moderator\n
ATSNN.com Editor\nposted on ..." becomes member_title="Super Moderator,
ATSNN.com Editor" plus a clean body, rather than losing that signal.

Why this exists: direct corpus queries (2026-07-26, redone 2026-07-27
after the ATS re-ingestion fix) found reply/quote headers ("Originally
posted by X", "reply to post by X", "reply posted on <date> @ <time> by
X", the older Ikonboard-style "AUTHOR\n[role lines]\nposted on <date> at
<time>") and site-chrome footers ("copyright & usage", edit-notices like
"[edit on <date> by X]") leaking into `body` across a large share of the
corpus. This is metadata the site's own template renders around a post,
not authored content, and it was pulling sentence-transformer embeddings
(which truncate at ~256 tokens) toward generic boilerplate structure
instead of the real reply text -- a likely contributor to a same-day
BERTopic run on ATS text collapsing to under 5 topics.

The reply/quote-header regexes here intentionally mirror (but broaden)
REPLY_TO_REGEX in ingest_ats_archive.py: that script already parses
"reply to (this) post by X" into structured reply_to_authors, but never
strips the matched span back out of body_text, so the same information
was left in twice. This script only touches the text; it doesn't change
reply_to_authors/reply_to_post_ids.

Known limitation: "originally posted by X" quote-header stripping here
only removes the label line, not the quoted content that follows it --
unlike the structural (BeautifulSoup-based) quotebox removal added to
ingest_ats_archive.py earlier the same day, this pass has no HTML
structure to find where a quote block actually ends, so it's a partial
mitigation for that specific leak (concentrated in the Common-Crawl-
sourced ~46% of the corpus, which runs through a separate parser that
never got the structural quote-stripping fix) -- not a full fix. See
handoff notes for the real fix (extending ingest_ats_common_crawl.py's
extraction the same way ingest_ats_archive.py's was).
"""
import os
import time
import duckdb

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_PATH = os.path.join(REPO_ROOT, 'data/processed/ats_comments_final.parquet')
OUTPUT_PATH = os.path.join(REPO_ROOT, 'data/processed/ats_comments_final_cleaned.parquet')

# Bracket-only edit notice, e.g. "[edit on 30-5-2010 by sstark]" -- captured
# BEFORE stripping so the date/author inside isn't lost.
EDIT_NOTE_PATTERN = r'\[edit on ([^\]\n]{1,80})\]'

# Old Ikonboard-style header: "AUTHOR\n[optional role/tagline lines]\nposted
# on <date> at|@ <time>\n(link\n)?" -- group 1 is the username line (already
# in `author`, discarded), group 2 is zero or more role/tagline lines
# ("Member", "Super Moderator", "ATSNN.com Editor", custom taglines like
# "Your Recon Daddy") that aren't captured anywhere else in the schema.
BARE_HEADER_PATTERN = r'^([^\n]{1,40})\n((?:[^\n]{1,60}\n)*?)posted on\s+[^\n]+\n(?:link\n)?'

# Applied in order, each as a DuckDB regexp_replace(body, pattern, '', 'gi').
# [^\n]{0,N} bounds keep these from running away across paragraph breaks.
STRIP_PATTERNS = [
    # bare Ikonboard-style header (see BARE_HEADER_PATTERN above) -- must
    # run first since it's anchored at the start of the string.
    BARE_HEADER_PATTERN,
    # "reply posted on <date> @ <time> by AUTHOR" / "Topic started on
    # <date>\n@ <time> by AUTHOR" -- newer skins, always has "by".
    r'^(?:reply posted on|topic started on|posted on)\b[\s\S]{0,40}?\bby\s*\n?[^\n"]{0,60}\n?',
    # quote/reply headers -- strip the header line, leave the quoted/reply
    # text that follows (Nash: "those top lines ... should be taken out as
    # metadata", not the content underneath them). \s* (not a literal
    # space) between "reply to" and "post by" because some captures have
    # them on separate lines ("reply to\npost by X").
    # [^\n"] (not just [^\n]) so a quote-wrapped reference to one of these
    # phrases inside someone's own sentence -- e.g. someone writing
    # 'Like i said to you on "reply posted on ... by X" Page 52, ...' while
    # discussing another post, not actually replying -- stops at the
    # closing quote instead of eating genuine follow-on prose past it.
    r'reply to\s*\n?\s*(this\s*)?post\s+by[^\n"]{0,60}',
    r'originally posted by[^\n"]{0,60}',
    r'a reply to:\s*[^\n"]{0,60}',
    # site-chrome footers -- literal phrases, not loose substrings (bare
    # "advertising supported" showed up as real discussion content in one
    # sample row, so match the full sentence only)
    r'copyright\s*&\s*usage',
    r'AboveTopSecret\.com is advertising supported\.',
    r'reply to this post:',
    # edit-note trailer (already captured into edit_note/edited above --
    # this just removes it from body). Date format varies wildly across
    # captures so match anything short non-greedily up to "because:"
    # rather than trying to parse the date.
    r'edit on [\s\S]{0,100}?because:\s*(\([^)\n]{0,80}\)|[^\n]{0,80})',
    EDIT_NOTE_PATTERN,  # bracket-only variant, no "because" clause
    # sequential post-number footer, e.g. "Post Number: 1332313\n(post id:
    # 1354206)" -- the post id half is already redundant with the post_id
    # column; the sequence number itself isn't captured anywhere but has
    # no real analytical value on its own, so this is stripped, not extracted.
    r'Post Number:\s*\d+\s*\n?\s*\(post id:\s*\d+\)\s*',
]


def main():
    con = duckdb.connect()
    con.execute("SET memory_limit='3GB'; SET threads=3;")

    total = con.execute(f"SELECT count(*) FROM '{INPUT_PATH}'").fetchone()[0]
    print(f"Loaded schema, {total:,} rows in source.")

    # Extract meaningful metadata BEFORE any stripping happens. DuckDB's
    # regexp_extract returns '' (not NULL) on no-match, so every downstream
    # NULL-check has to test for '' explicitly, not IS NULL/IS NOT NULL --
    # missing this the first time around wrongly flagged 100% of rows as
    # edited instead of the real ~7.8%.
    member_title_expr = f"nullif(trim(regexp_replace(regexp_extract(body, '{BARE_HEADER_PATTERN}', 2), '\\n', ', ', 'g')), '')"
    edit_note_expr = f"nullif(regexp_extract(body, '{EDIT_NOTE_PATTERN}', 1), '')"

    expr = "body"
    for pat in STRIP_PATTERNS:
        escaped = pat.replace("'", "''")
        expr = f"regexp_replace({expr}, '{escaped}', '', 'gi')"
    # collapse whitespace left behind by stripped spans
    expr = f"trim(regexp_replace(regexp_replace({expr}, '[ \\t]{{2,}}', ' ', 'g'), '\\n{{3,}}', chr(10) || chr(10), 'g'))"

    print("Running full-corpus clean + metadata extraction (single streaming DuckDB pass)...")
    t0 = time.time()
    con.execute(f"""
        COPY (
            SELECT
                thread_id, thread_title, page_num, post_id, author,
                raw_timestamp, body, {expr} AS body_clean,
                {member_title_expr} AS member_title,
                regexp_matches(body, '{EDIT_NOTE_PATTERN}') AS edited,
                {edit_note_expr} AS edit_note,
                starred, reply_to_authors, reply_to_post_ids, quoted_texts,
                star_count, engagement_z
            FROM '{INPUT_PATH}'
        ) TO '{OUTPUT_PATH}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    print(f"Wrote {OUTPUT_PATH} in {time.time()-t0:.1f}s")

    print("\n--- Verification ---")
    changed = con.execute(f"SELECT count(*) FROM '{OUTPUT_PATH}' WHERE body_clean != body").fetchone()[0]
    print(f"Rows changed: {changed:,} / {total:,} ({100*changed/total:.1f}%)")

    n_titles = con.execute(f"SELECT count(*) FROM '{OUTPUT_PATH}' WHERE member_title IS NOT NULL").fetchone()[0]
    print(f"Rows with a captured member_title: {n_titles:,}")

    n_edited = con.execute(f"SELECT count(*) FROM '{OUTPUT_PATH}' WHERE edited").fetchone()[0]
    print(f"Rows flagged edited: {n_edited:,}")

    avg_delta = con.execute(f"""
        SELECT avg(length(body) - length(body_clean))
        FROM '{OUTPUT_PATH}' WHERE body_clean != body
    """).fetchone()[0]
    print(f"Avg chars stripped per changed row: {avg_delta:.1f}")

    empty_after = con.execute(f"""
        SELECT count(*) FROM '{OUTPUT_PATH}'
        WHERE length(trim(body_clean)) = 0 AND length(trim(body)) > 0
    """).fetchone()[0]
    print(f"Rows now EMPTY after cleaning (was non-empty): {empty_after:,}")

    print("\n--- 8 before/after spot checks (rows that changed) ---")
    sample = con.execute(f"""
        SELECT body, body_clean, member_title, edited, edit_note FROM '{OUTPUT_PATH}'
        WHERE body_clean != body
        USING SAMPLE 8
    """).fetchdf()
    for i, row in sample.iterrows():
        print(f"\n[{i}] BEFORE: {row['body'][:180]!r}")
        print(f"[{i}] AFTER : {row['body_clean'][:180]!r}")
        if row['member_title']:
            print(f"[{i}] member_title: {row['member_title']!r}")
        if row['edited']:
            print(f"[{i}] edit_note: {row['edit_note']!r}")


if __name__ == '__main__':
    main()
