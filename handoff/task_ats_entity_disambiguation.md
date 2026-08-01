# ATS entity extraction + disambiguation to reddit-side parity (done, 2026-07-27)

**Status update (2026-07-27): the Stage B/C disambiguation transfer
itself is now done, verified against actual output, not just the
walkthrough text.** `src/stage_b_consolidated_corpus_pass.py` and
`src/stage_c_classify_ambiguous.py` got `--ats` flags (reusing the same
already-validated mainstream/maverick disambiguation logic from the
reddit side, not a reimplementation) and were run end-to-end against
the full 7.15M-comment ATS corpus.

Outputs, confirmed by direct query:
- `data/processed/ats_entity_examples.parquet` — 30,998 rows, 423
  unique entity keys, 27,111 maverick / 3,887 consensus, schema
  identical to reddit's `entity_examples.parquet`.
- `data/processed/ats_new_candidates_review.csv` — 953 new/community-
  specific candidate entities (e.g. James Casbolt, Ted Gunderson) not
  covered by the existing reddit-side clusters, with a blank `decision`
  column (confirmed 0/953 filled) — correctly left for Nash's review
  per the project's entity-judgment guardrail, not auto-decided.
- `data/processed/entity_final_review.csv` (15,988 rows, still blank
  `final_decision`) is an earlier intermediate candidate-scoring pass
  from the same push — kept for reference, superseded as the "current
  state" doc by the two files above.

`src/spot_check_ambiguous_names.py` (companion ambiguity spot-check
script) is still available if needed but not required for the pipeline
above.

**Feeds directly into `task_ats_stance_classification.md`**, which
already consumed `ats_entity_examples.parquet` (same 30,998-row count)
as its input — the dependency chain worked correctly across the two
sessions.

---

Part of the bigger push (see `ANTIGRAVITY_HANDOFF.md`'s index and the
sibling task files `task_ats_stance_classification.md`,
`task_ats_topic_modeling.md`, `task_ats_engagement_normalization.md`,
`task_ats_unified_cross_platform_schema.md`) to bring the AboveTopSecret
corpus (7.15M comments, ingested 2026-07-26) up to the same analytical
depth as the reddit side. This isn't a side project — ATS is the answer
to the standing methodological critique that r/conspiracy is too heavily
moderated to generalize from; the whole thesis's ability to talk about
"conspiracy communities" rather than just "r/conspiracy specifically"
rests on this actually getting done, not just the corpus existing.

## Current state on ATS (what NOT to redo)

- **Already done**: known-entity frequency *counts* only —
  `src/count_known_entities_in_ats.py` -> `ats_known_entity_counts.csv`.
  This is a crude regex bare-form count against the same 224-entity list
  used on reddit. It answers "does this name appear" — nothing about how
  it's framed (accusatory citation vs. genuine endorsement vs. neutral
  mention).
- **Not done at all**: the actual Stage A/B/C disambiguation pipeline
  that makes the reddit-side entity data trustworthy has never been run
  against ATS text.

## What "parity with reddit" actually requires

Reuse the already-verified reddit-side entity lists and pipeline rather
than rebuilding anything — the lists themselves are already trusted:

- `src/consensus_experts_verified.py` — the 82-name-variant / ~57-person
  consensus_expert allowlist.
- `src/verified_maverick_additions.py` + `src/maverick_authority_verified.py`
  — the maverick_authority allowlist (hand-reviewed against real corpus
  framing, see `ANTIGRAVITY_HANDOFF.md`'s guardrail #3 for why this
  matters — Ralph Baric is the canonical example of a real scientist
  whose corpus mentions are 100% accusatory, not citations).
- `src/stage_b_consolidated_corpus_pass.py`, `src/stage_c_classify_ambiguous.py`,
  `src/stage_g_auto_disambiguate.py` — the per-instance disambiguation
  machinery (bare-form/nickname resolution, shared-first-name
  disambiguation like the existing `hunter`/`hawking`/`ventura` clusters)
  that turned the reddit-side entity data from "undercounted, contaminated"
  into something trustworthy. This needs to run against ATS text the same
  way, not be skipped in favor of the cruder frequency count already done.
- `src/consensus_disambiguation_lookup.py` — the lookup table these stages
  depend on.

## Guardrail this explicitly falls under (from `ANTIGRAVITY_HANDOFF.md`)

**"Entity-list judgment calls are not yours to make unsupervised."**
Deciding whether a person/org counts as `consensus_expert` or
`maverick_authority` requires checking how they're actually framed in
real ATS text — the same judgment call already made carefully for reddit,
not something to auto-apply blind. Concretely: the *lists themselves*
(already verified against reddit text) can be reused as-is; what needs
fresh judgment is whether ATS's different era (1998-2020s) and community
norms produce different framing patterns for the same names, or surface
entities that never came up on reddit at all. Produce a reviewable
candidate list with a blank `decision` column for anything new or
ambiguous, same pattern as the reddit-side process — don't auto-merge.

## Suitability for delegation

Good fit for an Antigravity session for the *mechanical* part (running
the existing Stage A/B/C pipeline against ATS text, producing candidate
outputs) — this reuses already-built, already-trusted machinery, it's not
building anything new. The judgment-call part (reviewing anything the
pipeline flags as new/ambiguous for ATS specifically) is Nash's own call,
same as it always has been for the reddit side.

## Output needed for the bigger cross-platform push

An `entity_examples`-shaped table for ATS (same columns as the reddit-side
`entity_examples.parquet` already in the GCS bucket: `comment_id`,
`entity_key`, `construct`, plus whatever stance/predicted_label columns
land once `task_ats_stance_classification.md` is done) — this is what lets
the explorer's existing entity drill-down tabs work identically for both
platforms, and what the unified schema task needs as an input.
