# Fine-tuning a real stance classifier — plan + how to continue on free resources

**Status as of 2026-07-28: three training variants run and evaluated.
Net result: no improvement over the production baseline (kappa 0.345).
See "Results" section below before running a fourth variant — the
evidence now points at task/label ambiguity, not model capacity, as the
real ceiling. An inter-rater-reliability (IRR) check is the recommended
next step, not another training config.**

## Why this exists

The production stance classifier (hostile/endorsement/other, TF-IDF +
LogisticRegression) has kappa 0.345 on held-out human labels
(`task_stance_endorsement_blindspot.md`), and this session's AIITL audits
found only 33-36% raw agreement with an independent judge on a
stratified sample — corroborated by a bigger model on the disagreement
subset (see `task_2026-07-28_session_wrapup.md` section 1 and
`task_2026-07-28b_kaggle_backlog_and_dedup.md` section 3). Nash asked
directly whether this is worth fixing and how — see that conversation
for the full reasoning; short version: not the biggest risk to the
thesis (the core regression table doesn't use stance at all), but a real
weakness in the secondary "stance-split" findings, worth fixing since
the actual lever is "train a proper classifier," not "run a bigger LLM
at bigger scale" (a TPU/multi-device approach was considered and
correctly ruled out — see below).

## Why not TPU / bigger LLM / multi-device

Worth preserving this reasoning since it's a common temptation to
reach for more compute when "improve accuracy" is the goal:
- Splitting a dataset across multiple accelerators increases *throughput*
  (process more rows faster with the model you've got) — it does not let
  you use a *bigger* model. Those are unrelated levers.
- What actually lets a bigger model fit on limited hardware is
  quantization, already proven this session (4-bit Qwen2.5-7B on a
  single T4, `kaggle_entity_stance_bigmodel_kernel/`).
- Kaggle TPUs only give real speedup with a JAX/Flax stack — a naive
  PyTorch/HuggingFace model on TPU often runs no faster, sometimes
  slower, due to compatibility overhead. Not worth the rewrite here.
- The actual fix for classifier *accuracy* is a real trained model on
  more/better data, not a bigger frozen model doing zero-shot inference
  forever at corpus scale (that's expensive to run permanently and was
  never the plan — see the cascade design in the first wrap-up doc,
  section 3, where this is "Tier 2," designed but not built until now).

## Data pipeline (built, verified)

`src/build_stance_classifier_training_data.py` consolidates:
- **1,992 human-labeled rows** from `data/hitl/*.csv` — every queue using
  the stance taxonomy (endorsement/hostile/neutral/ambiguous/wrong_match),
  which turned out to be far more than the 238-row figure in `README.md`
  (that number is just one queue, `queue_consensus_stance.csv`; there are
  ~19 other labeled stance queues covering consensus/maverick entities
  across both platforms and multiple refinement rounds). Deliberately
  excludes `personal_experience`/`procedural_skepticism`/
  `maverick_authority`/`hedged_suspicion` queues — different constructs,
  different label taxonomy (positive/lean_positive/negative/unsure), not
  stance data.
- **1,659 AI-silver rows** from this session's AIITL work: 876 entity-
  stance cases where the small (1.5B) judge agreed with the production
  classifier, and 794 disagreement cases where a 7B model corroborated
  the small judge overriding the classifier (the strongest silver signal
  available — two independent models agreeing against the classifier).
  Weighted at 0.5 vs. 1.0 for human labels in the training loss.
- `neutral`/`ambiguous` collapsed into `other` to match the production
  classifier's 3-way scheme. `wrong_match` rows dropped entirely (that
  label means the entity mention itself was spurious, not that the
  stance call was hard — a different failure mode).
- Stratified 85/15 train/val split, **val set is human-labels-only** —
  never validate a model against its own weak supervision.

Output: `data/processed/stance_classifier_training_data.parquet`
(3,651 rows: 1,992 human / 1,659 silver, 3,354 train / 297 val).

