# Task: Scale up HITL labeling (stance, entity recognition, other constructs) via distributed multi-rater collection

**Status: not started (2026-07-22).** Nash is setting up a free-tier VM
to serve the rating tool online and recruiting friends to label batches
of comments. This task is about preparing the QUEUES and the TOOL for
that -- not the VM/hosting itself, which Nash is handling directly.

**Read `task_interrater_reliability_sample.md` alongside this one --
they share the same tool-modification prerequisite and the IRR task's
findings should inform whether/how far to push the volume target below.**

## Why, and the honest answer on "how many more rows"

Current stance classifier: two-stage cascade, end-to-end CV kappa=0.370,
trained on 1,774 rows (pooled). This project already has real learning-
curve data from its own active-learning rounds (`data/processed/
stance_classifier_round_progression_3class.csv`):

| round | n_train | cv_kappa |
|---|---|---|
| round1_base | 732 | 0.276 |
| round6 | 1098 | 0.278 |
| round11_jones_short | 1708 | 0.331 |

Whole-curve rate: ~0.057 kappa gained per 1,000 additional rows. Later,
more-targeted rounds (6->11) improved faster: ~0.087 per 1,000 rows.
Extrapolating (optimistically) from the current cascade's 0.370 to a
0.6 target: roughly **2,600-4,000 additional rows**, as a rough planning
number only -- diminishing returns are the norm for learning curves like
this (each additional batch typically buys less than the last), so the
real number could be meaningfully higher.

**Important, don't skip this**: kappa against a single human rater is
capped by human-human agreement on this task. If `task_interrater_reliability_sample.md`
finds human-human kappa is itself ~0.55-0.65, then 0.6 may already be
near the ceiling and no volume of additional single-labeled data closes
that gap. Treat the volume target above as provisional until that
ceiling is known -- don't commit to a large labeling campaign before at
least a preliminary IRR read comes back, even a small early batch.

## What to build

### 1. Extend `src/hitl_rater.py` for remote, multi-rater use

Currently local-only (binds to `localhost:8420` implicitly via the
`http.server` default) with **no rater-identity tracking at all** --
it writes `human_label`/`human_stance`/`notes` straight back to the
source CSV with no attribution. Needed before this can go on a VM with
multiple friends rating:
- Bind to `0.0.0.0` (or whatever the VM's public interface needs) with
  a configurable port -- Nash is handling the actual VM/networking, this
  just needs the server itself to accept non-localhost connections.
- Add a `rater_id` field (simplest: a name/token entered once per
  session, passed as a URL param or simple login prompt) and write it
  into a new `rater_id` column alongside each label -- this is required
  for the IRR task and for basic quality auditing (if one friend's
  labels look off, you need to know which ones are theirs).
- Basic abuse/access safety: this will be reachable on the open internet
  if served from a public VM -- at minimum, an unguessable URL path or a
  simple shared token, not wide-open. Not a full auth system, just don't
  leave it trivially discoverable.
- Preserve the existing crash-safety behavior (write-back after every
  submission, Back/Next navigation, entity-span highlighting, on-demand
  parent-comment context) -- these were real fixes from actual usage
  pain, don't regress them.

### 2. Build new active-learning queues, prioritized by where more data actually helps

Don't default to pure random sampling -- the round6-11 data suggests
targeted/uncertainty-driven sampling outperforms it. For stance
specifically, prioritize the same uncertainty-sampling approach already
used in `build_stance_active_learning_queue.py` (or whatever it's
currently called post-cache-refactor) -- comments where the cascade's
predicted probability is closest to the decision boundary, plus
deliberate coverage of under-represented entities/categories (the
existing round8-10 pattern of targeting wikileaks/assange/snowden/
greenwald specifically because they were underrepresented).

**Resolved 2026-07-22 -- scope narrowed to stance only, other constructs
checked and not prioritized this round:**
- `hedged_suspicion` already reports kappa=0.872/F1=0.933
  (`pipeline_validity_audit.md`) -- solid, not a bottleneck, skip.
- `pe_prob`/`ps_prob` have a regex-filter layer plus a loaded classifier
  (`staged_pipeline_models.joblib`) but no confirmed current kappa was
  found in this session -- worth a quick separate check sometime, but
  not enough is known about their current state to justify a labeling
  campaign for them right now, and they weren't flagged as a priority.
- `has_maverick`/`has_consensus_expert` are gazetteer/lookup-based entity
  detection, not a rated classifier -- not applicable to this kind of
  labeling expansion at all.

**Stance is the only construct in scope for this round of labeling.**
Don't build queues for the others without a fresh, specific reason to
revisit that decision.

### 3. Queue assignment: mostly single-labeled, reserve capacity for the IRR subset

Most of the new volume should be single-rater-labeled (each comment
rated once, whichever friend gets to it) to maximize total throughput.
The IRR sample (see the companion task) needs a specific subset
deliberately shown to 2+ raters -- coordinate with that task so the
same comment IDs aren't accidentally single-assigned when they need
dual coverage, and vice versa (don't waste a friend's time double-rating
something outside the designated IRR sample).

## When done

New queues loaded into the (modified) rater tool, ready for Nash to
distribute the URL to friends. Report back actual queue sizes per
construct and the reasoning for how they were prioritized, not just "N
more rows added."
