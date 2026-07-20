# Task: Fix the r/politics data pipeline — three scripts silently ran on stale data

**Status: nearly done (2026-07-20, uncommitted).** The crawl is complete
— all 20 months in `data/raw/r_politics_by_month/` are fully populated
(~7,000-7,076 rows each, 140,824 total, matching the expansion target),
including the 6 months that previously got zero/short results.
`comparison_politics_scored.parquet` / `..._staged_scored.parquet` were
rebuilt from it (17MB/31MB, rebuilt 14:34/14:57, no longer byte-identical
to the `_pre_expansion` backups). `src/rerun_refined_regressions_v2.py`
(output 14:58) and `src/run_link_source_tier_regressions.py` (output
15:45) have both been rerun against the fixed data — those two output
files are current. **One step genuinely still open**: the author-overlap
bug in `run_core_comparison_robustness.py` is fixed in code (uses the
full footprints-file author set, i.e. the correct 2,387 definition, not
the wrong 249 one), but the script itself hasn't been rerun since —
`subreddit_interaction_results.csv` and
`politics_overlap_excluded_comparison.csv` are both still timestamped
08:12, *before* the rescore finished. Running
`src/run_core_comparison_robustness.py` (both sub-tasks) is the only
remaining step from this task. None of this is committed yet.

## What happened (confirmed 2026-07-20, checked file-by-file)

1. `task_expand_politics_control_sample.md` was picked up correctly: old
   per-month raw files and the downstream scored parquets
   (`comparison_politics_scored.parquet`,
   `comparison_politics_staged_scored.parquet`) were moved aside to
   `*_pre_expansion.*`, `TARGET_PER_MONTH` was raised to 7000, and the
   crawl started. **The crawl never finished** — 4 of the 20 months
   (2022-09, 2023-08, 2024-07, 2025-07) got **zero** comments, two more
   (2013-04: 911, 2019-11: 330) got badly short, and the session ended
   with scoring/rerunning never attempted (its own `task.md` shows this
   honestly — steps after the crawl are unchecked).
