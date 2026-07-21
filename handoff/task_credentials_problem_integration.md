# Task: Integrate the credentials-problem scaffolding into an actual finding

**Status: not started (2026-07-21).** Everything this task needs already
exists as separate, validated pieces — this task is about assembling
them into one comparative finding, not building new infrastructure.

## Why

The thesis's "credentials problem" question — does this community's
epistemic style depend on genuine credentials, or something else
entirely — has been approached three separate ways this session, each
producing real results, none of them yet combined:

1. **Entity-based** (`has_maverick`/`has_consensus_expert`, the
   per-entity breakdown in `data/processed/per_entity_stance_breakdown.csv`)
   — shows *who* gets named and how they're received, but is a "weak
   signal" (Nash's framing) because it only sees people prominent enough
   to be pre-listed and named directly.
2. **`source_citation`** (`src/score_authority_appeal_full.py`, kappa=0.655,
   scored on the 4.78M-row enriched corpus) — entity-agnostic, catches
   "cites something as backing" regardless of whether a listed entity is
   named. 97.8% of high-scoring comments match no entity at all — most
   citation behavior is invisible to (1).
3. **URL/citation-content curation** (`src/rank_cited_urls_by_author.py`,
   `handoff/cited_content_curation_step2.md`) — identifies *what kind*
   of thing gets cited: credentialed-institutional (CDC, NEJM, DOJ),
   individual-with-implied-credentials (named whistleblowers, Corbett,
   Corey), or anonymous/movement-internal (QAnon archives, Cryptome).

## What to build

1. Classify the curated URL list (start with the top ~50 already
   identified in `cited_content_curation_step2.md`, extend further down
   `cited_urls_ranked.csv` as needed) into a small taxonomy — something
   like `credentialed_institutional` / `individual_named_source` /
   `movement_internal_anonymous` / `other`. Don't over-engineer the
   category count; 3-4 buckets that actually separate the real cases is
   better than a taxonomy nobody can apply consistently.
2. For comments where `source_citation==1` AND the linked URL is
   identifiable in that taxonomy, cross-tabulate against
   `has_maverick`/`has_consensus_expert` (and their stance, hostile vs.
   endorsement, where available) — does anti-consensus-position sourcing
   actually lean on a *different mix* of source types than
   consensus-aligned sourcing, or just a *smaller total volume* of named
   sourcing?
3. Report the cross-tab plainly. If the pattern is "anti-consensus
   comments cite fewer things overall, but what they DO cite skews
   individual/movement-internal rather than institutional" — that's the
   actual credentials-problem finding, worded precisely, not "conspiracy
   people don't cite sources" (which (2) above already disproves at the
   aggregate level).

## When done

This is the piece that turns three separate pieces of scaffolding into
one citable finding — don't chain into further exploration once the
cross-tab is built and reported, that's a judgment call for Nash/Claude
on what (if anything) to build next.
