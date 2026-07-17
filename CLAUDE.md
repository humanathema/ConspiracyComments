# Start here

This is Tobias Nash's honours thesis project. Read `ANTIGRAVITY_HANDOFF.md`
first — it's short on purpose (guardrails, current verified state, and
an index of open task files in `handoff/`).

## Immediate next task, raised 2026-07-17, not started

`handoff/task_notebook_and_repo_polish.md` — **read this before doing
anything else if picking up fresh work in this repo.** Covers, in order:

1. A wider audit of `ConspiracyMaster_Refactored.ipynb` for dormant-but-
   not-necessarily-obsolete work (not just the spaCy FactAppeal example
   already flagged elsewhere — that was just the first thing that came
   to mind, not a complete list; watch for recency bias, older sections
   are easy to walk past).
2. Notebook cleanup (run cells for visible output, collapse code cells,
   truncate large raw-output dumps) — the repo and this notebook
   specifically have been shared with Nash's supervisor for audit, it
   needs to be presentable.
3. Expanding `README.md` — it's the one markdown file GitHub renders on
   the repo homepage, the only thing a casual visitor sees without
   clicking through. Needs actual findings referenced, not just usage
   instructions.
4. Fixing hardcoded `/Users/nash/...` absolute paths (in
   `utils/file_paths.py` and the notebook's own `BASE` variable) to be
   relative to the repo root, before the next push.

Do this **before** the next `git push` — the path-portability fix
especially needs to land before pushing publicly, not after.
