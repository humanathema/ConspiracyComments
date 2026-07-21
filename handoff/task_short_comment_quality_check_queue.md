# Task: Quality-check queue for the short-comment (<=100 char) corpus

**Status: not started. Mechanical generalization of an existing, working
script — bounded, low-risk, safe for Antigravity.**

## Why

`data/processed/conspiracy_comments_short_lte100chars.parquet`
(18,580,083 rows, `Paths().short_comments`) is the exact complement of
the 21.4M "usable" corpus everything else in this project runs on —
comments <=100 characters, never touched by any classifier here. A first
manual look at Jones mentions in it (16,063 comments) suggested this
population is qualitatively different, not just shorter: more jokes,
more one-line dunks, more fragments that only make sense with parent-
comment context the pipeline doesn't have wired in (e.g. "Alex Jones,
for instance." with no other context).

Nash's idea: eventually fold this population into the core regression
(more Jones mentions = more statistical power) or otherwise use it more
generally, not just for the regression question. Before doing that: the
same entity-window stance classifier that struggled with sarcasm/mockery
on LONG comments (see `task_stance_endorsement_blindspot.md`) has never
been checked on SHORT ones at all, and short comments have inherently
less context for a +-15-word window to work with. Build a quality-check
queue the same way the Jones one was built, so this can be checked before
any scope decision about using this population more widely gets made.

## What to build

Generalize `src/build_jones_stance_quality_queue.py` (same base pattern
as `task_multi_entity_quality_check_queues.md` — if that task is done
first, build on top of its generalized version rather than duplicating
work) to:

1. Point at `Paths().short_comments`
   (`conspiracy_comments_short_lte100chars.parquet`) instead of
   `EMPATH_PATH` for the text/mention source. Note this parquet has NO
   `THREAD_PATH`/`BRIGADE_PATH` join keys pre-computed the way the main
   21M-row pipeline does (crosspost/brigade filtering) — check whether
   that matters here or whether it's fine to skip those filters for a
   quality-check sample (this is a judgment call worth flagging in the
   walkthrough, not silently deciding either way).
2. Use the 3-class model (`stance_classifier_3class.joblib`), same as
   the other quality-check queues.
3. **Entity**: Alex Jones only, to start — it's the entity with the most
   existing quality-check history (the long-comment version) to compare
   against, which is the point of this check (does accuracy hold up on
   short text, not just "what does short text look like").
4. **Sample size**: ~100, stratified by predicted_label same as the
   other queues.
5. Output: `data/hitl/queue_jones_short_stance_quality_check.csv` +
   a separate predictions file, same blind-labeling convention.

## Guardrails

- Queue-building only, no labeling, no scoring the results.
- Do not build a general-purpose "score the whole 18.6M short-comment
  corpus" pipeline as part of this task — that's a separate, larger
  scope decision (see `task_stance_endorsement_blindspot.md` item 4)
  that needs explicit sign-off, not something to start here even if it
  seems like a natural next step.
- If the THREAD_PATH/BRIGADE_PATH join question in step 1 turns out to
  block progress entirely (rather than being a minor judgment call),
  stop and report that rather than inventing a workaround.
