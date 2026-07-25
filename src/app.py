#!/usr/bin/env python
import os
import sys
import sqlite3
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
DB_PATH = "data/processed/ats_comments.db"

def get_db_connection():
    if not os.path.exists(DB_PATH):
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def build_thread_summary_if_needed(conn):
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS thread_summary (
        thread_id INTEGER PRIMARY KEY,
        thread_title TEXT,
        post_count INTEGER,
        min_timestamp TEXT,
        max_timestamp TEXT
    );
    """)
    
    # Check if summary is empty or needs populating
    cursor.execute("SELECT count(*) FROM thread_summary")
    if cursor.fetchone()[0] == 0:
        print("Pre-building thread summary table for sub-millisecond sidebar loads...")
        cursor.execute("""
        INSERT INTO thread_summary (thread_id, thread_title, post_count, min_timestamp, max_timestamp)
        SELECT 
            thread_id, 
            thread_title, 
            count(*) as post_count, 
            min(raw_timestamp) as min_timestamp, 
            max(raw_timestamp) as max_timestamp
        FROM comments
        GROUP BY thread_id
        """)
        conn.commit()
        print("Thread summary built successfully!")

@app.route('/')
def index():
    # Make sure DB and thread summaries are built
    conn = get_db_connection()
    if conn:
        try:
            build_thread_summary_if_needed(conn)
            conn.close()
        except Exception as e:
            print(f"Warning: could not build summary: {e}", file=sys.stderr)
    return render_template('index.html')

@app.route('/api/stats')
def api_stats():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database not initialized. Please run indexing first."}), 500
        
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT count(*) FROM comments")
        total_comments = cursor.fetchone()[0]
        
        cursor.execute("SELECT count(distinct thread_id) FROM comments")
        total_threads = cursor.fetchone()[0]
        
        cursor.execute("SELECT count(distinct author) FROM comments")
        total_authors = cursor.fetchone()[0]
        
        db_size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
        
        return jsonify({
            "total_comments": total_comments,
            "total_threads": total_threads,
            "total_authors": total_authors,
            "db_size_mb": round(db_size_mb, 2),
            "status": "online"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/threads')
def api_threads():
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    search = request.args.get('search', '').strip()
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"threads": [], "total_pages": 0})
        
    cursor = conn.cursor()
    offset = (page - 1) * per_page
    
    try:
        build_thread_summary_if_needed(conn)
        
        if search:
            # Query with search filter
            cursor.execute("""
            SELECT thread_id, thread_title, post_count, min_timestamp, max_timestamp 
            FROM thread_summary 
            WHERE thread_title LIKE ? OR CAST(thread_id AS TEXT) LIKE ?
            ORDER BY post_count DESC
            LIMIT ? OFFSET ?
            """, (f"%{search}%", f"%{search}%", per_page, offset))
            
            threads = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute("""
            SELECT count(*) FROM thread_summary 
            WHERE thread_title LIKE ? OR CAST(thread_id AS TEXT) LIKE ?
            """, (f"%{search}%", f"%{search}%"))
            total_threads = cursor.fetchone()[0]
        else:
            # Query standard summary index
            cursor.execute("""
            SELECT thread_id, thread_title, post_count, min_timestamp, max_timestamp 
            FROM thread_summary 
            ORDER BY thread_id ASC
            LIMIT ? OFFSET ?
            """, (per_page, offset))
            
            threads = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute("SELECT count(*) FROM thread_summary")
            total_threads = cursor.fetchone()[0]
            
        total_pages = (total_threads + per_page - 1) // per_page
        
        return jsonify({
            "threads": threads,
            "page": page,
            "per_page": per_page,
            "total_threads": total_threads,
            "total_pages": total_pages
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/thread/<int:thread_id>')
def api_thread(thread_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database not initialized"}), 500
        
    cursor = conn.cursor()
    try:
        cursor.execute("""
        SELECT thread_id, thread_title, page_num, post_id, author, raw_timestamp, body, starred, reply_to_authors, reply_to_post_ids
        FROM comments 
        WHERE thread_id = ?
        ORDER BY CAST(post_id AS INTEGER) ASC
        """, (thread_id,))
        
        posts = []
        for row in cursor.fetchall():
            post_dict = dict(row)
            # Unpack pipe-separated strings back into lists
            post_dict['reply_to_authors'] = post_dict['reply_to_authors'].split('|') if post_dict['reply_to_authors'] else []
            post_dict['reply_to_post_ids'] = post_dict['reply_to_post_ids'].split('|') if post_dict['reply_to_post_ids'] else []
            posts.append(post_dict)
            
        if not posts:
            return jsonify({"error": "Thread not found"}), 404
            
        return jsonify({
            "thread_id": thread_id,
            "thread_title": posts[0]["thread_title"],
            "posts": posts
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').strip()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    
    if not query:
        return jsonify({"results": [], "total_results": 0})
        
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database not initialized"}), 500
        
    cursor = conn.cursor()
    offset = (page - 1) * per_page
    
    try:
        # Full-Text Search with snippet formatting using FTS5
        cursor.execute("""
        SELECT 
            c.thread_id, 
            c.thread_title, 
            c.post_id, 
            c.author, 
            c.raw_timestamp, 
            snippet(comments_fts, 3, '<mark class="bg-teal-500/30 text-teal-200 px-1 rounded">', '</mark>', '...', 40) as snippet_text
        FROM comments_fts f
        JOIN comments c ON c.rowid = f.rowid
        WHERE comments_fts MATCH ?
        ORDER BY rank
        LIMIT ? OFFSET ?
        """, (query, per_page, offset))
        
        results = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT count(*) FROM comments_fts WHERE comments_fts MATCH ?", (query,))
        total_results = cursor.fetchone()[0]
        total_pages = (total_results + per_page - 1) // per_page
        
        return jsonify({
            "results": results,
            "query": query,
            "page": page,
            "per_page": per_page,
            "total_results": total_results,
            "total_pages": total_pages
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
