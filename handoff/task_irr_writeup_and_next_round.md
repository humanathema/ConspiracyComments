# Task: Write up the AI-vs-human agreement check; decide on real IRR

**Status: partially done (2026-07-21) — the check itself ran, the
writeup and the harder decision (a second human rater) haven't.**

## Why

Nash correctly identified inter-rater reliability as a real weak point:
every human-labeled construct in this project (stance, maverick_authority,
hedged_suspicion, etc.) has been rated by one person (Nash) across every
level of judgment. The "kappa" numbers reported throughout the project
are all classifier-vs-Nash agreement, not true inter-rater reliability
(which needs two independent human coders).

As a partial, immediately-actionable substitute, Claude blind-rated two
samples pulled from already-rated data (committed ratings to a file
before ever seeing the true labels, then revealed and scored):

- **Stance** (n=40 rows across all 4 base queues, hostile/endorsement
  subset n=21): kappa=0.422, 71.4% agreement. Full 5-way exact match
  only 50%. Higher than the trained stance classifier's own CV kappa
  (0.345), but only "fair" agreement in absolute terms — real inherent
  fuzziness in the construct, not just classifier weakness. Specific
  disagreement pattern: Claude under-called "endorsement" for
  tonally-flat/factual citations that functionally back the commenter's
  argument (the codebook counts function over tone; Claude's default
  reading leaned toward tone). Also missed 2 of 3 likely `wrong_match`
  cases identified from context alone (correctly caught 1).
- **`source_citation`** (n=25, from `labeled_2k_with_scores.csv`'s
  `human_1` subset): kappa=0.884, 96% agreement (24/25 exact match).
  Higher than the trained classifier's own CV kappa (0.655) — the
  construct itself is solid, the classifier has real headroom.

Raw working files (blind samples + committed ratings + truth, for
reproducibility/audit): `/tmp/stance_blind_SAMPLE.csv`,
`/tmp/stance_blind_TRUTH.csv`, `/tmp/sc_blind_SAMPLE.csv`,
`/tmp/sc_blind_TRUTH.csv` — these are in `/tmp`, not the repo, and may
not survive a machine restart. Regenerate via the sampling code in the
2026-07-21 conversation history if needed, or just rerun a fresh sample
(better, since the /tmp files could be overwritten).

## What to do

1. **Write this up properly** in whatever document ends up being the
   thesis methods section (or a dedicated `handoff/` note first) —
   frame it precisely as "AI-vs-single-human agreement, not
   inter-rater reliability," don't let it get cited as if it were IRR.
2. **Decide on a real second rater.** This is a resourcing decision only
   Nash can make — options include: recruiting an actual second human
   coder for a subsample of each major construct (the methodologically
   correct fix), or accepting single-coder labeling as a stated,
   disclosed limitation (defensible, just needs to be explicit in the
   methods section rather than glossed over).
3. If continuing the AI-vs-human check further: expand the sample size
   (40/25 is a reasonable first pass, not enough to fully characterize
   the disagreement pattern), and consider running it on
   `personal_experience`/`procedural_skepticism`/`hedged_suspicion` too
   — not done yet, lower priority since those constructs aren't
   currently load-bearing on any open question the way stance and
   source_citation are.

## When done

Report back what got decided on (2), since that determines how the
whole methods section frames labeling reliability — don't proceed with
more rating rounds of any kind until that's settled.
