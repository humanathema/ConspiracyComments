# Task: Entity fixed-effects regression for the per-entity stance finding

**Status: proposed, not decided (2026-07-21).** Nash's response when
this was proposed was "could do this, idk" — genuinely undecided, not a
clear yes. Check with Nash before spending real time on this rather than
assuming it's wanted.

## Why

`data/processed/per_entity_stance_breakdown.csv` shows a real, striking
pattern — leak-source whistleblowers (Wikileaks, Assange, Snowden)
near-universally endorsed, media-personality mavericks (Jones, Carlson,
Stone, Gaetz) near-universally attacked, and it's not a prominence effect
(Spearman corr(mention_count, pct_hostile) = -0.08 for maverick). That's
currently a descriptive finding (mean stance_prob / pct_hostile per
entity), not a regression result. An entity fixed-effects model would let
you say "controlling for which entity is mentioned, does stance still
predict traction" and separate the pure compositional story (which
entities dominate which population) from any residual within-entity
effect the descriptive table can't see.

## What to build

1. Reuse the long-format (comment, entity, stance_prob) table already
   built inside `src/per_entity_stance_breakdown.py` (currently only
   aggregated to per-entity summary stats, not saved in long form —
   you'll need to save the long table itself, not just re-derive the
   summary).
2. Fit `high_traction ~ stance_prob + C(entity) + pe_prob + ps_prob +
   log_char_length`, restricted to entities with enough volume (reuse
   `MIN_MENTIONS_TO_REPORT = 20` or raise it — with `C(entity)` as a
   categorical, you need real per-entity N, not just 20, probably 100+
   per entity to avoid the model being dominated by sparse-entity noise).
   Expect this to only be feasible for the top ~20-30 entities by volume,
   not the long tail.
3. Compare `stance_prob`'s coefficient with and without the entity
   fixed effects. If it shrinks toward zero once entity is controlled
   for, that confirms the effect is purely compositional (which entity
   dominates). If it stays similar, there's a genuine within-entity
   stance effect on top of the compositional one.

## When done

Report the before/after comparison plainly — a shrunk coefficient here
is not a failure, it's confirmation of the compositional story already
established via the population-comparison work.
