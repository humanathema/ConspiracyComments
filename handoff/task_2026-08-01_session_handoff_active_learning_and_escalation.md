# Session handoff — 2026-08-01 late session, active learning + escalation ladder

**Read this first if picking up fresh.** Long session, lots in flight. Check live state before trusting anything below as current (Kaggle kernels/quota especially — this is a snapshot).

## What's actually running right now
- **Local**: `src/hitl_rater.py` (nohup'd, port 8420) and `src/retry_failed_frontier_scores.py` (nohup'd, retrying the 760 rows that failed in the first continuous-scoring pass, mostly from a broken 45-min auth-refresh cycle across several session interruptions, not real rate-limiting). Check `ps aux | grep -E "hitl_rater|retry_failed_frontier"` — both die on a full reboot (survive an app close via nohup, not a restart).
- Kaggle AI-proxy quota (`tobiasnash` account, `kaggle_benchmarks` library) was down to ~$0.62 as of last check — the retry job will stall again once that's exhausted, same as it did before. Checkpointed every 15 rows, safe to resume anytime with `python src/retry_failed_frontier_scores.py`.

## Headline result tonight
Retrained the two-stage stance cascade on the corrected training data (98 label changes out of 120 rows Nash reviewed via the active-learning loop) → **kappa 0.4667**, beating the previously-verified baseline (0.4052) and every one of 7 architecture ablation arms tried tonight (best was 0.3704). Confirms: data-quality fixes via active learning outperformed architecture experimentation. Model output: kernel `tobiasnashws/stance-retrain-corrected-round1`.

For context, human-human IRR ceiling on this task is Fleiss kappa 0.48 (three real raters, 99-row triple-rated sample) — 0.4667 is now close to that ceiling, not far below it.

## Escalation ladder (aleatoric vs epistemic uncertainty), built and validated
Nash's idea: for boundary-confidence classifier predictions, test whether real thread context (parent/sibling comments) actually resolves them before deciding whether to dig further (mirrors what he does manually — Google it, ask an AI, read the thread). First run (`tobiasnashws/stance-escalation-context-check`, clean, no errors):
- 118 genuinely boundary-confidence rows (not just "disagrees with label" — the classifier itself was ~50/50)
- 89 had real thread context available; of those: **44 epistemic** (context measurably helped — escalate further) vs **45 aleatoric** (context didn't help — route straight to human review, don't waste more compute)
- 29 had no thread context at all (isolated comments)

**Not yet done**: run the frontier judge on those 44 epistemic rows (context baked into the prompt) — the actual "ask an AI" final rung. Output sitting at `/kaggle/working/escalation_candidates.csv` on that kernel, needs pulling down and filtering to `verdict == "epistemic_context_helped"`.

## Explicitly proposed next steps, not yet built
1. **Student-model distillation**: `train_stance_ordinal_v2_ablation.py` (built earlier, untested) trains a regression head on the frontier judge's continuous scores instead of forced ±1 targets. Have 1,592+ valid frontier scores now (growing via the retry job) — enough to launch without waiting for all 2,047. Needs: merge `stance_frontier_continuous_targets.parquet` into a fresh training-data dataset version (`build_frontier_targets_dataset.py` already written for this), push, launch the kernel.
2. **Move remaining/future frontier-judge-style scoring off the $10/day AI quota entirely**: reuse the existing Qwen2.5-7B-Instruct-on-Kaggle-GPU pattern (`kaggle_entity_stance_bigmodel_kernel`) instead of `kaggle_benchmarks` — draws from GPU-hour quota (27h+/30h available) instead of the AI-proxy quota, avoids the repeated stalling.
3. **44 epistemic-flagged rows** from the escalation ladder still need the actual frontier-judge call (see above).
4. **45 aleatoric + 29 no-context rows** from the escalation ladder should go into the next `hitl_rater.py` active-learning queue batch for Nash's direct review — not further automated escalation.
5. Active-learning loop itself is still ongoing — more HITL rating rounds → merge → retrain (Kaggle, `kaggle_stance_retrain_corrected/`, not local — local MPS on 8GB RAM proved impractical, OOM'd even after batch-size fixes).

## Known gaps / things to watch
- `stance_classifier_training_data.parquet`'s `label` column briefly got corrupted with 5-way rating values (neutral/ambiguous/wrong_match) from a merge-script bug — fixed (collapsed to 3-way, wrong_match dropped), but if `merge_active_learning_corrections.py` runs again, double check the label taxonomy stays 3-way in `label` (raw 5-way should only ever live in `raw_label`).
- `data/hitl/queue_active_learning_requeue.csv`'s `id` column was swapped from synthetic (`al_XXXX`) to real original comment ids (needed for the context-cache and cross-referencing) — safe, done, but don't regenerate that queue file without preserving that fix.
- Kaggle CLI needs the full path (`/Users/nash/miniforge3/bin/kaggle`) in scripts and sometimes in the interactive shell too — `kaggle` alone isn't reliably on PATH after a reboot.
