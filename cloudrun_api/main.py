"""cloudrun_api/main.py

Read-side of the corpus explorer's drilldown API, ported from
src/serve_drilldown_api.py to run on Cloud Run reading parquet from a GCS
bucket instead of a local sqlite file. See
handoff/task_cloud_run_gcs_migration.md for the full migration plan and
rationale.

Two different ways of reaching the same bucket, deliberately, for two
different access patterns:

- Bulk parquet reads (topic/entity/domain examples, the ATS corpus, etc.)
  go through Cloud Run's native Cloud Storage volume mount (a read-only
  GCS FUSE mount at GCS_MOUNT_PATH). DuckDB's own `gs://` `credential_chain`
  secret provider is a known, still-open bug (github.com/duckdb/duckdb#14331)
  -- it only tries a local `gcloud` CLI config file ('config' chain), not
  the Cloud Run instance's attached service account, so it can't
  authenticate that way at all. The volume mount sidesteps that entirely:
  Cloud Run handles auth itself via the service's IAM identity, and DuckDB
  just reads what looks like an ordinary local file. Parquet's sequential/
  columnar read pattern suits FUSE fine.

- The FTS search index (ats_search_fts.duckdb) is `ATTACH`ed directly over
  `gs://` instead, using an HMAC key for auth (org policy exception applied
  for this -- see git history/handoff docs). Tried the volume-mount path
  first for this too and it was unusably slow (a single query took minutes
  with no error, never completed within a 60s+ test) -- an FTS lookup does
  many small, scattered random reads across the index's internal tables,
  which generic FUSE handles far worse than parquet's sequential pattern.
  DuckDB's native `gs://` reader does real HTTP range-request fetching
  with its own caching, purpose-built for exactly this access pattern, and
  crucially only fetches the specific pages a query touches -- so a
  container that never receives an /api/ats_search request never pays
  this cost at all, unlike a full eager download at startup.

Write endpoints and anything that joins against the small human-annotation
tables (topic_fit_ratings, entity_merges, outlier_topic_assignments,
topic_merges, topic_claim_review) are intentionally stubbed here — those
tables move to Postgres on the VM in a later, VM-gated migration step, not
this one. Endpoints that need them return well-formed but empty/default
data for now (marked TODO(postgres) below) rather than 404ing, so the
frontend can be pointed here today without every tab breaking, and the
join gets filled in later without changing response shape.

Stdlib only apart from duckdb, matching the project's existing
serve_drilldown_api.py convention.
"""
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import duckdb

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8080"))
TOKEN = os.environ.get("API_TOKEN", "")
GCS_BASE = os.environ.get("GCS_MOUNT_PATH", "/mnt/gcs")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "sapient-zodiac-502400-k2-conspiracy-data")
GCS_HMAC_KEY_ID = os.environ.get("GCS_HMAC_KEY_ID", "")
GCS_HMAC_SECRET = os.environ.get("GCS_HMAC_SECRET", "")
DUCKDB_MEMORY_LIMIT = os.environ.get("DUCKDB_MEMORY_LIMIT", "1536MB")
DUCKDB_THREADS = os.environ.get("DUCKDB_THREADS", "2")

ALLOWED_SORT = {
    "topic_examples": {"upvotes", "char_length", "date"},
    "entity_examples": {"upvotes", "p_hostile", "p_endorsement"},
    "domain_examples": {"upvotes", "p_hostile", "p_endorsement"},
    "url_examples": {"upvotes", "p_hostile", "p_endorsement"},
}

TOPICS_SUMMARY = []

# One connection per container instance, configured once at startup with
# GCS credentials via the attached Cloud Run service account (keyless
# workload identity, no HMAC/key file needed). Per-request handlers get an
# independent cursor via BASE_CON.cursor() -- DuckDB's documented pattern
# for sharing one connection's catalog/attached-db state across threads.
BASE_CON = None

