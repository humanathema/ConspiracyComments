# Task: Apply the already-built maverick_authority non-person exclusion list

**Status: DONE (2026-07-20).** Nash hand-reviewed the full 446-entity
`maverick_candidate_entities_scored.csv` directly (scoring criterion:
not strictly "is this a person" — organizations functioning as an
alternative-authority source count, e.g. AE911Truth; platform-driven
commentators count too, e.g. Alex Jones/Joe Rogan/Tucker Carlson,
deliberately not disentangling the opinion/research overlap in this
domain for now) rather than working from the non-person exclusion list
this task originally proposed — a cleaner, more direct path since that
file already had real categories. Result: `src/maverick_authority_verified.py`
(446 entities + the 17 from `verified_maverick_additions.py`, 459
total), wired into `load_entities_split_corrected()` (the canonical
definition in `rerun_refined_regressions_v2.py`, which 5 other scripts
import; a duplicate copy in `run_link_source_tier_regressions.py` was
consolidated into an import instead) and into
`combined_maverick_detector.py` (feeds the attribution-scorer
validation — same contamination existed there independently). Core
regression rerun with the fix in progress as of this entry — see
`ANTIGRAVITY_HANDOFF.md` for the before/after once it lands.
**Follow-on, separate task**: `handoff/task_maverick_entity_disambiguation.md`
— the verified list is almost all full names, and ~99% of multi-word
entries have no bare-surname/nickname/partial-form variant, which is a
real, larger recall problem than this task's contamination fix was.

*Original status text below, kept for history only — the "not started"
framing no longer applies:*

> Status: not started, but far more mechanical than it first looked —
> the hard work (identifying candidates, reasoning about why) is already
> done and sitting unused. High priority — affects `has_maverick`, a
> headline regression variable, cited in every core regression throughout
> the project.

## The history here (this task's original version got this wrong —
correcting it)

On 2026-07-15, alongside the `consensus_expert` cleanup that produced
`src/consensus_experts_verified.py`, a **parallel maverick pipeline ran
too** and stalled one step short of the finish line:

1. `src/build_maverick_candidate_list.py` (top-down: Wikipedia
   whistleblower/conspiracy-theorist categories, cross-referenced
   against corpus frequency) and `src/mine_corpus_entity_frequency.py`
   (bottom-up: every named entity actually appearing in the corpus)
   together produced `data/processed/maverick_candidate_entities_scored.csv`
   — 446 entities with real taxonomic categories (`whistleblower`,
   `jfk_theorist`, `911_theorist`, `ufo_theorist`, `antivax`,
   `covid_theorist`, `credentialed_advocacy_org`, `qanon`, `flat_earth`,
   `hiv_aids_denialist`, `chemtrail_theorist`, `pseudoarchaeology`,
   `climate_skeptic_org`, `conspiracy_general`, etc.) and corpus mention
   counts.
2. `src/flag_non_person_contamination.py` (documented in
   `handoff/PROJECT_INVENTORY.md` as being for the consensus-expert
   cleanup only — that's an inventory gap, it was also run against the
   maverick candidates) queried Wikipedia descriptions and spaCy NER
   tags and produced `data/processed/maverick_non_person_candidates.csv`
   — **384 entities already flagged as likely non-person**, each with a
   `wp_description`, `doc_count`, and specific `reason_flagged`
   (`known_non_person_term`, `spacy_ner_tag: ORG`, description-keyword
   matches like "theory"/"organization"/"movement"/"website"). This is
   exactly the contamination this task exists to remove — "New World
   Order", "Deep State", "Roswell", "UFOS", "Conspiracy Theory",
   "Whistleblowers", "NLP", "Demons", "Bilderberg Group", etc. are all
   already in here with the evidence already gathered.
3. **Both files have a `decision` column that was never filled in, and
   neither was ever wired into the live pipeline.** Unlike
   `consensus_expert`, no `maverick_authority_verified.py` equivalent
   was ever built. `load_entities_split_corrected()` (in
   `src/rerun_refined_regressions_v2.py` and every script that copies
   it) still pulls straight from `entity_final_review.csv`'s raw,
   unaudited `final_bucket_guess == 'maverick_authority'` bucket (418
   entities), patched only with the 17 whistleblower additions in
   `src/verified_maverick_additions.py`.

Confirmed 2026-07-20: **194 of the 384 already-flagged non-person
candidates are sitting unfiltered in that live 418-entity bucket right
now.** Separately quantified against actual corpus matches: of 36,116
comments in the pure population that trigger `has_maverick`, 9,080
(25.1%) match only a topic term, no person name present at all —
consistent with, and explained by, this contamination. This affects
every `has_maverick` coefficient reported throughout the project,
including the core regression's headline +0.248 (r/conspiracy) / +0.544
(r/politics).

(An earlier version of this task file generated its own cruder,
keyword-heuristic candidate file from scratch, not knowing this real
one already existed. That file has been deleted — use
`maverick_non_person_candidates.csv` instead, it's much better
reasoned.)

## What to do

1. **Judgment checkpoint — the actual work, not delegatable to
   Antigravity unsupervised (guardrail 3).** Fill in the `decision`
   column in `data/processed/maverick_non_person_candidates.csv` (384
   rows) — for each, confirm `exclude` or override to `keep` if the
   flag looks wrong on inspection. Most of these look like clear-cut
   exclusions given the `reason_flagged` evidence already attached, so
   this should go faster than a from-scratch review — it's mostly
   spot-checking the reasoning already given, not doing the reasoning
   from zero. Pay closer attention to the borderline ones: some flagged
   entries are actually people whose Wikipedia description just happens
   to contain a matched keyword (e.g. "Chelsea Manning" is flagged for
   matching "act" in "American activist and whistleblower" — that's a
   real person, a false positive from the crude keyword match; check
   for others like this).
2. Build `src/maverick_authority_verified.py`: take the live 418-entity
   `final_bucket_guess == 'maverick_authority'` bucket, remove every
   entity marked `exclude` in the reviewed file, keep the rest as
   `VERIFIED_MAVERICK_AUTHORITY` (mirror `consensus_experts_verified.py`'s
   structure). Optionally cross-check against
   `maverick_candidate_entities_scored.csv`'s categories for anything
   worth adding, but that's a secondary enhancement, not required for
   this task's core fix.
3. Update `load_entities_split_corrected()` — currently duplicated
   across `rerun_refined_regressions_v2.py`,
   `run_link_source_tier_regressions.py`,
   `run_core_comparison_robustness.py`, `build_maverick_stance_queue.py`,
   and `run_pure_50k_topic_analysis.py` (check for other copies too,
   this pattern has spread) — to use the new verified list instead of
   the raw bucket, same way `consensus` already does.
4. Rerun the core regression and report the new `has_maverick`
   coefficients next to the old ones. Given 25% of matches are pure
   topic-noise, expect a real, possibly substantial change — that's the
   point, not a bug if it happens.

## When done

Report the final list size, what got cut, and the before/after
coefficient comparison. Don't overwrite `refined_regression_results_v2.csv`
directly — save alongside for comparison, same convention as other
reruns this session.
