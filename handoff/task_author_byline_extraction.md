# Task: Extract author bylines from cited articles (not just URL/title identification)

**Status: not started (2026-07-22).** Scoped-down piece of a larger
"individual sources/authors, not just domains" research direction Nash
raised. Distinct from `task_extend_citation_curation.md` (which
identifies/classifies WHAT a cited URL is) -- this task extracts WHO
wrote it, a genuinely different extraction step. Not the full
topic-dichotomy vision either -- see `task_bertopic_full_corpus_retrain.md`
for that, staged separately, later-phase, bigger scope.

## Why

Current citation-taxonomy findings (credentials-problem crosstab, MBFC/SJR
link-source tiers) operate at the domain/outlet level --
`credentialed_institutional` / `movement_internal_anonymous` / MBFC
reliability grade, etc. Real findings, but they can't say anything about
*which specific people* the community treats as authoritative -- an
article by a specific named investigative journalist and a wire-service
rewrite on the same domain currently look identical to this taxonomy.
`cited_urls_ranked.csv` already ranks every cited URL by distinct-author
count (despam'd), and the existing curation
(`cited_content_curation_step2.md`) already has hand-identified authors
for the top ~139 by volume, but that's the small slice reachable by
manual review alone. This task extends author identification via
automated byline extraction, not more manual curation, to reach further
down the tail.

## What to build

1. **New extraction function, not a reuse of `fetch_article_title()`** --
   that function (`src/translation.py`) extracts `<title>` text, not
   byline/author metadata; a different HTML target. Build
   `fetch_article_byline(url)` checking, in order of reliability:
   - schema.org `Article`/`NewsArticle` JSON-LD `author` field (most
     reliable where present, structured data)
   - `<meta name="author" content="...">` 
   - Common CMS byline HTML patterns (`.byline`, `.author-name`,
     `rel="author"` links) -- keep this a short, reasonable-effort list,
     not an attempt at a universal parser for every possible site layout
   - Graceful fallback to `None`/"unextracted" if nothing matches --
     do NOT guess an author from surrounding text or infer from domain
     conventions. Silent failure is fine; silent wrong-guessing is not,
     same principle as everything else in this citation-curation work.
2. **Run against a larger slice of `cited_urls_ranked.csv`** than the
   current 139 curated rows -- e.g. the next several hundred by
   distinct-author count, batched with a rate-limit delay matching the
   existing `fetch_article_titles_batch` convention (`delay=0.3` there;
   match or be more conservative).
3. **Verify a sample by hand before trusting the extractor at scale** --
   bylines are easier to get wrong silently than titles (syndication
   credits, editor credits, "About the author" boilerplate, multi-author
   pieces truncated to the first name only). Spot-check ~20-30 extracted
   bylines against the actual live page, same rigor as the original
   139-row curation's own verification discipline (which caught two
   confidently-wrong first-pass guesses on domain/content identification
   -- bylines have at least as much room to go wrong).
4. **Output**: `url | distinct_authors (from ranked file) | extracted_byline
   | extraction_method (json-ld / meta-tag / html-pattern / failed)
   | domain | title (if available) | verified (bool, for the hand-checked
   sample)`. Keep separate from the existing curation table rather than
   merging -- this is a different granularity/purpose (byline-level, not
   URL-classification-level), and the existing table's confidence-tagging
   convention (HIGH / HIGH-verified / UNVERIFIED-MEDIUM) is about source
   *type* classification, not extraction *success rate*, so don't force
   them into the same schema.

## Scope boundary

This is about identifying who the frequently-cited authors are, at a
larger scale than manual curation reaches. It is NOT about tying that to
specific topics/issues, computing per-author traction/stance statistics,
or building a new stance construct -- that's the separate
`task_bertopic_full_corpus_retrain.md` / future topic-dichotomy work.
Keep this task's output as a standalone "who actually wrote the most-cited
pieces" artifact that later work can join against.

## When done

A byline-identification table covering a meaningfully larger slice of
`cited_urls_ranked.csv` than the current 139 manually-curated rows, with
extraction-method transparency (so "we don't know" is visible, not
hidden) and a hand-verified sample confirming the extractor's real
accuracy before it gets used for anything downstream.
