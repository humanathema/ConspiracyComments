# Task: Wire the source-authority construct into a regression

**Status: COMPLETED (2026-07-22)**

The regressions for both r/conspiracy and r/politics have been fully executed, verified, and updated to split the heterogeneous `mixed_or_low_reliability` tier into `mainstream_imperfect` and `alt_media` (resolving the sign-flip confusion caused by pooling WaPo/The Guardian with Breitbart/RT/Infowars).

### Verified Coverage & Bare-URL Gap
- The bare-URL coverage gap (comments flagged with `has_link == 1` but containing a protocol-less URL that falls through to `no_link`) was checked and confirmed to be **negligible**:
  - **r/conspiracy**: 0.04%
  - **r/politics**: 0.00%
- No additional protocol-less normalizer adjustments are necessary.


## Why

`data/processed/source_authority_scores.csv` (526 entities: news
outlets + academic journals, scored via Media Bias/Fact Check
reliability labels and Scimago Journal Rank quartiles) was built
2026-07-19 (`build_source_authority.py`, see
`handoff/task_source_authority_construct.md` — mark that task file
**done**, it's stale, still says "not started") but has never been used
in a regression. Every current regression treats `has_link` as a flat
binary, collapsing "cites the Lancet" and "cites a random blog" into the
same variable — a real information loss given the thesis question is
specifically about *which* markers of authority get rewarded.

## What to build

1. A domain-extraction step: pull the linked domain out of comment text
   for rows where `has_link == 1` (there is prior art for this — check
   `data/processed/domain_epistemic_performance.csv` and whatever
   notebook cell in `ConspiracyMaster_Refactored.ipynb` Section 4/4.1
   produced it before reusing/duplicating logic).
2. Join extracted domains against `source_authority_scores.csv` on
   `matched_name`/`entity`. Note going in: that file is dominated at the
   top by generic aggregator/syndication domains (reddit.com,
   youtube.com, wikipedia.org, imgur.com, archive.is) rather than actual
   news/opinion outlets in the raw domain frequency data — you will need
   to decide (or flag for review, don't silently drop) how to bucket
   those: they are not "no link," but they are not "authoritative source"
   or "low-reliability source" either. A fourth bucket
   (`aggregator_or_platform`) is probably right; don't force them into
   the MBFC scale.
3. Build a categorical `link_source_tier` variable, something like:
   `no_link` / `mainstream_reliable` (MBFC least-biased/high-factual or
   SJR Q1) / `mixed_or_low_reliability` (MBFC mixed/questionable, or SJR
   Q3/Q4) / `aggregator_or_platform` / `unmatched_link` (has a link,
   domain not in the scored list at all — report what fraction of links
   this is, don't bury it).
4. Rerun the core regression formula from
   `src/rerun_refined_regressions_v2.py` with `has_link` replaced by
   `C(link_source_tier)` (keep the original `has_link`-only version
   too, saved separately, for comparison — do not overwrite
   `refined_regression_results_v2.csv`).
5. Save to `data/processed/link_source_tier_regression_results.csv`.

## When done

Report the coefficient for each tier plainly, including the
`unmatched_link` fraction (if it's large, that's an important caveat on
how much of `has_link` this construct actually explains, not a detail to
skip past). Stop there — don't chain into interpretation.
