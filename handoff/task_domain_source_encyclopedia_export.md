# Task: Export domain/subdomain source-quality data for the corpus explorer

**Status: not started (2026-07-24).** Raised directly by Nash while extending
the corpus explorer artifact (`handoff/task_topic_era_rerun_corrected_constructs.md`'s
sibling session) -- he wants "an encyclopedia of the research so far,"
separated by tabs, and this is the one facet that couldn't be built live in
that session because the source data is too large to aggregate on the fly.

## Why

The explorer already has tabs for topic volume over time, author-topic
engagement, credentials/stance-by-topic crosstabs, and named entities (source:
`per_entity_stance_breakdown_pure.csv` / `_unfiltered.csv`, ~880 rows,
directly embeddable). What's missing is the citation/source-quality layer:
`data/processed/cited_urls_ranked.csv` is 182MB (1.76M distinct URLs) --
nowhere near embeddable in a static artifact as-is, and this session ran out
of time/budget to build the aggregation pipeline properly.

## What to build

Two output CSVs, both small enough to embed directly in a browser tool
(target: well under 500KB each as JSON -- round floats, don't carry every raw
column, see the size discipline note below).

### 1. Domain-level source quality rollup

Group `cited_urls_ranked.csv` by domain (extract from `url`, reuse whatever
domain-extraction logic `integrate_credentials_problem.py` or
`run_link_source_tier_regressions.py` already has -- don't reimplement it).
For each domain with a reasonable minimum citation count (start at >=20
citations, adjust if that's too sparse or too large a table), join in:
- `credentials_taxonomy_tier` / `link_source_tier` (from `citations_cache.parquet`)
- `mbfc_reliability_label`, `sjr_quartile` (also in `citations_cache.parquet`)
- distinct author count and total citation count (`cited_urls_ranked.csv`
  already has `distinct_authors`, `mention_count` per URL -- sum these per domain)

Output: `data/processed/domain_source_quality_rollup.csv` --
one row per domain: `domain, n_distinct_urls, total_citations, total_distinct_authors,
credentials_taxonomy_tier, link_source_tier, mbfc_reliability_label, sjr_quartile`.

### 2. Individual top-cited URLs with quality + byline

The top ~200-300 individual URLs by `distinct_authors` (from
`cited_urls_ranked.csv`, already ranked, despammed-by-construction per its own
docstring), joined against:
- the same quality/reliability fields as above
- `byline_extraction_results.csv` (`extracted_byline`, `title`) where available
  -- most won't have one, that's fine, leave null rather than guessing

Output: `data/processed/top_cited_urls_with_quality.csv` -- one row per URL:
`url, domain, distinct_authors, mention_count, credentials_taxonomy_tier,
link_source_tier, mbfc_reliability_label, sjr_quartile, extracted_byline, title`.

## Size discipline (learned the hard way this session)

The first version of the explorer embedded ~868KB of raw-precision JSON and
silently failed to render in the actual Artifact sandbox (worked fine in a
local test server, which was the wrong test -- local file servers have no CSP
and no payload constraints, so passing there proved nothing about the real
target). Fix that shipped: round every float to ~6 significant figures, and
deduplicate repeated string columns into a lookup table + integer indices
rather than repeating full strings per row. Apply the same discipline to
these two exports from the start -- don't ship 15-decimal floats or repeat a
domain name string on every one of its citation rows.

## When done

Two CSVs sitting in `data/processed/`, small enough that a follow-up session
can embed them directly into two new explorer tabs ("Domains" and "Top cited
sources") using the same visual system already established in the published
artifact (warm paper/ink palette, Georgia headings, Cove chart-color order,
searchable/sortable tables matching the existing "Named entities" and
"Regression browser" tabs). Report back plainly if the >=20-citation domain
floor produces something too sparse or too large to be useful -- that's a
real design choice, not a fixed number to hit no matter what.
