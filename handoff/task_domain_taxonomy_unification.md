# Task: Unify the three parallel domain/source-classification systems

**Status: plan drafted 2026-07-22, NOT yet reviewed/approved by Nash --
do not execute until he signs off, same review-before-build pattern used
for the entity-mentions cache plan.**

## Why

This project has independently built THREE separate domain/source
classification systems at different points, none of which know about
each other:

1. **The credentials-problem 4-tier taxonomy** (`integrate_credentials_problem.py`,
   `cited_content_curation_step2.md`) -- `credentialed_institutional` /
   `individual_named_source` / `movement_internal_anonymous` / `other`.
   139 hand-curated URLs + a small hardcoded domain-fallback list (fixed
   today, 2026-07-22, to also fall back to curated DOMAINS, with a
   confirmed-necessary exclusion list for general-purpose platforms --
   see `task_domain_taxonomy_followups.md`).
2. **The Cell-61 Epistemic Domain Taxonomy** (`run_link_type_regressions.py`,
   originally from the master notebook) -- 10 categories: `mainstream_news`,
   `alt_media`, `academic_scientific`, `government_official`,
   `archive_preservation`, `leak_whistleblower`, `legal_documents`,
   `social_video`, `reference`, `image_screenshot`. Only 5 of the 10 were
   ever wired into actual regression covariates. The regression that used
   it (`research_notes/04_link_types.md`) is marked SUPERSEDED (contaminated
   entity list, invalid r/TopMindsOfReddit control), but the taxonomy
   dictionary itself isn't invalidated by that -- it's a reusable asset,
   not a dead end.
3. **The MBFC/SJR-based `link_source_tier` system** (`run_link_source_tier_regressions.py`,
   `source_authority_scores.csv`) -- real external reliability scores
   (Media Bias/Fact Check labels, Scimago Journal Rank quartiles), 5 tiers:
   `no_link` / `mainstream_reliable` / `mixed_or_low_reliability` /
   `aggregator_or_platform` / `unmatched_link`. This is CURRENT (rerun
   2026-07-20 after the r/politics pipeline fix) and produced the most
   rigorous of the three results so far, but its `mixed_or_low_reliability`
   tier needs splitting (see `task_domain_taxonomy_followups.md` item 4)
   before its cross-subreddit finding is trustworthy.

Each system has independently rediscovered pieces of the same ground
truth (all three separately conclude reddit.com/youtube.com/wikipedia.org
need "platform" treatment distinct from content-based categories; all
three separately list ae911truth.org/corbettreport.com/wikileaks.org as
alternative-authority sources) -- but there's no single source of truth,
so fixing a classification in one place (like today's domain-fallback fix)
doesn't propagate to the other two, and future work risks re-deriving the
same judgment calls a third time.

## Proposed unified design (draft, needs Nash's review)

### 1. One canonical domain classification lookup

Build `data/processed/domain_classification_lookup.csv`:
`domain | category | mbfc_reliability_label | sjr_quartile | is_platform | source`

- `category`: adopt Cell-61's richer category set (10 categories) as the
  base vocabulary, since it's more granular than the credentials-problem
  4-tier scheme and the 4-tier categories map onto it cleanly
  (`credentialed_institutional` ~ `government_official` +
  `academic_scientific`; `individual_named_source` + `movement_internal_anonymous`
  ~ `alt_media` + `leak_whistleblower`). Fix the `documentcloud.org`
  dict-collision bug while merging (currently silently resolved to
  `legal_documents` over `leak_whistleblower` by dict-insertion-order).
- `mbfc_reliability_label`/`sjr_quartile`: carried over from
  `source_authority_scores.csv` where available (news/journal domains
  only) -- this is a QUALITY axis, not a category axis, and should stay a
  separate column rather than forcing reliability into the category
  scheme (a domain can be `mainstream_news` AND have a `mixed` MBFC label
  -- these are different facts, conflating them is exactly what caused
  the r/politics sign-flip confusion in `task_domain_taxonomy_followups.md`
  item 4).
- `is_platform`: boolean, adopted from `run_link_source_tier_regressions.py`'s
  `PLATFORM_DOMAINS` set (reddit.com and variants, youtube.com, twitter.com/x.com,
  wikipedia.org, imgur.com, archive.* mirrors, reveddit.com/removeddit.com/
  ceddit.com/snewd.com, google.com, amazon.com, facebook.com, github.com) --
  a domain being a platform should suppress category/reliability inference
  entirely (this is the general-purpose-platform problem confirmed today
  with reddit.com/businessinsider.com/usatoday.com; note businessinsider.com/
  usatoday.com are NOT platforms, they're just multi-topic mainstream
  outlets -- don't conflate "is a platform" with "shouldn't get domain-level
  category inference," they're related but not identical; a multi-topic
  publisher needs its OWN exclusion reasoning per-domain, not blanket
  `is_platform` status).
- `source`: which of the 3 original systems (or manual curation) the row
  came from, for provenance/audit -- don't silently merge without keeping
  this trail, the same "don't guess, keep it verifiable" principle as the
  original curation doc.

### 2. Materialize a citation-level cache, same pattern as entity_mentions_cache

Mirror `entity_mentions_cache_2stage_pooled.parquet`'s approach: one
citation-scan pass, materialized once, that all three consumer scripts
(`integrate_credentials_problem.py`, `run_link_type_regressions.py`,
`run_link_source_tier_regressions.py`) read from instead of independently
re-extracting URLs and re-joining. Schema: `comment_id | url | domain |
category | mbfc_reliability_label | is_platform`. This is the same
redundant-scanning problem the entity-mentions cache was built to solve,
just on the citation side instead of the entity-mention side -- currently
each of these 3 scripts extracts URLs from the corpus independently.

### 3. Refactor order (don't do all three scripts at once)

1. Build the lookup + cache first, verify it reproduces
   `run_link_source_tier_regressions.py`'s CURRENT (2026-07-20) results
   near-exactly (that's the most rigorous/trusted of the three right now
   -- use it as the regression test, same "automated verification"
   discipline as the entity-mentions cache build).
2. Refactor `integrate_credentials_problem.py` to read from the unified
   lookup/cache, applying today's domain-fallback fix + exclusions as the
   lookup's authoritative state (not re-derived).
3. Decide whether `run_link_type_regressions.py`/`research_notes/04_link_types.md`
   is worth reviving at all now that the taxonomy is unified -- it may be
   fully subsumed by the more rigorous MBFC/SJR system once `alt_media` is
   folded in there, in which case retire it rather than maintain 3 systems
   forever.

## Open questions for Nash (not decided here)

- Is the Cell-61 10-category vocabulary the right base, or should the
  unified category set be something new that better fits how the
  credentials-problem taxonomy has actually been used in the thesis so far?
- Should `mixed_or_low_reliability` get split into `mainstream_imperfect`
  vs. `alt_media` as part of this unification, or as a separate quick fix
  first (see `task_domain_taxonomy_followups.md` item 4) before the bigger
  refactor?
- How much of this is worth Antigravity's time now vs. deferring until
  closer to thesis write-up, given it's an infrastructure/consistency
  improvement rather than a new finding?

## When done

A single `domain_classification_lookup.csv` + citation-level cache that
`integrate_credentials_problem.py` and `run_link_source_tier_regressions.py`
both read from, with `run_link_type_regressions.py` either folded in or
explicitly retired -- not three independently-maintained domain
dictionaries that can silently drift out of sync with each other, which
is exactly the failure mode today's `classify_url()` fix had to catch by
hand.
