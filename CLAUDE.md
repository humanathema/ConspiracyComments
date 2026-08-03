# Start here

This is Tobias Nash's honours thesis project. Read `ANTIGRAVITY_HANDOFF.md`
first — it's short on purpose (guardrails, current verified state, and
an index of open task files in `handoff/`).

## `handoff/task_notebook_and_repo_polish.md` — superseded (2026-08-03)

Raised 2026-07-17. As of 2026-08-03, marked superseded — a long stance-cascade
and topic-escalation session took priority instead (see
`handoff/task_2026-08-03_session_handoff_stance_cascade_and_topic_escalation.md`).
Original items:

1. Wider audit of `ConspiracyMaster_Refactored.ipynb` for dormant work — superseded.
2. Notebook cleanup (visible output, collapsed cells, truncated dumps) — superseded.
3. Expanding `README.md` with real findings — superseded.
4. ~~Fixing hardcoded `/Users/nash/...` absolute paths~~ — **done** (verified
   2026-08-03: `utils/file_paths.py` has no hardcoded paths left, and the
   notebook's `BASE` is now derived from a `REPO_ROOT` variable). No longer
   a blocker on pushing.

If picking this back up, treat 1-3 as a fresh call rather than resuming — check
current notebook/README state first, since "superseded" here means deprioritized,
not necessarily completed.
