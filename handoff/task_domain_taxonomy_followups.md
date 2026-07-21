# Task: Domain-taxonomy follow-ups from the credentials-problem fix

**Status: COMPLETED (2026-07-22)**

All items have been fully addressed:
1. `documentcloud.org` URLs normalized and hand-curated to 31 distinct documents, verified using HTML title scraping.
2. `reddit.com`/`businessinsider.com`/`usatoday.com` verified as exact-page matches only (correct-as-is).
3. `cia.gov` domain fallback resolved by adding it to `DOMAIN_FALLBACK_EXCLUDED`. `pfizer.com` duplicate row corrected in `cited_content_curation_step2.md`.
4. `mixed_or_low_reliability` tier split into `mainstream_imperfect` and `alt_media` across the regressions and all consumer pipelines.
5. Bare-URL coverage confirmed negligible and wiring status updated.


## 1. documentcloud.org: normalize URL variants, then hand-curate top ~20-30 documents

`documentcloud.org` was deliberately left OUT of the domain-fallback fix
(unlike reddit.com/businessinsider.com/usatoday.com, see #2) because it
shows a genuinely different, concentrated pattern: 3,001 citations across
881 distinct URLs, with the top ~16 documents alone accounting for
roughly a third of all citations, clustering into a handful of recurring
scandal narratives:
- Epstein legal documents (flight manifests, "little black book",
  Maxwell case flight logs, deposition excerpts, Giuffre exhibits)
- Trump-Russia (intelligence allegations dossier, Mueller report,
  Rosenstein's Mueller-appointment letter, NSA spearphishing report)
- COVID-origins/institutional (Fauci NIH FOIA emails, Moderna-NIH
  confidential agreements, the DEFUSE lab-leak grant proposal)
- Pizzagate (Comet Ping Pong/Edgar Welch criminal complaint)

**Before curating**: normalize URL variants first. The SAME document
fragments across multiple forms -- confirmed e.g. `www.documentcloud.org/
documents/1508273-....html`, the same ID without `.html`, `assets.
documentcloud.org/documents/1508273/....pdf`, and an `s3.amazonaws.com/
s3.documentcloud.org/...` mirror all citing the identical black-book
document. True per-document citation counts are higher than raw per-URL
counts show. Same normalization class of issue the original curation
already found for ae911truth.org's www/non-www split -- see
`cited_content_curation_step2.md`'s "Notes on data quality".

Then hand-review the top ~20-30 normalized documents by distinct-author
count, following the SAME guardrail-against-guesswork rigor as
`cited_content_curation_step2.md` (don't guess document contents; verify
directly). Note: the older Cell-61 taxonomy (`run_link_type_regressions.py`)
already lists documentcloud.org under BOTH `leak_whistleblower` and
`legal_documents` -- a real dict-key collision in that code (silently
resolved by dict-insertion-order, `legal_documents` wins) -- worth fixing
if that taxonomy gets folded in (see `task_domain_taxonomy_unification.md`).

## 2. reddit.com / businessinsider.com / usatoday.com: confirmed correct as-is, no action needed

These were excluded from the domain-fallback fix after concentration
checks confirmed they're genuine general-purpose platforms/outlets, not
single-character sites:
- reddit.com: 2 curated rows (both r/conspiracy-specific pages tagged
  "alternative/conspiracy analysis site") were generalizing to EVERY
  subreddit on the platform -- 1,551,155 of ~1.6M citations moved out of
  `other` came from this alone before the fix.
- usatoday.com: top 15 URLs (by distinct author) cover only 7.8% of its
  9,411 citations, spread across completely unrelated topics (COVID
  fact-checks, a 2013 Israel story, NFL deaths, Maui wildfire coverage).
- businessinsider.com: top 15 cover only 6.4% of 12,964 citations, same
  pattern (media-criticism pieces, Epstein-Trump coverage, vaccine news,
  all mixed together).

No further work needed on these three -- leave on exact-page-match-only,
confirmed correct.

## 3. cia.gov / pfizer.com: unresolved tiebreak judgment calls

`build_taxonomy_matchers()`'s domain-level vote hit two real conflicts,
both currently resolved by majority-vote-with-a-printed-warning, neither
manually reviewed:
- **cia.gov**: 2 curated rows say `movement_internal_anonymous` (the
  MKUltra/Bloodlines-of-Illuminati declassified PDFs), 1 says
  `credentialed_institutional`. Majority picked movement_internal, which
  may or may not generalize correctly to future cia.gov citations --
  depends on whether the corpus's cia.gov citations skew toward
  declassified/fringe-adjacent material (as the 3 sampled here do) or
  toward routine institutional content.
- **pfizer.com**: a 1-1 tie between `other` and `movement_internal_anonymous`,
  broken arbitrarily by whichever came first in `pd.value_counts()`'s
  ordering.

Needs the same hand-review as the original 139-row curation, not an
auto-decided default either way.

## 4. r/politics `mixed_or_low_reliability` sign flip: needs tier-splitting, not just noting

`link_source_tier_regression_results.csv` shows `mixed_or_low_reliability`
flips sign between subreddits: r/conspiracy -0.133 (p<0.0001), r/politics
+0.300 (p=0.004). Confirmed this is NOT a data/matching bug --
`source_authority_scores.csv` genuinely labels Washington Post, Guardian,
The Hill, USA Today, and Newsweek as MBFC `reliability_label=mixed`
(their occasional factual-accuracy flags, not a "fringe" judgment).
Composition check: both subreddits' `mixed_or_low_reliability` citations
are dominated BY RAW COUNT by these same mainstream-but-imperfect outlets,
but r/conspiracy's version of the tier carries a much heavier alt-media
tail (zerohedge.com, corbettreport.com, bitchute.com, breitbart.com,
rumble.com, rt.com, globalresearch.ca, infowars.com -- genuinely
fringe/movement sources, largely absent from r/politics's citations to
this tier). This is the SAME pooling-hides-a-real-split problem as the
maverick whistleblower/media-personality finding earlier this session --
`mixed_or_low_reliability` needs to split into (at minimum)
`mainstream_imperfect` (WaPo/Guardian/Hill/USA Today/Newsweek-type) vs.
`alt_media` (Breitbart/RT/Zerohedge/Infowars-type) as two separate
regression tiers before the current pooled coefficient means anything.
Rerun `run_link_source_tier_regressions.py` with that split before citing
either subreddit's `mixed_or_low_reliability` number in the thesis.

## 5. Known-resolved, no action needed

- **Bare-URL coverage gap** (flagged in `task_source_authority_regression_wiring.md`
  as "not yet quantified"): checked 2026-07-22, negligible in both
  populations -- 0.04% (185/415,527) in r/conspiracy pure, 0.0% (2/10,053)
  in r/politics. The mismatched rows are genuine edge cases (users
  deliberately obfuscating URLs to dodge auto-linking, e.g. "w w w
  .google.c o m", "b!tchute.com"), not a systematic undercount. Mark this
  caveat resolved.
- **`task_source_authority_regression_wiring.md`'s own status header is
  stale** -- it says the r/politics side "needs a rerun" citing staleness,
  but `task_fix_stale_politics_pipeline.md` confirms the r/politics data
  was fixed and `run_link_source_tier_regressions.py` was rerun AFTER
  that fix (output timestamp 2026-07-20 15:45, matching). Update that
  status line so it doesn't mislead the next person who reads it first.

## When done

Items 1 and 4 are the ones that actually change numbers (documentcloud
curation adds real classification coverage; the tier-split re-run
produces a corrected, citable coefficient). Items 2/3/5 are bookkeeping
-- confirm/record and move on, don't reopen them without new evidence.
