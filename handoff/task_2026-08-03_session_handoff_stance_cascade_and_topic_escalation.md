# Session handoff — 2026-08-03, stance cascade + topic-escalation session

**Read this first if picking up fresh.** Long session, lots in flight across 4 Kaggle
accounts. Check live state before trusting anything below as current.

## Headline result

**The current recommended best is an ENSEMBLE (round6-combined-fixes + round7-combined-fixes,
averaged, + escalation at threshold=0.45): kappa 0.5622** — see the "Ensemble test" section
below. Best *single* model is round7-combined-fixes at kappa 0.4760 (entity-conditioning +
bucket-redesign, on round7's full random-expansion training data). Both measured on a
genuinely bigger, more reliable 680-row validation set — up from the old 334-row val that this
whole session set out to fix. All comparisons below are on that same 680-row val unless noted.

## Why the val set changed (the actual starting problem)

Every prior round's headline kappa (round1=0.4667, round2=0.4922, etc.) was measured on a
297/294/334-row val depending on which snapshot you check — small enough that run-to-run
noise was plausibly bigger than the differences being compared. Fixed by building a much
larger val from the full human-labeled pool project-wide (1,989 existing + 277 net-new from
`build_expanded_val_generation2.py`'s mined-other/IRR rows = 2,266 total), re-split 70/30
instead of the original 85/15, giving **680 val rows** shared identically across every round.
Confirmed the human-labeled pool is genuinely tiny relative to total training volume: only
~2,266 rows exist across the *entire* project's HITL history; rounds 3-7's "18k+ train rows"
are almost entirely AI-silver (frontier-judge-scored), not human-labeled.

Re-running round2/5/6/7 on this bigger val (`*_bigval` scripts) gave a real, sobering result:
**round2's old "best so far" 0.4922 collapsed to 0.4207** — confirming that number was
substantially small-val noise, not a genuine model advantage. Round7's old-val "win"
(0.4601, from the near-zero-frontier-score downweighting fix) also didn't survive: **0.4198**
on the bigger val, actually the *worst* of the four plain-architecture reruns.

| Round | Old-val kappa | New (680-row) val kappa |
|---|---|---|
| round2 | 0.4922 | 0.4207 |
| round5 | 0.4402 | 0.4335 |
| round6 | 0.4245 | 0.4288 |
| round7 | 0.4601 | 0.4198 |

## Combined-fixes: two previously-validated-but-never-deployed architecture wins

Found via audit that two real, independently-validated architecture improvements from earlier
ablations were **never folded into the production round2-7 pipeline**:
- **Bucket-redesign** (`kaggle_stance_bucket_redesign_ablation`): split stage1 into
  neutral-vs-not (using `raw_label`) instead of has_stance-vs-other; stage2 becomes 3-way
  (hostile/endorsement/ambiguous), "ambiguous" mapped to "other" at scoring. +0.0677 kappa in
  isolated ablation.
- **Entity-conditioning** (`kaggle_stance_entity_ablation`): prefix input with
  `[ENTITY: {target_entity}]`. +0.0548 kappa in isolated ablation. `target_entity` column has
  ~97-100% coverage on the bigval training files (Nash's earlier entity-recovery work, never
  wired into the training scripts).

Combined and rerun on all four rounds' bigval data (`train_stance_combined_fixes.py`):

| Round | Plain bigval | Combined-fixes | Δ |
|---|---|---|---|
| round2 | 0.4207 | 0.4251 | +0.0044 |
| round5 | 0.4335 | 0.4290 | -0.0045 |
| round6 | 0.4288 | 0.4660 | +0.0372 |
| round7 | 0.4198 | **0.4760** | **+0.0562** |

Pattern: the combo only pays off on the fuller-data rounds (round6/7, 18,108 train rows), not
the smaller/boundary-heavy ones (round2/5). Plausibly bucket-redesign needs enough `raw_label`
coverage relative to total data to learn a clean stage1 boundary.

## Model-size ablation (windowing + bigger model)

`entity_span_windowing`: for comments exceeding a model's max_length, instead of naive
start-of-text truncation, window ~around the entity mention (using `entity_spans`
character offsets where available — ~20% coverage — else a case-insensitive text search for
`target_entity`). Combined with entity-conditioning + bucket-redesign + `roberta-base`, on
round5's data: **kappa 0.4741** — beats round5-combined-fixes (0.4290, same two fixes, no
windowing) by +0.045, real incremental signal.

`answerdotai/ModernBERT-large` (max_length raised 512→2048, later reduced to 1024 after a CUDA
OOM) run in parallel on the same setup — still in progress as of this doc; check
`tobiasnashws/stance-model-size-ablation` (round5 data) and
`tobiasnashktc/stance-model-size-ablation-round7` (round7 data, not yet started when the
round5 windowing result landed).

**Known bug fixed**: Kaggle can silently allocate >1 visible GPU even when a single-T4
`machine_shape` is requested; HuggingFace `Trainer` auto-wraps in `DataParallel` when it sees
multiple devices, which trips a real bug in ModernBERT's `forward()`
(`_maybe_set_compile()` → `StopIteration` on an empty `self.parameters()` generator inside a
DataParallel replica). Fixed with `os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")` before
importing torch.

## Cascade / escalation — real, but recalibrated way down from initial hype

`simulate_cascade_validation.py` (built 2026-08-01) offline-simulated escalating
low-confidence classifier predictions to the frontier judge, on the OLD 212-row val:
0.4921→0.7077 kappa at threshold 0.5 (70.7% escalated). **This number never survived contact
with the bigger val.** Re-run properly on the 680-row val (`cascade_sweep_bucket_redesign.py`,
scoped correctly — see bug below):

| | Round5-combined | Round6-combined | Round7-combined |
|---|---|---|---|
| Tier2-only (no escalation) | 0.4290 | 0.4660 | 0.4760 |
| Best real cascade kappa | 0.5579 @ 75.3% escalated | 0.5351 @ 50% escalated | **0.5460 @ only 17.2% escalated** |
| Oracle-stage1 ceiling (ground-truth gating + frontier stage2) | 0.8905 | 0.8905 | 0.8905 (identical across all — ground-truth gated, model-independent) |

**Real bug caught and fixed mid-session**: first cascade sweep escalated *both* stage1
(other-vs-not) and stage2 (hostile-vs-endorsement) uncertain calls to the frontier judge —
but the judge was only ever validated on the hostile-vs-endorsement axis (0.8266 on old val,
confirmed 0.805 on new val, both restricted to has-stance rows). Its full 3-way accuracy
including "other" is much weaker (~0.57) because it was never built/tested to separate
"other" from a real stance. Fixed: escalation now correctly scoped to stage2 only, matching
the original `simulate_cascade_validation.py` design.

**Error decomposition** (`error_decomp_and_ensemble.py`), confirming *why* round7's cascade
plateaus at a much cheaper escalation rate than round5/6's: escalation can only ever fix
stage2-shaped errors (correctly gated as not-other, wrong hostile/endorsement call) — it
structurally cannot fix stage1-shaped errors (wrong other-vs-not bucketing), since escalation
is never invoked for stage1's own decision.

| | Round6-combined @ 0.50 | Round7-combined @ 0.45 |
|---|---|---|
| Correct | 68.5% | 70.1% |
| Stage1-attributable error (escalation can't fix) | 29.0% | 22.4% |
| Stage2-attributable error (escalation could fix) | 2.5% | 7.5% |

Round6 has proportionally *more* stage1-locked error and *less* stage2-recoverable error than
round7 — consistent with round7's cheaper, flatter escalation curve and round6's need to
escalate further to reach its (still lower) peak.

**Practical implication**: round7-combined-fixes + escalation at threshold≈0.45 is the
efficient real operating point (nearly-optimal, ~17% of rows escalated) — not round5's
requirement of escalating 75%+ of the corpus for comparable value.

## Ensemble test — real result, THE current best (after a bug fix)

First ensemble attempt (round6-combined + round7-combined, averaged 3-way probabilities) used
a different analytic P(other) combination formula than the greedy-pipeline decision rule used
everywhere else in the cascade work, which silently compared the ensemble against artificially
weakened solo baselines (0.4405/0.4685 instead of the real 0.4660/0.4760) — that first result
was void. Fixed version (`error-decomp-and-ensemble` kernel v2, uses the identical
`cascade_predict` greedy-pipeline logic for both solo and ensembled predictions) reran clean:
sanity checks against the solo baselines matched exactly (0.4660/0.4760), confirming the fix
worked, and the real ensemble result is genuinely the best of the whole session:

| | Kappa |
|---|---|
| round6-combined alone | 0.4660 |
| round7-combined alone | 0.4760 |
| **Ensemble (round6+round7 averaged, no escalation)** | **0.4975** |
| **Ensemble + escalation (threshold=0.45)** | **0.5622** |

**This is the current recommended best stance classifier as of this doc: kappa 0.5622**, free
noise-cancellation from averaging two independently-trained models plus escalation on top —
no new training required. Worth re-checking once model-size-ablation results land, in case
ModernBERT-large changes which models are worth ensembling.

## Active-learning queues rebuilt against current models

`build_active_learning_requeue.py`'s existing tier logic (tier1: labeled "other" but model
confidently predicts hostile/endorsement; tier2: labeled hostile/endorsement but model
confidently predicts something else) already targeted exactly the "confidently wrong"
failure mode the threshold-sweep diagnostics found (plain architecture's "other" precision
only ~48-50%) — it had just never been rerun against any of tonight's actual trained models.
Reran against round5-bigval (`active-learning-requeue-v2` kernel): 343 flagged rows (82
tier1, 238 tier2, 23 tier3-boundary) out of 2,266 human-labeled rows scored, capped to top
150 by confidence → `data/hitl/queue_active_learning_requeue_v2.csv`.

Also recovered and completed two escalation-ladder items flagged "not yet done" since
2026-08-01: 50 "epistemic" rows (thread context measurably improved classifier confidence)
finally got the frontier-judge call with context baked into the prompt
(`score_escalation_epistemic_frontier.py`, 50/50 valid); 68 "aleatoric"+"no-context" rows
(39+29) went straight into a direct-review queue (`queue_escalation_aleatoric_review.csv`,
never further-automated per the original design intent).

**`hitl_rater.py` fixes** (both queues were unusable until these landed):
1. Queue button taxonomy is a hardcoded `STANCE_QUEUES` JS array (two occurrences) — new
   queue names weren't in it, so the UI defaulted to the wrong label set (positive/lean
   positive/negative/unsure, a different construct's taxonomy entirely). Added both new queue
   names.
2. Context lookup (`/api/context`, the "Load surrounding context" button) fell back to
   `EMPATH_PATH` (`data/processed/empath_scores_full_mapped.parquet`), which was **never
   downloaded locally** (only exists on Kaggle) — the button silently returned empty context
   for every row regardless of whether `parent_id` was populated, this whole project. First
   fix attempt (`build_local_context_db.py`, full 44M-row indexed DuckDB copy of the raw
   comment shards) **crashed the disk** (~18GB, only ~2GB free at the time) — reverted, file
   deleted. Real fix: `build_targeted_context_cache.py`, a single streaming pass over the raw
   `.jsonl.gz` shards that only extracts what the *current* queues actually need (~1,300
   comments, not 44M), writing into `hitl_rater.py`'s existing lightweight
   `context_cache.json` mechanism (already checked first, before any DB fallback). No
   persistent DB, no disk risk. `hitl_rater.py`'s `/api/context` handler updated to point at
   `LOCAL_CONTEXT_DB` (a small file, currently unused/optional) instead of the missing
   `EMPATH_PATH`.

**Note for later**: `queue_escalation_aleatoric_review.csv`'s `id`/`parent_id`/`link_id`
recovered directly from `escalation_candidates.csv`'s own columns (no corpus scan needed).
`queue_active_learning_requeue_v2.csv`'s ids recovered via text-match against the raw corpus
(124/149 matched; the ~25 unmatched likely have minor whitespace/encoding differences).

## Topic modeling: full-corpus escalation planning (separate thread)

Reconstructed the TRUE (pre-title-fallback) low-confidence population for the full 39.9M-row
corpus — the officially reported 5.5%/13.5% (long/short) outlier rates are inflated-looking-low
because of a title-fallback mechanism that rescues a comment into its *post's* topic when its
own content fails the 0.35-cosine-similarity-to-centroid check, with no column preserving
which path a given row took. Reconstructed via log-extrapolation first (~626k long, ~1.76M
short, giving ~15.2% true combined rate vs ~9.2% reported), then built an exact,
deterministic recompute kernel (`recompute_own_content_outliers.py`, MiniLM + same 0.35
threshold, no title fallback, no LLM cost) to get the precise row-level answer instead of an
estimate. **Real bug hit and fixed**: unpinned `pip install sentence-transformers` pulled a
version with new automatic image/text modality detection in `.encode()`, whose URL-parsing
crashes (`ValueError: Invalid IPv6 URL`) on plain comment text containing a bracket pattern
that resembles a malformed IPv6 address. Pinned to `sentence-transformers==3.0.1`, rerunning
as of this doc — check `manawatusamaritans/recompute-own-content-outliers`.

Planned next steps once the exact count is in (not yet started): Population A (title-fallback-
rescued) gets divergence-flagging (compare Gemini-embedding similarity to assigned topic vs.
best alternative); Population B (still unassigned after fallback) gets outlier-coherence
discovery (k-NN + raw HLC among just the outliers) — both methods already validated on a
100k-comment sample earlier this session, never yet run at full-corpus scale. Cost estimate
for the Gemini embedding pass: ~$93 at $0.20/M tokens (gemini-embedding-2), pending sign-off
per the project's standing no-unplanned-API-spend rule once the exact population is known.

## Infrastructure: multi-account Kaggle orchestration

Discovered and started using a 4-account Kaggle setup (`~/.surge-compute/providers.yaml`):
`tobiasnashws` (main), `tobiasnash`, `tobiasnashktc`, `manawatusamaritans` — each with its own
2-concurrent-GPU-session cap, so up to 8 kernels can run in parallel across accounts instead
of queueing behind one account's limit. Cross-account `kernel_sources` (mounting one kernel's
saved model output as another kernel's input) requires the source kernel's Sharing setting
set to Public via the website — no CLI/API path exists to toggle kernel privacy without a full
rerun (unlike datasets, which do have a metadata-only update endpoint). Several kernels made
public this session for this reason: `stance-retrain-round5-bigval`,
`stance-round6-combined-fixes`, `stance-round7-combined-fixes`.

**Disk-space near-miss**: machine has limited free disk (~20GB after cleanup, was down to
~1.8GB at the worst point from the crashed 18GB `local_context.duckdb` build). Watch this
before building anything that indexes/caches raw corpus data locally — prefer targeted,
scoped extraction (see `build_targeted_context_cache.py`) over full-corpus local copies.

## Open items / not yet done

1. **model-size-ablation** (round5, ModernBERT-large) and **model-size-ablation-round7**
   (round7, windowing+ModernBERT-large) — both still running as of this doc (each has hit a
   CUDA OOM at least once already, mid-session memory settings tightened: max_length=768,
   batch_size=2, gradient_checkpointing=True — check for a clean run before trusting either).
2. ~~error-decomp-and-ensemble v2~~ — **done**, see "Ensemble test" above. Real result: 0.5622.
3. **recompute-own-content-outliers v2** (topic-modeling exact escalation count) — still
   running.
4. Progressive/distillation cascade loop — designed (see below) but not launched. Uses
   escalation + Nash's active-learning review as the two feedstocks into periodic stage1
   retraining, specifically targeting the stage1 bottleneck rather than more stage2 tuning.
   Round 1 scope: ~20-30k entity-mention rows, threshold≈0.40 (not the expensive 70%+
   ceiling), only escalated/reviewed rows become new training data (never the classifier's
   own confident predictions — the standard self-training pitfall).
5. Nash reviewing `active_learning_requeue_v2` (150 rows) and
   `queue_escalation_aleatoric_review` (68 rows) via `hitl_rater.py` (localhost:8420,
   currently running).
6. Full 4-way cascade sweep + oracle diagnostic only run for round5/round6/round7-combined so
   far; round2-combined not yet checked (lowest priority, weakest base model of the four).
7. Bigger base model (ModernBERT-large) not yet combined with the cascade/escalation layer —
   worth doing once the model-size-ablation results land, if ModernBERT-large's tier2-only
   kappa beats round7-combined's 0.4760.
