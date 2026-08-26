# Session handoff: full-corpus inference, FP-detector v10 (failed), escalation cascade context-walk

Session spanned 2026-08-24 to 2026-08-26. Long session, several distinct
threads. This doc is the narrative summary; hard numbers are all also in
`data/experiment_log.jsonl` (grep by `name` field, see pointers below) and
infra facts in `data/infra_map.jsonl`.

## 1. FP-detector pipeline applied to real populations for the first time

The binconf<0.3 + blind-spot-ensemble (v8/v9/confidence GBT) flag,
previously only validated on small ground-truth sets, was run for real on:
- Train population (32,607 rows) — `src/apply_fp_pipeline_full_train.py`
- Round9 pool (22,459 rows) — `src/score_round9_binconf_v8_v9.py`

Flagged rows were sent to a frontier-judge blind check
(`src/score_fp_flagged_frontier_blind.py`), then a 220-row **genuine human**
spot-check queue was built and fully rated by Nash
(`data/hitl/queue_fp_pipeline_spotcheck80.csv`, grew 80→220 rows).

**Real result** (`fp_pipeline_spotcheck220_FINAL_confirms_and_sharpens_80row_finding`
in the experiment log): 18.8% flagged precision (95% CI 13.7–25.2%), 1.5%
dangerous-direction error rate (vs 19.8% baseline dangerous-direction
rate), 56.8% frontier-judge/human agreement, 84.2% self-consistency. This
is a real, meaningful drop from the frontier-judge-only precision claims
this lineage had previously trusted — directionally the flag is safe (it
rarely flips a correct label the wrong way) but far less precise than
earlier evidence suggested. Frontier judge on its own overstates its own
reliability against real human labels.

## 2. v10 (fine-tune on real human labels): looked real, wasn't

Question from Nash: can we fine-tune something on his real labels to
improve the flagged-population detector? Built `fp_detector_v10` on the
pooled 470 real human labels (274 original ground truth + 220 from the
spot-check above).

- Single 80/20 split: AUC 0.733 — looked like a genuine, meaningful win
  over v8 (0.6417) and the scalar-feature ensemble (0.694 best case).
- Proper 5-fold CV (`src/train_fp_detector_v10_5fold_cv.py`): fold AUCs
  **0.680 / 0.571 / 0.611 / 0.536 / 0.498** — honest mean **0.557**,
  essentially indistinguishable from chance-adjacent. The single split had
  gotten lucky.
- Also tried retraining the scalar-feature GBT ensemble on the same 470
  labels: made things worse (OOF AUC 0.694 → 0.568).

**Conclusion, logged as authoritative**
(`fp_detector_v10_5fold_CV_REVEALS_single_split_was_lucky_not_real`):
neither approach beats the existing pipeline at ~470 labeled rows. Do not
deploy v10. The honest state of the art for "refine an already-flagged
population" stays the original binconf+v8/v9 ensemble from section 1
(modestly useful per the 220-row check above). Would need materially more
labels (probably 1000+) before another modeling attempt is worth it.

## 3. Full-corpus inference: the documented-best pipeline over all 451,815 rows

The validated non-frontier 5-model ensemble + binconf blend
(`combined = 0.7*ensemble_p_hasstance + 0.3*binconf_confidence`,
threshold 0.55, documented kappa 0.5656) had never been run over the full
uncapped entity-mention corpus (`data/processed/round9/full_entity_mention_pool.parquet`,
451,815 rows, built earlier on 2026-08-18). This session ran it, for real,
across both GCP projects in parallel:

- `src/infer_fullcorpus_r7v1.py` (conspiracycomments-gce) — r7v1_baseline
- `src/infer_fullcorpus_gpuincrease4.py` (gpuincrease) — r7v2_split,
  r5v2_baseline, r5v2_split, r7v3_baseline, run sequentially on one VM
- `src/infer_fullcorpus_r7v3.py` — a redundant *duplicate* r7v3_baseline
  pass that should have been killed by a Monitor before it started (the
  monitor failed to fire; caught manually ~5.5hrs later, no data harm,
  wasted GPU time — logged as a lesson, see infra_map.jsonl)
