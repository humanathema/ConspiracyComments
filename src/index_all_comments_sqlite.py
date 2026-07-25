#!/usr/bin/env python
import os
import sys
import json
import sqlite3
import time

DB_PATH = "data/processed/ats_comments.db"

# List of all files to index in priority order (oldest/largest first)
JSONL_FILES = [
    "data/processed/ats_comments_cc_complete.jsonl",
    "data/processed/ats_comments_legacy_complete.jsonl",
    "data/processed/ats_comments.jsonl"
]

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

def index_all_files():
    print("===============================================================")
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

    batch_size = 10000
    total_added = 0

    for file_path in existing_files:
        print(f"\nStreaming & Indexing {file_path}...")
        file_size_bytes = os.path.getsize(file_path)
        
        batch = []
        file_processed_bytes = 0
        file_added = 0
        file_start_time = time.time()
        last_print_time = file_start_time

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                file_processed_bytes += len(line.encode('utf-8'))
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    post_id = str(item.get("post_id", ""))
                    if not post_id or post_id in indexed_posts:
                        continue
                        
                    # Format list columns into pipe-separated string
                    reply_to_authors = item.get("reply_to_authors", [])
                    if isinstance(reply_to_authors, list):
                        reply_to_authors = "|".join(reply_to_authors)
                        
                    reply_to_post_ids = item.get("reply_to_post_ids", [])
                    if isinstance(reply_to_post_ids, list):
                        reply_to_post_ids = "|".join(reply_to_post_ids)
                        
                    batch.append((
                        item.get("thread_id"),
                        item.get("thread_title"),
                        item.get("page_num"),
                        post_id,
                        item.get("author", "Unknown"),
                        item.get("raw_timestamp", ""),
                        item.get("body", ""),
                        1 if item.get("starred") else 0,
                        reply_to_authors,
                        reply_to_post_ids
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
                        
                    # Print real-time streaming progress
                    now = time.time()
                    if now - last_print_time >= 1.0:
                        last_print_time = now
                        percent = (file_processed_bytes / file_size_bytes) * 100
                        mb_processed = file_processed_bytes / (1024 * 1024)
                        total_mb = file_size_bytes / (1024 * 1024)
                        print(f"  Progress: {mb_processed:.1f}/{total_mb:.1f} MB ({percent:.1f}%) | "
                              f"New Posts Added: {file_added:,}", end="\r", flush=True)
                except Exception:
                    continue

            # Insert any remaining records in last batch
            if batch:
                cursor.executemany("""
                INSERT OR IGNORE INTO comments (
                    thread_id, thread_title, page_num, post_id, author, raw_timestamp, body, starred, reply_to_authors, reply_to_post_ids
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, batch)
                conn.commit()

        duration = time.time() - file_start_time
        print(f"\n  Completed in {duration:.1f}s | Retained {file_added:,} new unique comments.")

    if total_added > 0:
        print("\nOptimizing Full-Text Search index (this may take a few seconds)...")
        cursor.execute("INSERT INTO comments_fts(comments_fts) VALUES('rebuild');")
        conn.commit()
        
    print(f"\nSuccess! Total database records: {len(indexed_posts):,} ({total_added:,} newly indexed)")
    print("===============================================================")
    conn.close()

if __name__ == "__main__":
    index_all_files()
