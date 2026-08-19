# Start here

This is Tobias Nash's honours thesis project. Read `ANTIGRAVITY_HANDOFF.md`
first — it's short on purpose (guardrails, current verified state, and
an index of open task files in `handoff/`).

## `data/experiment_log.jsonl` — the structured results log, PROJECT-WIDE

This project spans many largely-independent branches (stance classifier,
topic modeling, entity disambiguation, regressions, ATS/BTS ingestion,
embeddings, graph-based topic structure, citation/source-authority work,
and more) — this log is not classifier-specific, it's for ANY quantitative
result anywhere in the project. Found 2026-08-20 the hard way: a real
result (an ensemble+confidence blend, kappa 0.428) existed ONLY as a
one-sentence prose summary in a handoff doc, with no way to verify or
reproduce it later — hours were then spent trying to relocate/reconstruct
it, unsuccessfully.

**Append one line every time you compute or report a real quantitative
result** — a model finishes training, a regression runs, a comparison
gets scored, anything with a number worth citing later. One JSON object
per line, fields:
- `date`, `category` (a short tag for which branch of the project —
  `stance_classifier`, `topic_modeling`, `entity_disambiguation`, etc —
  invent new ones as needed, don't force everything into existing ones),
  `name` (short, specific).
- `artifact`: where the actual model/checkpoint/output file lives
  (local path, VM + path, Kaggle dataset — wherever it actually is).
- `metric`: a flat dict of every number worth keeping, real key names not
  "value1/value2".
- `scope`: the EXACT population/subset/split the metric was computed
  against — this is usually the thing that goes missing first and makes
  a number unreproducible later.
- `method_pointer`: don't restate the method here — point to it (a
  script path, ideally a function/class name too). If the method was
  never saved as a script, say that explicitly rather than leaving the
  field to imply one exists.
- `status`: `done`, `superseded`, `retracted`, or `unverified` (with a
  reason) — so a later session doesn't have to re-discover that a number
  is stale or unrecoverable, it's marked at the point that's discovered.
- `source`: where the number itself is printed/saved (a log file, a CSV,
  a conversation) — separate from `method_pointer`, which is about HOW,
  not WHERE the raw output landed.

This does NOT replace the prose handoff docs in `handoff/` — those are
still where the narrative/reasoning lives (why a decision was made, what
was tried and ruled out, open threads). This log is just the queryable
hard-numbers layer those docs currently bury in prose. When a handoff doc
reports a metric, it should be backed by an entry here too.

## Check for concurrent/recent sessions before assuming you have the full picture

This project routinely has multiple sessions (Claude Code, Antigravity, or
both) active on the same repo/VMs around the same time — found directly
2026-08-20 when a concurrent session had written its own same-day handoff
doc (`handoff/task_2026-08-20c_...`) and modified several `src/*.py` files
I hadn't touched, discovered only because Nash pointed at it, not because
I checked. **At the start of a session, and again before any big
conclusion or handoff write**, cheaply check: `ls -t handoff/*.md | head`
(any doc dated today or very recent that you haven't read?), `git status`
(uncommitted changes you didn't make?), and `git log --oneline -10`
(commits since you last looked?). If a cross-session messaging channel is
available, a peer session may also proactively message you — treat that
as current, not stale. This is one cheap check each time, not a deep
audit — the failure mode being guarded against is asserting a "complete"
picture when a concurrent session already has newer information.

## `data/infra_map.jsonl` — sticky, same format, for infrastructure facts

Same JSONL-append convention as the experiment log above, but for
non-experiment facts that keep getting re-discovered from scratch each
session and shouldn't have to be: which GCP project owns which VM, which
zone, what's actually on its disk, checkpoint locations that don't match
their "obvious" path. Found 2026-08-20 the hard way — over an hour spent
re-deriving a two-project, five-VM infrastructure layout (`gpuincrease`
and `conspiracycomments-gce`, each with a stale us-east/us-central
original and a superseding asia-southeast re-image) that Nash already
knew and had explained before. Append an entry whenever you learn an
infra fact worth not re-learning — same fields as the experiment log
(`date`, `category`, `name`, `detail`, `status`), just a different
subject matter. Both logs are meant to accrete over time, not be
complete now — add what you learn as you learn it.

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
