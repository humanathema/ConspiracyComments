# Task: Wider notebook audit + public-repo polish (notebook, README, path portability)

**Status: not started. Raised 2026-07-17. This is Claude-instance work
(editorial/judgment calls about what matters, what looks presentable to
a supervisor), not something to hand to Antigravity unsupervised — same
guardrail as the mainstream-expert review.**

**Context that matters**: the repo is now public and has been shared
directly with Nash's academic supervisor for audit purposes, with
`ConspiracyMaster_Refactored.ipynb` specifically linked in that email.
This isn't just internal tooling anymore — a real external reader may
open both the repo and that notebook.

## Part 1: wider dormant-work audit (not just spaCy FactAppeal)

The existing `handoff/task_pipeline_lineage_audit.md` names one
concrete example (the superseded spaCy FactAppeal approach) because
that's what came to mind first when it was raised — Nash's explicit
observation is that this is a **recency-bias problem, not a complete
list**: an audit pass (his or Antigravity's) tends to treat whatever's
most recently touched as ground truth and walk past older work that's
gone dormant without necessarily being obsolete. Don't treat the spaCy
example as the only thing to check.

**Starting point, not a full read**: `ConspiracyMaster_Refactored.ipynb`'s
markdown section headers jump from `## 0. Imports and File Paths` and
`### 2.1 Lexical Scoring Validation` straight to `### 9.1` through
`### 9.10` — sections 1, most of 2, and 3 through 8 have no matching
top-level markdown header in the current notebook. This could mean: (a)
non-standard header formatting my scan missed, (b) genuine content gaps
where documentation was lost during refactoring, or (c) those sections
were deliberately folded into what's now numbered 9.x. Find out which,
and specifically check whether any WORKING analysis got silently dropped
in that renumbering rather than just its heading.

**Method**: for each numbered section/major cell group in the notebook,
ask the same question this task's example already answers for spaCy
FactAppeal: is this (a) still live and feeding the current core
regression, (b) a valid finding that's just not been referenced
recently and should be, or (c) genuinely superseded/abandoned, and if
so why. Cross-reference against `data/processed/` files still marked
`ACTIVE` in the stale `DATA_MANIFEST.md` (see
`handoff/task_pipeline_lineage_audit.md` piece 4 — that manifest itself
needs regenerating, but its current ACTIVE list is still a reasonable
starting inventory of what the notebook touches).

## Part 2: notebook cleanup for the public/supervisor-facing copy

- Run the cells that don't currently have output visible, so someone
  reading the notebook (not executing it) can see real results.
- Collapse code cells where the code itself isn't the point — the
  supervisor audience cares about findings and methodology, not scrolling
  through implementation.
- **Truncate large raw-output dumps** — the spaCy FactAppeal spot-check
  output specifically was flagged as an example of a cell dumping large
  amounts of raw data with no summary; there are likely other cells with
  the same problem (large `.head()` calls with wide dataframes, full
  printed lists, etc.) — check for these broadly, not just that one.
- Goal stated directly by Nash: "I need it to look cool and have some
  good stuff in it" — this means presentable, not necessarily exhaustive.
  Favor a smaller number of clearly-explained, well-supported findings
  over a wall of every cell ever run.

## Part 3: expand README.md for a public audience

Distinct from the small fixes already in `handoff/task_markdown_cleanup.md`
(stale corpus-list detail, stale `src/` description) — this is bigger.
Nash's framing: README.md is **"the one piece of markdown that will
actually be visible to everyday visitors to the repo"** — GitHub renders
it on the repo homepage, so it's the only doc a casual visitor sees
without clicking through. It should include actual findings and pointers
to other markdown files, not just setup/usage instructions. Consider
referencing: the corrected core regression findings (see
`ANTIGRAVITY_HANDOFF.md`'s current-state section for the numbers),
`walkthrough.md` and `research_notes/` (once banner-flagged per
`handoff/task_markdown_cleanup.md`, note them as historical), and the
`mainstream_expert_corpus_briefing (2).md` methodology if it's still
relevant framing for a visitor.

## Part 4: path portability (do this before any push)

**Root cause found**: `utils/file_paths.py`'s `Paths.__init__` hardcodes
`self.base = Path(base or '/Users/nash/Projects/ConspiracyComments/')`
as its default. Separately, `ConspiracyMaster_Refactored.ipynb` also
defines its own `BASE = '/Users/nash/Projects/ConspiracyComments/data/processed/'`
directly (not going through the `Paths` class) — 28 total occurrences of
`/Users/nash` in the notebook file, most likely all downstream of this
one `BASE` assignment via string concatenation, not 28 independent
hardcoded paths.

**Fix, both places**: make the default resolve relative to the repo
root instead of a hardcoded absolute path. Standard practice for this:
`Path(__file__).resolve().parent` walked up to the repo root (robust to
being run from any working directory) for `utils/file_paths.py`, and
either the equivalent notebook-relative approach or a documented
convention of "always run this notebook with the repo root as the
working directory" (simpler, very common for research-code repos, but
worth stating explicitly in the README per Part 3 so a cloner knows).
Nash's question about the repo living inside `~/Projects/` on his own
machine: this doesn't matter once paths are relative to the repo root
itself rather than to `/Users/nash/` specifically — the repo can sit
anywhere on anyone's machine after that fix, no special handling needed
for the fact that it's nested under a personal `Projects/` folder.

Verify after fixing: `grep -c "/Users/nash" ConspiracyMaster_Refactored.ipynb`
should return 0, and a quick smoke-test cell run from a fresh clone (or
at least from a different working directory) should resolve paths
correctly.

## Sequencing

Nash's stated plan: do this work, then run+collapse notebook cells,
THEN push to git. Don't push between these steps — the path-portability
fix in particular should land before any push, not after, since pushing
public with hardcoded personal paths partly defeats the point of fixing
it.