# Separate connection onto the pre-built FTS-indexed database (see
# src/build_ats_search_fts_index.py) for /api/ats_search. A plain
# LIKE '%term%' scan over the 1.8GB ats_comments_browse parquet has no
# index to use -- it decompresses and scans the full `text` column on
# every request (measured: ~78s for one query, the same underlying cost
# that OOM-crashed the old VM, just survivable here instead of fast).
# The FTS extension's inverted index turns that into a real lookup.
FTS_CON = None
FTS_GCS_URI = f"gs://{GCS_BUCKET}/ats_search_fts.duckdb"


def init_duckdb():
    global BASE_CON, FTS_CON
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{DUCKDB_MEMORY_LIMIT}'")
    con.execute(f"PRAGMA threads={DUCKDB_THREADS}")
    con.execute("PRAGMA preserve_insertion_order=false")
    BASE_CON = con

    FTS_CON = duckdb.connect()
    FTS_CON.execute("INSTALL httpfs; LOAD httpfs;")
    FTS_CON.execute("INSTALL fts; LOAD fts;")
    FTS_CON.execute(
        "CREATE SECRET gcs_hmac_secret (TYPE gcs, KEY_ID ?, SECRET ?)",
        [GCS_HMAC_KEY_ID, GCS_HMAC_SECRET],
    )
    FTS_CON.execute(f"ATTACH '{FTS_GCS_URI}' AS fts_db (READ_ONLY)")
    FTS_CON.execute("USE fts_db")
    FTS_CON.execute(f"PRAGMA memory_limit='{DUCKDB_MEMORY_LIMIT}'")
    FTS_CON.execute(f"PRAGMA threads={DUCKDB_THREADS}")

    print(f"DuckDB initialized: mount={GCS_BASE} fts_gcs_uri={FTS_GCS_URI} "
          f"memory_limit={DUCKDB_MEMORY_LIMIT} threads={DUCKDB_THREADS}")


def pq(table):
    """SQL fragment for reading a table's parquet file off the mounted GCS volume."""
    return f"read_parquet('{GCS_BASE}/{table}.parquet')"


def cur():
    return BASE_CON.cursor()


def rows_as_dicts(c, result):
    cols = [d[0] for d in c.description]
    return [dict(zip(cols, r)) for r in result]


STATIC_TABLES_CACHE = {}
ATS_THREAD_INDEX_DEFAULT_CACHE = None


def load_topics_summary():
    global TOPICS_SUMMARY
    c = cur()
    try:
        row = c.execute(f"SELECT * FROM read_json_auto('{GCS_BASE}/topics_summary.json')").fetchall()
        # topics_summary.json is a JSON array of objects; read_json_auto
        # infers the schema and returns one row per array element.
        cols = [d[0] for d in c.description]
        data = [dict(zip(cols, r)) for r in row]
        TOPICS_SUMMARY = [t for t in data if t.get("Topic") != -1]
        print(f"Loaded {len(TOPICS_SUMMARY)} topics from topics_summary.json for suggestions.")
    except Exception as e:
        print(f"WARNING: could not load topics_summary.json: {e}")


def load_static_tables_and_thread_defaults():
    global STATIC_TABLES_CACHE, ATS_THREAD_INDEX_DEFAULT_CACHE
    c = cur()
    for table_name in ["ats_top_threads", "ats_domains", "ats_known_entities"]:
        try:
            rows = c.execute(f"SELECT * FROM {pq(table_name)}").fetchall()
            STATIC_TABLES_CACHE[table_name] = {"rows": rows_as_dicts(c, rows)}
            print(f"Loaded {len(rows)} rows into memory cache for static table: {table_name}")
        except Exception as e:
            print(f"WARNING: could not cache static table {table_name}: {e}")

    try:
        res = query_ats_thread_index(q="", sort="total_comments", direction="desc", offset=0, limit=50)
        ATS_THREAD_INDEX_DEFAULT_CACHE = res
        print(f"Loaded default landing view for ats_thread_index into memory cache")
    except Exception as e:
        print(f"WARNING: could not cache default landing view for ats_thread_index: {e}")



