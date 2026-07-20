# Task: Build (don't rate) two more stance-detection queues

**Status: DONE — all 3 queues built AND rated by Nash (confirmed 2026-07-20).**
`data/hitl/queue_maverick_stance.csv` (240/240 rated),
`data/hitl/queue_consensus_stance_politics.csv` (124/124 rated), and
`data/hitl/queue_maverick_stance_politics.csv` (240/240 rated) are all
complete. Build scripts for the two r/politics queues exist at
`src/build_consensus_stance_queue_politics.py` and
`src/build_maverick_stance_queue_politics.py` (uncommitted as of
2026-07-20 — mirror `src/build_consensus_stance_queue.py` as intended).
All three are registered in `src/hitl_rater.py`. Note: a separate,
unrelated change to `hitl_rater.py` earlier in the session added `../`
prefixes to every queue path, which broke the documented invocation
(`python3.12 src/hitl_rater.py` from the repo root); this has been
reverted, don't reintroduce it. The r/politics queues were built against
the now-fixed, expanded r/politics sample (see
`handoff/task_fix_stale_politics_pipeline.md` — crawl completed same
day), not the stale N=30,881 one.

**Found during rating, not yet fixed — flagged by Nash 2026-07-20:**
at least two bare-form entries in the entity lists are producing noise
in the rated queues: `"Brand"` (bare surname alias for Russell Brand,
`src/maverick_authority_verified.py:537`) appears to be matching as
common-noun/other noise ("brand new", "name brand", etc. — full noise),
and `"Hawking"` (bare surname alias for Stephen Hawking,
`src/consensus_experts_verified.py:134`) is partially colliding with the
verb "hawking" (e.g. "hawking a book/product" — partial noise). Nash is
examining the extent of this and may fix the alias lists and rerun the
affected queues. Until resolved, treat `has_maverick`/
`has_consensus_expert` positive-case counts drawn from these bare forms
as having some unknown amount of false-positive contamination — this is
the same bare-form-collision risk `handoff/task_maverick_entity_disambiguation.md`
already flagged in general, now with two concrete confirmed instances.
Anyone touching either alias list should check for other common-noun/
common-verb collisions among the other bare surnames in both
`UNAMBIGUOUS_MAVERICK_ALIASES` and the consensus-expert bare-form list
before trusting counts built from them.

## Why

The completed `queue_consensus_stance.csv` (238/238 rated, see
`ANTIGRAVITY_HANDOFF.md`) only covers *consensus-expert* mentions inside
*r/conspiracy*. Two adjacent questions are still open:

1. Does the same "engagement lightning rod regardless of stance" pattern
   hold for **maverick/whistleblower mentions** (`has_maverick`) too, or
   is it specific to consensus-expert mentions?
2. Does either pattern hold in **r/politics** (the control subreddit,
   `data/processed/comparison_politics_staged_scored.parquet`), or is
   stance-blind engagement a r/conspiracy-specific phenomenon?

## What to build (mirror `src/build_consensus_stance_queue.py` exactly —
same blinding/stratification logic, do not redesign)

1. `data/hitl/queue_maverick_stance.csv` — same construction as the
   consensus queue: comments where `has_maverick == 1` in the r/conspiracy
   pure population, stratified by traction (aim for the same ~120
   high/120 low split the consensus queue used), blinded (no upvote data
   shown, rows shuffled), same schema (`id, full_text, human_stance,
   notes, entity_spans, parent_id, link_id`).
2. `data/hitl/queue_consensus_stance_politics.csv` — same construction,
   but drawn from `comparison_politics_staged_scored.parquet` /
   `comparison_politics_scored.parquet` where `has_consensus_expert == 1`.
   N will be small (41 positive cases found in the 30,881-comment
   control sample as of 2026-07-20) — stratify by traction if the split
   allows it, otherwise just note the population is small and queue all
   of it.
3. `data/hitl/queue_maverick_stance_politics.csv` — same, for
   `has_maverick == 1` in the r/politics sample.

Register each new queue with `src/hitl_rater.py` the same way
`queue_consensus_stance` was added (see git history around 2026-07-15/17
for that diff) so Nash can rate them at `http://localhost:8420` — but
**do not rate any of them yourself**, same guardrail as the original
consensus-stance task.

## When done

Report back queue sizes and stop. Rating and the eventual stance ×
traction analysis (mirror `src/analyze_consensus_stance.py`, parameterize
it to take a queue path + strata-map path instead of hardcoding the
consensus one) are separate follow-on tasks, not this one.
