# Start here (this is the actual entry point — not ANTIGRAVITY_HANDOFF.md)

Read this whole file (short on purpose). Then run the "first move" block
below before doing anything else. Everything else in this repo — the long
chronological `ANTIGRAVITY_HANDOFF.md`, individual `handoff/*.md` task
docs, `data/experiment_log.jsonl`, `data/infra_map.jsonl` — is detail you
pull on demand, not a queue you read front-to-back. This file exists so a
fresh session doesn't burn its first several tool calls re-deriving state
that's already known.

**Last updated: 2026-08-26, by a Claude Code session.**
If it's been more than ~1 day since that date, treat everything below as
a starting hypothesis, not fact — confirm via the first-move block, don't
skip it just because this file looks current.

## First move — do this in ONE parallel batch, always, no exceptions

1. `ListAgents` — any peer sessions active right now, on this machine.
2. `tail -20 data/session_registry.jsonl` — who's touched what recently,
   what's claimed/running, without needing to reach any of them.
3. `git status && git log --oneline -8` — uncommitted work, commits since
   you last looked.
4. Skim the "Headline state" section below — don't re-derive it if it's
   recent (see the date above); do re-verify anything you're about to
   rely on for a real decision (see CLAUDE.md's verification discipline).

`context_checkpoint` (the Oracle-hosted context-repo MCP) is a **second
line, not first** — it's slower (network round-trip) and can be stale by
a session or two if a peer forgot to write to it. Call it only if
`session_registry.jsonl` doesn't answer your question, or before a big
cross-session decision. Don't make it part of the reflexive first move.

**If `ListAgents` or the registry shows an active peer touching anything
you're about to touch (same VM, same script, same model file): message
them BEFORE starting, not after.** This has caused real GPU/RAM
contention and duplicate work before (see `git log` / handoff docs for
2026-07-28, 2026-08-20 incidents). One `SendMessage` costs nothing;
untangling concurrent writes to the same file/VM costs hours.

## Registering yourself (do this at start AND at wrap-up)

Append one line to `data/session_registry.jsonl` when you start
substantive work, with your best-known session name/id, what you intend
to touch (files, scripts, VMs/Kaggle kernels), and status `active`.
Update or append a second line at wrap-up with status `wrapped` and a
one-line summary + pointer to your handoff doc if you wrote one. Schema
and examples are in the file's own header comment (first line). This is
the single cheapest thing you can do to prevent the next session (or a
concurrent one) from re-deriving what you already know, or colliding
with what you're mid-way through.

## Headline state (2026-08-26) — one line each, NOT the full story

- **Newest work (2026-08-24 to 2026-08-26)**: FP-detector pipeline applied
  to real populations for the first time (real precision only 18.8%, far
  below earlier frontier-judge-only estimates — see
  `handoff/task_2026-08-26_session_handoff_fullcorpus_inference_and_escalation_cascade.md`),
  a v10 fine-tune attempt that looked real (single-split AUC 0.733) but
  failed proper 5-fold CV (honest AUC 0.557, do NOT deploy), the full
  documented-best ensemble+binconf pipeline run for the first time over
  the entire 451,815-row entity-mention corpus, and an escalation-cascade
  context-walk taken from 63.4%→99.99% coverage. **Four new HITL queues
  are unrated and waiting** — see that doc's §6. GPU re-scoring of the
  now-context-complete escalation population has NOT been started yet —
  natural next step.
- **Deadline**: finish compute this week (week of 2026-08-20), write
  8k-12k word honours report over the following 1-2 weeks. Nash's call
  on scope tradeoffs, not the session's — see CLAUDE.md.
- **Stance classifier best validated**: kappa **0.5773** (5-model
  ensemble + frontier escalation, 680-row val). A separate 0.428 number
  exists but is a *different, stage1-only* metric — do not compare the
  two without reading `handoff/task_2026-08-20c_session_handoff_kappa_comparison_gotchas.md`
  first. That doc documents 4 real methodological traps hit this project
  (stale citation, overfit-on-val number, a "held-out" set that was 100%
  in training data, a flipped class index) — **read it before citing or
  comparing ANY kappa number**, not after getting one wrong.
- **Regression headline finding** (whistleblower vs. other-maverick
  stance-traction split): survives author/thread-clustered SEs, still
  "most defensible number in the project." BUT: real unresolved
  discrepancy in the "genuine insider environment" population size
  (N=2,463,379 now vs. historical N=27,312 for the same filter, ~90x
  gap, root cause not found) — don't cite either N without flagging this.
- **ATS cross-platform stance**: blocked on Nash labeling a 99-row blind
  quality-check queue (`data/hitl/queue_ats_stance_quality_check.csv`) —
  cheap, high-leverage, decides whether ATS-vs-Reddit generalization is
  a defensible report claim.
- **As of this writing**: a peer session is running a GPU continuation
  fine-tune on `vm2image-20260810-093317` (entity-type-tag input format
  on `binconf_other015`, ~2.5-3hr job, confirmed via direct SSH no other
  process contending) — do not touch that VM's training job. Check
  `session_registry.jsonl` for current status before assuming it's still
  running or has finished.
- **Open discrepancy, unresolved**: a "v2" restart of
  `score_fp_detector_full_train.py` was reported mid-run (~15:36 VM time)
  by a since-wrapped session, started by neither session active at the
  time — a later direct SSH check found no such process running at all.
  Not established whether it finished, was killed, or the report was a
  misread. See `session_registry.jsonl`'s last line before trusting any
  claim that the FP-detector work is fully done.
- **Session identity note**: two different ID spaces exist for the same
  session — local titles (e.g. "Recent open threads") from
  `list_sessions`/`list_events`, and generated peer names (e.g.
  "conspiracycomments-34") from `ListAgents`/`SendMessage`. Neither is
  stable across reconnects and they don't map 1:1 in an obvious way —
  confirmed the hard way 2026-08-20 (see registry). Match by task content
  (what they say they're touching), not by assuming a name from one space
  means a different session than the same name from the other.
- **Housekeeping open**: three stale `.claude/worktrees/` (superseded,
  ~1 month old, not yet removed — Nash's call); local `git` is 4+ commits
  ahead of `origin/master`, not yet pushed (check current count).

## Where to go next depending on what you're doing

- **Picking up FP-detector / full-corpus / escalation-cascade work** →
  `handoff/task_2026-08-26_session_handoff_fullcorpus_inference_and_escalation_cascade.md`
  (newest). Rate the 4 unrated HITL queues it lists before doing anything
  else in this area.
- **Citing/comparing a kappa number** →
  `handoff/task_2026-08-20c_session_handoff_kappa_comparison_gotchas.md` FIRST.
- **Picking up stance-classifier work** →
  `handoff/task_2026-08-20_session_handoff_paraphrase_stability_and_confidently_wrong.md`
  (newest), then `ANTIGRAVITY_HANDOFF.md`'s "CURRENT STATE" section if
  you need the fuller history.
- **Picking up regression/pure-population work** →
  `handoff/task_2026-08-20b_session_handoff_overnight_audit_and_writing_plan.md`
  §4 (the N discrepancy) and §9 (open questions).
- **A file referenced by a script isn't on disk** →
  `handoff/REMOTE_STORAGE_MAP.md` before assuming it needs rebuilding.
- **Infra facts** (which VM, which project, checkpoint locations) →
  `data/infra_map.jsonl` (tail it, don't re-derive).
- **A specific real number** (kappa, N, AUC, anything quantitative) →
  `data/experiment_log.jsonl` (grep it before trusting a number quoted in
  prose anywhere else — prose docs drift, this log is append-only and
  meant to be the ground truth for numbers specifically).
- **The full chronological narrative, decisions-behind-decisions,
  corrections-to-corrections** → `ANTIGRAVITY_HANDOFF.md`. It is long
  (1300+ lines) and append-only by design — read it when you need *why*,
  not to get oriented. Getting oriented is what this file is for.
- **A specific term/decision/number and you don't know which doc it's
  in** → `python3 tools/query_index.py "<search terms>"` — full-text
  search across every handoff doc, the three structured logs, all git
  commit messages, AND Antigravity's own local task/plan/walkthrough
  history (`~/.gemini/{antigravity,antigravity-ide}/brain/`, filtered to
  task folders mentioning this project — 46 as of first indexing) in one
  shot. `build_project_index.py` rebuilds the underlying SQLite index in
  ~1s if it's stale/missing; the `.db` itself isn't git-tracked, it's a
  derived artifact. For Claude Code session transcripts specifically
  (not covered by this index), use `search_session_transcripts` instead.
- **Live, per-turn activity across ALL currently-running sessions**
  (this is different from the registry above — cheaper, higher-frequency,
  not git-tracked) → `tail -30 data/live_turn_log.jsonl`. Any session
  that's been running long (hours/days) accumulates real context drift
  from wall-clock time — this is how you (or a fresh session) see what
  just happened without scrolling someone else's transcript. Append to
  it yourself after any substantive turn:
  `python3 tools/log_turn.py "<your session label>" "<short note>"`
  (optionally `--touching file1 file2 --tag topic`). Skip pure no-op
  turns; err toward writing for anything that changes state, finds
  something real, or takes meaningful wall-clock time.

## On "why isn't this all just in ANTIGRAVITY_HANDOFF.md"

It was, for a long time, and that's exactly the problem this file fixes:
a single append-only chronological log becomes expensive to read cold
and biases toward whatever's most recent rather than what's actually
load-bearing. `ANTIGRAVITY_HANDOFF.md` is kept as the deep archive (full
narrative, still genuinely useful when you need reasoning history) — but
it is no longer the entry point. If you find yourself about to read it
top-to-bottom "to get oriented," stop — that's this file's job.
