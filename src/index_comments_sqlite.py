#!/usr/bin/env python
import os
import sys
import json
import sqlite3
import time

DB_PATH = "data/processed/ats_comments.db"
JSONL_PATH = "data/processed/ats_comments_master.jsonl"

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

def index_jsonl():
    if not os.path.exists(JSONL_PATH):
        print(f"Error: JSONL file not found at '{JSONL_PATH}'", file=sys.stderr)
        sys.exit(1)
        
    print(f"Initializing SQLite database at {DB_PATH}...")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    
    # Find existing post IDs to avoid double indexing
    cursor = conn.cursor()
    cursor.execute("SELECT post_id FROM comments")
    indexed_posts = {row[0] for row in cursor.fetchall()}
    print(f"Already indexed: {len(indexed_posts):,} posts.")
    
    print(f"Reading and indexing {JSONL_PATH}...")
    start_time = time.time()
    batch = []
    batch_size = 5000
    added_count = 0
    total_processed = 0
    
    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            total_processed += 1
            try:
                item = json.loads(line)
                post_id = str(item.get("post_id", ""))
                if post_id in indexed_posts:
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
                
                if len(batch) >= batch_size:
                    cursor.executemany("""
                    INSERT OR IGNORE INTO comments (
                        thread_id, thread_title, page_num, post_id, author, raw_timestamp, body, starred, reply_to_authors, reply_to_post_ids
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, batch)
                    conn.commit()
                    added_count += len(batch)
                    print(f"Indexed {added_count:,} new posts...")
                    batch = []
            except Exception as e:
                print(f"Error parsing line {total_processed}: {e}", file=sys.stderr)
                
        if batch:
            cursor.executemany("""
            INSERT OR IGNORE INTO comments (
                thread_id, thread_title, page_num, post_id, author, raw_timestamp, body, starred, reply_to_authors, reply_to_post_ids
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch)
            conn.commit()
            added_count += len(batch)
            
    # Rebuild FTS index if we added new items
    if added_count > 0:
        print("Optimizing Full-Text Search index (this might take a few seconds)...")
        cursor.execute("INSERT INTO comments_fts(comments_fts) VALUES('rebuild');")
        conn.commit()
        
    elapsed = time.time() - start_time
    print(f"\nIndexing finished in {elapsed:.2f} seconds!")
    print(f"Total posts in database: {len(indexed_posts) + added_count:,} ({added_count:,} new additions)")
    
    conn.close()

if __name__ == "__main__":
    index_jsonl()
