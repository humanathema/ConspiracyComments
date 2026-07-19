# Task: Build (don't rate) two more stance-detection queues

**Status: not started. Mechanical data-generation only — no rating, no
interpretation. Antigravity's job here ends at producing queue CSVs.**

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