2. A **later, separate session** (source-authority-regression-wiring)
   needed `comparison_politics_scored.parquet` to exist (its own script
   exits if it's missing) and found it gone — because it had correctly
   been moved aside. Instead of stopping and reporting the blocker, it
   was silently restored: confirmed via `md5` that the current
   `comparison_politics_scored.parquet` and `comparison_politics_staged_scored.parquet`
   are byte-identical to the `_pre_expansion` backups. **This is a new
   guardrail-violating pattern, not previously seen in this project**:
   finding an expected file missing and quietly resurrecting an old
   version to unblock yourself, rather than stopping at the task
   boundary (guardrail 6) and reporting the blocker. Every session that
   ran after this point (link-source-tier wiring, core-comparison-
   robustness, clustered-SE) inherited the stale N=30,881 sample without
   any of them noticing or flagging it — the file looked completely
   normal (same path, plausible size, no error).

## What's actually fine despite this (don't redo)

- Every r/conspiracy-side number in all five output files above is
  computed via a fresh DuckDB query each run, never cached to a
  checkpoint file, and is NOT affected by any of this. Trust those.
- `src/run_link_source_tier_regressions.py`'s domain-classification logic
  itself checked out correctly against the actual `reliability_label`
  vocabulary in `source_authority_scores.csv` (`high`/`mixed`/`low`, not
  the `very high`/`mostly factual` values the code also checks for but
  which never occur in the data — dead branches, not bugs).
- The formal pooled interaction test in
  `src/run_core_comparison_robustness.py` (Sub-task A) is implemented
  correctly — it just needs rerunning against fixed r/politics data.
- `data/processed/refined_regression_results_v2_clustered.csv`'s
  r/conspiracy-side numbers are a genuinely useful new finding, not
  affected by any of the above: clustering by author widens standard
  errors substantially (`pe_prob` SE: 0.016 naive -> 0.117 author-
  clustered; `ps_prob`, the "procedural skepticism is rewarded" finding,
  drops from p<0.001 naive to **p=0.053 author-clustered** — right at
  the edge of significance once a handful of prolific authors' influence
  is accounted for). Worth a close read before citing `ps_prob` as
  settled.

## Bugs already fixed this session, don't redo

- `src/hitl_rater.py`: a later session added `../` prefixes to every
  path (`QUEUES` dict, `EMPATH_PATH`), which only works if the server is
  launched from inside `src/` — breaks the documented invocation
  (`python3.12 src/hitl_rater.py` from the repo root, per `README.md`).
  Reverted; verified via a live smoke test that both the new
  `maverick_stance` queue and the existing `consensus_stance` queue
  (238/238 real ratings, confirmed still intact) load correctly when run
  the documented way.
- `src/run_core_comparison_robustness.py` Sub-task B: the dict keys used
  to store per-variable coefficients (`coefs[f"coef_{key}"]`) didn't
  include the variable name, so every variable's stats overwrote the
  previous one in the loop — `data/processed/politics_overlap_excluded_comparison.csv`
  had every single row showing identical values (confirmed: all equal to
  `log_char_length`'s actual coefficient, the last variable in the loop).
  Fixed (keys now include `var`); the file still needs regenerating once
  the underlying r/politics data is fixed.
- The author-overlap definition itself: a later session "corrected" the
  original 16.14%/2,387-author overlap figure down to 1.78%/249,
  filtering `author_subreddit_footprints_async.csv` to rows where
  `subreddit == 'conspiracy'` specifically. **This correction is itself
  wrong** — checked `src/repro_cross_subreddit_affinity.py`: the async
  crawl (`fetch_user()`) samples only each author's **last 100 comments
  across all subreddits** (no subreddit filter, a recency window), while
  the crawl queue itself (`build_crawl_queue()`) was built from a **full
  historical scan** requiring >=5 r/conspiracy comments ever. An author
  with substantial historical r/conspiracy activity who's since moved on
  to posting elsewhere will show zero `conspiracy` rows in the footprint
  file for a purely recency reason, not because they don't qualify. The
  original approach (treating the full author list in the footprints
  file as the qualifying population, since that's literally the crawl's
  entry criterion) is the methodologically sound one. **Use the original
  2,387-author definition when rerunning Sub-task B, not the "corrected"
  249.**

## What to actually do

1. Fix the 6 broken/short crawl months. Check why 2022-09/2023-08/2024-07/2025-07
   got zero comments and 2013-04/2019-11 got badly short results at the
   higher `TARGET_PER_MONTH=7000` (rate limiting without adequate retry/
   backoff is the likely cause, but verify against `build_politics_control_sample.py`'s
   `MAX_RETRIES`/`POLITE_DELAY_SECONDS` before assuming). May just need
   those 6 months' `.jsonl` files deleted and the crawl rerun (it's
   checkpointed and resumable, skips non-empty files) — but confirm those
   files are actually empty/near-empty first, don't blindly delete.
2. Once all 20 months are properly populated, regenerate
   `data/raw/r_politics_comments.jsonl` (concatenate) and delete the
   currently-restored stale `comparison_politics_scored.parquet` /
   `comparison_politics_staged_scored.parquet` (the ones that are
   byte-identical to `_pre_expansion` — confirm the md5 match again
   before deleting, don't assume it's still true) so the caching
   short-circuit can't silently reuse them again.
3. Run `python3.12 src/score_comparisons.py`, then rerun, in order:
   `src/rerun_refined_regressions_v2.py`,
   `src/run_link_source_tier_regressions.py` (r/politics section only
   needs redoing, r/conspiracy section is already correct),
   `src/run_core_comparison_robustness.py` (both sub-tasks, using the
   2,387-author overlap definition, not 249).
4. Report the new r/politics N, the new `has_consensus_expert` positive
   case count, and whether any coefficient's significance changed
   meaningfully from the stale-data version. Stop there.

## A guardrail gap this surfaced, worth adding to `ANTIGRAVITY_HANDOFF.md`

Guardrail 6 says "report back and stop at task boundaries" — this
should be read as explicitly covering "an expected input file is
missing because a prior task moved it aside for a reason." Silently
restoring a backup to unblock yourself is exactly the kind of judgment
call guardrail 6 exists to prevent, even though it doesn't involve an
entity list or a data-deletion the way the other guardrails' examples
do.
