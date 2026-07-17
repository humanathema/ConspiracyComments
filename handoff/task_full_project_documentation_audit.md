# Task: Full project inventory + derivation history audit

**Status: staged, not started. Large, read-only — no code, notebook, or
data changes of any kind. Purely a documentation-production task.**

## Why this task exists

Nash's supervisor has repeatedly asked for the project's actual history
to be tracked — approaches that were tried, found flawed, and replaced —
not just the current state. `pipeline_validity_audit.md` (repo root)
already does this well for the **10 currently-active** pipeline
components (8-part questionnaire: what/location/derivation/validation/
limitations/construct validity/analytical impact/next steps) — that
document is current and correct, don't redo it.

What's missing: nothing has ever inventoried **everything else** —
`src/` has 61 Python files, `utils/` has 6; a meaningful fraction are
superseded, experimental-and-abandoned, or just never explained. Two
concrete known examples: an early spaCy-based attribution approach
(predates and was replaced by the current TF-IDF+LogReg FactAppeal
classifier) and an earlier, cruder lexical-scoring pass (predates the
current 5-dimension `LEXICAL` / 11-dimension `EMPATH` split — check
`research_notes/01_pe_and_insiders.md` onward for what that looked
like). There are almost certainly more examples neither Nash nor Claude
currently has a clear list of — that's what this task finds.

## Relationship to other handoff tasks — read this first, don't duplicate

- **`handoff/task_pipeline_lineage_audit.md`** (staged, not started as of
  2026-07-18) has real overlap. Its Piece 2 already scopes the spaCy
  FactAppeal predecessor audit specifically; Piece 3 already scopes a
  general lineage narrative across the 17 archived notebooks. **If that
  task has been completed by the time you pick this one up, read its
  output first and cite it rather than re-deriving.** If it hasn't been
  done, a lighter version of that same ground will naturally surface
  from Part A below — but don't chase that task's Piece 1 (the
  duplicate-ID bug hunt), that's out of scope here and belongs to that
  task specifically.
- **`handoff/task_markdown_cleanup.md`** already identified 8 files
  (`walkthrough.md` + all of `research_notes/*.md`) as superseded, due
  to a contaminated entity list and an invalid control subreddit
  (r/TopMindsOfReddit — confirmed mockery/meta-community, not neutral).
  Treat that as an already-confirmed fact, don't re-derive it — but do
  extend the same "superseded, here's why, here's what replaced it"
  treatment to everything else you find that this task didn't cover.
- **`DATA_MANIFEST.md`** (stale, dated 2026-07-06) inventories
  `data/processed/` *output files*, not code. Useful cross-reference for
  Part A (which script produced which file) but don't trust its
  ACTIVE/legacy/orphan calls without checking — it predates a lot.

## What to actually do

### Part A: Full `src/` and `utils/` inventory

For every `.py` file in `src/` (61 files) and `utils/` (6 files, skip
`__pycache__`), determine:

- **Purpose** — one paragraph, in your own words after actually reading
  the file, not just restating its docstring.
- **Status** — one of:
  - `active` (currently imported/called by the notebook or by another
    active script — verify with `grep`, don't assume)
  - `superseded` (replaced by something else — name what replaced it)
  - `experimental/unfinished` (exists, was never wired into anything live)
  - `dead/orphaned` (no clear current purpose, nothing references it)
- **Evidence** — grep results showing where (if anywhere) it's imported
  or called from; relevant git log dates; or a specific citation from
  `ANTIGRAVITY_HANDOFF.md` / `handoff/ARCHIVE_full_session_history.md`
  that explains it.
- **Confidence** — high/medium/low. If you can't find clear evidence
  either way, say exactly that rather than guessing.

### Part B: Mine the project's own history

- `git log --follow -p ANTIGRAVITY_HANDOFF.md` — 11 revisions as of
  2026-07-18. Each commit message is itself a compressed decision record
  (e.g. "Fix has_maverick blind spot: WikiLeaks/Assange/Manning/Snowden
  never bucketed"). Extract the actual narrative thread across commits,
  don't just list messages.
- `handoff/ARCHIVE_full_session_history.md` (2,402 lines) — the
  uncompressed version of the same history and the primary source for
  "why was X replaced by Y." Read it fully.
- `pipeline_validity_audit.md` — already covers the 10 current
  components in depth; note it exists and is current, don't reproduce
  its content.

### Part C: Write the deliverable

Produce **one new file**: `handoff/PROJECT_INVENTORY.md`, structured as:

1. **A table**, one row per `src/`/`utils/` file: purpose / status /
   evidence / confidence.
2. **"Superseded work" section** — for each superseded approach found
   (spaCy FactAppeal, the earlier lexical-scoring pass, the contaminated
   entity list, r/TopMindsOfReddit-as-control, and anything else
   surfaced by Part A/B): what it was, why it was replaced, what
   replaced it — with a citation (file path + line, git commit hash, or
   an exact quote + location from the archive) specific enough that
   someone can jump straight to the evidence without re-deriving your
   reasoning.
3. **"Open questions / unresolved mysteries" section** — anything you
   genuinely could not determine with confidence. Be specific about
   what's missing (e.g. "no evidence either way for whether X is still
   used by anything"). Don't guess or paper over gaps — an honest gap
   here is more useful than a confident wrong answer, since this
   document exists so a human/Claude can decide what to check next.

**Every claim needs a citation.** This is what makes the document
cheaply verifiable later without anyone having to redo the research —
don't skip citations to save time now.

## Guardrails specific to this task

- Read-only. Do not edit, move, or delete anything in `src/`, `utils/`,
  the notebook, or `data/` — this is documentation, not cleanup.
- Don't make judgment calls about entity-list correctness or which
  approach was objectively "better" beyond what the historical record
  already says. Report what happened and why, cite the source, and put
  anything genuinely ambiguous in the mysteries section instead of
  deciding it yourself — same spirit as this project's existing
  entity-list guardrail (see `ANTIGRAVITY_HANDOFF.md` guardrail 3).
- Report back once Part C's document exists, even if some rows/sections
  are thin. Don't hold the whole thing back hoping to fill every gap
  perfectly first — a flagged gap is a valid, useful result here.
