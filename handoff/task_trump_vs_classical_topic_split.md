# Task: Trump-era vs. classical-conspiracy topic split

**Status: DONE (2026-07-20), redone with an actually-reviewed term list
after the first attempt's review gate turned out to be a no-op (see
below for the full history — kept for context, don't repeat this
process, just use the current result).**

`data/processed/candidate_topic_split_terms.csv` now has real `confirmed`
values (`yes`/`no`), reviewed by Nash/Claude 2026-07-20. Excluded:
`trump`, `biden`, `hunter biden`, `burisma`, `fake news` (70% of the
original trump_era match set was these terms alone, nothing
Trump-conspiracy-specific) and `aliens`, `alien`, `dallas`, `nasa`
(immigration/city-name/routine-space-news collisions in the classical
bucket). Kept but flagged as borderline, not cut: `satan`, `satanic`,
`occult`, `assassination` — broader than ideal but more thematically
tied to the actual conspiracy content; revisit if they turn out to
matter. Current results in
`data/processed/trump_vs_classical_regression_results.csv`
(classical N=35,179, trump_era N=13,253 — down from 49,118/44,876
pre-cleaning, exactly the coverage cost of removing real contamination).

**What changed vs. the contaminated version**: the classical `ps_prob`
procedural-skepticism penalty is robust and basically unchanged
(survives Bonferroni both before and after cleaning). The classical
`has_maverick` "premium" lost even naive significance after cleaning —
that one looks like it was partly an artifact of the contamination, not
cite it as a finding. `has_consensus_expert` newly reaches naive
significance in the cleaned classical bucket (wasn't there before) but
is now completely untestable in trump_era — that stratum's 70% coverage
loss pushed its positive-case count below the sparsity threshold in
every trump_era sub-stratum (pooled/pre-ban/post-ban), so the
classical-vs-trump-era comparison specifically for consensus-expert
citation can no longer be made with this lexicon. The trump_era "flat
profile" claim for maverick/canonical-expert/procedural-skepticism still
basically holds; a `has_link` penalty (Bonferroni-significant, pooled
and pre-ban) is the most robust trump_era-specific finding now.

**One loose end, not yet checked**: the printed significance table marks
some Logit rows lowercase `yes` (naive-only) even where the p-value is
numerically below the stated Bonferroni threshold (e.g. trump_era pooled
`has_link` Logit, p=1.68e-03 vs. threshold 2.00e-03) — possible
inconsistency in how `src/run_trump_vs_classical_regression.py` applies
the correction to Logit vs. OLS rows. Worth checking before trusting the
Logit significance markers specifically; the OLS ones look consistent.

---

## History of the first (invalid) attempt — context only, already fixed

## What went wrong the first time (fixed, but the run needs redoing)

The review checkpoint below was built and even produced the right
artifact (`data/processed/candidate_topic_split_terms.csv`, blank
`confirmed` column) — but `src/run_trump_vs_classical_regression.py`'s
filter logic *excluded* only terms explicitly marked
`no`/`exclude`/`reject`/etc., so a blank `confirmed` cell (every row,
since nobody had reviewed it) passed through as if approved. No review
ever happened between the candidate file being written (07:57) and the
regression finishing (08:01), four minutes later. Confirmed 2026-07-20:
of 46,493 comments matching any Trump-era term, 70% (32,509) matched
*only* an overly generic term (bare `trump`, `biden`, `hunter biden`,
`burisma`, `fake news`) with no distinctively Trump-conspiracy term
present at all — the "trump_era" bucket in the existing output is
mostly generic political commentary, not MAGA/QAnon-adjacent
conspiracist content specifically. The filter bug itself is fixed (now
requires an explicit affirmative mark, not just "not explicitly
rejected") — but the candidate list still needs an actual human pass
before rerunning, and the existing regression output/walkthrough should
not be cited or reused.

## Original task (still applies — the process below was correct, only
the execution skipped the review it called for)

**Reuse the existing candidate file, don't regenerate it** —
`data/processed/candidate_topic_split_terms.csv` already has the right
structure (58 terms, `term`/`proposed_bucket`/`source_topic_id`/`confirmed`
columns). It just needs an actual human pass on the `confirmed` column
before rerunning `src/run_trump_vs_classical_regression.py` (filter bug
now fixed — only rows explicitly marked `yes`/`confirmed`/`true`/`1` will
be included, so this pass is not optional/skippable this time). Flag for
whoever reviews it: `trump`, `biden`, `hunter biden`, `burisma`, and
`fake news` are almost certainly too generic to keep as bare terms —
they're the ones responsible for the 70% contamination found 2026-07-20.
Whether to drop them outright, require co-occurrence with a
conspiracy-specific term, or find a narrower phrasing is a real judgment
call for Nash/Claude, not Antigravity, per the main guardrails.

## Why

Nash's question (2026-07-20): does Trump/MAGA-adjacent conspiracism
(surging after the r/The_Donald ban, 2020-06-29) behave differently from
classical conspiracism (JFK, moon landing, chemtrails, Illuminati)? The
existing BERTopic super-topics (`data/processed/topic_time_regression_results_pure_50k.csv`
and friends) are organized by subject domain — Elections/Finance,
Geopolitics, 9/11, Alex Jones/Deep State, Sci-Fi/UFO, Environment/Health
— not by political era or valence, so none of them isolate this axis on
their own.

## What to build (no LLM calls — deterministic dictionary tagging, same
style as `stage_a_dictionary_filter.py`)

