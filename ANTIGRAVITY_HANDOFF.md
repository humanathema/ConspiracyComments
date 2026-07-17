# Antigravity Handoff — Index

Honours thesis: **"Epistemic Credibility in Online Conspiracy Communities."**
This file is short on purpose. Read it fully before doing anything, then
open exactly one task file from `handoff/` for whatever you're picking up.

**Full session narrative/history** (how every decision below was reached,
including corrections-to-corrections) lives in `handoff/ARCHIVE_full_session_history.md`
and in `git log`. You don't need it to execute a task — only read it if
you need to understand *why*, not just *what*.

## Guardrails — apply to every task, no exceptions

1. **No paid LLM/API calls without explicit sign-off.** A $100 unplanned
   bill already happened once. Free/deterministic methods only (DuckDB,
   regex, spaCy, Wikipedia/Wikidata/Arctic Shift/OpenAlex APIs) unless
   told otherwise.
2. **Never edit or delete anything under `data/raw/`.** If something
   there looks wrong, flag it, don't touch it.
3. **Entity-list judgment calls are not yours to make unsupervised.**
   Deciding whether a person/organization counts as `consensus_expert`
   or `maverick_authority` requires checking how they're actually framed
   in real corpus text (see `handoff/ARCHIVE_full_session_history.md` for
   why — the Ralph Baric case is the canonical example: real scientist,
   but corpus mentions are 100% accusatory, not citations). Produce a
   reviewable candidate list with a blank `decision` column instead of
   deciding and merging. This is the single most common way this project
   has gone wrong.
4. **Never overwrite a file that has real human ratings in it**
   (anything in `data/hitl/queue_*.csv`) without backing it up first and
   verifying row count / rating count are unchanged after.
5. **Before trusting a join, check for duplicate join keys.** This
   project has hit the same join-fanout bug three separate times
   (`empath_scores_full.parquet`, `research_corpus_staged_scores_full21m.parquet`
   both have ~58,669 duplicate `id`s; a HITL-queue migration script hit
   it too). Check `count(*)` vs `count(DISTINCT id)` before and after any
   join, not after something looks wrong.
6. **Report back and stop at task boundaries.** Don't chain into the next
   task or touch the core regression (`src/rerun_refined_regressions_v2.py`)
   based on your own judgment that a prior task's results look good
   enough — that decision belongs to Nash/Claude, not Antigravity.
7. **Never use `git push --force`, never amend a commit that isn't the
   one you just made, never delete a branch.**

## Current verified state (as of 2026-07-17)

- **Posts archive**: recovered (`data/raw/r_conspiracy_posts.jsonl`,
  1.83M posts). `data/processed/thread_quality_metrics.csv` covers all
  of it — this is what fixed the sample-size problem (pure r/conspiracy
  population went from 21K to ~2M comments).
- **`src/consensus_experts_verified.py`**: the authoritative
  `consensus_expert` allowlist. 82 name-variants / ~57 people. Use this,
  never `refine_thesis_models.load_entities_split()`'s own `consensus`
  output (contaminated, kept only for its `canon`/`mavericks` outputs).
- **`src/verified_maverick_additions.py`**: 17 name-variants (WikiLeaks,
  Assange, Manning, Snowden, Ellsberg, Kiriakou) that the automated
  entity-bucketing pipeline never promoted despite a correct weak-hint.
  Merged into the maverick regex in `rerun_refined_regressions_v2.py`
  and `combined_maverick_detector.py`.
- **Current core regression numbers** (`src/rerun_refined_regressions_v2.py`,
  pure r/conspiracy population N=1,985,823): `has_maverick` +0.246
  (p<0.001), `has_consensus_expert` +0.533 (p<0.001), `has_link` -1.052
  (p<0.001). Both entity effects also appear in the r/politics control
  (`has_maverick` even more strongly there — +0.650 — so don't present it
  as r/conspiracy-specific without qualification).
- **`src/attribution_confidence_scorer.py`**: local, deterministic
  evidentiary-function scorer (replaces bare entity-mention co-occurrence
  with ordering/proximity/competing-source logic). Validated, has known
  fixed bugs (appositive-vs-accusation conflict, "made" idiom) — NOT yet
  wired into the core regression, see `handoff/task_attribution_scorer_wiring.md`.
- **Consensus-stance HITL queue** (`data/hitl/queue_consensus_stance.csv`):
  152/240 rated as of this entry. Preliminary read: hostile framing
  outnumbers endorsement ~3:1 among `has_consensus_expert` mentions —
  this may mean the +0.533 coefficient reflects *attacking* consensus
  figures predicting engagement, not citing them approvingly. Not final.
- **Known open data-quality issue, not yet fixed**: ~58,669 duplicate
  `id`s in the two foundational corpus parquet files (0.85% pseudo-
  replication in the actual regression population). Root cause traced
  as far as practical without a large notebook-archaeology effort — see
  `handoff/task_pipeline_lineage_audit.md`.

## Open task files — pick one, read it fully, do only that one

| File | What it is |
|---|---|
| `handoff/task_pipeline_lineage_audit.md` | Trace the duplicate-ID bug through 17 archived notebooks; audit the superseded spaCy FactAppeal approach; regenerate the stale `DATA_MANIFEST.md`. Large — break into pieces. |
| `handoff/task_mainstream_expert_review.md` | Review the 453-name `mainstream_expert_augmented_superset.csv` candidate list (Musk, Duesberg, Chomsky, name-collisions flagged, not resolved); fix the domain/basis_type metadata bug. |
| `handoff/task_source_authority_construct.md` | Build the news-outlet/journal/.gov "authoritative source" construct via NELA-GT + SJR, using `data/processed/institutional_source_candidates.csv` as the seed. Not started. |
| `handoff/task_attribution_scorer_wiring.md` | Finish validating the attribution scorer against human labels, then (only after review) wire it into the core `has_maverick` measure. |
| `handoff/task_consensus_stance_completion.md` | Rate the remaining ~88 comments in the consensus-stance queue, then run the formal stance × traction analysis. |
| `handoff/task_markdown_cleanup.md` | Small: add "superseded, see this handoff" banners to `walkthrough.md`/`research_notes/*.md`, fix two stale details in `README.md`. |
| `handoff/task_notebook_and_repo_polish.md` | **Do before the next `git push`.** Wider dormant-work audit of the master notebook (not just spaCy FactAppeal), notebook cleanup for the now-public/supervisor-shared repo, README expansion, and fixing hardcoded `/Users/nash/...` paths to be portable. |
| `handoff/task_full_project_documentation_audit.md` | Large, read-only. Full inventory of every `src/`/`utils/` file (purpose/status/evidence/confidence) plus a mined narrative history from `ANTIGRAVITY_HANDOFF.md`'s git log and `ARCHIVE_full_session_history.md`, written to a new `handoff/PROJECT_INVENTORY.md`. Every claim needs a citation — this is what makes it cheaply spot-checkable afterward. Has real overlap with `task_pipeline_lineage_audit.md` — read that task's overlap note before starting. |

Each task file is short and self-contained on purpose — if it references
something it doesn't explain, that's a bug in the task file, flag it
rather than guessing.
