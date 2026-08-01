# src/serve_drilldown_api.py
"""serve_drilldown_api.py

Read/write API behind the corpus explorer's live drill-down: paginated,
sortable, full-text (no truncation) comment examples for any topic,
entity, domain, or URL, plus monthly time series for any real entity
(not just the static artifact's top 25) and for any covered domain/URL
(citation-context stance, see src/build_source_stance.py). Also serves
the fuzzy topic-fit rating workflow (GET current ratings, POST new ones)
and outlier manual assignment.

WAL journal mode and 5s busy-timeouts are enabled programmatically
for concurrency safeguards. Outlier suggestions use a zero-dependency,
memory-safe TF-IDF keyword representation overlap + live kNN boost.

Stdlib only (sqlite3 + http.server).
"""
import argparse
import csv
import json
import os
import re
import sqlite3
import duckdb
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HOST = "0.0.0.0"
PORT = 8420
TOKEN = ""
DB_PATH = "data/processed/drilldown.sqlite"

ALLOWED_SORT = {
    "topic_examples": {"upvotes", "char_length", "date"},
    "entity_examples": {"upvotes", "p_hostile", "p_endorsement"},
    "domain_examples": {"upvotes", "p_hostile", "p_endorsement"},
    "url_examples": {"upvotes", "p_hostile", "p_endorsement"},
}

TOPIC_FIT_RATINGS = {"clearly_fits", "lean_fits", "unsure", "lean_doesnt_fit", "clearly_doesnt_fit"}
TOPICS_SUMMARY = []


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode programmatically on connection retrieval
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def load_topics_summary():
    global TOPICS_SUMMARY
    summary_path = "data/processed/topics_summary.json"
    if os.path.exists(summary_path):
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Exclude Outliers (Topic -1) from suggestions list
            TOPICS_SUMMARY = [t for t in data if t.get("Topic") != -1]
            print(f"Loaded {len(TOPICS_SUMMARY)} topics from {summary_path} for suggestions.")
        except Exception as e:
            print(f"⚠️ Warning: Could not load topics_summary.json: {e}")
    else:
        print(f"⚠️ Warning: topics_summary.json not found at {summary_path}")


def query_examples(table, key_col, key_val, sort, direction, offset, limit, rater=None):
    if sort not in ALLOWED_SORT[table]:
        sort = "upvotes"
    direction = "ASC" if direction == "asc" else "DESC"
    rater = rater or "nash"
    conn = get_conn()
    try:
        if table == "entity_examples":
            sources = [r[0] for r in conn.execute("SELECT source_key FROM entity_merges WHERE lower(target_key) = lower(?)", (key_val,)).fetchall()]
            all_keys = [k.lower().strip() for k in ([key_val] + sources)]
            placeholders = ",".join("?" for _ in all_keys)
            
            total = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {key_col} IN ({placeholders})", all_keys
            ).fetchone()[0]
            
            rows = conn.execute(
                f"SELECT t.* FROM {table} t WHERE t.{key_col} IN ({placeholders}) ORDER BY t.{sort} {direction} LIMIT ? OFFSET ?",
                all_keys + [limit, offset],
            ).fetchall()
        else:
            total = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {key_col} = ?", (key_val,)
            ).fetchone()[0]
            
            if table == "topic_examples":
                rows = conn.execute(
                    f"SELECT t.*, r.rating, r.note AS rating_note FROM {table} t "
                    f"LEFT JOIN topic_fit_ratings r ON r.comment_id = t.comment_id AND r.topic_name = t.topic_name AND r.rater = ? "
                    f"WHERE t.{key_col} = ? ORDER BY t.{sort} {direction} LIMIT ? OFFSET ?",
                    (rater, key_val, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT t.* FROM {table} t WHERE t.{key_col} = ? ORDER BY t.{sort} {direction} LIMIT ? OFFSET ?",
                    (key_val, limit, offset),
                ).fetchall()
        return {"total": total, "rows": [dict(r) for r in rows]}
    finally:
        conn.close()


def query_ats_search(q, offset, limit):
    # DuckDB reading the parquet directly, not sqlite -- the same 7.15M-row comment
    # table stored raw in sqlite balloons to ~7GB (uncompressed row storage) vs 1.8GB
    # as zstd parquet; querying the parquet in place avoids importing it at all.
    # Path computed at call time (not module load) since DB_PATH is reassigned from
    # --db after this module's top-level code has already run once.
    ats_parquet_path = os.path.join(os.path.dirname(DB_PATH), "ats_comments_browse.parquet")
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='450MB'")
    con.execute("PRAGMA threads=1")
    con.execute("PRAGMA preserve_insertion_order=false")
    
    q_str = q.strip() if q else ""
    if q_str.startswith("thread_id:"):
        try:
            thread_id = int(q_str.split(":")[1].strip())
            total = con.execute(
                f"SELECT COUNT(*) FROM read_parquet('{ats_parquet_path}') WHERE thread_id = ?",
                [thread_id]
            ).fetchone()[0]
            rows = con.execute(
                f"SELECT * FROM read_parquet('{ats_parquet_path}') WHERE thread_id = ? "
                f"ORDER BY starred DESC, hs_prob DESC LIMIT ? OFFSET ?",
                [thread_id, limit, offset]
            ).fetchall()
        except Exception as e:
            print(f"⚠️ Error querying thread_id: {e}")
            total = 0
            rows = []
    elif not q_str:
        # Empty browse query: avoid scanning text entirely, return instant row stream
        total = 7147196
        rows = con.execute(
            f"SELECT * FROM read_parquet('{ats_parquet_path}') LIMIT ? OFFSET ?",
            [limit, offset]
        ).fetchall()
    else:
        like = f"%{q_str}%"
        total = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{ats_parquet_path}') WHERE text LIKE ? OR thread_title LIKE ?",
            [like, like],
        ).fetchone()[0]
        rows = con.execute(
            f"SELECT * FROM read_parquet('{ats_parquet_path}') WHERE text LIKE ? OR thread_title LIKE ? "
            f"ORDER BY starred DESC, hs_prob DESC LIMIT ? OFFSET ?",
            [like, like, limit, offset],
        ).fetchall()
        
    cols = [d[0] for d in con.description]
    con.close()
    return {"total": total, "rows": [dict(zip(cols, r)) for r in rows]}


