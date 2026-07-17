# Task: Finish validating the attribution scorer, then (only after
# review) wire it into the core regression

## Status: mostly done, one review checkpoint before the final step

`src/attribution_confidence_scorer.py` replaces bare entity-mention
co-occurrence with a scored check (ordering, proximity, competing-source
detection) for whether a maverick/consensus entity is genuinely being
cited as a source, vs. merely mentioned, discussed, or accused.

**Already fixed, don't redo**:
- Original appositive-vs-accusation bug (credential-appositive patterns
  like "X, a virologist, ..." could never be overridden by an accusation
  verb later in the sentence because appositives are always structurally
  closer to the entity) — fixed, verified.
- "made" idiom bug (removing "made" from `ACCUSATION_VERBS` entirely to
  avoid "has made a career" false-triggering also reopened "made the
  virus" as a false negative) — fixed with a negative-lookahead, both
  directions verified.
- QAnon incorrectly flagged for removal from `maverick_authority` in the
  non-person-contamination pass — fixed, QAnon stays in, the scorer
  handles citation-vs-discussion per comment instead of a blanket
  exclude.

**Current validation numbers** (`src/validate_against_human_labels.py`
against `data/hitl/queue_maverick_authority.csv`, N=197):
- High confidence only: κ=-0.0144 (precision 0.38, recall 0.03)
- Medium or high: κ=-0.0025 (precision 0.44, recall 0.04)
- Low/medium/high: κ=0.0114 (precision 0.50, recall 0.07)

These are still low. Some of that is confirmed genuine construct
mismatch (the human queue labels broader "maverick figure invoked in a
credibility-relevant way," not strict grammatical citation — verified by
reading actual disagreement cases, most support this). But don't assume
the gap is now fully explained — every previous round of "this proves
it's a different construct" checking found at least one more real,
fixable pattern gap underneath it. Check a fresh sample of disagreements
the same way before concluding no further pattern work is worth it.

## What's NOT done

- No further recall improvement attempted beyond the verb-list expansion
  already done (`releas(ed/es/ing)`, `publish(ed/es/ing)`, `leak(ed/es/ing)`,
  `disclos(ed/es/ing)`, `provid(ed/es/ing)` added to `POST_NOMINAL_VERBS`).
- The scorer has NOT been wired into `has_maverick`/`has_consensus_expert`
  in `src/rerun_refined_regressions_v2.py`. This is deliberate — see the
  main handoff guardrails. **Do not do this step without Nash/Claude
  explicitly signing off on the validation numbers first.** Report the
  current κ/precision/recall and stop.

## If/when sign-off happens, the wiring itself

Replace the bare `regexp_matches(text, pattern)` boolean in
`rerun_refined_regressions_v2.py`'s `has_maverick`/`has_consensus_expert`
construction with a confidence-tier-based flag (e.g.
`confidence in ('high','medium')`), then rerun and compare against the
current numbers in the main handoff index — expect the coefficient to
change since this is a stricter, more precise measure of the same
underlying construct, not a bug if it does.
