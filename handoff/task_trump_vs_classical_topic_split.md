# Task: Trump-era vs. classical-conspiracy topic split

**Status: not started. Mostly mechanical, one small judgment checkpoint
(term-list review — see below, keep it short).**

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
