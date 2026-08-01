# Two-stage stance pipeline: verified numbers, two bugs fixed, and a stale-number warning for future sessions

**Status: two-stage combined pipeline result is now independently verified. If
you see kappa -0.057 or -0.11 for this pipeline anywhere, it is STALE
pre-fix output -- do not cite it, do not compare new work against it.**

## What was wrong (both bugs now fixed)

Two independent bugs in the diagnostic tooling (not in the training script,
`train_stance_classifier_twostage.py`, which was correct throughout) produced
a cascade of wrong conclusions across several sessions:

1. **Missing tokenizer on raw mid-training checkpoints.** The training script
   never passes `tokenizer=` to `Trainer`, so `save_strategy="epoch"`
   checkpoints (e.g. `checkpoints_stage1_has_stance/checkpoint-420`) have no
   tokenizer files -- only the final `trainer.save_model(out_dir)` +
   `tokenizer.save_pretrained(out_dir)` call writes a tokenizer, and only to
   the final `stance_stage1_model`/`stance_stage2_model` dirs. Loading
   `AutoTokenizer.from_pretrained()` on a raw checkpoint dir silently produced
   garbage encodings -- looked like a collapsed/broken model.
2. **Empirically-guessed class index instead of the deterministic one.** An
   earlier diagnostic script (`paired_bootstrap_stance_v2.py`) inferred which
   output index meant "other" via mean-probability heuristics on known rows.
   This is unnecessary and fragile: the index is fixed by the training
   script's own label construction --
   `stage_label = (train_df["label"] != "other").astype(int)` -- so index 0 is
   *always* "other", index 1 is *always* "has_stance", by construction of
   cross-entropy training (no permutation freedom). The heuristic broke
   exactly when the model underperformed on the minority "other" class,
   producing a backwards-looking confusion pattern that several sessions
   misdiagnosed as a training/label-corruption bug.

Both bugs are fixed in the replacement script, `stance_pipeline_eval.py`
(`run()` function -- no argparse, notebook-safe, call directly with explicit
paths). It always sources the tokenizer from the final model dir (even when
auditing a raw checkpoint) and uses the fixed index convention, never
empirical guessing.

## Verified numbers (from a real Kaggle run, both stage1 sources agreeing)

Confirmed 2026-07-30 by running `stance_pipeline_eval.py` end-to-end with the
tokenizer fix in place, auditing raw `checkpoint-420` against the final saved
model:

| Metric | Value |
|---|---|
| Baseline single-stage kappa | 0.3244 |
| Stage1 standalone kappa, raw checkpoint-420 | 0.2332 |
| Stage1 standalone kappa, final saved model | 0.2332 (identical to checkpoint -- strong evidence `load_best_model_at_end` worked correctly and the earlier -0.11 was a diagnostic-script artifact, not a save/load bug) |
| Stage2 standalone kappa (has-stance rows only, n=240) | 0.5322 |
| **Combined two-stage pipeline kappa** | **0.4052** |
| Paired bootstrap (two-stage vs baseline, 10,000 resamples) | mean delta-kappa=0.0806, 95% CI [0.0076, 0.1566], p=0.0153 -- CI excludes zero, statistically significant |

The 0.4052 combined-pipeline confusion matrix
(`[[74,21,19],[19,87,20],[20,14,23]]`) was also independently hand-verified
against the Cohen's kappa formula directly (not just trusted from script
output) and matches exactly.

**"Other" class is still the bottleneck** -- F1 0.39 (precision 0.37, recall
0.40) vs 0.65/0.70 for hostile/endorsement. This is the real number to move,
not the headline 3-way kappa.

## If you see a competing claim

An informally-run comparison in this same period reported combined pipeline
kappa of -0.057 and stage1 kappa of -0.11, and used those numbers as the
baseline to benchmark a new regression-head experiment against (reporting
"other" recall 0.37 -> 0.54 vs a single-stage 0.324 baseline, not the
two-stage 0.405). Those two negative numbers are the exact pre-fix bug
outputs described above -- check whether whatever produced that comparison
was using `stance_pipeline_eval.py` (post-fix) or the older
`paired_bootstrap_stance_v2.py` before trusting it. Any regression/ordinal
comparison work should be benchmarked against verified **0.4052**, not 0.324
or -0.057.

## Open threads / not yet run

- `mine_other_candidates.py` (mines likely-"other" candidates from the large
  unlabeled pool for human review) -- built, unit-tested locally, not yet
  successfully run on Kaggle. Last attempt failed because the
  `stance-classifier-two-stage` notebook wasn't attached as an input to that
  particular Kaggle session (inputs don't carry over between notebooks).
- `train_stance_classifier_twostage.py` now has two additional experimental
  arms beyond the verified two-stage binary: a CORAL ordinal model and a
  "regression-with-zero-anchor" continuous polarity model (uses
  `ordinal_targets.csv`, built from raw per-rater IRR votes, for genuine
  fractional calibration targets on the 99 triple-rated items). Neither arm
  has been run yet.
- Planned sequence (deliberately incremental, one change at a time, for
  clean attribution): (1) two-stage binary -- done, verified 0.4052; (2)
  regression-with-zero-anchor on current data only; (3) two-stage binary +
  mined/reviewed "other" data; (4) regression + new data combined. Do not
  run (2)+(3) combined before running them separately.
