# Task: rebuild entity mention counts via full-corpus regex (fix systematic undercounting)

**Status: scoped 2026-07-26, ready to build, but READ THE VERIFICATION
SECTION FIRST and treat it as a hard gate, not a suggestion.** This task
touches counts that feed a lot of downstream material (the explorer's
Named Entities table, entity time series, stance breakdowns) -- get the
verification wrong and you'll confidently ship worse numbers than what's
there now. If you can't make the verification numbers in this doc match
within a small tolerance, stop and report back rather than pushing
forward.

## Why (found 2026-07-26, verified by direct corpus queries, not assumed)

Three distinct, confirmed problems with how entity mention counts are
currently produced:

1. **`corpus_entity_frequency.csv` (built by `src/mine_corpus_entity_
   frequency.py`) only scans ~12% of the long-comment corpus, by explicit
   design** -- its own docstring says full spaCy NER over 21.4M rows was
   estimated at ~32 hours, so it instead scans ~1.6M authority/evidence-
   flagged rows + a random 1M sample (~2.6M of 21.35M rows). This causes
   systematic 5-8x undercounts wherever it's the source. Confirmed:
   Netanyahu shows 1,755 in `corpus_entity_frequency.csv` vs. 14,084 in a
   direct full-corpus regex count of the same file it was sampled from --
   ratio 12.5%, matching the sampling fraction almost exactly.
2. **A separate ~18.58M-row short-comment corpus
   (`data/processed/conspiracy_comments_short_lte100chars_mapped.parquet`,
   mean length 48.7 chars) exists with its own cache infrastructure
   already built (`entity_mentions_cache_short.parquet`), but isn't
   unioned into the `entity_monthly` regex-extraction query in
   `src/build_drilldown_backend_db.py`** -- that file defines a
   `SHORT_CORPUS` constant and never uses it in that specific query.
   This misses another 14-34% of true mentions depending on the entity
   (measured directly, see table below).
3. **Some entities are identified in `entity_final_review.csv` (real
   Wikipedia-level disambiguation) but never got a `final_bucket_guess`
   assigned** -- e.g. AOC: `best_identity="Alexandria Ocasio-Cortez"`,
   real `wp_description`, but blank bucket. Since `build_missing_entity_
   candidates.py` excludes anything already present in `entity_final_
   review.csv` (regardless of whether it got a real bucket), she's
   invisible in *both* the missing-entities gap list *and* the classified
   tables. Not a counting problem -- a pipeline crack.

**What this is NOT**: a spaCy-accuracy problem. Direct random-sample
validation (30-50 matches, manually read, not just a keyword-proximity
heuristic) found ~0% false positives for both "trump" and "HRC" in this
corpus -- simple regex matching against a known candidate name is
reliable here once you already have the name. The damage is from *scope*
(1 and 2 above), not from NER/regex precision. A better NER tool would
help with a *different* problem (discovering entities nobody's named
yet) but wouldn't fix 1-3 on its own.

## Reference numbers -- your rebuild must reproduce these (verification gate)

Computed directly against `data/processed/empath_scores_full_mapped.parquet`
(long, 21,349,908 rows, char_length 101-17365, mean 370.5/median 234) and
`data/processed/conspiracy_comments_short_lte100chars_mapped.parquet`
(short, 18,580,083 rows, char_length 0-100, mean 48.7/median 47), both
via case-insensitive whole-word DuckDB `regexp_matches`, 2026-07-26:

| entity | pattern used | long count | short count | combined |
|---|---|---|---|---|
| trump | `\btrumps?\b` | 1,228,530 | 299,905 | 1,528,435 |
| AOC (deduped, incl. "Occasio" misspelling) | `\bAOC\b\|\bOc+asio.Cortez\b\|\bAlexandria Oc+asio\b` | 10,353 | 3,385 | 13,738 |
| Netanyahu | `\bNetanyahu\b` | 14,084 | 2,490 | 16,574 |
| HRC | `\bHRC\b` | 13,674 | 1,922 | 15,596 |

