# Task: Build a hand-verified maverick_authority allowlist

**Status: not started, candidate file already generated. High priority
— this affects `has_maverick`, a headline regression variable, cited in
every core regression throughout the project.**

## Why

`consensus_expert` had this exact problem and was already fixed via
`src/consensus_experts_verified.py` (a hand-verified allowlist replacing
the raw, unaudited `final_bucket_guess` bucketing). `maverick_authority`
never got the equivalent treatment — `load_entities_split_corrected()`
in `src/rerun_refined_regressions_v2.py` still pulls straight from
`entity_final_review.csv`'s `final_bucket_guess == 'maverick_authority'`
bucket (418 entities), patched only with the 17 whistleblower additions
in `src/verified_maverick_additions.py`.

Confirmed 2026-07-20: that bucket mixes genuine people (Seth Rich, Alex
Jones, Joe Rogan, David Icke, Tucker Carlson) with generic conspiracy
*topic* vocabulary that isn't a person at all — "New World Order",
"Deep State", "Flat Earth", "Blue Beam", "Chemtrail", "Conspiracy
Theory"/"Theorist"/"Theories", "Bilderberg", organizations ("Judicial
Watch", "AE911Truth", "Natural News", "Scientology"), and even the bare
plural "Whistleblowers". Quantified against the actual corpus: of 36,116
comments in the pure population that trigger `has_maverick`, **9,080
(25.1%) match only a topic term, no actual person name present at all**.
This affects every reported `has_maverick` coefficient throughout the
project (core regression: +0.248 r/conspiracy / +0.544 r/politics;
topic/era stratification; link-source-tier wiring; the maverick-stance
HITL queue's entity highlighting, which is what surfaced this).

## What's already done (don't redo)

`data/processed/candidate_maverick_authority_review.csv` — all 418
entities, with a `proposed_bucket` column (`likely_person` /
`likely_topic_not_person`, 374/44 split by a crude keyword heuristic —
**treat this as a starting hint, not a verdict**, it will have both
false positives and false negatives) and a blank `confirmed` column.

## What to do

1. **Judgment checkpoint — this is the actual work, not delegatable to
   Antigravity unsupervised (guardrail 3).** Review
   `candidate_maverick_authority_review.csv` and fill in `confirmed`
   (`yes`/`no`) for each entity: does it name a specific real person
   functioning as a maverick/whistleblower/anti-establishment authority
   figure, or is it a topic, organization, phenomenon, or generic
   category term? The `likely_topic_not_person` bucket (44 entities) is
   the fast pass — most of those are probably clear "no"s. Spot-check a
   sample of the `likely_person` bucket (374 entities) too, since the
   heuristic is keyword-based and will have missed some non-person terms
   that don't contain an obvious marker word (e.g. an organization name
   or acronym that doesn't look like a topic).
2. Once reviewed, build `src/maverick_authority_verified.py` mirroring
   `src/consensus_experts_verified.py`'s structure exactly (a plain
   `VERIFIED_MAVERICK_AUTHORITY` list of confirmed entity strings).
3. Update `load_entities_split_corrected()` (currently duplicated across
   `rerun_refined_regressions_v2.py`, `run_link_source_tier_regressions.py`,
   `run_core_comparison_robustness.py`, `build_maverick_stance_queue.py`,
   and `run_pure_50k_topic_analysis.py` — check for other copies too,
   this pattern has spread) to use the new verified list instead of the
   raw bucket, same way `consensus` already does.
4. Rerun the core regression and report the new `has_maverick`
   coefficients next to the old ones. Given 25% of matches are pure
   topic-noise, expect a real, possibly substantial change — that's the
   point, not a bug if it happens.

## When done

Report the final list size, what got cut, and the before/after
coefficient comparison. Don't overwrite `refined_regression_results_v2.csv`
directly — save alongside for comparison, same convention as other
reruns this session.
