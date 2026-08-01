# Cross-platform engagement normalization: reddit upvotes vs. ATS stars (done, 2026-07-26)

**Status update (2026-07-26, later same day): built and verified.**
`src/compute_engagement_normalization.py` adds an `engagement_z` column
to both platforms' core tables, in place (DuckDB, temp-file-then-replace
pattern). Verified directly against the actual parquet files (not just
trusting the build log): `data/processed/ats_comments_final.parquet`
has `engagement_z` with mean ≈0, stddev ≈1 across all 7,147,196 rows;
`data/processed/empath_scores_full.parquet` has 21,349,908 non-null
`engagement_z` values, matching the corpus's known deduped row count
(see `ANTIGRAVITY_HANDOFF.md`'s dedup-fix note).

Reference frames chosen (this is the "decide and document" population
choice the task called for below):
- **Reddit**: z-scored against the pure r/conspiracy population's own
  mean/stddev (upvotes μ=1.864241, σ=3.319672, N=1,968,864) — but the
  column is written onto the full unfiltered 21.3M-row table, so
  non-pure-population rows get an `engagement_z` relative to the pure
  population's stats, not their own. Intentional or not, that's worth
  confirming before citing engagement_z on non-pure rows.
- **ATS**: z-scored against the *entire* corpus (star_count μ=0.205821,
  σ=1.260803, N=7,147,196) — there's no ATS equivalent of the "pure vs.
  unfiltered" reddit distinction, so this is corpus-wide by default, not
  a deliberate population match to reddit's "pure" choice. Also uses the
  corrected star counts (`recount_ats_stars.py`/`patch_ats_star_overflow.py`),
  not the old boolean flag, per the original task instruction. Posts
  absent from `ats_star_counts.csv` get `star_count = 0`.

**Open question, not yet resolved**: whether reddit-pure vs. ATS-
corpus-wide is the right pair of reference frames for a genuinely
comparable cross-platform `engagement_z`, or whether they should both
be the same *kind* of population (e.g. both "pure"/most-restrictive, or
both "everything") before this feeds the unified schema task. Flag this
for whoever picks up `task_ats_unified_cross_platform_schema.md` rather
than assuming the current choice is final.

---

Original task file below, kept for the rationale that led to the above:

Sibling task to the other `task_ats_*.md` files — part of the same push
to bring ATS to analytical parity with reddit. This one's small and
mechanical relative to the entity/stance/topic pieces; no real
methodological risk, safe to delegate outright.

## The idea (Nash's, 2026-07-26)

Reddit upvotes and ATS stars are both engagement/endorsement signals, but
on different scales — different community sizes, different eras, ATS's
star mechanic historically capped display at 24 icons with a "+N more"
overflow label (see `src/patch_ats_star_overflow.py` and
`src/recount_ats_stars.py` for the real recount — max observed is 120,
not 24). Raw counts aren't comparable across platforms. Z-scoring within
each platform independently (subtract that platform's own mean, divide by
its own stddev) puts both on a comparable "how much more/less engagement
than typical for this platform" scale — standard technique for combining
heterogeneous popularity metrics across different populations.

## What this needs

- Reddit side: z-score `upvotes` within the existing population
  (whichever population is the current canonical one for the core
  regressions — check `ANTIGRAVITY_HANDOFF.md`'s current-state section
  for which one that is at time of pickup, the pure vs. unfiltered
  distinction matters and has shifted before).
- ATS side: z-score the corrected `starred` column (from
  `src/recount_ats_stars.py` + `src/patch_ats_star_overflow.py` —
  make sure to use the corrected count, not the original boolean
  `starred` flag that undercounts).
- Decide and document: z-score computed over what population for each
  (all comments? only comments with nonzero engagement? matters for the
  mean/stddev used) — pick one and be explicit about it rather than
  leaving it implicit, since this number will presumably feed into
  cross-platform comparisons later.

## Output needed for the bigger cross-platform push

An `engagement_z` column (or equivalent name matching whatever the
unified schema task settles on) on both reddit and ATS comment tables,
computed independently per-platform as described above.
