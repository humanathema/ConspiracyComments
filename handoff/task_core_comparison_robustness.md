# Task: Harden the r/conspiracy vs r/politics comparison

**Status: not started. Two independent, mechanical sub-tasks — no
judgment calls, both are straightforward reruns/extensions of existing
scripts. Do both, report both, don't skip to interpretation.**

**Do `task_expand_politics_control_sample.md` first if it hasn't run
yet** — this task's numbers (N=30,881, the 2,387-author overlap count)
are the pre-expansion figures. If the expansion has already landed by
the time this is picked up, recompute the overlap count and N against
the expanded sample rather than using the numbers below.

## Why

The headline finding (`has_consensus_expert` rewarded in r/conspiracy,
null in r/politics — see `README.md` / `ANTIGRAVITY_HANDOFF.md`) is
currently supported by two *separately fit* logit models compared by
eye, not a formal test that the coefficient genuinely differs between
communities. Separately, a 2026-07-20 check found that **16.14% of the
r/politics control sample's comments (2,387 distinct authors) are
written by people who are also established r/conspiracy commenters**
(>=5 comments there, per `data/processed/author_subreddit_footprints_async.csv`)
— nobody had checked this before. Neither of these invalidates the
finding, but both need to be checked explicitly rather than left as an
open question.

## Sub-task A: formal interaction test

Mirror the pattern in `src/run_integrated_regressions.py`'s
`run_interaction_regressions()` (pooled model, explicit interaction
terms, read off the interaction term's own p-value — do not just compare
two separate models by eye, that is the exact mistake this sub-task
exists to fix).

1. Pool the r/conspiracy pure-population dataframe and the r/politics
   dataframe from `src/rerun_refined_regressions_v2.py` into one
   dataframe with a `subreddit` categorical column.
2. Fit one logit: `high_traction ~ (pe_prob + ps_prob + has_link +
   has_maverick + has_canonical_expert + has_consensus_expert +
   log_char_length) * C(subreddit)`.
3. Report the six `variable:C(subreddit)[T.r/politics]` interaction
   coefficients and p-values specifically — that is the actual test of
   "does this predictor's effect on engagement genuinely differ by
   community."
4. Save to `data/processed/subreddit_interaction_results.csv`.

## Sub-task B: author-overlap-excluded rerun

1. Build the overlap set: authors in
   `data/processed/comparison_politics_staged_scored.parquet` whose
   `author` also appears in
   `data/processed/author_subreddit_footprints_async.csv` (2,387
   authors as of 2026-07-20 — recompute, don't hardcode that number).
2. Rerun the r/politics-side logit from
   `src/rerun_refined_regressions_v2.py` twice: once on the full sample
   (already have this), once excluding those overlap-author comments.
3. Save both side by side to
   `data/processed/politics_overlap_excluded_comparison.csv` — do not
   overwrite `refined_regression_results_v2.csv`.
4. Note the resulting N for the excluded version — it was 4,984 comments
   removed from 30,881 as of 2026-07-20, so expect roughly 26,000 left.
   If that's now too sparse for `has_consensus_expert` (which only had
   41 positive cases to begin with), report the sparsity plainly rather
   than forcing a fit.

## When done

Report both results plainly — including if the interaction terms turn
out non-significant, or if the overlap-excluded rerun changes the
r/politics-side coefficient. Either outcome is informative; this is not
a task with a "right" answer to fish for.