def query_examples(table, key_col, key_val, sort, direction, offset, limit):
    if sort not in ALLOWED_SORT[table]:
        sort = "upvotes"
    direction = "ASC" if direction == "asc" else "DESC"
    c = cur()

    # TODO(postgres): entity_examples originally expands key_val to every
    # source_key that merges into it via the entity_merges overlay table.
    # That table lives in Postgres once step 6/7 of the migration lands;
    # until then this only matches the exact key requested, same as every
    # other example table.
    total = c.execute(
        f"SELECT COUNT(*) FROM {pq(table)} WHERE {key_col} = ?", [key_val]
    ).fetchone()[0]

    if table == "topic_examples":
        # TODO(postgres): originally LEFT JOINs topic_fit_ratings for the
        # current rater's rating/note. Stubbed as NULL until Postgres is
        # wired so the response shape matches what the frontend expects.
        rows = c.execute(
            f"SELECT *, NULL AS rating, NULL AS rating_note FROM {pq(table)} "
            f"WHERE {key_col} = ? ORDER BY {sort} {direction} LIMIT ? OFFSET ?",
            [key_val, limit, offset],
        ).fetchall()
    else:
        rows = c.execute(
            f"SELECT * FROM {pq(table)} WHERE {key_col} = ? ORDER BY {sort} {direction} LIMIT ? OFFSET ?",
            [key_val, limit, offset],
        ).fetchall()
    return {"total": total, "rows": rows_as_dicts(c, rows)}


ATS_SEARCH_COLUMNS = "comment_id, thread_id, thread_title, author, starred, raw_timestamp, text, hs_prob"


def query_ats_search(q, offset, limit):
    # Reads from ats_comments_thread_view, not a separate ats_comments_browse
    # file -- the two were near-duplicate copies of the same 7.15M-row
    # corpus (thread_view is a strict superset, built by joining browse's
    # data with 3 extra columns for the threaded viewer), so keeping both
    # in the bucket was ~3GB of pure duplication. Only the original
    # browse-shaped columns are selected here, since thread_view's extra
    # columns (page_num, reply_to_post_ids, thread_seq) aren't meaningful
    # in a flat search-results context.
    c = cur()
    q_str = q.strip() if q else ""
    if q_str.startswith("thread_id:"):
        try:
            thread_id = int(q_str.split(":")[1].strip())
            total = c.execute(
                f"SELECT COUNT(*) FROM {pq('ats_comments_thread_view')} WHERE thread_id = ?", [thread_id]
            ).fetchone()[0]
            rows = c.execute(
                f"SELECT {ATS_SEARCH_COLUMNS} FROM {pq('ats_comments_thread_view')} WHERE thread_id = ? "
                f"ORDER BY starred DESC, hs_prob DESC LIMIT ? OFFSET ?",
                [thread_id, limit, offset],
            ).fetchall()
        except Exception as e:
            print(f"WARNING: error querying thread_id: {e}")
            total, rows = 0, []
    elif not q_str:
        total = 7147196
        rows = c.execute(
            f"SELECT {ATS_SEARCH_COLUMNS} FROM {pq('ats_comments_thread_view')} LIMIT ? OFFSET ?", [limit, offset]
        ).fetchall()
    else:
        # Real full-text search: use the pre-built FTS index (inverted
        # index over text+thread_title) instead of a LIKE scan over the
        # 1.8GB parquet -- LIKE '%term%' can't use any index and measured
        # ~78s per query; match_bm25 turns it into a real lookup.
        # The FTS database keeps comment_id + starred (small) alongside
        # the index itself, but not the bulky text/thread_title columns
        # (see build_ats_search_fts_index.py for why duplicating those was
        # wasteful) -- ranking/pagination (needs `starred` for the ORDER
        # BY) happens entirely here, cheaply; only the resulting page's
        # full row content gets fetched from the mounted parquet, bounded
        # to `limit` rows, then reordered to match this ranking (measured:
        # ~0.8s total, vs. 78s for the original LIKE scan).
        # match_bm25's own macro body references its supporting tables
        # schema-qualified but NOT catalog-qualified (e.g. just
        # `fts_main_ats_comments.dict`, never `fts_db.fts_main_ats_comments.dict`)
        # -- confirmed by dumping the macro definition. That only resolves
        # if fts_db is the CURRENT default catalog for the session, which
        # `USE` sets -- but a fresh cursor() apparently doesn't inherit
        # that from the connection it was created from, so it has to be
        # re-run on every request's cursor, not just once at startup.
        fc = FTS_CON.cursor()
        fc.execute("USE fts_db")
        total = fc.execute(
            "SELECT COUNT(*) FROM ats_comments WHERE fts_main_ats_comments.match_bm25(comment_id, ?) IS NOT NULL",
            [q_str],
        ).fetchone()[0]
        ranked = fc.execute(
            "SELECT comment_id FROM ("
            "  SELECT comment_id, starred, fts_main_ats_comments.match_bm25(comment_id, ?) AS bm25_score FROM ats_comments"
            ") WHERE bm25_score IS NOT NULL "
            "ORDER BY starred DESC, bm25_score DESC LIMIT ? OFFSET ?",
            [q_str, limit, offset],
        ).fetchall()
        if not ranked:
            return {"total": total, "rows": []}

        ranked_ids = [r[0] for r in ranked]
        placeholders = ",".join("?" for _ in ranked_ids)
        content_rows = c.execute(
            f"SELECT {ATS_SEARCH_COLUMNS} FROM {pq('ats_comments_thread_view')} WHERE comment_id IN ({placeholders})",
            ranked_ids,
        ).fetchall()
        by_id = {d["comment_id"]: d for d in rows_as_dicts(c, content_rows)}
        ordered = [by_id[cid] for cid in ranked_ids if cid in by_id]
        return {"total": total, "rows": ordered}
    return {"total": total, "rows": rows_as_dicts(c, rows)}