def query_ats_thread_posts(thread_id, center_post_id, offset, limit):
    # Backs the threaded forum view: a scrollable window of a thread's posts
    # in original page/post order (thread_seq), loaded in chunks so a
    # ~10k-post thread never has to be fetched in one shot. Pass either
    # center_post_id (first load -- centers the window on that post) or
    # offset (subsequent scroll-more calls in either direction).
    thread_view_path = os.path.join(os.path.dirname(DB_PATH), "ats_comments_thread_view.parquet")
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='450MB'")
    con.execute("PRAGMA threads=1")
    con.execute("PRAGMA preserve_insertion_order=false")

    total = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{thread_view_path}') WHERE thread_id = ?",
        [thread_id],
    ).fetchone()[0]

    if center_post_id is not None:
        center_row = con.execute(
            f"SELECT thread_seq FROM read_parquet('{thread_view_path}') WHERE thread_id = ? AND comment_id = ?",
            [thread_id, center_post_id],
        ).fetchone()
        center_seq = center_row[0] if center_row else 0
        offset = max(0, center_seq - limit // 2)

    rows = con.execute(
        f"SELECT * FROM read_parquet('{thread_view_path}') WHERE thread_id = ? "
        f"ORDER BY thread_seq LIMIT ? OFFSET ?",
        [thread_id, limit, offset],
    ).fetchall()
    cols = [d[0] for d in con.description]
    con.close()
    return {"total": total, "offset": offset, "rows": [dict(zip(cols, r)) for r in rows]}


ATS_THREAD_INDEX_SORT = {"total_comments", "thread_title"}


def query_ats_thread_index(q, sort, direction, offset, limit):
    # Backs the ATS forum index -- browse all 339k threads (not just the
    # top 50 by engagement), sortable/paginated, so navigation starts from
    # a real thread list rather than a flat unfiltered comment dump.
    conn = get_conn()
    try:
        sort = sort if sort in ATS_THREAD_INDEX_SORT else "total_comments"
        direction = "ASC" if direction == "asc" else "DESC"
        q_str = (q or "").strip()
        if q_str:
            like = f"%{q_str}%"
            total = conn.execute(
                "SELECT COUNT(*) FROM ats_thread_index WHERE thread_title LIKE ?", (like,)
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM ats_thread_index WHERE thread_title LIKE ? "
                f"ORDER BY {sort} {direction} LIMIT ? OFFSET ?",
                (like, limit, offset),
            ).fetchall()
        else:
            total = conn.execute("SELECT COUNT(*) FROM ats_thread_index").fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM ats_thread_index ORDER BY {sort} {direction} LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return {"total": total, "rows": [dict(r) for r in rows]}
    finally:
        conn.close()


def query_ats_static_table(table_name, limit=1000):
    conn = get_conn()
    try:
        rows = conn.execute(f"SELECT * FROM {table_name} LIMIT ?", (limit,)).fetchall()
        return {"rows": [dict(r) for r in rows]}
    finally:
        conn.close()


def query_topic_rating_summary(topic_name):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT rating, COUNT(*) AS n FROM topic_fit_ratings WHERE topic_name = ? GROUP BY rating",
            (topic_name,),
        ).fetchall()
        return {"counts": {r["rating"]: r["n"] for r in rows}}
    finally:
        conn.close()


