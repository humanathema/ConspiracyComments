# Task: Trump-era vs. classical-conspiracy topic split

**Status: attempted 2026-07-20, result INVALID, needs redo. Do not use
`data/processed/trump_vs_classical_regression_results.csv` or the
walkthrough at `/Users/nash/.gemini/antigravity/brain/c67f482a-0056-4ddd-a994-286b7b505769/walkthrough.md`
as-is — see below.**

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
