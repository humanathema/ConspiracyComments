# Task: Fix scope gaps in `handoff/PROJECT_INVENTORY.md`

**Status: not started. Follow-up to `task_full_project_documentation_audit.md`,
which is done but has a confirmed systematic error — read this before
touching the file.**

## Why this task exists

Claude spot-checked `handoff/PROJECT_INVENTORY.md` against actual grep
evidence (2026-07-18) and found the reference-search step had a
systematic blind spot, confirmed by reading the audit script itself
(`~/.gemini/antigravity/brain/*/scratch/scratch_inventory.py`): its
`find_references_in_files()` only checks files ending in `.py`, and its
notebook cross-reference only checks the one hardcoded
`ConspiracyMaster_Refactored.ipynb`. It never searched `notebooks/pipeline/`,
`notebooks/archive/`, `notebooks/legacy_production/`, or
`notebooks/scratchpads/` — all of which contain other `.ipynb` files.

This caused two confirmed, reproducible errors:

- `src/ingestion.py` is labeled `experimental/unfinished, never imported
  by any notebook or script` — **false**. `notebooks/pipeline/01_Data_Ingestion.ipynb`
  literally says "This notebook imports our clean logic from
  `src/ingestion.py`" and does `from src.ingestion import extract_media_titles`.
- `src/network.py` has the identical false claim — **false**.
  `notebooks/pipeline/02_Network_Topology.ipynb` does
  `from src.network import (...)`.

Worse: this same false claim was then promoted into the document's own
**"Unresolved Mysteries" section as Mystery #1** — a search-scope gap
got written up as if it were a genuine unexplained puzzle in the
project's history. It isn't a mystery; the search just never looked in
the right place.

A separate, different problem was also found: `src/classification.py`'s
row claims evidence "Imported in `score_main_corpus_staged.py`" — this
is **also false**. It's actually imported by `src/staged_pipeline.py` and
a root-level `classify_commons_queue.py` script. The *conclusion*
(status: active) happens to be correct, but the *stated evidence* was
fabricated, not derived from an actual grep. Since the citation
requirement exists specifically so claims can be cheaply verified
without redoing the research, a fabricated-but-plausible citation is
worse than no citation — it looks verified without being verified.

## What to actually do

1. **Expand the reference search.** Re-run (or patch and re-run) the
   cross-reference step to search `notebooks/**/*.ipynb` (all of
   `notebooks/pipeline/`, `notebooks/archive/`, `notebooks/legacy_production/`,
   `notebooks/scratchpads/` — not just the master notebook), and
   root-level `.py` files (not just `src/`/`utils/` — `classify_commons_queue.py`
   is a confirmed example of a root-level script with real imports that
   was never inventoried at all).

2. **Investigate `notebooks/pipeline/` itself.** It's 3 numbered
   notebooks (`01_Data_Ingestion.ipynb`, `02_Network_Topology.ipynb`,
   `03_Semantic_Classification.ipynb`), all dated 2026-06-29 — older
   than most of the active work (which clusters around 2026-07-06
   onward). This looks like a separate, possibly earlier or parallel
   numbered-notebook pipeline architecture that nothing in the project's
   existing docs (`ANTIGRAVITY_HANDOFF.md`, `ARCHIVE_full_session_history.md`,
   `pipeline_validity_audit.md`) has ever characterized as active,
   superseded, or abandoned. Figure out what it actually is and update
   the inventory's status calls for `ingestion.py`/`network.py`/`classification.py`
   accordingly (their status may still end up `active`, `superseded`, or
   something else entirely — the point is to base the call on what
   `notebooks/pipeline/` itself turns out to be, not to assume).

3. **Rewrite Mystery #1** to reflect what's actually true (or remove it,
   if the `notebooks/pipeline/` investigation resolves it completely).

4. **Re-verify a sample of existing citations**, not just the two
   confirmed-wrong ones. Pick at least 15 of the ~68 rows currently
   marked "High confidence" at random, actually open the file(s) named
   in each citation, and confirm the cited evidence really says what
   the row claims. Report the sample's error rate honestly — if it's
   similar to what Claude found (2 wrong out of the ~6 checked), that's
   useful to know and worth stating explicitly in the document rather
   than leaving every row's confidence rating as-is.

## Guardrails

Same as the original task: read-only except for editing
`handoff/PROJECT_INVENTORY.md` itself. Don't touch `src/`, `utils/`,
the notebook, or `data/`. Every corrected/added claim still needs a
real citation — file path + line, git commit hash, or an exact quote +
location.