1. Draft two seed term lists:
   - Trump-era cluster: MAGA, QAnon, deep state, stolen election, Jan 6,
     rigged, adrenochrome, Q drop, etc. — pull candidate terms from
     existing entity-frequency data (`mine_corpus_entity_frequency.py`
     output, or the BERTopic topic-13/16/78/106 top terms already
     extracted — "election", "ballots", "maga", "qanon", "psyop" are
     already visible in `monthTopics1.csv`'s topic names) rather than
     inventing terms from scratch.
   - Classical-canon cluster: JFK, grassy knoll, moon landing, Illuminati,
     chemtrails, MK-Ultra, Rothschild, New World Order, etc. — same
     approach, pull from existing topic term lists (topic 49 "jfk kennedy
     oswald cia", topic 63 "moon landing apollo nasa", topic 26 "ancient
     antarctica pyramids").
2. **Judgment checkpoint, keep it brief**: produce the two candidate
   lists as a reviewable CSV (term, proposed_bucket, source_topic_id)
   with a blank `confirmed` column — same pattern as the entity-list
   guardrail elsewhere in this project. Don't merge/tag the corpus with
   an unreviewed list. This should be a five-minute skim for Nash/Claude,
   not a deep audit — the lists are seeded from already-validated topic
   labels, not invented.
3. Once confirmed, tag the full corpus (or the same low-elasticity/
   high-insider pure population used elsewhere, for consistency) with a
   `topic_era_cluster` flag (`trump_era` / `classical` / `other`) via a
   DuckDB regex pass, same style as `stage_a_dictionary_filter.py`.
4. Run the same regression formula used elsewhere, stratified by this
   new flag, plus a temporal cut at 2020-06-29 (the ban date) within the
   `trump_era` bucket specifically, to see if the post-ban surge changed
   anything within that cluster.
5. Save to `data/processed/trump_vs_classical_regression_results.csv`.

## When done

Report the term lists used, the tagging coverage (what fraction of
comments got a non-"other" label — if it's small, say so), and the
regression table. Apply proper multiple-comparison correction if
reporting per-cell significance (see how
`src/run_pure_50k_topic_analysis.py`'s `write_synthesis_report` does
this — Bonferroni across every OLS test actually run, not just the ones
being highlighted). Stop at reporting the table; don't write "key
discoveries" prose.
