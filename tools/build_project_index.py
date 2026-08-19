"""
Build a searchable local index of this project's durable, file-based
history: every handoff doc, every structured log line (experiment_log,
infra_map, session_registry), and every git commit message. SQLite +
FTS5, rebuilt from source files each run -- the index itself is a
derived artifact, not committed to git (regenerate with this script,
it's cheap, seconds not minutes).

Deliberately scoped to what's actually reachable and durable across
tools/sessions:
- handoff/*.md + ANTIGRAVITY_HANDOFF.md + SESSION_START.md (the prose
  narrative/decision record)
- data/experiment_log.jsonl, data/infra_map.jsonl,
  data/session_registry.jsonl (the structured logs)
- `git log` (every commit message + author + date, project-wide, not
  just this session's)
- Antigravity's own local task history (`task.md`/`implementation_plan.md`/
  `walkthrough.md` per task, under `~/.gemini/antigravity/brain/<uuid>/`
  and `~/.gemini/antigravity-ide/brain/<uuid>/`), filtered to task folders
  that mention this project -- found 2026-08-20, was previously assumed
  inaccessible from here (it isn't; see infra_map.jsonl's
  antigravity_brain_directory entry for the discovery). 45/120 folders in
  the `antigravity` app's brain dir and however many in `antigravity-ide`'s
  match this project as of first indexing. The `antigravity-cli` and
  `antigravity-backup` brain dirs are skipped (smaller, older, look like
  stale mirrors of the two indexed here -- revisit if that assumption
  turns out wrong).

Explicitly NOT covered (know the limits before treating this as "index
of everything"):
- Claude Code session transcripts on this machine -- already separately
  searchable via the ccd_session_mgmt MCP server's
  search_session_transcripts tool (substring search across other
  sessions' full message content). Not duplicated here.
- Anything only ever said in a chat that was never written to a file
  (or, for Antigravity, never became a task.md/walkthrough.md/
  implementation_plan.md -- if Antigravity ever changes its own storage
  format this section will silently stop finding anything, worth an
  occasional sanity check that the antigravity_tasks table isn't empty).

Usage:
    python3 tools/build_project_index.py          # rebuild data/project_index.db
    python3 tools/query_index.py "search terms"    # search it
"""
import json
import re
import sqlite3
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "data" / "project_index.db"


