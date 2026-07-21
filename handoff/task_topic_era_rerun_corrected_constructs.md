# Task: Rerun the topic/era Bonferroni analysis with corrected constructs

**Status: not started (2026-07-21).**

## Why

`src/run_pure_50k_topic_analysis.py` produced the project's
Bonferroni-corrected topic/era stratification (67 OLS tests, honest null
result: no epistemic-construct effect survives correction in any
topic/era cell except `has_link`/`log_char_length`) — but that ran
before today's entity-list fixes (Brand dropped, Hawking/Ventura/
Hancock/Kory disambiguated), before the 5-tier link source-quality
taxonomy existed, and before `hs_prob` was wired into anything. The
result may or may not change once rerun with corrected constructs —
that's exactly why it needs rerunning rather than assumed either way.

**Do NOT merge this into `run_integrated_regressions.py`'s
elasticity/insider-threshold grid.** That was explicitly considered and
rejected in conversation on 2026-07-20/21: crossing topic/era with the
existing 24-cell grid would multiply sparsity (has_consensus_expert is
already thin at 24 cells) and, more importantly, the topic/era analysis's
whole point is its Bonferroni correction across many simultaneous tests
— folding it into an already-uncorrected grid would just manufacture
more chances for a spurious "significant" cell without adding the
multiple-comparisons discipline that makes the topic/era result
trustworthy in the first place. Keep them as separate, differently-built
analyses.

## What to build

1. Rerun `src/run_pure_50k_topic_analysis.py` as-is first, to get a
   baseline "what changed" comparison — don't skip straight to modifying
   it.
2. Update it to use: the corrected entity lists
   (`load_entities_split_corrected()`, already used throughout the
   rest of the pipeline), the 5-tier `link_source_tier` taxonomy instead
   of flat `has_link` (reuse `run_link_source_tier_regressions.py`'s
   classification functions, same as `run_integrated_regressions.py`
   does), and add `hs_prob` as a construct (needs `HEDGED_SUSPICION_PATH`
   joined in, same pattern as `run_integrated_regressions.py`).
3. Keep the Bonferroni correction exactly as designed — don't loosen it
   just because more tests are now being run.

## When done

Report old-vs-new side by side: which cells' significance changed, and
whether the "no epistemic-construct effect survives correction" headline
still holds with the corrected constructs. If it flips for
`has_consensus_expert` specifically (given that's the construct that
strengthened the most from the entity-list fix), that's worth flagging
prominently, not burying in a table.
