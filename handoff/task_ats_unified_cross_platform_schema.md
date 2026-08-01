# Unified reddit + ATS comment schema (not started, 2026-07-26)

Depends on the other four `task_ats_*.md` sibling files — this is the
assembly step, not independent work. Do this last, once entity
disambiguation, stance classification, topic modeling, and engagement
normalization each have real output for ATS (or at least the subset of
them Nash has decided to prioritize — check status before assuming all
four are done).

## The idea (Nash's, 2026-07-26)

A single common-shape table spanning both platforms, so the same
analytical question can be asked across both populations at once rather
than needing separate reddit-only and ATS-only code paths everywhere.
Sketched columns, from the conversation that raised this:

- `comment_id` (unique — may need a platform prefix if the two platforms'
  raw IDs collide as raw strings/ints)
- `platform` (`reddit` | `ats`)
- `thread_id` — reddit's submission/post ID and ATS's thread ID are the
  right conceptual match (both are the top-level container a comment
  hangs off), confirmed during scoping
- `author`
- `timestamp_normalized` — reddit's timestamps and ATS's
  (`raw_timestamp`, currently a free-text string like "dec, 30 2016 @
  09:21 am") need a common parsed/normalized format; check
  `ingest_ats_archive.py`'s `POSTED_TIMESTAMP_REGEX` for how the raw ATS
  string is currently captured before assuming it's already structured
- `text`
- `engagement_z` — from `task_ats_engagement_normalization.md`
- `topic_name` — from `task_ats_topic_modeling.md`
- entity/stance columns — from `task_ats_entity_disambiguation.md` /
  `task_ats_stance_classification.md`

## Scope note

This is explicitly the *last* piece — building it before the four inputs
above exist just means rebuilding it again once they land. If picked up
early, treat it as schema design + a stub/placeholder build (real columns
where data exists, clearly-marked nulls where it doesn't yet) rather than
pretending it's complete.

## Not a replacement for the existing separate parquet files

The reddit-side and ATS-side parquet files already in the GCS bucket
(`topic_examples.parquet`, `ats_comments_thread_view.parquet`, etc.) stay
as-is for the explorer's existing per-platform drill-down/browse
features — those have different query patterns (keyed by topic_name vs.
thread_id) and combining them was explicitly considered and rejected for
that use case (see the Cloud Run migration's architecture notes). This
unified table is a *new, additional* artifact for cross-platform analysis
specifically, not a replacement for what's already serving the live
explorer.
