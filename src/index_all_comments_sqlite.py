#!/usr/bin/env python
import os
import sys
import json
import sqlite3
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.concurrency_utils import atomic_write_json

DB_PATH = "data/processed/ats_comments.db"
OFFSET_STATE_PATH = "data/processed/.ats_index_offsets.json"

# List of all files to index in priority order (oldest/largest first)
JSONL_FILES = [
    "data/processed/ats_comments_cc_complete.jsonl",
    "data/processed/ats_comments_legacy_complete.jsonl",
    "data/processed/ats_comments.jsonl"
]

def load_offsets():
    if os.path.exists(OFFSET_STATE_PATH):
        try:
            with open(OFFSET_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_offsets(offsets):
    atomic_write_json(offsets, OFFSET_STATE_PATH)

def clean_text(s):
    """Strip lone UTF-16 surrogate characters that can end up embedded in scraped
    text via malformed \\uXXXX JSON escapes (a source-data issue from the original
    scrape, not something json.loads itself rejects -- it happily parses an
    unpaired surrogate escape into a str). SQLite's UTF-8 storage can't encode
    those and raises UnicodeEncodeError on insert, so they need to be sanitized
    on the way in rather than caught after the fact -- the string may not be
    string-like at all if the source JSON had a non-string value in this field.
    """
    if not isinstance(s, str):
        return s
    return s.encode("utf-8", errors="replace").decode("utf-8")

def init_db(conn):
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS comments (
        thread_id INTEGER,
        thread_title TEXT,
        page_num INTEGER,
        post_id TEXT PRIMARY KEY,
        author TEXT,
        raw_timestamp TEXT,
        body TEXT,
        starred INTEGER,
        reply_to_authors TEXT,
        reply_to_post_ids TEXT
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_thread ON comments(thread_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_author ON comments(author);")
    
    # Virtual table for Full-Text Search (FTS5)
    cursor.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS comments_fts USING fts5(
        post_id UNINDEXED,
        thread_title,
        author,
        body,
        content='comments',
        content_rowid='rowid'
    );
    """)
    
    # Triggers to keep FTS index synchronized
    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS comments_ai AFTER INSERT ON comments BEGIN
        INSERT INTO comments_fts(rowid, post_id, thread_title, author, body)
        VALUES (new.rowid, new.post_id, new.thread_title, new.author, new.body);
    END;
    """)
    
    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS comments_ad AFTER DELETE ON comments BEGIN
        INSERT INTO comments_fts(comments_fts, rowid, post_id, thread_title, author, body)
        VALUES('delete', old.rowid, old.post_id, old.thread_title, old.author, old.body);
    END;
    """)
    
    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS comments_au AFTER UPDATE ON comments BEGIN
        INSERT INTO comments_fts(comments_fts, rowid, post_id, thread_title, author, body)
        VALUES('delete', old.rowid, old.post_id, old.thread_title, old.author, old.body);
        INSERT INTO comments_fts(rowid, post_id, thread_title, author, body)
        VALUES (new.rowid, new.post_id, new.thread_title, new.author, new.body);
    END;
    """)
    
    conn.commit()

def index_all_files(max_seconds=None):
    run_start_time = time.time()
    time_budget_hit = False

    print("===============================================================")
    if max_seconds:
        print(f"Time budget: will stop cleanly (checkpoint saved, safe to resume) after {max_seconds:,.0f}s.")
    # Check which files actually exist on disk
    existing_files = [f for f in JSONL_FILES if os.path.exists(f)]
    if not existing_files:
        print("Error: No parsed comment files (.jsonl) found to index.", file=sys.stderr)
        print("Please wait for your 'parse' script to complete.", file=sys.stderr)
        return

    print("Discovered files to index:")
    for f in existing_files:
        size_gb = os.path.getsize(f) / (1024 * 1024 * 1024)
        print(f"  - {f} ({size_gb:.3f} GB)")

    print(f"\nInitializing SQLite database at {DB_PATH}...")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    cursor = conn.cursor()
    cursor.execute("SELECT post_id FROM comments")
    indexed_posts = {row[0] for row in cursor.fetchall()}
    print(f"Already indexed in database: {len(indexed_posts):,} posts.")
    # INSERT OR IGNORE (via the post_id PRIMARY KEY) is what actually guarantees
    # no duplicate rows get written -- this in-memory set is a Python-side
    # pre-check so we don't waste time json.loads-ing and batching rows we
    # already have. Skipping it entirely (tried earlier) let a resumed/replayed
    # scan re-attempt an insert for essentially every row in a multi-GB file
    # instead of just the genuinely new tail, which is both why the "new posts"
    # counter went nonsensical and very likely why the machine started swapping
    # heavily again -- millions of pointless batch-insert cycles, not a leak.
    # This is a one-time, bounded cost per run; the byte-offset skip below is
    # what keeps *repeat* runs cheap once a file's fully consumed once.

    offsets = load_offsets()
    batch_size = 10000
    total_added = 0

    for file_path in existing_files:
        file_size_bytes = os.path.getsize(file_path)
        start_offset = offsets.get(file_path, 0)

        if start_offset >= file_size_bytes:
            print(f"\n{file_path}: unchanged since last run ({file_size_bytes/(1024*1024):.1f} MB already fully consumed) -- skipping.")
            continue

        print(f"\nStreaming & Indexing {file_path} (resuming from byte {start_offset:,} of {file_size_bytes:,})...")

        batch = []
        file_processed_bytes = start_offset
        file_added = 0
        file_start_time = time.time()
        last_print_time = file_start_time
        last_checkpoint_time = file_start_time
        last_checkpoint_offset = start_offset

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            f.seek(start_offset)
            while True:
                # readline() (not `for line in f`) -- the iterator protocol uses a
                # read-ahead buffer that disables f.tell() mid-iteration (raises
                # OSError: "telling position disabled by next() call"). readline()
                # doesn't buffer ahead, so tell() stays valid after each call.
                line = f.readline()
                if not line:
                    break
                file_processed_bytes = f.tell()
                line = line.strip()
                if not line:
                    continue

                # Wall-clock checkpoint/print/time-budget checks run on EVERY line read,
                # before the duplicate check below -- these used to sit after the
                # duplicate-skip `continue`, so a long duplicate-heavy stretch (the
                # overwhelming majority of rows in a resumed/replayed scan) skipped
                # straight past them every single iteration and they never fired at all.
                # That's the actual reason checkpoints/progress looked frozen, not disk
                # I/O or memory pressure.
                now = time.time()
                if now - last_checkpoint_time >= 10.0:
                    last_checkpoint_time = now
                    if batch:
                        cursor.executemany("""
                        INSERT OR IGNORE INTO comments (
                            thread_id, thread_title, page_num, post_id, author, raw_timestamp, body, starred, reply_to_authors, reply_to_post_ids
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, batch)
                        conn.commit()
                        batch = []
                    if file_processed_bytes != last_checkpoint_offset:
                        last_checkpoint_offset = file_processed_bytes
                        offsets[file_path] = last_checkpoint_offset
                        save_offsets(offsets)
                    if max_seconds and (now - run_start_time) >= max_seconds:
                        time_budget_hit = True
                        print(f"\n\nTime budget of {max_seconds:,.0f}s reached -- stopping cleanly at "
                              f"byte {file_processed_bytes:,} of {file_path}. Checkpoint saved; "
                              f"re-run this same command to continue from here.")
                        break
                if now - last_print_time >= 1.0:
                    last_print_time = now
                    percent = (file_processed_bytes / file_size_bytes) * 100
                    mb_processed = file_processed_bytes / (1024 * 1024)
                    total_mb = file_size_bytes / (1024 * 1024)
                    print(f"  Progress: {mb_processed:.1f}/{total_mb:.1f} MB ({percent:.1f}%) | "
                          f"New Posts Added: {file_added:,}", end="\r", flush=True)

                try:
                    item = json.loads(line)
                    post_id = clean_text(str(item.get("post_id", "")))
                    if not post_id or post_id in indexed_posts:
                        continue

                    # Format list columns into pipe-separated string
                    reply_to_authors = item.get("reply_to_authors", [])
                    if isinstance(reply_to_authors, list):
                        reply_to_authors = "|".join(str(a) for a in reply_to_authors)

                    reply_to_post_ids = item.get("reply_to_post_ids", [])
                    if isinstance(reply_to_post_ids, list):
                        reply_to_post_ids = "|".join(str(p) for p in reply_to_post_ids)

                    batch.append((
                        item.get("thread_id"),
                        clean_text(item.get("thread_title")),
                        item.get("page_num"),
                        clean_text(post_id),
                        clean_text(item.get("author", "Unknown")),
                        clean_text(item.get("raw_timestamp", "")),
                        clean_text(item.get("body", "")),
                        1 if item.get("starred") else 0,
                        clean_text(reply_to_authors),
                        clean_text(reply_to_post_ids)
                    ))

                    indexed_posts.add(post_id)
                    file_added += 1
                    total_added += 1

                    if len(batch) >= batch_size:
                        cursor.executemany("""
                        INSERT OR IGNORE INTO comments (
                            thread_id, thread_title, page_num, post_id, author, raw_timestamp, body, starred, reply_to_authors, reply_to_post_ids
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, batch)
                        conn.commit()
                        batch = []
                        # Checkpoint the byte offset only after a successful commit, so an
                        # interrupted run resumes from the last safely-written batch, not
                        # from a partially-committed position.
                        last_checkpoint_offset = file_processed_bytes
                        offsets[file_path] = last_checkpoint_offset
                        save_offsets(offsets)
                except Exception:
                    continue

            # Insert any remaining records in last batch (whether we hit EOF or the
            # time budget -- either way, don't leave collected rows uncommitted).
            if batch:
                cursor.executemany("""
                INSERT OR IGNORE INTO comments (
                    thread_id, thread_title, page_num, post_id, author, raw_timestamp, body, starred, reply_to_authors, reply_to_post_ids
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, batch)
                conn.commit()
                offsets[file_path] = file_processed_bytes
                save_offsets(offsets)

        if time_budget_hit:
            # Stopped early on purpose -- do NOT mark this file as fully consumed
            # (file_size_bytes), the loop above already saved the real, honest
            # resume point. Don't touch any other files this run either.
            break

        # Reached genuine EOF for this file -- checkpoint at the full file size so a
        # future run with no new appended content can skip it entirely (the fast path).
        offsets[file_path] = file_size_bytes
        save_offsets(offsets)

        duration = time.time() - file_start_time
        print(f"\n  Completed in {duration:.1f}s | Retained {file_added:,} new unique comments.")

    # No explicit FTS rebuild here -- the comments_ai/comments_ad/comments_au
    # triggers in init_db() already keep comments_fts incrementally synced on
    # every insert. A full 'rebuild' re-tokenizes the entire table from scratch
    # regardless of how little changed, which is what drove this script into
    # heavy swapping on an 8GB machine once the comments table got large.

    final_count = cursor.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
    if time_budget_hit:
        print(f"\nStopped for now (time budget). Total database records so far: {final_count:,} "
              f"({total_added:,} newly indexed this run). Re-run to continue.")
    else:
        print(f"\nSuccess! Total database records: {final_count:,} ({total_added:,} newly indexed)")
    print("===============================================================")
    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index ATS comment jsonl files into a searchable sqlite db.")
    parser.add_argument("--max-seconds", type=float, default=None,
                         help="Stop cleanly (checkpoint saved, safe to resume) after roughly this many "
                              "seconds, instead of running until every file is fully consumed. "
                              "Example: --max-seconds 300 to run in ~5-minute chunks.")
    args = parser.parse_args()
    index_all_files(max_seconds=args.max_seconds)