def fresh_db():
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            path TEXT,
            kind TEXT,          -- 'handoff_doc' | 'core_doc'
            mtime TEXT,
            body TEXT
        );
        CREATE VIRTUAL TABLE documents_fts USING fts5(
            path, body, content='documents', content_rowid='id'
        );

        CREATE TABLE experiments (
            id INTEGER PRIMARY KEY,
            date TEXT, category TEXT, name TEXT,
            metric_json TEXT, scope TEXT, status TEXT,
            method_pointer TEXT, source TEXT, artifact_json TEXT,
            raw_json TEXT
        );
        CREATE VIRTUAL TABLE experiments_fts USING fts5(
            name, category, scope, raw_json, content='experiments', content_rowid='id'
        );

        CREATE TABLE infra_facts (
            id INTEGER PRIMARY KEY,
            date TEXT, category TEXT, name TEXT, detail TEXT, status TEXT,
            raw_json TEXT
        );
        CREATE VIRTUAL TABLE infra_facts_fts USING fts5(
            name, category, detail, raw_json, content='infra_facts', content_rowid='id'
        );

        CREATE TABLE session_events (
            id INTEGER PRIMARY KEY,
            date TEXT, session_label TEXT, status TEXT,
            touching_json TEXT, summary TEXT, note TEXT, raw_json TEXT
        );
        CREATE VIRTUAL TABLE session_events_fts USING fts5(
            session_label, summary, touching_json, note, content='session_events', content_rowid='id'
        );

        CREATE TABLE commits (
            id INTEGER PRIMARY KEY,
            hash TEXT, date TEXT, author TEXT, subject TEXT, body TEXT
        );
        CREATE VIRTUAL TABLE commits_fts USING fts5(
            hash, subject, body, content='commits', content_rowid='id'
        );

        CREATE TABLE antigravity_tasks (
            id INTEGER PRIMARY KEY,
            app TEXT,           -- 'antigravity' | 'antigravity-ide'
            task_uuid TEXT,
            file_kind TEXT,     -- 'task' | 'implementation_plan' | 'walkthrough'
            mtime TEXT,
            body TEXT
        );
        CREATE VIRTUAL TABLE antigravity_tasks_fts USING fts5(
            app, task_uuid, file_kind, body, content='antigravity_tasks', content_rowid='id'
        );
        """
    )
    return conn


def index_docs(conn):
    paths = list((REPO_ROOT / "handoff").glob("*.md"))
    for core in ["ANTIGRAVITY_HANDOFF.md", "SESSION_START.md", "CLAUDE.md"]:
        p = REPO_ROOT / core
        if p.exists():
            paths.append(p)
    for p in paths:
        kind = "core_doc" if p.parent == REPO_ROOT else "handoff_doc"
        body = p.read_text(errors="replace")
        mtime = p.stat().st_mtime
        cur = conn.execute(
            "INSERT INTO documents (path, kind, mtime, body) VALUES (?, ?, ?, ?)",
            (str(p.relative_to(REPO_ROOT)), kind, str(mtime), body),
        )
        rid = cur.lastrowid
        conn.execute(
            "INSERT INTO documents_fts (rowid, path, body) VALUES (?, ?, ?)",
            (rid, str(p.relative_to(REPO_ROOT)), body),
        )
    print(f"Indexed {len(paths)} docs.")


def index_jsonl(conn, filename, table, fields):
    path = REPO_ROOT / "data" / filename
    if not path.exists():
        print(f"  ({filename} not found, skipping)")
        return 0
    n = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "_schema" in row:
                continue
            n += 1
    return n


def index_experiment_log(conn):
    path = REPO_ROOT / "data" / "experiment_log.jsonl"
    if not path.exists():
        return
    n = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "_schema" in row:
                continue
            cur = conn.execute(
                "INSERT INTO experiments (date, category, name, metric_json, scope, status, method_pointer, source, artifact_json, raw_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row.get("date"), row.get("category"), row.get("name"),
                    json.dumps(row.get("metric", {})), row.get("scope"),
                    row.get("status"), row.get("method_pointer"), row.get("source"),
                    json.dumps(row.get("artifact", {})), line,
                ),
            )
            rid = cur.lastrowid
            conn.execute(
                "INSERT INTO experiments_fts (rowid, name, category, scope, raw_json) VALUES (?, ?, ?, ?, ?)",
                (rid, row.get("name", ""), row.get("category", ""), row.get("scope", ""), line),
            )
            n += 1
    print(f"Indexed {n} experiment_log.jsonl entries.")


def index_infra_map(conn):
    path = REPO_ROOT / "data" / "infra_map.jsonl"
    if not path.exists():
        return
    n = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "_schema" in row:
                continue
            cur = conn.execute(
                "INSERT INTO infra_facts (date, category, name, detail, status, raw_json) VALUES (?, ?, ?, ?, ?, ?)",
                (row.get("date"), row.get("category"), row.get("name"), row.get("detail"), row.get("status"), line),
            )
            rid = cur.lastrowid
            conn.execute(
                "INSERT INTO infra_facts_fts (rowid, name, category, detail, raw_json) VALUES (?, ?, ?, ?, ?)",
                (rid, row.get("name", ""), row.get("category", ""), row.get("detail", ""), line),
            )
            n += 1
    print(f"Indexed {n} infra_map.jsonl entries.")


def index_session_registry(conn):
    path = REPO_ROOT / "data" / "session_registry.jsonl"
    if not path.exists():
        return
    n = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "_schema" in row:
                continue
            cur = conn.execute(
                "INSERT INTO session_events (date, session_label, status, touching_json, summary, note, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    row.get("date"), row.get("session_label"), row.get("status"),
                    json.dumps(row.get("touching", [])), row.get("summary"), row.get("note"), line,
                ),
            )
            rid = cur.lastrowid
            conn.execute(
                "INSERT INTO session_events_fts (rowid, session_label, summary, touching_json, note) VALUES (?, ?, ?, ?, ?)",
                (rid, row.get("session_label", ""), row.get("summary", ""), json.dumps(row.get("touching", [])), row.get("note") or ""),
            )
            n += 1
    print(f"Indexed {n} session_registry.jsonl entries.")


def index_git_log(conn):
    fmt = "%H%x1f%aI%x1f%an%x1f%s%x1f%b%x1e"
    out = subprocess.run(
        ["git", "log", f"--pretty=format:{fmt}"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    n = 0
    for record in out.split("\x1e"):
        record = record.strip()
        if not record:
            continue
        parts = record.split("\x1f")
        if len(parts) != 5:
            continue
        h, date, author, subject, body = parts
        cur = conn.execute(
            "INSERT INTO commits (hash, date, author, subject, body) VALUES (?, ?, ?, ?, ?)",
            (h, date, author, subject, body),
        )
        rid = cur.lastrowid
        conn.execute(
            "INSERT INTO commits_fts (rowid, hash, subject, body) VALUES (?, ?, ?, ?)",
            (rid, h, subject, body),
        )
        n += 1
    print(f"Indexed {n} git commits.")


ANTIGRAVITY_BRAIN_DIRS = {
    "antigravity": Path.home() / ".gemini" / "antigravity" / "brain",
    "antigravity-ide": Path.home() / ".gemini" / "antigravity-ide" / "brain",
}
ANTIGRAVITY_FILE_KINDS = ["task.md", "implementation_plan.md", "walkthrough.md"]
PROJECT_MARKERS = ["ConspiracyComments", "conspiracycomments"]


def index_antigravity_brain(conn):
    n_folders = 0
    n_files = 0
    for app, brain_dir in ANTIGRAVITY_BRAIN_DIRS.items():
        if not brain_dir.exists():
            continue
        for task_dir in brain_dir.iterdir():
            if not task_dir.is_dir():
                continue
            bodies = {}
            for kind in ANTIGRAVITY_FILE_KINDS:
                fp = task_dir / kind
                if fp.exists():
                    try:
                        bodies[kind] = fp.read_text(errors="replace")
                    except OSError:
                        continue
            if not bodies:
                continue
            combined = "\n".join(bodies.values())
            if not any(marker in combined for marker in PROJECT_MARKERS):
                continue
            n_folders += 1
            for kind, body in bodies.items():
                mtime = str((task_dir / kind).stat().st_mtime)
                cur = conn.execute(
                    "INSERT INTO antigravity_tasks (app, task_uuid, file_kind, mtime, body) VALUES (?, ?, ?, ?, ?)",
                    (app, task_dir.name, kind.replace(".md", ""), mtime, body),
                )
                rid = cur.lastrowid
                conn.execute(
                    "INSERT INTO antigravity_tasks_fts (rowid, app, task_uuid, file_kind, body) VALUES (?, ?, ?, ?, ?)",
                    (rid, app, task_dir.name, kind.replace(".md", ""), body),
                )
                n_files += 1
    print(f"Indexed {n_files} Antigravity task files across {n_folders} task folders (matching this project).")


def main():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = fresh_db()
    index_docs(conn)
    index_experiment_log(conn)
    index_infra_map(conn)
    index_session_registry(conn)
    index_git_log(conn)
    index_antigravity_brain(conn)
    conn.commit()
    conn.close()
    print(f"\nBuilt {DB_PATH.relative_to(REPO_ROOT)}. Query with tools/query_index.py.")


if __name__ == "__main__":
    main()
