# ATS stance classification (hostile/endorsement) to reddit-side parity (step 1-2 done, step 3 blocked on Nash, 2026-07-27)

**Status update (2026-07-27): steps 1 and 2 below are done, verified
against actual output.** `src/classify_ats_stance.py` applies the
already-established two-stage cascade model (`stance_classifier_2stage_pooled.joblib`
— confirmed already in use on the reddit side via
`rerun_regressions_with_stance_cascade.py`, not a new/experimental
model) to the disambiguated ATS mentions from
`task_ats_entity_disambiguation.md`. It correctly reuses
`stance_window_utils.py`'s quote-stripping and list-dump filters (the
same fix that mattered for the reddit-side endorsement blind spot)
rather than rebuilding that logic.

Output confirmed by direct query: `data/processed/ats_entity_examples_stance.parquet`,
30,998 rows — endorsement 50.8% (15,759), hostile 42.4% (13,129), other
6.8% (2,110), 4 list-dumps flagged. Entity-level breakdown looks
face-valid even before formal scoring: Assange 88.3% endorsement,
Snowden 86%, Greenspan 95.7% hostile — consistent with the established
reddit-side whistleblower-endorsed / consensus-target-attacked pattern.

**Step 2 (quality-check queue) is also done**: `src/build_entity_stance_quality_queues.py`
and `src/score_entity_stance_quality_checks.py` got `--platform ats`
support. `data/hitl/queue_ats_stance_quality_check.csv` is a genuinely
balanced 99-row blind queue (16-19 rows per era x label cell, spanning
Assange/Snowden/WikiLeaks/Alex Jones across an Early Era 1998-2011 /
Late Era 2012-2026 split) with predictions saved separately
(`data/processed/ats_stance_quality_check_predictions.csv`) to preserve
blind-rating discipline. `human_stance` is confirmed 100% blank.

**Step 3 is NOT done and is explicitly not delegatable** — see below.
The session correctly stopped here rather than pushing forward.

## Next step (Nash's, not delegatable)

1. Label the `human_stance` column in `data/hitl/queue_ats_stance_quality_check.csv`
   (99 rows: hostile / endorsement / neutral / ambiguous, append "list"
   for list-dump windows).
2. Run `python3 src/score_entity_stance_quality_checks.py --platform ats`
   — reports accuracy/kappa on the hostile/endorsement subset, PLUS a
   temporal-drift breakdown (early vs. late era) and per-entity
   breakdown, to check whether the reddit-trained classifier holds up
   across ATS's much wider era range.
3. If it finds the same kind of blind spot the reddit-side Jones check
   found (confident-endorsement calls unreliable), or a different
   ATS-specific one (e.g. era-specific drift), it needs the same kind of
   fix before any ATS stance number gets cited — quote-stripping/
   list-dump filtering already carried over, so the likeliest gap left
   is either an era-specific vocabulary shift or a genuinely
   ATS-specific classifier weakness.

---

Sibling task to `task_ats_entity_disambiguation.md` — depends on it
(stance classification needs the disambiguated entity mentions as input,
not the crude frequency count). Part of the bigger push described there;
same motivation (ATS as the answer to the "r/conspiracy is too moderated"
critique, not a side project).

## What exists on the reddit side to reuse

- `src/train_stance_classifier.py` — the trained hostile/endorsement/other
  classifier, 5 rounds of active-learning uncertainty sampling, kappa
  0.287->0.352 across rounds (see `ANTIGRAVITY_HANDOFF.md`'s 2026-07-21
  updates for the full history, including the round-2-through-5 detail and
  the endorsement-blind-spot fix from `task_stance_endorsement_blindspot.md`).
- `src/stance_window_utils.py` — entity-focused text windowing (+-15 words
  around the target entity), the same convention as the Stage B/C
  disambiguation windowing. Use this, not whole-comment-text, for whatever
  gets fed to the classifier on ATS text too.
- `src/train_twostage_classifier.py` — if the two-stage (bare-form ->
  refined) approach used on reddit is still the current best pattern by
  the time this is picked up, check current state before assuming.

## The real risk here, stated plainly

The classifier was trained on 2020s r/conspiracy text. ATS text spans
1998-2020s, a different community, different moderation norms, different
writing conventions across eras. There is no reason to assume it
transfers cleanly, and the project has already been burned by trusting a
classifier on a population it wasn't validated against — the Alex Jones
quality-check found 87.5% accuracy on confident-hostile predictions but
only 38.9% (worse than chance) on confident-endorsing ones, on reddit's
own text (see `task_stance_endorsement_blindspot.md`). Applying to a
different-era, different-forum corpus without the equivalent check is a
bigger version of the same mistake.

## What "parity with reddit" requires, in order

1. Apply the classifier to ATS entity-mention windows (once
   `task_ats_entity_disambiguation.md`'s output exists) — mechanical,
   fine to delegate.
2. **Before citing any ATS stance number**, build the same kind of
   hand-labeled quality-check queue the reddit side used (the 99-row
   Jones check, generalized in `task_multi_entity_quality_check_queues.md`
   for Wikileaks/Assange/Snowden/Greenwald) — but for ATS specifically,
   spanning multiple eras of the archive, not just one entity. This is
   the step that turns "we ran a classifier" into "we know whether the
   result means anything." **This step is Nash's judgment call, not
   delegatable** — same as every other stance-quality-check has been.
3. If the quality-check finds the same kind of blind spot found on
   reddit (or a different one specific to ATS's era range), fix it the
   same way that was fixed for reddit (quote-stripping, list/link-dump
   filtering, active-learning round targeting the specific blind spot)
   before trusting the numbers.

## Suitability for delegation

Step 1 (mechanical application) is a reasonable Antigravity task. Step 2
(building the quality-check queue itself — assembling candidate rows for
human review) is also mechanical and delegatable. **Actually rating the
quality-check queue and deciding whether the classifier is trustworthy on
ATS is Nash's own call** — this is the same "not yours to make
unsupervised" pattern as the entity-list guardrail, applied to stance
classification transfer validity instead.

## Output needed for the bigger cross-platform push

A stance-labeled version of the ATS entity mentions (predicted_label,
p_hostile, p_endorsement columns matching the reddit-side
`entity_examples.parquet` schema) — with the quality-check result
documented alongside it (what accuracy/kappa was found, on what sample,
covering what era range) so nobody downstream cites an unvalidated number.