- `src/score_binconf_fullcorpus.py` — binconf pass, split into half1/half2
  and run in parallel across both projects (explicitly fp32, see the
  in-code NOTE — Nash recalled a prior bf16/fp16 crash on some model in
  this project and the risk wasn't worth a ~2x speed gain)
- `src/score_fp_v8_fullcorpus.py` / `src/score_fp_v9_fullcorpus.py` — v8/v9
  scored on the 270,951-row stanced-predicted subset, run in parallel

Infra technique used repeatedly: direct VM-to-VM checkpoint transfer
(ed25519 keypair on source VM, public key added to destination's GCP
instance metadata, direct `scp` between external IPs) — bypasses the slow
relay through the local machine. Also hit repeated
`ZONE_RESOURCE_POOL_EXHAUSTED` errors, worked around via disk imaging +
zone sweeps.

**Final deliverable**: `outputs/reinfer_probs/fullcorpus_FINAL_complete.parquet`
(451,815 rows) — all 5 models' p_other, binconf confidence, the blend at
threshold 0.55, majority-vote polarity, final flags. Logged as
`fullcorpus_inference_COMPLETE_451815_entity_mentions`:
- 180,863 "other" (40.0%), 126,670 hostile + 144,281 endorsement (60.0% stanced)
- 59,146 flagged (21.8% of stanced): 311 binconf-low + 58,835 blind-spot-ensemble arm

**Real finding surfaced along the way**: the "baseline" vs "split"/"redesign"
model architecture arms systematically diverge in their p_other
distributions at this scale — worth checking before treating the 5 models
as interchangeable in any future ensemble work.

## 4. Escalation cascade — context-walk, cheap-phase only

Reused/adapted round9's chain-walk methodology
(`src/build_fullcorpus_chain_contexts.py`, from
`walk_round9_aleatoric_chains.py`) for the full-corpus uncertain/flagged
population: MARGIN_THR-style uncertainty triggers combining ensemble
argmax/softmax + binconf confidence, batched BFS chain-walk against
`local_context.duckdb` (rebuilt this session after the external drive
remounted at `/Volumes/Backup` instead of `/Volumes/NO NAME`), MAX_DEPTH=15.

Coverage went through three real fixes, each driven by Nash pushing back
on a premature "nothing more we can do" claim:

1. First pass: 63.4% coverage, 30,487 rows with zero context. My original
   analysis mislabeled these as `no_parent_id` — they actually all had
   valid `t3_`-prefixed parent_ids; the real problem was the sparse
   `data/raw/r_conspiracy_posts2.jsonl.gz` (0/26,421 posts found in it).
2. Nash: use the top-level post, selftext, title, and "submission
   statement" (SS:) comment as fallback context even without a full
   post-record match. Built `src/fill_fullcorpus_no_context_gaps.py`
   (SS-comment regex fallback) → coverage 63.4%→70.9%.
3. Nash insisted the real posts data existed somewhere else in the
   corpus and to keep looking rather than accept the gap — found
   `/Volumes/Backup/processed/r_conspiracy_posts_for_context.parquet`
   (1,831,271 rows, vs the 13.5MB sparse file previously used), covering
   99.96% of the remaining gap.
4. Nash: for rows that only reached a top-level parent comment
   (`max_depth_hit` / `parent_not_found` terminal reasons), append post +
   SS content to their existing partial context too, not just the
   zero-context rows. Final coverage: **99.99%** (84,324/84,335), logged
   as `fullcorpus_context_walk_FULL_COVERAGE_via_real_post_source` and
   `fullcorpus_context_walk_max_depth_and_broken_chain_augmented`.

**Not yet done**: the actual GPU re-scoring of the escalation population
WITH this now-complete context, to measure how much of the
uncertain/flagged population actually resolves. This was explicitly
deferred as a "decide after seeing cheap-phase results" item
(`fullcorpus_escalation_cascade_cheap_phase` in the log) and was still
pending when the session wrapped — natural next step for a future
session.

## 5. Aboutness pilot (not yet reviewed)

`src/build_aboutness_features.py` (pre-existing, untracked, unmodified)
was run on a 500-row sample of the escalation population as a pilot for a
possible additional cascade-resolution signal beyond context-walk/frontier
judge. A 30-row blind spot-check queue was built
(`data/hitl/queue_aboutness_pilot30.csv`) but is **unrated** — needs
Nash's review before any conclusion.

## 6. Four new HITL queues awaiting review (all unrated)

All currently live in the running `hitl_rater.py` server (port 8420 as of
last check — verify it's still up, it needs a restart to pick up any
queue built after it started):
- `data/hitl/queue_fullcorpus_spotcheck80.csv`
- `data/hitl/queue_fullcorpus_other_spotcheck60.csv`
- `data/hitl/queue_fullcorpus_stratified88.csv` (22 from each of 4
  categories, blind re-labeling, requested specifically to check whether
  the full-corpus "other" proportion is in keeping with prior smaller
  populations or is a scale artifact)
- `data/hitl/queue_aboutness_pilot30.csv` (see section 5)

## What a future session should do first

1. Rate the 4 queues above (or at least the stratified88 one, since it
   answers a live open question about whether full-corpus proportions are
   trustworthy).
2. Decide whether to run the GPU re-scoring pass on the
   now-99.99%-context-complete escalation population (section 4) — this
   is the natural next step, not yet started.
3. Do NOT restart v10 work (section 2) without materially more human
   labels than the current 470.

## Reconstructed files (repo hygiene note)

Two scripts (`src/infer_fullcorpus_r7v3.py`,
`src/score_fp_v9_fullcorpus.py`) were originally built via `sed` directly
into `/tmp` and pushed straight to a VM without ever being saved into
`src/` locally. Both VMs are now TERMINATED (disks intact, not deleted).
Rather than reprovision just to pull two files back, both were
reconstructed locally as straight siblings of their already-tracked
counterparts (`infer_fullcorpus_r7v1.py`, `score_fp_v8_fullcorpus.py`) —
same architecture, different checkpoint path/column name only. Marked as
such in each file's docstring.
