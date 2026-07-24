# Task: Extend entity-stance AND credentials-problem/citation detection to the 18.6M short-comment population

**Status: not started (2026-07-22).** Nash's observation: short comments
(<=100 chars, `Paths().short_comments`, the exact complement of the 21.4M
"usable" corpus everything else runs on) often carry completely
unambiguous entity stance despite being short -- "Alex Jones is a lying
shill" is 30 characters and needs no more context to classify. The
`char_length>100` filter is necessary for constructs that need room to
show reasoning patterns (`pe_prob`, `ps_prob`, `hedged_suspicion`), but
there's no similar justification for excluding short comments from
entity-mention detection specifically. This task extends ONLY the
entity-stance pipeline to this population -- not a full-pipeline rescan,
not a redefinition of the populations every other finding this session
already used.

## Design: index first, then scan only the delta -- don't rescan anything already covered

The existing `entity_mentions_cache_2stage_pooled.parquet` already covers
the full 21.4M "unfiltered" population + r/politics. Do NOT rebuild that.
Two-stage approach, matching the cheap-filter-then-expensive-classifier
pattern already used elsewhere in this project (e.g.
`filter_maverick_entity_mentions.py`'s Stage-1 design):

1. **Index pass (cheap, regex/lookup only, no model scoring)**: scan
   `conspiracy_comments_short_lte100chars.parquet` (18,580,083 rows) with
   just the existing entity-detection logic (`compute_has_maverick`/
   `compute_has_consensus_expert`-equivalent regex + disambiguation
   lookup) to identify which short comments mention ANY tracked maverick/
   consensus entity at all. This is a cheap DuckDB regex pass, no
   classifier involved -- produces a small index (comment_id + matched
   entity spans) of the short comments that actually need scoring. Given
   the demonstrated ~85%+ non-mention rate in the long-comment population
   for these entity lists, expect this to shrink 18.6M down to a much
   smaller candidate set fast.
2. **Scan pass (expensive, cascade model)**: for ONLY the indexed subset,
   extract stance windows (same `stance_window_utils` functions already
   used everywhere) and score with the cascade model
   (`stance_classifier_2stage_pooled.joblib`, reuse
   `build_entity_mentions_cache.py`'s `score_windows_cascade()` directly
   rather than reimplementing it).
3. **Long-table cache for the short-comment population**: output in the
   exact same schema as `entity_mentions_cache_2stage_pooled.parquet`
   (`comment_id | entity_key | construct | p_hostile | p_endorsement |
   p_other | predicted_label | is_list_dump`, both per-entity and
   `merged_maverick`/`merged_consensus`/`merged_whistleblower`/
   `merged_other_maverick` rows), plus an explicit `population` column
   (e.g. `'short'` vs `'long'`) so downstream queries can filter or union
   cleanly. Comment IDs between the long and short corpora don't collide
   (clean length-based split of one original corpus), so this can either
   be a separate `entity_mentions_cache_short.parquet` unioned at query
   time, or appended to the existing cache with the population tag --
   Antigravity's call, but the schema must match exactly either way.

## Before trusting this population's stance labels at the same confidence as the long-comment ones

Only Jones has been quality-checked on short-comment text so far (kappa
0.274 after retraining with jones_short folded into training data --
real, but still meaningfully worse than the ~0.33-0.37 long-comment
kappa, with errors spread across all 3 classes, not concentrated in one
fixable blind spot). Before running any regression on the expanded
population, extend the quality-check to at least 2-3 more entities
(reuse `build_entity_stance_quality_queues.py`'s pattern, pointed at the
short-comment population the way `build_jones_stance_quality_queue.py`
was generalized for `task_short_comment_quality_check_queue.md`) so the
accuracy tradeoff on this population is actually known, not assumed.

## What to do with it once built

Treat as a **robustness extension, not a replacement**. Rerun the
whistleblower/other_maverick split regression (and the pooled
maverick/consensus regressions) with the short-comment population folded
in, and report it as a comparison against today's already-validated
long-comment-only numbers -- "does the finding hold up when short
comments are included" is the right framing. The existing long-comment
findings remain valid regardless of what this shows; this either
strengthens them (more data, same story) or surfaces something that
needs its own explanation (different story on short text) -- either
outcome is a real, reportable result, not a prerequisite that blocks
citing today's findings.

## Memory constraint

This machine has 8GB RAM and full-corpus scans have hit OOM before at
this scale. 18.6M rows is comparable to the 21.4M already handled
successfully by `build_entity_mentions_cache.py` today -- use the same
chunked/streaming DuckDB patterns already established there, not a naive
full-load of text into memory.

## Companion item: extend the credentials-problem/citation pipeline to the same population

Checked directly (2026-07-22) before scoping this, per the "verify before
assuming" discipline used throughout today: **expanding citations to the
full 21.4M long-comment corpus gains nothing** -- the existing 4.78M
`research_corpus_enriched.parquet` (`evidence_count>0 OR has_link=1 OR
alt_authority_count>0 OR quantitative_count>0`) already contains 100% of
the 3,047,729 `has_link=1` comments in the full 21.4M corpus (verified:
0 missing). The credentials-problem population is NOT under-covering the
long-comment corpus for citations specifically -- don't rescan it.

The real, verified gap is the short-comment population, same as above:
**404,019 short comments (2.17% of 18,580,083) have `has_link=1`** --
never scanned for citations at all, since the short-comment parquet was
never part of either the 21.4M usable corpus or the 4.78M enriched
subset derived from it. This is a real, worthwhile population (~13% the
size of the existing 3.05M-comment citation dataset) and cheap to add:
`has_link` is already precomputed on `conspiracy_comments_short_lte100chars.parquet`,
so there's no indexing pass needed at all -- extract URLs and classify
directly from those 404,019 pre-filtered rows using the existing
`citations_cache.parquet` / `domain_classification_lookup.csv`
machinery (same normalization, same taxonomy, no new logic to build).

Fold the results into the credentials-problem crosstab as an expanded-N
robustness check, same framing as the entity-stance work above -- report
whether the movement-internal-anonymous citation-share finding holds up
with short comments included, don't replace the existing long-comment
numbers.
