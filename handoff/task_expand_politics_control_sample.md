# Task: Expand the r/politics control sample

**Status: not started. Mechanical — one constant change plus a rerun of
an existing, already-working pipeline. No judgment calls. Long-running
(est. ~3 hours) but unattended/resumable — good overnight job.**

## Why

The r/politics control (`data/processed/comparison_politics_staged_scored.parquet`,
N=30,881) only has 41 positive `has_consensus_expert` cases (0.133% base
rate) — that coefficient's `-0.158, se=0.397` "null" result is a wide,
noisy estimate, not strong evidence of a true zero. Every other
coefficient in the r/politics side of `refined_regression_results_v2.csv`
is fine at the current N; this is specifically about that one sparse
predictor.

Checked 2026-07-20: every one of the 20 existing per-month crawls
(`data/raw/r_politics_by_month/*.jsonl`), including the earliest
(2008-07), landed right at the ~1,500-1,570 target with no sign of
running out of available comments — r/politics has plenty of headroom
in every month already sampled. Raising the per-month target is safe
across the whole date range, not just the recent high-volume months.

## What to do

1. In `src/build_politics_control_sample.py`, raise `TARGET_PER_MONTH`
   from `1500` to `7000` (this targets ~140,000 total comments across
   the same 20 months, aiming for ~180-190 positive `has_consensus_expert`
   cases at the current 0.133% base rate — recompute this expectation
   once the crawl is done rather than assuming the base rate holds
   exactly). **Do not change `MONTHS`** — same 20 evenly-spaced months,
   same temporal-stratification design, only pulling deeper per month.
2. Run it: `python3.12 src/build_politics_control_sample.py`. It's
   checkpointed per month (skips any month whose file already exists
   non-empty) — the existing 20 files at the 1500-target size need to be
   moved aside first, or the script will skip them and you'll get the
   old smaller files back, not the expanded ones. This is a deliberate,
   pre-approved resample (this task file exists specifically because of
   that approval, 2026-07-20), so guardrail 2's "never edit/delete
   `data/raw/`" does not block it — but move, don't delete: `mkdir -p
   data/raw/r_politics_by_month_1500target_bak && mv
   data/raw/r_politics_by_month/*.jsonl
   data/raw/r_politics_by_month_1500target_bak/` before rerunning, so
   the original smaller sample is still there if the expansion needs to
   be compared against or rolled back.
3. Once the new files are in place, rerun `python3.12 src/score_comparisons.py`
   (regenerates `data/processed/comparison_politics_scored.parquet`)
   then `python3.12 src/rerun_refined_regressions_v2.py` (regenerates
   `refined_regression_results_v2.csv` and the keyness results) — this
   will overwrite the current r/politics-side numbers with the expanded
   ones. Save the old file first
   (`cp data/processed/refined_regression_results_v2.csv data/processed/refined_regression_results_v2_pre_expansion.csv`)
   so the before/after is comparable, don't just let it get overwritten
   silently.
4. Estimated time: the existing 20-month, ~31K-comment crawl took ~34
   minutes wall-clock (file timestamps). A ~4.5x volume increase
   (30,881 -> ~140,000) should scale roughly linearly with the
   API rate-limit delay, i.e. **~2.5-3 hours** — plan for the high end,
   some of that scaling may not be perfectly linear (fixed per-month
   connection overhead vs. per-page delay).

## Sequencing — do this before `task_core_comparison_robustness.md`

That task references the current N=30,881 and the current
2,387-author overlap count directly. Running the expansion first means
the robustness checks (interaction test, overlap-excluded rerun) run
once on final numbers instead of needing to be redone after this lands.
If `task_core_comparison_robustness.md` is already done by the time
this is picked up, rerun both its sub-tasks against the expanded sample
afterward rather than treating them as permanently finished.

## When done

Report the new r/politics N, the new `has_consensus_expert` positive
count and base rate, and the new coefficient/SE/p-value for it next to
the old one. Stop there — don't reinterpret the substantive story,
that's a separate step.