**Rerunning this script is safe and idempotent** if more human labels get
added to `data/hitl/` later (e.g. from continued rating) — just rerun it
and repush the training job with the refreshed parquet.

## Training job

`surge-compute/kaggle_stance_classifier_finetune/train_stance_classifier.py`
— fine-tunes `roberta-base` (125M params, general-purpose, no domain
pretraining needed for a first pass) with a custom weighted-loss Trainer
(human labels weight 1.0, AI-silver weight 0.5), 6 epochs, evaluates
Cohen's kappa on the human-only validation set every epoch, keeps the
best checkpoint by kappa. Runs comfortably on a single T4 — no TPU, no
quantization, no multi-device tricks needed, this is a small
classification head, not a multi-billion-param generative model.

Includes the `os.walk`-based `/kaggle/input` file-finding fix (another
session found the documented mount path unreliable for freshly-created
datasets even after `status=ready`, confirmed independently twice today
— worth keeping in any new kernel template going forward).

Pushed as `tobiasnashws/stance-classifier-finetune` (kernel-metadata.json
pins `machine_shape: NvidiaTeslaT4` to avoid the P100-compatibility
issue hit earlier today).

## How to continue if Kaggle/other credits run out

Everything here is free-tier already (Kaggle GPU quota, open-weight
models, no paid API calls anywhere in this pipeline) — "free resources"
concern is really about *Kaggle account GPU-hour quota* (30h/week per
account, 4-5 accounts available, see `surge-compute/providers.yaml`),
not money. If quota runs out on all accounts:
1. **Wait for weekly quota reset** — genuinely free, just slower.
2. **Google Colab free tier** — same T4-class GPU, same
   transformers/HuggingFace stack, would need only trivial changes to
   `train_stance_classifier.py` (swap the `/kaggle/input` file-finding
   for a Google Drive mount or direct upload).
3. **Run locally, CPU-only, if desperate** — `roberta-base` fine-tuning
   on ~3,650 rows is small enough to run on a modern laptop CPU in a
   few hours (slow, not GPU-fast, but genuinely possible; reduce
   `per_device_train_batch_size` and expect it to take much longer per
   epoch). Not recommended as a first choice, but a real fallback that
   needs zero new infrastructure.
4. GitHub Actions is registered and idle (see compute patchwork table in
   `task_2026-07-28_session_wrapup.md` section 6) but has no GPU — not
   useful for this specific job, only for CPU-bound scripts.

## Results (three variants, all run same day)

**v1 (roberta-base, 256-token truncation, human=1.0/silver=0.5 sample
weights, no class weighting)**: first push errored (`KeyError:
'sample_weight'` — `TrainingArguments.remove_unused_columns` defaults to
`True` and silently strips any batch key not in the model's forward()
signature, including the custom `sample_weight` needed by
`WeightedTrainer.compute_loss`; fixed by setting
`remove_unused_columns=False`). After that fix:
- **Kappa: 0.344** (production baseline: 0.345) — essentially identical.
- Per-class: hostile P/R/F1 0.63/0.56/0.59, endorsement 0.60/0.77/0.68,
  **other 0.47/0.28/0.35** — the model badly under-predicts `other`
  (recall 0.28), tending to force ambiguous cases into hostile/
  endorsement instead.

