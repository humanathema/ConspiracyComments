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
import json
import os
import re
import sqlite3
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

    load_topics_summary()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Serving drilldown API on {args.host}:{args.port} (db={DB_PATH}, token={'set' if TOKEN else 'NONE'})")
    server.serve_forever()


if __name__ == "__main__":
    main()
