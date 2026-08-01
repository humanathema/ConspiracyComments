# Source/citation/domain coverage expansion (raised 2026-07-27/28, not started)

Background-agent audit finding, not yet acted on.

## The finding

Less than 1% of citation events rest on actual human-verified
classification, on **either** platform:

- **Reddit**: only 0.79% of citations are `curated` (hand-verified) out
  of 4.67M citation rows across 132,009 distinct domains; 74.9%
  `unreviewed`, 24.3% `provisional_heuristic` (rule-based fallback, not
  verified).
- **ATS**: 0.51% of 25,024 distinct domains match the classification
  lookup at all, covering just 8% of citation mentions — no curated layer
  exists for ATS.
- **Manual curation table** (`handoff/cited_content_curation_step2.md`):
  139 URLs, hand-classified, careful methodology (documented
  self-corrections, explicit anti-padding guardrail) — against
  1,763,438 distinct URLs in `cited_urls_ranked.csv`. That's 0.008% of
  the long tail.

**Concentration matters for how bad this is**: Reddit's top 20 domains
cover 59.7% of citation rows (domain-level tiering is at least defensible
for the head), but ATS's top 20 only cover 24.4% — a flatter, more
fragmented distribution (older, more idiosyncratic web-1.0 forum, sites
like `rense.com`/`geocities.com`) where domain-level tiering alone can't
explain most of the corpus.

## What's already good, worth keeping

- URL normalization/dedup logic is solid (documented, self-corrected bugs
  like parenthesis-truncation and http/https splitting).
- Byline/article-level extraction (`src/translation.py`) is real and
  precision-validated at small scale (500 URLs, 352 successful) — see
  `handoff/task_media_personality_and_byline_review.md` for the caveat on
  how that precision claim was validated, before trusting it further.
- The curation table's confidence-tagging discipline (refusing to pad
  `UNVERIFIED` rows to `HIGH`) is a real methodological strength.

## Ranked next steps (feasible without new labeled training data)

1. **Extend byline extraction mechanically** — it already works at
   validated precision on json-ld/meta-tag sources; running it against
   the next 5,000-10,000 URLs by citation volume (already ranked, no new
   labels needed) would take Reddit-side article-author coverage from
   ~0.02% of URLs to something defensible, entirely with existing
   deterministic code, no LLM calls.
2. **Fix the DOI-casing undercounting bug** already flagged in the
   curation notes (`nejmoa2034577` vs `NEJMoa2034577` splitting identical
   papers into two entries) — small, deterministic, immediately improves
   accuracy for the single most-cited scientific paper in the dataset.
3. **Wire the byline/article layer into the explorer** — it exists
   (`build_domain_source_encyclopedia_export.py` produces
   `top_cited_urls_with_quality.csv`) but isn't surfaced anywhere a reader
   sees it. Integration work, not new analysis.
4. **Requires new labeled data or LLM assistance** (needs explicit
   sign-off first, per the standing no-unplanned-LLM-spend rule): building
   a genuinely representative domain-classification lookup beyond the
   current 268 hand-picked domains, to move past the 0.2-0.5% match rate.
   Could plausibly reuse the same AIITL-judge technique already proven
   this session (`domain_epistemic_type_sample.parquet` /
   `domain_epistemic_judged.parquet` already exist from a first pass —
   check those before starting a new one) rather than a fresh design.