**v2 (same as v1, but max_length 256→512)**: human-labeled rows contain
the FULL original comment (avg 1,225 chars, up to 9,535), not a
truncated window — 256 tokens was cutting most of them off well before
the actual context ended. AI-silver rows use a genuinely short
`text_window` and couldn't be extended (no comment id survived the
AIITL pipeline that produced them, see below) — this fix only helped the
human-labeled ~55% of the training set.
- Result: **kappa 0.324** — no change worth calling significant given a
  297-row validation set (this training data quirk means the 256/512
  distinction turned out not to matter much in practice for these
  particular short human_stance-queue texts, which are shorter on
  average than the full_text column's overall mean suggested).

**v3 (v2 + inverse-frequency class weighting on top of the existing
human/silver sample weights, to specifically target the `other`
under-prediction)**:
- **Kappa: 0.324** (unchanged from v2, still below the 0.345 baseline).
- Per-class: hostile 0.59/0.58/0.58, endorsement 0.66/0.65/0.65,
  **other 0.35/0.37/0.36** — `other` recall improved (0.28→0.37) exactly
  as intended, but at the cost of precision on the majority classes,
  netting no overall improvement. Classic precision/recall tradeoff, not
  a bug.
- **Confidence margin (softmax top-prob minus second-prob) is a real,
  usable signal even though the classifier itself isn't better**:
  accuracy 60.6% when margin ≥0.5 (n=221) vs. 46.1% when margin <0.5
  (n=76). This is the same "confidence separates trustworthy from
  untrustworthy predictions" pattern found for the citation/entity-stance
  Tier 1 classifiers earlier this session — usable for cascade-style
  routing regardless of whether the base classifier improves further.

**Conclusion**: three structurally different attempts (baseline
architecture change, more context, class-balanced loss) all converged on
the same narrow 0.32-0.35 kappa band. That convergence is itself the
finding — it's much more consistent with a genuine ceiling from label/
task ambiguity (short, sometimes-contradictory human judgments on
inherently ambiguous stance calls) than with a fixable modeling gap.
**Recommended next step: establish an actual human-human inter-rater
reliability (IRR) number** on a small double-rated sample before
attempting a fourth training variant — if two independent human raters
only agree with each other at, say, kappa 0.4-0.5 on the same texts,
that tells us 0.32-0.35 is close to what's achievable given this data,
a different and more honest conclusion than "the classifier needs more
work." `data/hitl/queue_irr_stance_shared.csv` exists but has zero
ratings — would need a second rater (or the same rater at a different
time, for intra-rater reliability as a cheaper proxy) to actually rate it.

## Real infra bugs found and fixed while running these jobs (unrelated to
## the classifier itself, but worth knowing)

While debugging a live claude.ai connector session hitting `fs_search`/
`fs_list` failures during this same window, two real bugs in
`project-fs-agent` were found and fixed:

1. **Unbounded `search()` could hang the entire single-process server.**
   `fs_search` with a broad `path`/`glob` (e.g. `path="."`, matching the
   whole `~/Projects` allowed root) had no cap except "stop once you've
   found enough results" — a query matching nothing would read every
   file under the root with no early exit, observed in practice pinning
   CPU at ~90% for 2+ minutes and blocking *every other request*
   (confirmed: even a trivial `fs_list` timed out during this window, and
   a direct localhost connection bypassing the tunnel also timed out —
   this was the actual server being stuck, not a network/wake-latency
   issue, even though it looked identical to "the laptop is asleep" from
   the caller's side). Fixed: `MAX_SEARCH_FILES_SCANNED` (5,000) and
   `MAX_SEARCH_FILE_SIZE` (1MB) added to `projectfsagent/config.py`,
   enforced in `tools.py`'s `search()` — verified a previously-hanging
   query now returns in ~4s with a clear "stopped after scanning N
   files, narrow your query" result instead of hanging indefinitely.
2. **`wake_poller.py` doesn't detect its own child processes dying** and
   gets stuck believing it's still mid-cycle, ignoring new `/wake`
   requests until its internal idle timer independently elapses (which,
   if the process died early into what the poller thought was a fresh
   20-minute cycle, could be a long wait). Hit this directly after
   manually killing a stuck `projectfsagent.api` process while
   debugging (1) above — a subsequent manual `POST /wake` to wake_relay
   had no visible effect because the poller wasn't even checking.
   Worked around by restarting the `com.nash.wake-poller` launchd job
   itself (`launchctl unload` + `load`), which resets its state machine
   and immediately picked up demand correctly. **Not fixed at the code
   level** — `wake_poller.py` should ideally track its child PIDs and
   detect early death rather than trusting its own elapsed-time state.
   If this recurs, the launchd restart is a known, fast workaround, not
   a mystery to re-debug from scratch.
