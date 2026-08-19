"""
Search the project index built by build_project_index.py. Searches
across all five sources (docs, experiments, infra facts, session
registry, git commits) and prints ranked hits with enough context to
jump to the source.

Usage:
    python3 tools/query_index.py "kappa ensemble"
    python3 tools/query_index.py "clustered SE" --limit 5
"""
import argparse
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "project_index.db"


def fts_query(term):
    # FTS5 default query syntax chokes on bare punctuation/hyphens in a
    # plain phrase search -- wrap in quotes for a straightforward
    # substring-ish phrase match, which is what most callers want.
    return '"' + term.replace('"', '""') + '"'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--limit", type=int, default=8)
    args = ap.parse_args()

    if not DB_PATH.exists():
        print("No index found. Run: python3 tools/build_project_index.py")
        return

    conn = sqlite3.connect(DB_PATH)
    q = fts_query(args.query)

    print(f"=== docs (handoff/*.md, ANTIGRAVITY_HANDOFF.md, SESSION_START.md, CLAUDE.md) ===")
    for path, snippet in conn.execute(
        "SELECT path, snippet(documents_fts, 1, '>>>', '<<<', ' ... ', 20) "
        "FROM documents_fts WHERE documents_fts MATCH ? ORDER BY rank LIMIT ?",
        (q, args.limit),
    ):
        print(f"  [{path}]")
        print(f"    {snippet.strip()}")

    print(f"\n=== experiments (data/experiment_log.jsonl) ===")
    for name, category, scope, snippet in conn.execute(
        "SELECT e.name, e.category, e.scope, snippet(experiments_fts, 3, '>>>', '<<<', ' ... ', 25) "
        "FROM experiments_fts JOIN experiments e ON e.id = experiments_fts.rowid "
        "WHERE experiments_fts MATCH ? ORDER BY rank LIMIT ?",
        (q, args.limit),
    ):
        print(f"  [{category}/{name}] scope={scope}")
        print(f"    {snippet.strip()}")

    print(f"\n=== infra facts (data/infra_map.jsonl) ===")
    for name, category, snippet in conn.execute(
        "SELECT i.name, i.category, snippet(infra_facts_fts, 2, '>>>', '<<<', ' ... ', 25) "
        "FROM infra_facts_fts JOIN infra_facts i ON i.id = infra_facts_fts.rowid "
        "WHERE infra_facts_fts MATCH ? ORDER BY rank LIMIT ?",
        (q, args.limit),
    ):
        print(f"  [{category}/{name}]")
        print(f"    {snippet.strip()}")

    print(f"\n=== session registry (data/session_registry.jsonl) ===")
    for label, date, snippet in conn.execute(
        "SELECT s.session_label, s.date, snippet(session_events_fts, 1, '>>>', '<<<', ' ... ', 25) "
        "FROM session_events_fts JOIN session_events s ON s.id = session_events_fts.rowid "
        "WHERE session_events_fts MATCH ? ORDER BY rank LIMIT ?",
        (q, args.limit),
    ):
        print(f"  [{date}] {label}")
        print(f"    {snippet.strip()}")

    print(f"\n=== git commits ===")
    for hsh, date, subject in conn.execute(
        "SELECT c.hash, c.date, c.subject "
        "FROM commits_fts JOIN commits c ON c.id = commits_fts.rowid "
        "WHERE commits_fts MATCH ? ORDER BY rank LIMIT ?",
        (q, args.limit),
    ):
        print(f"  {hsh[:8]} ({date[:10]}) {subject}")

    print(f"\n=== Antigravity task history (~/.gemini/*/brain/) ===")
    for app, task_uuid, file_kind, snippet in conn.execute(
        "SELECT a.app, a.task_uuid, a.file_kind, snippet(antigravity_tasks_fts, 3, '>>>', '<<<', ' ... ', 25) "
        "FROM antigravity_tasks_fts JOIN antigravity_tasks a ON a.id = antigravity_tasks_fts.rowid "
        "WHERE antigravity_tasks_fts MATCH ? ORDER BY rank LIMIT ?",
        (q, args.limit),
    ):
        print(f"  [{app}/{task_uuid[:8]}/{file_kind}]")
        print(f"    {snippet.strip()}")


if __name__ == "__main__":
    main()