def upsert_topic_rating(comment_id, topic_name, rating, note, rater):
    if rating not in TOPIC_FIT_RATINGS:
        raise ValueError(f"rating must be one of {sorted(TOPIC_FIT_RATINGS)}")
    rater = rater or "nash"
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO topic_fit_ratings (comment_id, topic_name, rating, note, rater, rated_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(comment_id, topic_name, rater) DO UPDATE SET rating=excluded.rating, note=excluded.note, rated_at=excluded.rated_at",
            (comment_id, topic_name, rating, note, rater, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def upsert_outlier_assignment(comment_id, original_topic, assigned_topic, rater):
    rater = rater or "nash"
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO outlier_topic_assignments (comment_id, original_topic_name, assigned_topic_name, rater, assigned_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(comment_id, rater) DO UPDATE SET assigned_topic_name=excluded.assigned_topic_name, assigned_at=excluded.assigned_at",
            (comment_id, original_topic, assigned_topic, rater, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def initialize_topic_quality_tables(db_path):
    print("=== Initializing/Migrating Topic Quality Tables ===")
    conn = sqlite3.connect(db_path, timeout=5.0)
    try:
        # 1. Create topic_merges
        conn.execute("""
            CREATE TABLE IF NOT EXISTS topic_merges (
                source_topic TEXT,
                target_topic TEXT,
                decision TEXT DEFAULT 'merge',
                rater TEXT DEFAULT 'nash',
                merged_at TEXT,
                PRIMARY KEY (source_topic, target_topic, rater)
            );
        """)

        # 2. Create topic_near_duplicate_pairs
        conn.execute("""
            CREATE TABLE IF NOT EXISTS topic_near_duplicate_pairs (
                topic_a INTEGER,
                topic_a_name TEXT,
                topic_b INTEGER,
                topic_b_name TEXT,
                centroid_cosine_sim REAL,
                keyword_jaccard REAL
            );
        """)
        
        # Seed topic_near_duplicate_pairs if empty
        row = conn.execute("SELECT COUNT(*) FROM topic_near_duplicate_pairs").fetchone()
        if row[0] == 0:
            csv_path = 'data/processed/topic_near_duplicate_pairs.csv'
            if os.path.exists(csv_path):
                print(f"  Seeding topic_near_duplicate_pairs from {csv_path}...")
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        conn.execute("""
                            INSERT INTO topic_near_duplicate_pairs 
                            (topic_a, topic_a_name, topic_b, topic_b_name, centroid_cosine_sim, keyword_jaccard)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (int(r['topic_a']), r['topic_a_name'], int(r['topic_b']), r['topic_b_name'],
                              float(r['centroid_cosine_sim']), float(r['keyword_jaccard'])))
                print("  Seeded topic_near_duplicate_pairs!")

        # 3. Create topic_central_claims
        conn.execute("""
            CREATE TABLE IF NOT EXISTS topic_central_claims (
                topic_id INTEGER PRIMARY KEY,
                topic_name TEXT,
                n_comments INTEGER,
                top_signature_claims TEXT,
                top_claim_1 TEXT,
                top_claim_1_local_ratio REAL,
                top_claim_2 TEXT,
                top_claim_2_local_ratio REAL,
                top_claim_3 TEXT,
                top_claim_3_local_ratio REAL
            );
        """)
        
        # Seed topic_central_claims if empty
        row = conn.execute("SELECT COUNT(*) FROM topic_central_claims").fetchone()
        if row[0] == 0:
            csv_path = 'data/processed/topic_central_claims.csv'
            if os.path.exists(csv_path):
                print(f"  Seeding topic_central_claims from {csv_path}...")
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        conn.execute("""
                            INSERT INTO topic_central_claims 
                            (topic_id, topic_name, n_comments, top_signature_claims, top_claim_1, top_claim_1_local_ratio, 
                             top_claim_2, top_claim_2_local_ratio, top_claim_3, top_claim_3_local_ratio)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (int(r['topic_id']), r['topic_name'], int(r['n_comments']), r['top_signature_claims'],
                              r['top_claim_1'], float(r['top_claim_1_local_ratio'] or 0.0),
                              r['top_claim_2'], float(r['top_claim_2_local_ratio'] or 0.0),
                              r['top_claim_3'], float(r['top_claim_3_local_ratio'] or 0.0)))
                print("  Seeded topic_central_claims!")

        # 4. Create topic_claim_review
        conn.execute("""
            CREATE TABLE IF NOT EXISTS topic_claim_review (
                topic_id INTEGER,
                has_claim TEXT, -- 'has_claim' | 'no_coherent_claim' | 'noise_meaningless' | 'unreviewed'
                rater TEXT DEFAULT 'nash',
                reviewed_at TEXT,
                PRIMARY KEY (topic_id, rater)
            );
        """)

        # 5. Create topic_residual_comments
        conn.execute("""
            CREATE TABLE IF NOT EXISTS topic_residual_comments (
                comment_id TEXT PRIMARY KEY,
                text TEXT,
                assigned_topic TEXT,
                assigned_sim REAL,
                best_other_topic TEXT,
                best_other_sim REAL,
                gap REAL
            );
        """)
        
        # Seed topic_residual_comments if empty
        row = conn.execute("SELECT COUNT(*) FROM topic_residual_comments").fetchone()
        if row[0] == 0:
            csv_path = 'data/processed/topic_residual_comments.csv'
            if os.path.exists(csv_path):
                print(f"  Seeding topic_residual_comments from {csv_path}...")
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        conn.execute("""
                            INSERT INTO topic_residual_comments 
                            (comment_id, text, assigned_topic, assigned_sim, best_other_topic, best_other_sim, gap)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (r['comment_id'], r['text'], r['assigned_topic'], float(r['assigned_sim']),
                              r['best_other_topic'], float(r['best_other_sim']), float(r['gap'])))
                print("  Seeded topic_residual_comments!")

        conn.commit()
    except Exception as e:
        print(f"⚠️ Error initializing topic quality tables: {e}")
    finally:
        conn.close()


def query_topic_near_duplicates(rater="nash"):
    rater = rater or "nash"
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT p.*, m.decision, m.rater, m.merged_at
            FROM topic_near_duplicate_pairs p
            LEFT JOIN topic_merges m ON 
              ((m.source_topic = p.topic_a_name AND m.target_topic = p.topic_b_name AND m.rater = ?) OR
               (m.source_topic = p.topic_b_name AND m.target_topic = p.topic_a_name AND m.rater = ?))
        """, (rater, rater)).fetchall()
        return {"pairs": [dict(r) for r in rows]}
    finally:
        conn.close()


def upsert_topic_merge(source_topic, target_topic, decision, rater="nash"):
    rater = rater or "nash"
    if decision not in ["merge", "keep_separate"]:
        raise ValueError("decision must be 'merge' or 'keep_separate'")
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO topic_merges (source_topic, target_topic, decision, rater, merged_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_topic, target_topic, rater) DO UPDATE SET 
              decision=excluded.decision, merged_at=excluded.merged_at
        """, (source_topic, target_topic, decision, rater, datetime.now(timezone.utc).isoformat()))
        conn.commit()
    finally:
        conn.close()


def delete_topic_merge(source_topic, target_topic, rater="nash"):
    rater = rater or "nash"
    conn = get_conn()
    try:
        conn.execute("""
            DELETE FROM topic_merges 
            WHERE (source_topic = ? AND target_topic = ? AND rater = ?)
               OR (source_topic = ? AND target_topic = ? AND rater = ?)
        """, (source_topic, target_topic, rater, target_topic, source_topic, rater))
        conn.commit()
    finally:
        conn.close()


def query_topic_claims(rater="nash"):
    rater = rater or "nash"
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT c.*, COALESCE(r.has_claim, 'unreviewed') AS has_claim, r.reviewed_at
            FROM topic_central_claims c
            LEFT JOIN topic_claim_review r ON r.topic_id = c.topic_id AND r.rater = ?
            ORDER BY c.topic_id
        """, (rater,)).fetchall()
        return {"claims": [dict(r) for r in rows]}
    finally:
        conn.close()


def upsert_topic_claim_review(topic_id, has_claim, rater="nash"):
    rater = rater or "nash"
    if has_claim not in ["has_claim", "no_coherent_claim", "noise_meaningless", "unreviewed"]:
        raise ValueError("has_claim must be 'has_claim', 'no_coherent_claim', 'noise_meaningless', or 'unreviewed'")
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO topic_claim_review (topic_id, has_claim, rater, reviewed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(topic_id, rater) DO UPDATE SET 
              has_claim=excluded.has_claim, reviewed_at=excluded.reviewed_at
        """, (topic_id, has_claim, rater, datetime.now(timezone.utc).isoformat()))
        conn.commit()
    finally:
        conn.close()


def query_topic_residual_comments(offset=0, limit=20):
    conn = get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM topic_residual_comments").fetchone()[0]
        rows = conn.execute("""
            SELECT * FROM topic_residual_comments
            ORDER BY gap ASC
            LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
        return {"total": total, "rows": [dict(r) for r in rows]}
    finally:
        conn.close()


def probe_seed_claims_stage1(topic_name, seeds):
    if not topic_name:
        return {"results": []}
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT comment_id, text, upvotes, char_length, date
            FROM topic_examples
            WHERE topic_name = ?
        """, (topic_name,)).fetchall()
        comments = [dict(r) for r in rows]
    finally:
        conn.close()

    if not comments or not seeds:
        return {"results": []}

    results = []
    for comment in comments:
        text_words = tokenize(comment["text"])
        if not text_words:
            continue
        
        best_seed = ""
        best_score = 0
        overlap_words = []
        
        for seed in seeds:
            seed_words = tokenize(seed)
            overlap = text_words & seed_words
            score = len(overlap)
            if score > best_score:
                best_score = score
                best_seed = seed
                overlap_words = list(overlap)
        
        if best_score > 0:
            results.append({
                "comment_id": comment["comment_id"],
                "text": comment["text"],
                "upvotes": comment["upvotes"],
                "char_length": comment["char_length"],
                "date": comment["date"],
                "matched_seed": best_seed,
                "overlap_score": best_score,
                "overlap_words": overlap_words
            })
    
    results.sort(key=lambda x: (-x["overlap_score"], -x["upvotes"]))
    return {"results": results[:100]}


def query_entity_monthly(entity_key):
    conn = get_conn()
    try:
        sources = [r[0] for r in conn.execute("SELECT source_key FROM entity_merges WHERE lower(target_key) = lower(?)", (entity_key,)).fetchall()]
        all_keys = [k.lower().strip() for k in ([entity_key] + sources)]
        placeholders = ",".join("?" for _ in all_keys)
        
        rows = conn.execute(
            f"SELECT month, construct, SUM(mentions) AS mentions, SUM(n_hostile) AS n_hostile, SUM(n_endorsement) AS n_endorsement, SUM(n_other) AS n_other "
            f"FROM entity_monthly WHERE entity_key IN ({placeholders}) "
            f"GROUP BY month, construct ORDER BY month",
            all_keys,
        ).fetchall()
        return {"rows": [dict(r) for r in rows]}
    finally:
        conn.close()


def query_source_monthly(table, key_col, key_val):
    conn = get_conn()
    try:
        rows = conn.execute(
            f"SELECT month, mentions, n_hostile, n_endorsement, n_other "
            f"FROM {table} WHERE {key_col} = ? ORDER BY month",
            (key_val,),
        ).fetchall()
        return {"rows": [dict(r) for r in rows]}
    finally:
        conn.close()


def tokenize(text):
    if not text:
        return set()
    text = text.lower()
    words = re.findall(r"\b[a-z0-9]{2,}\b", text)
    return set(words)


def get_comment_text(comment_id):
    conn = get_conn()
    try:
        for table in ["topic_examples", "entity_examples", "domain_examples", "url_examples"]:
            row = conn.execute(f"SELECT text FROM {table} WHERE comment_id = ? LIMIT 1", (comment_id,)).fetchone()
            if row:
                return row[0]
        # Check parent_text
        row = conn.execute("SELECT parent_text FROM comment_context WHERE comment_id = ? LIMIT 1", (comment_id,)).fetchone()
        if row and row[0]:
            return row[0]
        return None
    finally:
        conn.close()


def compute_suggestions(comment_id):
    comment_text = get_comment_text(comment_id)
    if not comment_text:
        return []
        
    comment_words = tokenize(comment_text)
    if not comment_words:
        return []
        
    # 1. Base TF-IDF representation match
    scores = {}
    for t in TOPICS_SUMMARY:
        t_name = t["Name"]
        repr_words = t.get("Representation", [])
        score = 0.0
        for idx, word in enumerate(repr_words):
            if word in comment_words:
                score += (10 - idx) # Weight earlier words higher
        if score > 0:
            scores[t_name] = score
            
    # 2. kNN online boosting from manual outlier topic corrections
    conn = get_conn()
    try:
        assignments = conn.execute(
            "SELECT comment_id, assigned_topic_name FROM outlier_topic_assignments"
        ).fetchall()
        
        for ass in assignments:
            ass_comment_id = ass["comment_id"]
            assigned_topic = ass["assigned_topic_name"]
            
            ass_text = get_comment_text(ass_comment_id)
            if ass_text:
                ass_words = tokenize(ass_text)
                intersection = comment_words & ass_words
                union = comment_words | ass_words
                if union:
                    jaccard = len(intersection) / len(union)
                    if jaccard > 0.05:
                        # Boost manually corrected outlier topics proportional to Jaccard overlap
                        boost = jaccard * 15.0
                        scores[assigned_topic] = scores.get(assigned_topic, 0.0) + boost
    except Exception as e:
        print(f"⚠️ kNN Suggestion Error: {e}")
    finally:
        conn.close()
        
    sorted_suggestions = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    results = []
    for t_name, score in sorted_suggestions[:3]:
        topic_id = None
        for t in TOPICS_SUMMARY:
            if t["Name"] == t_name:
                topic_id = t["Topic"]
                break
        results.append({
            "topic_id": topic_id,
            "topic_name": t_name,
            "score": round(score, 2)
        })
    return results


def query_comment_context(comment_id):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT post_id, thread_title, thread_domain, thread_score, parent_id, parent_comment_id, parent_text "
            "FROM comment_context WHERE comment_id = ? LIMIT 1",
            (comment_id,),
        ).fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")

    def is_authorized(self, qs):
        if not TOKEN:
            return True
        token_val = qs.get("token", [None])[0] or self.headers.get("X-Access-Token")
        return token_val == TOKEN

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-Access-Token, Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/api/health":
            self.send_json({"status": "ok"})
            return

        if parsed.path in {"/explorer", "/explorer/", "/explorer/index.html"}:
            try:
                paths_to_try = [
                    "/home/nash/www/explorer/index.html",
                    "index.html",
                    "./index.html"
                ]
                content = None
                for p in paths_to_try:
                    if os.path.exists(p):
                        with open(p, "rb") as f:
                            content = f.read()
                        break
                if content is not None:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                else:
                    self.send_json({"error": "could not find index.html locally"}, status=404)
            except Exception as e:
                self.send_json({"error": "could not load explorer interface", "detail": str(e)}, status=500)
            return

        if parsed.path == "/api/entity_merges":
            conn = get_conn()
            try:
                # Retrieve all merges across all raters
                rows = conn.execute("SELECT source_key, target_key, rater FROM entity_merges").fetchall()
                self.send_json({"merges": [dict(r) for r in rows]})
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            finally:
                conn.close()
            return

        if not self.is_authorized(qs):
            self.send_json({"error": "unauthorized"}, status=401)
            return

        def q1(name, default=None):
            return qs.get(name, [default])[0]

        try:
            offset = int(q1("offset", "0"))
            limit = min(int(q1("limit", "20")), 100)
        except ValueError:
            self.send_json({"error": "invalid offset/limit"}, status=400)
            return

        sort = q1("sort", "upvotes")
        direction = q1("dir", "desc")
        rater = q1("rater", "nash")

        try:
            if parsed.path == "/api/topic_examples":
                topic = q1("topic")
                if not topic:
                    self.send_json({"error": "missing topic"}, status=400)
                    return
                self.send_json(query_examples("topic_examples", "topic_name", topic, sort, direction, offset, limit, rater))
            elif parsed.path == "/api/entity_examples":
                entity = q1("entity")
                if not entity:
                    self.send_json({"error": "missing entity"}, status=400)
                    return
                self.send_json(query_examples("entity_examples", "entity_key", entity.lower(), sort, direction, offset, limit, rater))
            elif parsed.path == "/api/domain_examples":
                domain = q1("domain")
                if not domain:
                    self.send_json({"error": "missing domain"}, status=400)
                    return
                self.send_json(query_examples("domain_examples", "domain", domain, sort, direction, offset, limit, rater))
            elif parsed.path == "/api/url_examples":
                url = q1("url")
                if not url:
                    self.send_json({"error": "missing url"}, status=400)
                    return
                self.send_json(query_examples("url_examples", "url", url, sort, direction, offset, limit, rater))
            elif parsed.path == "/api/entity_monthly":
                entity = q1("entity")
                if not entity:
                    self.send_json({"error": "missing entity"}, status=400)
                    return
                self.send_json(query_entity_monthly(entity.lower()))
            elif parsed.path == "/api/domain_monthly":
                domain = q1("domain")
                if not domain:
                    self.send_json({"error": "missing domain"}, status=400)
                    return
                self.send_json(query_source_monthly("domain_monthly", "domain", domain))
            elif parsed.path == "/api/url_monthly":
                url = q1("url")
                if not url:
                    self.send_json({"error": "missing url"}, status=400)
                    return
                self.send_json(query_source_monthly("url_monthly", "url", url))
            elif parsed.path == "/api/topic_rating_summary":
                topic = q1("topic")
                if not topic:
                    self.send_json({"error": "missing topic"}, status=400)
                    return
                self.send_json(query_topic_rating_summary(topic))
            elif parsed.path == "/api/outlier_suggestions":
                comment_id = q1("comment_id")
                if not comment_id:
                    self.send_json({"error": "missing comment_id"}, status=400)
                    return
                self.send_json({"suggestions": compute_suggestions(comment_id)})
            elif parsed.path == "/api/comment_context":
                comment_id = q1("comment_id")
                if not comment_id:
                    self.send_json({"error": "missing comment_id"}, status=400)
                    return
                ctx = query_comment_context(comment_id)
                if ctx:
                    self.send_json(ctx)
                else:
                    self.send_json({"error": "comment not found in context mapping"}, status=404)
            elif parsed.path == "/api/topic_near_duplicates":
                self.send_json(query_topic_near_duplicates(rater))
            elif parsed.path == "/api/topic_claims":
                self.send_json(query_topic_claims(rater))
            elif parsed.path == "/api/topic_residual_comments":
                self.send_json(query_topic_residual_comments(offset, limit))
            elif parsed.path == "/api/ats_search":
                q = q1("q") or ""
                self.send_json(query_ats_search(q, offset, limit))
            elif parsed.path == "/api/ats_thread_posts":
                thread_id = q1("thread_id")
                if not thread_id:
                    self.send_json({"error": "missing thread_id"}, status=400)
                    return
                center_post_id = q1("center_post_id")
                self.send_json(query_ats_thread_posts(
                    int(thread_id),
                    int(center_post_id) if center_post_id else None,
                    offset, limit,
                ))
            elif parsed.path == "/api/ats_top_threads":
                self.send_json(query_ats_static_table("ats_top_threads"))
            elif parsed.path == "/api/ats_thread_index":
                q = q1("q") or ""
                sort = q1("sort") or "total_comments"
                direction = q1("dir") or "desc"
                self.send_json(query_ats_thread_index(q, sort, direction, offset, limit))
            elif parsed.path == "/api/ats_domains":
                self.send_json(query_ats_static_table("ats_domains"))
            elif parsed.path == "/api/ats_known_entities":
                self.send_json(query_ats_static_table("ats_known_entities"))
            elif parsed.path == "/api/probe_seed_claims_stage1":
                topic_name = q1("topic")
                seeds_json = q1("seeds")
                try:
                    seeds = json.loads(seeds_json) if seeds_json else []
                except ValueError:
                    seeds = []
                self.send_json(probe_seed_claims_stage1(topic_name, seeds))
            else:
                self.send_json({"error": "not found"}, status=404)
        except sqlite3.Error as e:
            self.send_json({"error": "db error", "detail": str(e)}, status=500)

    def do_POST(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if not self.is_authorized(qs):
            self.send_json({"error": "unauthorized"}, status=401)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self.send_json({"error": "invalid JSON body"}, status=400)
            return

        try:
            if parsed.path == "/api/rate_topic_fit":
                comment_id = body.get("comment_id")
                topic_name = body.get("topic_name")
                rating = body.get("rating")
                note = body.get("note", "")
                rater = body.get("rater", "nash")
                
                if not comment_id or not topic_name or not rating:
                    self.send_json({"error": "comment_id, topic_name, and rating are required"}, status=400)
                    return
                upsert_topic_rating(comment_id, topic_name, rating, note, rater)
                self.send_json({"status": "ok"})
                
            elif parsed.path == "/api/assign_outlier_topic":
                comment_id = body.get("comment_id")
                original_topic_name = body.get("original_topic_name")
                assigned_topic_name = body.get("assigned_topic_name")
                rater = body.get("rater", "nash")
                
                if not comment_id or not original_topic_name or not assigned_topic_name:
                    self.send_json({"error": "comment_id, original_topic_name, and assigned_topic_name are required"}, status=400)
                    return
                upsert_outlier_assignment(comment_id, original_topic_name, assigned_topic_name, rater)
                self.send_json({"status": "ok"})
                
            elif parsed.path == "/api/combine_entities":
                target = body.get("target")
                sources = body.get("sources", [])
                rater = body.get("rater", "nash").strip()
                if not rater:
                    rater = "nash"
                
                if not target or not sources:
                    self.send_json({"error": "target and sources are required"}, status=400)
                    return
                
                conn = get_conn()
                try:
                    for s in sources:
                        tk = target.lower().strip()
                        sk = s.lower().strip()
                        if tk == sk or not sk:
                            continue
                        # Remove any existing map where this source is a target to keep flat hierarchies
                        conn.execute("DELETE FROM entity_merges WHERE target_key = ? AND rater = ?", (sk, rater))
                        conn.execute(
                            "INSERT OR REPLACE INTO entity_merges (source_key, target_key, rater) VALUES (?, ?, ?)",
                            (sk, tk, rater),
                        )
                    conn.commit()
                    self.send_json({"status": "ok"})
                finally:
                    conn.close()
                    
            elif parsed.path == "/api/uncombine_entity":
                source = body.get("source")
                rater = body.get("rater", "nash").strip()
                if not rater:
                    rater = "nash"
                if not source:
                    self.send_json({"error": "source is required"}, status=400)
                    return
                
                conn = get_conn()
                try:
                    conn.execute("DELETE FROM entity_merges WHERE source_key = ? AND rater = ?", (source.lower().strip(), rater))
                    conn.commit()
                    self.send_json({"status": "ok"})
                finally:
                    conn.close()
                
            elif parsed.path == "/api/rate_topic_merge":
                source_topic = body.get("source_topic")
                target_topic = body.get("target_topic")
                decision = body.get("decision")
                rater = body.get("rater", "nash")
                if not source_topic or not target_topic or not decision:
                    self.send_json({"error": "source_topic, target_topic, and decision are required"}, status=400)
                    return
                upsert_topic_merge(source_topic, target_topic, decision, rater)
                self.send_json({"status": "ok"})
                
            elif parsed.path == "/api/unmerge_topic":
                source_topic = body.get("source_topic")
                target_topic = body.get("target_topic")
                rater = body.get("rater", "nash")
                if not source_topic or not target_topic:
                    self.send_json({"error": "source_topic and target_topic are required"}, status=400)
                    return
                delete_topic_merge(source_topic, target_topic, rater)
                self.send_json({"status": "ok"})
                
            elif parsed.path == "/api/rate_topic_claim":
                topic_id = body.get("topic_id")
                has_claim = body.get("has_claim")
                rater = body.get("rater", "nash")
                if topic_id is None or not has_claim:
                    self.send_json({"error": "topic_id and has_claim are required"}, status=400)
                    return
                upsert_topic_claim_review(int(topic_id), has_claim, rater)
                self.send_json({"status": "ok"})
                
            else:
                self.send_json({"error": "not found"}, status=404)
        except ValueError as e:
            self.send_json({"error": str(e)}, status=400)
        except sqlite3.Error as e:
            self.send_json({"error": "db error", "detail": str(e)}, status=500)


def main():
    global TOKEN, DB_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--token", default="")
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()
    TOKEN = args.token
    DB_PATH = args.db

    # Initialize/Migrate entity_merges table with rater column if missing
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    try:
        res = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entity_merges'").fetchone()
        if res:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(entity_merges);")
            columns = [row[1] for row in cursor.fetchall()]
            if 'rater' not in columns:
                print("  Upgrading 'entity_merges' table to support 'rater' column...")
                conn.execute("ALTER TABLE entity_merges RENAME TO entity_merges_old;")
                conn.execute("""
                    CREATE TABLE entity_merges (
                        source_key TEXT,
                        target_key TEXT,
                        rater TEXT DEFAULT 'nash',
                        PRIMARY KEY (source_key, rater)
                    );
                """)
                conn.execute("""
                    INSERT INTO entity_merges (source_key, target_key)
                    SELECT source_key, target_key FROM entity_merges_old;
                """)
                conn.execute("DROP TABLE entity_merges_old;")
                print("  Migration of 'entity_merges' table complete!")
        else:
            conn.execute("""
                CREATE TABLE entity_merges (
                    source_key TEXT,
                    target_key TEXT,
                    rater TEXT DEFAULT 'nash',
                    PRIMARY KEY (source_key, rater)
                );
            """)
        conn.commit()
    except Exception as e:
        print(f"⚠️ Error initializing/migrating entity_merges: {e}")
    finally:
        conn.close()

    initialize_topic_quality_tables(DB_PATH)

    load_topics_summary()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Serving drilldown API on {args.host}:{args.port} (db={DB_PATH}, token={'set' if TOKEN else 'NONE'})")
    server.serve_forever()


if __name__ == "__main__":
    main()
