# Task: Test whether the epistemic markers are a general style, not topic-specific content

**Status: not started. Mechanical once scoped (below) — a join and a
regression, not a new judgment call — but read the framing carefully
before building, this is a specific hypothesis test, not a re-run of an
existing script.**

## Why

`src/run_pure_50k_topic_analysis.py`'s properly-corrected topic/era
stratification found no epistemic-construct effect (`has_maverick`,
`has_canonical_expert`, `has_consensus_expert`, `pe_prob`, `ps_prob`)
survives Bonferroni correction in any single topic or era cell, even
though the pooled/aggregate effects are real and well-powered (see
`ANTIGRAVITY_HANDOFF.md`). One plausible reading, raised 2026-07-20: this
is consistent with the "monological belief system" pattern in the
conspiracy-belief literature (Goertzel 1994; also discussed under
generalized/generic conspiracist ideation, e.g. Wood, Douglas & Sutton)
— conspiracist reasoning behaves as a domain-general disposition rather
than topic-specific content knowledge. If that's right, these markers
should function as a general epistemic *style* applied uniformly across
whatever topic an author happens to be posting in, which is exactly
compatible with "real pooled effect, no topic-specific signature."

This hasn't been tested directly. The existing topic-stratified
regression asks "does this predictor's effect differ **by topic**" (a
between-topic question, comments as the unit). The sharper test of the
general-style hypothesis is a **within-author, between-topic** question:
does an author's own average usage rate of these markers predict their
engagement **independent of which topic they're posting in**?

## What to build

1. Using `data/processed/user_topic_specialization.csv` (author-level
   HHI/dominant-topic data, already built) as the author roster, join
   back to each author's full comment set in the pure r/conspiracy
   population (same population `rerun_refined_regressions_v2.py` uses)
   and compute, per author: `maverick_rate`, `consensus_rate` (share of
   their own comments with `has_maverick`/`has_consensus_expert` == 1),
   mean `pe_prob`, mean `ps_prob`, plus their existing `hhi_specialization`
   and engagement metrics (`peak_upvotes`, `median_upvotes`, `big_hits`
   from `df_users_live.csv`, already joined in
   `user_topic_specialization.csv`).
2. Regress an engagement outcome (e.g. `log(median_upvotes + 1)`) on
   `maverick_rate + consensus_rate + pe_prob_mean + ps_prob_mean +
   hhi_specialization` (author-level, not comment-level — one row per
   author, restrict to authors with a minimum comment count, e.g. >=10,
   for rate estimates to be stable; report how many authors this
   restriction leaves).
3. The test of the hypothesis: do `maverick_rate`/`consensus_rate`/etc.
   predict engagement **after controlling for `hhi_specialization`**? If
   they do, and `hhi_specialization` itself doesn't add much beyond
   them, that's supportive of "general style" over "topic-specific
   content" as the driver. If `hhi_specialization` dominates instead,
   that points the other way (topic-specialization matters more than
   general marker usage).
4. Save to `data/processed/general_epistemic_style_test.csv`.

## When done

Report the coefficients and which one dominates, plus the N of authors
that survived the minimum-comment-count filter (small N would weaken
this considerably — say so plainly). This is exploratory/interpretive
groundwork for the thesis discussion chapter, not a confirmatory test —
don't overstate what a single author-level regression can prove either
way.