Random-sample validation already done (don't redo unless you change the
pattern): "trump" (50 random matches, 0 non-Trump usages), "HRC" (40
random matches, 0 non-Hillary usages -- despite "HRC" also commonly
meaning Human Rights Campaign in general English, this corpus's topic
skew makes it a non-issue here specifically; don't assume that transfers
to other ambiguous acronyms without checking each one).

Your rebuilt pipeline's numbers for these four should land at or very
near these combined totals (small differences from exact regex
construction are fine; being off by anything like the 5-8x factor that
motivated this task is not). **If they don't match, the bug is in your
rebuild, not in these reference numbers** -- these were independently
verified by direct query, not inferred from any existing pipeline
output.

## What to build

1. **A new full-corpus (long + short, unioned) regex-based entity
   frequency count**, covering every name/variant already present in
   `entity_final_review.csv`, `missing_entity_candidates.csv`, and the
   maverick/canonical candidate list CSVs (don't try to discover new
   names -- that's the separate, bigger NER-tool task, out of scope
   here). Reuse the exact alternation-regex pattern shape already in
   `build_drilldown_backend_db.py`'s `entity_monthly` construction
   (`\b(name1|name2|...)\b`, longest names first so multi-word names win
   over their substrings), just add the `SHORT_CORPUS` union it's
   currently missing. Output to a new file, e.g. `data/processed/
   entity_frequency_full_corpus.csv` -- **do not overwrite `corpus_
   entity_frequency.csv` in place**, this is a new, independent
   measurement that should be reviewable side-by-side with the old one,
   not a silent replacement.
2. **Fix `src/build_drilldown_backend_db.py`'s `entity_monthly` query**
   to actually union `SHORT_CORPUS` (the constant already exists,
   currently unused in that specific query) -- small, contained change.
   Re-run the backend rebuild once this lands so the live explorer's
   entity_monthly numbers reflect both corpora.
3. **Audit pass over `entity_final_review.csv`**: find every row with a
   non-empty `best_identity`/`wp_description` but a blank `final_bucket_
   guess` (AOC is one confirmed example -- there are likely more).
   Produce a reviewable CSV of these (same convention as `missing_
   entity_candidates.csv`: blank decision column, Nash's call, not
   something to auto-bucket). Don't touch `entity_final_review.csv`
   itself.
4. **Ambiguity spot-check for risky names**: for any candidate name that
   is short (<=4 chars), a bare acronym, or a common English word/verb,
   pull a random sample (30-50 matches) from the full-corpus regex hits
   and read them (or have a human -- flag for Nash rather than
   auto-deciding) before trusting the count. Not required for every
   entity -- most multi-word proper names (e.g. "Alexandria Ocasio-
   Cortez") don't need this, it's specifically for the ambiguous-string
   case. Use the trump/HRC checks above as the template for how to do
   this (random sample via `ORDER BY random() LIMIT N`, not a keyword-
   proximity pre-filter -- that approach was tried first this session
   and produced a badly biased false-positive estimate, see session
   history if curious why).

## Guardrails

- No LLM/API calls anywhere -- everything above is deterministic regex +
  DuckDB, matching the existing budget guardrail.
- Don't overwrite `entity_final_review.csv`, `missing_entity_candidates.
  csv`, or `corpus_entity_frequency.csv` in place. All of this task's
  outputs are new files, reviewable alongside the old ones, never a
  silent replacement.
- Don't auto-bucket anything found in step 3 -- reviewable list only,
  same as every other entity-classification decision in this project.
- This is a real accuracy correction to numbers that may already have
  been cited/discussed -- flag clearly in your report-back whether any
  already-written analysis (stance breakdowns, crosstabs, thesis text)
  cites the old undercounted numbers, so Nash can decide whether that
  needs a methods-limitation note or a re-run, rather than silently
  leaving stale citations in place.
- **Report back and stop at this task's boundary.** Don't chain into the
  separate full-NER-discovery project (a different, bigger, tool-choice
  decision) without a checkpoint.
