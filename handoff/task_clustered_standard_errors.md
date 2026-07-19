# Task: Add clustered standard errors to the core regressions

**Status: not started. Mechanical — `statsmodels` supports this natively
(`fit(cov_type='cluster', cov_kwds={'groups': ...})`), no judgment calls,
no new data needed.**

## Why

None of the current regression scripts cluster standard errors by
thread or author. Comments from the same thread share that thread's
visibility/audience, and comments from the same author share that
author's writing style and posting pattern — both violate the
independence assumption plain logit/OLS standard errors rely on.
With N in the hundreds of thousands to millions, this plausibly makes
several reported p-values more confident than they should be. This
hasn't been checked anywhere in the pipeline yet.

## What to do

For each of the following scripts, refit the existing formula(s) with
clustered SEs and save the comparison **alongside**, not overwriting,
the existing output:

1. `src/rerun_refined_regressions_v2.py` — cluster by `SUBSTR(link_id, 4)`
   (post/thread id, already extracted as `t.post_id` in the query) for
   both the r/conspiracy and r/politics fits. Save to
   `data/processed/refined_regression_results_v2_clustered.csv`.
2. `src/run_integrated_regressions.py` — same, cluster by thread id
   (`t.post_id` equivalent) across the elasticity/insider grid. This is
   72 fits; if refitting all 72 with clustering is too slow, at minimum
   redo the "Unfiltered" / no-insider-threshold row for each of the
   three model types, and flag that the rest weren't reclustered.
3. `src/run_pure_50k_topic_analysis.py` — cluster by thread id across
   the era/super-topic strata.

Also try clustering by `author` instead of thread id as a second pass if
time allows (same author posting many times is a separate
non-independence source from same-thread comments) — report both, don't
pick one and discard the other silently.

## When done

Report, for each script, which coefficients' significance changed
(gained or lost significance under clustering) vs. the unclustered
version already on file. This is the actual point of the task — a
coefficient's significance surviving clustering is meaningfully
different evidence than one that only looked significant under the
naive (unclustered) SEs. Stop at reporting; don't reinterpret the
substantive story.