def query_ats_thread_posts(thread_id, center_post_id, offset, limit):
    c = cur()
    total = c.execute(
        f"SELECT COUNT(*) FROM {pq('ats_comments_thread_view')} WHERE thread_id = ?", [thread_id]
    ).fetchone()[0]

    if center_post_id is not None:
        center_row = c.execute(
            f"SELECT thread_seq FROM {pq('ats_comments_thread_view')} WHERE thread_id = ? AND comment_id = ?",
            [thread_id, center_post_id],
        ).fetchone()
        center_seq = center_row[0] if center_row else 0
        offset = max(0, center_seq - limit // 2)

    rows = c.execute(
        f"SELECT * FROM {pq('ats_comments_thread_view')} WHERE thread_id = ? "
        f"ORDER BY thread_seq LIMIT ? OFFSET ?",
        [thread_id, limit, offset],
    ).fetchall()
    return {"total": total, "offset": offset, "rows": rows_as_dicts(c, rows)}


def query_ats_thread_index(q, sort, direction, offset, limit):
    c = cur()
    sort = sort if sort in {"total_comments", "thread_title"} else "total_comments"
    direction = "ASC" if direction == "asc" else "DESC"
    q_str = (q or "").strip()

    # Hit memory cache for the default landing view (loads in <1ms!)
    if not q_str and sort == "total_comments" and direction == "DESC" and offset == 0 and limit == 50:
        if ATS_THREAD_INDEX_DEFAULT_CACHE is not None:
            return ATS_THREAD_INDEX_DEFAULT_CACHE

    if q_str:
        like = f"%{q_str}%"
        total = c.execute(
            f"SELECT COUNT(*) FROM {pq('ats_thread_index')} WHERE thread_title ILIKE ?", [like]
        ).fetchone()[0]
        rows = c.execute(
            f"SELECT * FROM {pq('ats_thread_index')} WHERE thread_title ILIKE ? "
            f"ORDER BY {sort} {direction} LIMIT ? OFFSET ?",
            [like, limit, offset],
        ).fetchall()
    else:
        total = c.execute(f"SELECT COUNT(*) FROM {pq('ats_thread_index')}").fetchone()[0]
        rows = c.execute(
            f"SELECT * FROM {pq('ats_thread_index')} "
            f"ORDER BY {sort} {direction} LIMIT ? OFFSET ?",
            [limit, offset],
        ).fetchall()
    return {"total": total, "rows": rows_as_dicts(c, rows)}


def query_static_table(table_name, limit=1000):
    if table_name in STATIC_TABLES_CACHE:
        return {"rows": STATIC_TABLES_CACHE[table_name]["rows"][:limit]}

    c = cur()
    rows = c.execute(f"SELECT * FROM {pq(table_name)} LIMIT ?", [limit]).fetchall()
    return {"rows": rows_as_dicts(c, rows)}


def query_topic_rating_summary(topic_name):
    # TODO(postgres): topic_fit_ratings lives in Postgres from step 6/7.
    return {"counts": {}}


def query_topic_near_duplicates():
    c = cur()
    # TODO(postgres): originally LEFT JOINs topic_merges for decision/rater/merged_at.
    rows = c.execute(
        f"SELECT *, NULL AS decision, NULL AS rater, NULL AS merged_at FROM {pq('topic_near_duplicate_pairs')}"
    ).fetchall()
    return {"pairs": rows_as_dicts(c, rows)}


def query_topic_claims():
    c = cur()
    # TODO(postgres): originally LEFT JOINs topic_claim_review; default
    # 'unreviewed' matches the original COALESCE fallback.
    rows = c.execute(
        f"SELECT *, 'unreviewed' AS has_claim, NULL AS reviewed_at FROM {pq('topic_central_claims')} ORDER BY topic_id"
    ).fetchall()
    return {"claims": rows_as_dicts(c, rows)}


def query_topic_residual_comments(offset, limit):
    c = cur()
    total = c.execute(f"SELECT COUNT(*) FROM {pq('topic_residual_comments')}").fetchone()[0]
    rows = c.execute(
        f"SELECT * FROM {pq('topic_residual_comments')} ORDER BY gap ASC LIMIT ? OFFSET ?",
        [limit, offset],
    ).fetchall()
    return {"total": total, "rows": rows_as_dicts(c, rows)}


def query_entity_monthly(entity_key):
    c = cur()
    # TODO(postgres): originally expands entity_key via entity_merges first (see query_examples note).
    rows = c.execute(
        f"SELECT month, construct, SUM(TRY_CAST(mentions AS BIGINT)) AS mentions, "
        f"SUM(TRY_CAST(n_hostile AS BIGINT)) AS n_hostile, "
        f"SUM(TRY_CAST(n_endorsement AS BIGINT)) AS n_endorsement, "
        f"SUM(TRY_CAST(n_other AS BIGINT)) AS n_other "
        f"FROM {pq('entity_monthly')} WHERE entity_key = ? GROUP BY month, construct ORDER BY month",
        [entity_key],
    ).fetchall()
    return {"rows": rows_as_dicts(c, rows)}


def query_source_monthly(table, key_col, key_val):
    c = cur()
    rows = c.execute(
        f"SELECT month, TRY_CAST(mentions AS BIGINT) AS mentions, "
        f"TRY_CAST(n_hostile AS BIGINT) AS n_hostile, "
        f"TRY_CAST(n_endorsement AS BIGINT) AS n_endorsement, "
        f"TRY_CAST(n_other AS BIGINT) AS n_other "
        f"FROM {pq(table)} WHERE {key_col} = ? ORDER BY month",
        [key_val],
    ).fetchall()
    return {"rows": rows_as_dicts(c, rows)}



def query_comment_context(comment_id):
    c = cur()
    row = c.execute(
        f"SELECT post_id, thread_title, thread_domain, thread_score, parent_id, parent_comment_id, parent_text "
        f"FROM {pq('comment_context')} WHERE comment_id = ? LIMIT 1",
        [comment_id],
    ).fetchone()
    if row is None:
        return None
    cols = [d[0] for d in c.description]
    return dict(zip(cols, row))


def tokenize(text):
    if not text:
        return set()
    return set(re.findall(r"\b[a-z0-9]{2,}\b", text.lower()))


def get_comment_text(comment_id):
    c = cur()
    for table in ["topic_examples", "entity_examples", "domain_examples", "url_examples"]:
        row = c.execute(f"SELECT text FROM {pq(table)} WHERE comment_id = ? LIMIT 1", [comment_id]).fetchone()
        if row:
            return row[0]
    row = c.execute(
        f"SELECT parent_text FROM {pq('comment_context')} WHERE comment_id = ? LIMIT 1", [comment_id]
    ).fetchone()
    return row[0] if row and row[0] else None


def compute_suggestions(comment_id):
    comment_text = get_comment_text(comment_id)
    if not comment_text:
        return []
    comment_words = tokenize(comment_text)
    if not comment_words:
        return []

    scores = {}
    for t in TOPICS_SUMMARY:
        t_name = t["Name"]
        repr_words = t.get("Representation", []) or []
        score = 0.0
        for idx, word in enumerate(repr_words):
            if word in comment_words:
                score += (10 - idx)
        if score > 0:
            scores[t_name] = score

    # TODO(postgres): the original kNN boost from manually-corrected
    # outlier_topic_assignments is dropped until that table exists in
    # Postgres (step 6/7) -- base TF-IDF-style scoring only for now.

    sorted_suggestions = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    results = []
    for t_name, score in sorted_suggestions[:3]:
        topic_id = next((t["Topic"] for t in TOPICS_SUMMARY if t["Name"] == t_name), None)
        results.append({"topic_id": topic_id, "topic_name": t_name, "score": round(score, 2)})
    return results


def probe_seed_claims_stage1(topic_name, seeds):
    if not topic_name:
        return {"results": []}
    c = cur()
    rows = c.execute(
        f"SELECT comment_id, text, upvotes, char_length, date FROM {pq('topic_examples')} WHERE topic_name = ?",
        [topic_name],
    ).fetchall()
    cols = [d[0] for d in c.description]
    comments = [dict(zip(cols, r)) for r in rows]

    if not comments or not seeds:
        return {"results": []}

    results = []
    for comment in comments:
        text_words = tokenize(comment["text"])
        if not text_words:
            continue
        best_seed, best_score, overlap_words = "", 0, []
        for seed in seeds:
            seed_words = tokenize(seed)
            overlap = text_words & seed_words
            if len(overlap) > best_score:
                best_score = len(overlap)
                best_seed = seed
                overlap_words = list(overlap)
        if best_score > 0:
            results.append({
                "comment_id": comment["comment_id"], "text": comment["text"],
                "upvotes": comment["upvotes"], "char_length": comment["char_length"],
                "date": comment["date"], "matched_seed": best_seed,
                "overlap_score": best_score, "overlap_words": overlap_words,
            })
    results.sort(key=lambda x: (-x["overlap_score"], -x["upvotes"]))
    return {"results": results[:100]}


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
                with open("/mnt/gcs/www/explorer/index.html", "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_json({"error": "could not load explorer interface", "detail": str(e)}, status=500)
            return

        if parsed.path == "/api/entity_merges":
            # TODO(postgres): entity_merges lives in Postgres from step 6/7.
            self.send_json({"merges": []})
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

        try:
            if parsed.path == "/api/topic_examples":
                topic = q1("topic")
                if not topic:
                    self.send_json({"error": "missing topic"}, status=400); return
                self.send_json(query_examples("topic_examples", "topic_name", topic, sort, direction, offset, limit))
            elif parsed.path == "/api/entity_examples":
                entity = q1("entity")
                if not entity:
                    self.send_json({"error": "missing entity"}, status=400); return
                self.send_json(query_examples("entity_examples", "entity_key", entity.lower(), sort, direction, offset, limit))
            elif parsed.path == "/api/domain_examples":
                domain = q1("domain")
                if not domain:
                    self.send_json({"error": "missing domain"}, status=400); return
                self.send_json(query_examples("domain_examples", "domain", domain, sort, direction, offset, limit))
            elif parsed.path == "/api/url_examples":
                url = q1("url")
                if not url:
                    self.send_json({"error": "missing url"}, status=400); return
                self.send_json(query_examples("url_examples", "url", url, sort, direction, offset, limit))
            elif parsed.path == "/api/entity_monthly":
                entity = q1("entity")
                if not entity:
                    self.send_json({"error": "missing entity"}, status=400); return
                self.send_json(query_entity_monthly(entity.lower()))
            elif parsed.path == "/api/domain_monthly":
                domain = q1("domain")
                if not domain:
                    self.send_json({"error": "missing domain"}, status=400); return
                self.send_json(query_source_monthly("domain_monthly", "domain", domain))
            elif parsed.path == "/api/url_monthly":
                url = q1("url")
                if not url:
                    self.send_json({"error": "missing url"}, status=400); return
                self.send_json(query_source_monthly("url_monthly", "url", url))
            elif parsed.path == "/api/topic_rating_summary":
                topic = q1("topic")
                if not topic:
                    self.send_json({"error": "missing topic"}, status=400); return
                self.send_json(query_topic_rating_summary(topic))
            elif parsed.path == "/api/outlier_suggestions":
                comment_id = q1("comment_id")
                if not comment_id:
                    self.send_json({"error": "missing comment_id"}, status=400); return
                self.send_json({"suggestions": compute_suggestions(comment_id)})
            elif parsed.path == "/api/comment_context":
                comment_id = q1("comment_id")
                if not comment_id:
                    self.send_json({"error": "missing comment_id"}, status=400); return
                ctx = query_comment_context(comment_id)
                if ctx:
                    self.send_json(ctx)
                else:
                    self.send_json({"error": "comment not found in context mapping"}, status=404)
            elif parsed.path == "/api/topic_near_duplicates":
                self.send_json(query_topic_near_duplicates())
            elif parsed.path == "/api/topic_claims":
                self.send_json(query_topic_claims())
            elif parsed.path == "/api/topic_residual_comments":
                self.send_json(query_topic_residual_comments(offset, limit))
            elif parsed.path == "/api/ats_search":
                self.send_json(query_ats_search(q1("q") or "", offset, limit))
            elif parsed.path == "/api/ats_thread_posts":
                thread_id = q1("thread_id")
                if not thread_id:
                    self.send_json({"error": "missing thread_id"}, status=400); return
                center_post_id = q1("center_post_id")
                self.send_json(query_ats_thread_posts(
                    int(thread_id), int(center_post_id) if center_post_id else None, offset, limit,
                ))
            elif parsed.path == "/api/ats_top_threads":
                self.send_json(query_static_table("ats_top_threads"))
            elif parsed.path == "/api/ats_domains":
                self.send_json(query_static_table("ats_domains"))
            elif parsed.path == "/api/ats_known_entities":
                self.send_json(query_static_table("ats_known_entities"))
            elif parsed.path == "/api/ats_thread_index":
                self.send_json(query_ats_thread_index(
                    q1("q") or "", q1("sort") or "total_comments", q1("dir") or "desc", offset, limit
                ))
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
        except Exception as e:
            self.send_json({"error": "query error", "detail": str(e)}, status=500)

    def do_POST(self):
        # Write endpoints (rate_topic_fit, combine_entities, etc.) move here
        # once Postgres is wired in step 6/7 of the migration -- until then
        # this service is read-only.
        self.send_json({"error": "writes not yet available on this service"}, status=501)


def main():
    init_duckdb()
    load_topics_summary()
    load_static_tables_and_thread_defaults()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Serving Cloud Run read API on {HOST}:{PORT} (mount={GCS_BASE}, token={'set' if TOKEN else 'NONE'})")
    server.serve_forever()


if __name__ == "__main__":
    main()
