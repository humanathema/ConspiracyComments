# Session handoff: kappa-comparison gotchas — read this before citing ANY kappa number in this project

**Why this file exists**: across one evening (2026-08-20, this session), three separate
confident-sounding kappa comparisons were made and had to be walked back, each for a
different, real reason. Not sloppiness in the arithmetic — each number reproduced
correctly from its source. The failures were methodological: comparing numbers that
looked like the same metric but weren't, trusting a citation without checking whether
something newer superseded it, and not checking whether a "held-out" set was actually
held out. This file exists so the next session (or this one, later) doesn't have to
rediscover these the expensive way.

## The checklist — run this before citing or comparing any kappa number

1. **Is it the same metric?** "Kappa" in this project can mean: polarity-only
   (hostile vs endorsement, on already-stanced rows), stage1-proxy (has-stance vs
   other gate only), or overall/combined 3-way (stage1 gate + stage2 polarity
   chained, on the full population including "other"). These numbers live in
   completely different ranges (polarity kappa 0.7+, overall 3-way kappa 0.4-0.6) and
   are NOT interchangeable. Check which one a cited number actually is before
   comparing it to another number.
2. **Is it the same population?** val680 (680-row val set) and the 425-row
   "aleatoric" set are different populations with different label distributions.
   A kappa computed on one is not directly comparable to a kappa computed on the
   other, even if the metric type matches.
3. **Is the citation current, or superseded?** "Best single model: r7v2_baseline,
   kappa 0.4840" (ANTIGRAVITY_HANDOFF.md, 2026-08-04 section) predates later work
   (r7v3_retrain, 2026-08-10/11) that produced higher-scoring individual models.
   Search broadly across handoff docs by date before trusting a "best X" superlative
   — a later doc likely supersedes it, but only if you find it.
4. **Does a high number generalize, or is it overfit?** r7v3_retrain_redesign's
   val kappa (0.5374) looked like the best individual model found this session —
   until checked against a genuinely separate held-out set, where it collapsed to
   0.2116 (handoff/round8_state_v4.md section 4, real overfitting, not a fluke).
   A single val-set number is not evidence of generalization by itself.
5. **Is the "held-out" set actually held out?** Checked directly this session:
   the 425-row "aleatoric" set (data/hitl/queue_escalation_round8_aleatoric.csv)
   is 100% present in binconf_other015's training data (exact text match against
   stance_classifier_training_data_round10_truncation_fixed.parquet). binconf's
   0.91-0.97 "kappa" on this set is memorization, not generalization — the set's
   file date (2026-08-10) predates when binconf was trained (2026-08-17) on a
   training corpus that had since absorbed it. A set that was genuinely held-out
   for one model at one point in time is not automatically still held-out for a
   model trained later, if the corpus grew to include it in between. Check
   text-overlap directly (cheap, exact-match against the training parquet) before
   trusting any "held-out"/"aleatoric"/"generalization" claim.

## What happened tonight, concretely (for context, not required reading if the checklist above is enough)

1. **Claimed binconf_other015 (val680 overall kappa 0.5219) beats the best individual
   ensemble model, citing only "r7v2_baseline, kappa 0.4840."** Wrong — that citation
   was stale. A broader search found r7v3_retrain's redesign arm at 0.5374 (higher
   than binconf), on the same metric, same population. Corrected in-session.
2. **That 0.5374 number itself turned out to be an overfitting artifact** — checked
   against `round8_state_v4.md` section 4 (already documented, just not read closely
   enough the first time): aleat kappa 0.2116, a 0.32-point collapse. r7v3_retrain's
   *baseline* arm (0.5283 val / 0.5594 aleat) is the one that actually generalizes.
   Nash's memory that "split/redesign was deprecated" was correct; my first
   correction was itself incomplete.
3. **Tried to settle it by scoring binconf_other015 against that same aleat set** —
   got an implausible 0.91-0.97, checked for leakage rather than reporting it, found
   100% train/test contamination. The comparison is currently unrecoverable without
   building a fresh, verified-clean held-out set — not attempted this session, not
   worth it for a fine-tuning decision under a 1-week deadline.

**UPDATE, later same session — resolved.** Nash's newest val-expansion batch
(`queue_expanded_entity_val_r1.csv`, 410 rows, fully human-labeled, never used for
training) gave a real path to a clean comparison. Checked (text, target_entity)
overlap against the round10 training parquet directly: only 12/374 usable rows
overlapped — excluded them, leaving a verified-clean 362-row set
(`data/hitl/queue_expanded_entity_val_r1_CLEAN_for_comparison.csv`).

Scored both models against it (`src/score_binconf_on_aleatoric.py`,
`src/score_r7v3retrain_on_clean_r1.py`):
- **binconf_other015: overall 3-way kappa 0.5303**, polarity kappa 0.6865.
- **r7v3_retrain_baseline: overall 3-way kappa 0.4940**, polarity kappa 0.6865.

**binconf_other015 wins** on this genuinely clean population. (One more bug hit and
fixed en route: r7v3's stage1 checkpoint reports generic `LABEL_0`/`LABEL_1`, no
informative id2label — first attempt guessed the wrong index and got a nonsensical
-0.0078 kappa; fixed using the convention already established in
`infer_round9_twostage.py`, index 0 = other / index 1 = has-stance. Four real
methodological traps in one evening, not three — the checklist above should have
also said "if a model's id2label is uninformative, verify the class-index convention
against a script that already scores this checkpoint family successfully, don't
guess from label strings.")

**Net position going into the fine-tune**: binconf_other015 is now supported as the
fine-tuning target on BOTH the architectural grounds (confidence head, cascade-design
compatibility, already-wired code) AND a properly verified kappa comparison — not
just the architectural case alone, as the first version of this note said.

## Process note, not just a factual one

All three of these were catchable in one grep/query each — the information needed
to avoid the mistake already existed in the repo (a later handoff section, a
column-overlap check, a metric-type note in a docstring). The failure mode wasn't
missing data, it was not checking before asserting. The concrete habit this should
turn into: before stating a comparative number as fact, spend one cheap check (grep
across dated handoff docs for a superseding number; verify metric type matches;
verify population matches; for anything called "held-out," verify it actually is)
rather than asserting from the first citation found. This costs one tool call, not
a rebuilt pipeline — cheap enough to always do, expensive to skip.
