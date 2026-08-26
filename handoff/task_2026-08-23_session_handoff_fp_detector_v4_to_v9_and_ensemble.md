# Session handoff: FP-detector v4 → v9, the ensemble, and where this actually lands

**Status: a real, deployable recommendation exists at the end of this,
but it's modest, not a breakthrough.** Read this before touching any
`fp_detector_v*` file, the blind-spot ensemble, or citing any precision/
recall number from this whole lineage.

**Timeline correction, since this caused real confusion in-session**: the
v4-v7 diagnosis happened **2026-08-21**. Everything from §2 onward in
this doc happened **2026-08-23**, a separate session two days later. They
are not the same stretch of work — don't let anyone (including a future
AI session) conflate them.

## 1. Recap: where 2026-08-21 left off

v4 was broken (shortcut-learned to read its own tag fields). v5 fixed
that (text-only input). v5→v6→v7 ran an active-learning loop (verify the
model's own flags via frontier, retrain), reaching held-out-val AUC 0.759
by v7. Full detail:
`handoff/task_2026-08-21_session_handoff_fp_detector_active_learning_loop.md`.
**That held-out-val number turned out to be almost meaningless** — see
§2.

## 2. 2026-08-23: the random-sample reckoning

Built a genuinely random, blind, human-labeled validation set (199 rows,
then +89 more = 288 total, hand-labeled by Nash with no current label or
model output shown). Scored v7 against it:

**v7: AUC 0.4852 — statistically indistinguishable from chance.** All
three active-learning rounds' apparent improvement (0.71→0.73→0.76) was
measured on a training-adjacent, increasingly self-referential population
(confidence-filtered, then verifying the model's own prior-round flags).
None of it transferred to real, representative data.

**Real base rate, now measured directly, not extrapolated**: pooling two
independent random samples (199 + 89 = 288 rows), **~17.4%** of currently
stanced-labeled (hostile/endorsement) rows are genuinely mislabeled
"other." (Two individual sub-samples gave 20.6% and 10.1% respectively —
a borderline-significant difference, z≈2.17, p≈0.03, not fully resolved;
treat 17.4% as the best pooled estimate.)

**Frontier judge (Gemini 3.5 Flash), validated against this same real
population**: 78.7% (3-way) / 83.1% (binary other-vs-stanced) agreement
with Nash's blind labels, on a 90-row spot-check drawn from a 3,000-row
random frontier-labeled batch. Frontier is directionally conservative
(over-calls "other" 13x more often than it under-calls it).

## 3. v8: fixing the root cause

Diagnosis: v4-v7's entire training composition (all generations) was
built from confidence-filtered or self-referential (prior-model-flagged)
populations — never a representative sample. v8
(`src/train_fp_detector_v8_representative.py`) trained on ONE generation
of genuinely random, frontier-labeled data (2,910 rows) instead.

**Real result, evaluated against the 288-row human ground truth (never
trained on): AUC 0.6417, precision 0.276, recall 0.480.** A real,
above-chance detector, first one in this lineage that generalizes at all.
Confirms the diagnosis was right — genuinely representative training data
fixed the generalization failure in a single generation, no active-
learning loop needed.

**Three polish attempts (continuing fine-tune on the 199-row human set at
low LR) all failed** — logged in detail as
`fp_detector_v8_polish_stage_FAILED_three_attempts` in
`data/experiment_log.jsonl`. Same AUC (0.6264) recurred across three
different hyperparameter configs, strongly suggesting the low-LR nudge
was only recalibrating the final layer's scale, not genuinely improving
the representation. Abandoned; don't retry without meaningfully more
human-labeled positives or a fundamentally different approach.

## 4. The uncomfortable finding: binconf alone beats v8

Nash pushed back hard here, correctly: is any of this actually earning
its keep, or did we just rebuild stage1 with less data and noisier
labels? Checked directly:

| | AUC | precision | recall |
|---|---|---|---|
| **binconf confidence alone (threshold 0.5)** | **0.7188** | **0.357** | 0.100 |
| v8 alone | 0.6417 | 0.276 | 0.480 |
| union (either flags) | — | 0.275 | 0.500 |

Binconf's own confidence — already fully computed, zero additional
training, zero cost — beats v8 on AUC and precision. Union of both barely
helps (v8's flags nearly subsume binconf's). **Threshold-tuned, binconf
alone reaches 44.4% precision at binconf<0.3** (3.1% of population
flagged) — better than anything else built this session, using only what
already existed.

## 5. The real structural insight: binconf's blind spot

Binconf's confidence rule can **never** flag a row where confidence≥0.5 —
that's 95% of the currently-stanced population, by construction, at any
threshold. So "binconf alone" isn't a complete answer even though it wins
on aggregate metrics — it has zero recall on the vast majority of the
population, structurally, forever.

Nash correctly identified (verified by re-reading
`train_fp_detector_v4_finetuned.py`'s `d1_neg` construction directly) that
v5-v7's *original* Gen1/Gen2 training data was genuinely scoped to a
different, coherent task than v8: "is binconf's own prediction wrong,"
not "is the random population's label wrong." That framing was real, just
diluted by v6/v7's later Gen3/Gen4 additions and abandoned entirely by v8.

**v9** (`src/train_fp_detector_v9_blindspot.py`) tested this directly:
trained only on binconf's actual blind spot (confidence≥0.5 subset of the
frontier-labeled 3k batch, 2,745 rows, 657 positives). Evaluated against
the confidence≥0.5 subset of the real 288-row set (274 rows):

**v9: AUC 0.5855 — did NOT beat v8 (0.6280) on the same restricted
population.** The properly-scoped-training hypothesis, tested directly,
did not produce a better model. Best guess: restricting to only
confidently-predicted negatives produced a more homogeneous, easier
negative class that taught less robust signal than v8's broader exposure.
**The conceptual diagnosis was right; the fix attempt didn't pan out.**

## 6. What did work: a small ensemble, specifically for the blind spot

Combined v8's score + v9's score + binconf's raw (continuous) confidence
value as three features into a small Gradient Boosting classifier,
cross-validated on the 274-row blind-spot ground truth:

**Ensemble (GBT, v8+v9+confidence): 5-fold CV AUC 0.6944-0.708 depending
on seed (mean 0.708, std 0.014 across 8 different random splits — a real,
robust improvement, not a lucky fold).** Beats v8 alone (0.628) and v9
alone (0.586) on the identical population. Precision advantage is
concentrated at the "fewer, higher-confidence flags" end — around 30
flags gets ~40% precision, vs. ~33-38% for v8 alone at a comparable count.
Adding the aboutness features (see §7) did not help once these three were
already included (0.682 vs 0.699 AUC — slightly worse, dropped from the
final version).

**Saved, trained on all 273 available rows**:
`outputs/checkpoints/fp_detector_blindspot_ensemble_v1.joblib`. Apply via
`src/score_fp_blindspot_ensemble.py` — needs `fp_v8_score`, `fp_v9_score`,
and `confidence` already computed per row (feature order: `fp_v8_score`,
`fp_v9_score`, `confidence`).

**Same GBT-probability-calibration issue as the polish attempts**: the
default 0.5 threshold badly under-flags (10/274 rows, recall 0.067,
because GBT's probability outputs are compressed toward low values on
this small, imbalanced dataset). **Use a lower threshold or rank-based
selection, not 0.5** — e.g. threshold 0.3 gives 27 flagged / 40.7%
precision / 24.4% recall; threshold 0.15 gives 102 flagged / 25.5%
precision / 57.8% recall, depending on how much coverage vs. precision is
wanted.

## 7. Aboutness feature: rebuilt, tested, did not reproduce the original finding

Rebuilt from documented method (2026-08-20's original script lives only
in an inaccessible session scratchpad, not recoverable) —
`src/build_aboutness_features.py`. Tested on the 288-row real ground
truth: **showed the OPPOSITE direction from the original 2026-08-20
finding** (entity-in-max-eval-sentence higher for genuinely-other rows,
not lower). Found and fixed one real bug along the way (spaCy's default
sentencizer fails to split on paragraph breaks without terminal
punctuation, common in Reddit text — confirmed directly on a concrete
example) — but the reversal persisted after the fix, and persisted when
conditioned specifically on binconf's blind spot too. **Conclusion: this
specific reimplementation, on this population, is not a usable signal on
its own.** Most likely explanation: the original signal was validated on
a narrower population (specifically "confidently wrong" adversarial
cases) that isn't representative of the broader "genuinely other" mix in
a random sample. Not proven useless in the narrower original context,
just not reproduced here. Feature columns are still computed and saved
(`outputs/reinfer_probs/real_validation_288_with_aboutness.csv`) if
someone wants to dig further.

## 8. The recommended final pipeline

**Two-part, each tool gated to the population segment it's actually good
at — not a naive full-population ensemble (which showed no aggregate
improvement in earlier checks):**

1. **binconf confidence < 0.3** → flag directly. 44.4% precision, covers
   ~3% of the population (the part binconf itself already suspects).
2. **binconf confidence ≥ 0.5** (the remaining ~95%, binconf's structural
   blind spot) → score with the blind-spot ensemble
   (`fp_detector_blindspot_ensemble_v1.joblib`), threshold tuned to
   taste (0.3 for higher precision/lower recall, 0.15 for more coverage).

**Neither v8 nor v9 alone is the final answer — the ensemble is.**

## 9. Honest overall assessment

This was NOT a strong result. Real, above-chance signal exists (ensemble
AUC ~0.70 in its target population), but precision tops out around 40%
even at the sharpest, lowest-coverage operating point. Every attempt to
meaningfully improve on the free baseline (binconf alone) required real
engineering effort for a modest gain. Document this honestly if it feeds
into the thesis write-up — don't overstate what a ~40%-precision screening
tool can be trusted to do unsupervised.

## 10. What's NOT done — concrete next steps, in priority order

1. **Never applied to the actual populations.** Everything in this doc is
   validated on the 288/274-row ground-truth sets. Nothing has been run
   across the full 32,607-row stanced train population or the 22,459-row
   round9 pool yet. Needs: binconf confidence (already have for train;
   round9 needs a fresh binconf pass — `round9_unlabeled_pool.parquet`
   exists at `/home/nash/round9_unlabeled_pool.parquet` on
   `vm2image-fpv5-temp`, 22,459 rows with real Reddit `id`/`parent_id`/
   `link_id` columns), v8 score, v9 score, then the ensemble script.
2. **The actual correction loop is still never closed.** Nothing in this
   whole lineage (2026-08-21 or 2026-08-23) has corrected a training
   label, retrained the real stage1 gate (`binconf_other015` or a
   successor), or re-measured stage1 kappa against the documented best
   (0.428, the ensemble+binconf blend — confirmed this is the right
   number, the earlier "-0.248" figure Nash cited was a typo). This is
   the single biggest remaining gap if the goal is actually moving that
   number.
3. **Reddit IDs are recoverable for at least the human-labeled portion of
   train** (confirmed directly, contradicts an earlier session's claim
   that they don't exist) — not yet checked whether this extends to the
   machine/silver-labeled majority (different loader functions in
   `src/build_stance_classifier_training_data.py`, not inspected this
   session). Relevant if context-walk is ever revisited.
4. **Aboutness/paraphrase-stability/labeling-metadata features** — only
   aboutness was tried, and it didn't reproduce. Paraphrase-stability and
   rater-agreement metadata were named as candidates but never built or
   tested this session.

## 11. Infra state

All VMs across both projects (`gpuincrease`, `conspiracycomments-gce`)
confirmed `TERMINATED` at session end. `vm2image-fpv5-snapshot` image
still exists in `gpuincrease` (storage cost only) — the fast-path if
`vm2image-20260810-093317`'s home zone (`asia-southeast1-b`) is still
GPU-capacity-exhausted next time; `vm2image-fpv5-temp` (`us-east1-c`) is
the known-working temp instance, currently stopped, safe to just restart
directly rather than re-image.

New scripts this session, all uncommitted:
`src/train_fp_detector_v8_representative.py`,
`src/score_fp_v8_on_full_train_stanced.py`,
`src/finetune_fp_detector_v8_polish_on_human.py` (abandoned, kept for
reference),
`src/score_fp_v8_polished_on_spotcheck.py`,
`src/train_fp_detector_v9_blindspot.py`,
`src/score_fp_v9_on_blindspot_validation.py`,
`src/build_aboutness_features.py`,
`src/score_fp_blindspot_ensemble.py`.
