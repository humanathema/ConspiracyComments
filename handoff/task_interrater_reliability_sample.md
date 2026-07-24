# Task: Inter-rater reliability sample (human-human agreement ceiling)

**Status: not started (2026-07-22).** Companion to
`task_scale_up_hitl_labeling.md` -- read that one for context on why
this matters for deciding how much more labeling volume is actually
worth pursuing. This task should ideally run first, or at least get an
early preliminary read, before committing to a large labeling campaign.

## Why

Every kappa number in this project so far measures classifier-vs-single-
human-rater agreement. None of it measures human-vs-human agreement on
the same task. That's a real gap: kappa against one rater is
mechanically capped by how consistent humans are with each other on this
labeling task in the first place. If two people independently rating the
same comment for stance only agree at, say, kappa=0.6 themselves, then
a classifier hitting 0.6 against either one of them individually would
actually be at (or near) the practical ceiling, not underperforming --
and no amount of additional single-labeled training data changes that.
Nash wants this measured on a **sample**, not the full labeling volume --
correct call, IRR is a property of the task/rater-agreement, not
something that needs full-corpus coverage to estimate reliably.

## What to build

### 0. Scope: stance only, not every construct (revised 2026-07-22)

Checked what this project actually has HITL ground truth for before
scoping this:
- **Stance** (maverick/consensus, hostile/endorsement/other) -- by far
  the heaviest HITL investment (~1,700+ rows across base queues + active-
  learning rounds + entity-specific quality checks), and the one with a
  known, only-partially-fixed weakness (kappa=0.370 pooled cascade,
  known endorsement blind spots). **This is the only construct in scope
  for this IRR task.**
- `has_maverick`/`has_consensus_expert` -- entity detection via curated
  gazetteer + disambiguation lookup, not a per-comment rated task. Out
  of scope, "does rater A agree with rater B" isn't the right question
  for it.
- `hedged_suspicion` -- real trained classifier, real HITL ground truth,
  but already reports kappa=0.872/F1=0.933 (`pipeline_validity_audit.md`)
  -- not a bottleneck, out of scope for now. (Not independently re-
  audited the way stance's original number turned out to be optimistic,
  so not bulletproof, but not urgent either.)
- `pe_prob`/`ps_prob` -- has a regex-filter layer plus a loaded
  classifier (`staged_pipeline_models.joblib`), but no confirmed kappa
  number was found. Out of scope for this task; worth a separate quick
  check sometime, not blocking.

Maverick and consensus stance ARE combined into one shared panel below
(same 3-class task, same classifier lineage, no reason to split them).

### 1. One small SHARED panel, not split pairs (revised design, 2026-07-22)

Original design (split a larger sample into separate non-overlapping
blocks for different rater pairs) is superseded -- Nash's question ("why
pairs, why not just compare everyone against my own ratings") surfaced a
better structure. **Have every participating rater -- Nash included --
label the exact same small shared set of ~80-100 stance items** (combined
maverick + consensus, not split into separate panels per entity type; not
150-200 split across pairs). This is smaller per-person AND more
informative:
- Every rater's kappa against Nash directly -- the most relevant number
  for this project specifically, since the classifier was trained mostly
  on Nash-supplied labels, so "do fresh humans reproduce Nash's specific
  judgments" is a more targeted ceiling estimate than generic peer
  agreement.
- Every rater's kappa against every OTHER rater, for free, from the same
  data -- full Fleiss' kappa across the whole panel, at zero extra
  labeling cost, answering the separate "is the task/category scheme
  itself well-defined enough for independent people to converge"
  question.
- Equal, low, predictable burden per rater (everyone does the same ~50-80
  items, nobody gets a bigger chunk than anyone else) -- important given
  raters are casual volunteers, not paid annotators.

Stratify the shared set the same way existing quality-check queues
already do (across predicted-probability buckets / predicted labels, not
pure random) so the IRR estimate isn't dominated by the easy, high-
agreement majority class.

### 2. Optional: add an LLM rater to the same shared panel

Nash may also run Gemini against this same shared set as an additional
"rater" for a human-vs-AI comparison. **Scope this explicitly to the
small shared stance panel only (~80-100 items, one construct) -- do NOT
run it across the bulk labeling volume, other constructs, or the full
corpus.** This project has a specific prior incident on record (a $100
unplanned budget blowout traced to a multi-pass Gemini labeling cascade,
see `handoff/methods_provenance_audit.md`) -- keeping any LLM comparison
bounded to this already-small IRR set avoids repeating that at a much
safer, trivial cost. Gemini's ratings slot into the exact same kappa
matrix as the human raters -- gemini-vs-Nash, gemini-vs-each-friend,
alongside human-vs-human -- no separate analysis pipeline needed.

### 3. Tool support for the shared panel

Depends on `task_scale_up_hitl_labeling.md` item 1 (rater-identity
tracking) being done first -- once `rater_id` exists, the shared panel's
comment IDs need to be served identically to every participating rater
(a dedicated IRR queue/URL, separate from each person's individual bulk-
volume queue, so it doesn't get silently absorbed into single-rater
throughput). Track completion per rater_id so the same person doesn't
accidentally re-rate their own prior submission.

### 4. Agreement computation

Once the shared panel comes back from all raters (+ Gemini if used):
Cohen's kappa for every pair (`sklearn.metrics.cohen_kappa_score`, same
convention already used throughout this project's other kappa
reporting), plus Fleiss' kappa across the full panel. Report:
- Overall panel-wide IRR kappa (the headline ceiling number)
- Per-class agreement breakdown (are raters agreeing well on "hostile"
  but poorly on "other"/ambiguous cases, the same kind of breakdown
  already standard in this project's quality-check reports)
- Explicit side-by-side: classifier-vs-Nash kappa (already known, 0.370),
  each-rater-vs-Nash kappa, and the peer-to-peer/Fleiss' number -- this
  is what answers "is the classifier close to the human ceiling or
  genuinely underperforming it," and if used, where Gemini falls in that
  same comparison.

## When done

A clear answer to: what's the realistic kappa ceiling for this labeling
task, and is the current classifier (0.370 pooled cascade) close to it
or genuinely far from it? That answer should directly inform whether
`task_scale_up_hitl_labeling.md`'s volume target is worth pursuing at
the scale estimated there, worth pursuing further, or already close to
diminishing returns regardless of volume.
