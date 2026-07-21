# Task: Stance classifier's endorsement-detection blind spot

**Status: 3-class redesign built, trained, and wired into the per-entity
breakdown/over-time scripts (2026-07-21, same session, later still).
Round 6 still needs labeling.**

## Update: 3-class redesign done

Per Nash's correction (list/link-dumps and name-enumerations aren't
necessarily neutral -- they can carry real hostile/endorsing content, so
hard-excluding them was wrong) and design call (stop forcing every
mention onto a binary hostile<->endorsement axis; add a low-effort
`other` bucket for neutral/ambiguous/questioning/etc. rather than
proliferating categories):

- `train_stance_classifier.py` now supports `--classes 3` (new default),
  folding the previously-discarded `neutral`+`ambiguous` labels (154 rows,
  already sitting unused in the queues) into `other`. No new labeling
  needed to start. `--classes 2` still reproduces the exact original
  binary behavior and writes to the original `stance_classifier.joblib`
  path, so `rerun_regressions_with_stance.py`/`run_integrated_regressions.py`
  (the core thesis regression numbers) are untouched -- the 3-class model
  writes to a SEPARATE file, `stance_classifier_3class.joblib`. Migrating
  the production regressions to a 3-class stance variable is a separate
  design decision (how does a 3-class categorical enter a traction
  regression?) not made here.
- Trained: 996 rows (hostile 468 / endorsement 382 / other 146), kappa
  0.274, macro AUC 0.649 (both lower than the binary model's 0.352/0.722
  -- expected, 3-class is a strictly harder problem, and `other`'s recall
  is weak at n=146, never specifically targeted by active learning).
- `per_entity_stance_breakdown.py` and `per_entity_stance_over_time.py`
  both rewired to the 3-class model and rerun. List/link-dump mentions
  are now scored normally (flagged via `is_list_dump`, not excluded).
  **Alex Jones: 73.0% hostile / 14.7% endorsement / 12.3% other**
  (`per_entity_stance_breakdown_unfiltered.csv`) -- down from the old
  85.8% binary figure and much closer to the quality check's ~76-80%
  ground-truth estimate; endorsement is now a real, visible share
  instead of near-zero across every year 2008-2026
  (`per_entity_stance_over_time.csv`). Reversal-summary entity list
  shifted somewhat under the new `pct_hostile` definition (argmax-based,
  not threshold-based) -- Roseanne Barr still tops it.

This is now the current, correct numbers -- **use these, not the old
85.8%/binary ones**, anywhere this gets cited.

## Why

The per-entity stance breakdown's headline number (Alex Jones ~85.8%
hostile, stable across populations) had never been checked against fresh
human labels for any single entity in depth. Built a 99-row stratified
quality-check queue for Jones specifically (hostile/borderline/endorsing
predicted buckets, ~33 each) and hand-labeled it. Result was worse than
the training CV numbers suggested, and lopsided in a specific direction:

| predicted bucket | n | accuracy | human ground truth |
|---|---|---|---|
| hostile (<0.35) | 32 | **87.5%** | 28 hostile / 4 endorse |
| borderline (0.35-0.65) | 26 | 65.4% | 19 hostile / 7 endorse |
| endorsing (>0.65) | 18 | **38.9%** | 11 hostile / 7 endorse |

Held-out kappa on this fresh sample: **0.243**, vs. 0.352 on the training
CV — a real generalization gap. The classifier is good at "confidently
hostile," bad at "confidently endorsing" (worse than chance: when it says
>0.65, the comment is actually hostile 61% of the time, often sarcasm
like "even Jones was right about..." or "nice try Alex Jones"). Across
ALL 40,263 Jones mentions in the 21M corpus, 89.5% land in the
0.35-0.65 "borderline" band and only 55 (0.1%) score >0.65 at all — so
the pooled 85.8% figure is mostly "which side of 0.5 does a
low-confidence prediction fall on," not confident classification. In the
76 binary-labeled ground-truth rows here, true hostile:endorse is
58:18 = 76%:24%, noticeably below the pooled 85.8% headline (wide CI at
n=76, but the direction of the gap — real rate probably somewhat lower
than reported — is worth a caveat before citing 85.8% to that precision
in the thesis).

Re-ran the SAME classifier on a completely different, previously-unscored
population (the newly-indexed short-comment corpus, see below) and got
the identical failure signature: only 1 of 15,891 scored Jones mentions
landed in the confident-endorsing bucket, and that one was sarcasm
("Nice try Alex Jones."). This is reproducible across populations, not a
training-sample fluke.

## What's already fixed this session

1. **Quote-stripping** (`stance_window_utils.py`: `quoted_line_ranges()`/
   `filter_quoted_spans()`, wired into `compute_spans_for_row()` and
   `per_entity_stance_breakdown.py`'s `entity_groups_for_row()`). Reddit
   markdown blockquote lines (`>`/`&gt;`) mean the target entity's window
   could be someone else's quoted words, not the commenter's own stance.
   Retrained `stance_classifier.joblib`: 42/892 training rows (4.7%) had
   their only entity mention inside a quote and were dropped; kappa
   0.345->0.352, AUC 0.713->0.722, n_train 892->850.
2. **List/link-dump filter** (`stance_window_utils.is_list_or_link_dump_window()`,
   2+ URLs in the entity's own +-15-word window). Confirmed against two
   real quality-check misses (link-dump comments scored as confidently
   endorsing purely for lacking hostile-coded vocabulary nearby). Wired
   into `per_entity_stance_breakdown.py`, `per_entity_stance_over_time.py`
   (both now print how many mentions got excluded), and
   `build_stance_active_learning_queue.py` (excluded from future sampling
   entirely — 1,477 of ~25,000 candidates, 5.9%, in the pure r/conspiracy
   maverick population alone).
3. **`per_entity_stance_over_time.py`** (new script): per-entity/per-year
   stance breakdown + early-vs-late-half reversal test, answering "was
   Jones always hated, or is this recent." Finding: Jones has been
   majority-hostile (78.9%-89.4%) every single year 2008-2026, no
   reversal. Of ~200 entities tested corpus-wide, only 6 crossed the
   50%-hostile line between early/late halves (Roseanne Barr, F. William
   Engdahl, Steve Pieczenik, Kary Mullis moved toward hostile; Stefan
   Lanka, Mark Dice moved toward endorsement) — see
   `data/processed/per_entity_stance_over_time.csv` and
   `per_entity_stance_reversal_summary.csv`.
4. **Active-learning round 6** (`build_stance_active_learning_queue.py
   --queue maverick_stance --n 80 --round 6 --strategy high_endorse`, new
   `--strategy` flag) targets the confirmed weak spot directly: samples
   the HIGHEST stance_prob rows instead of the most-uncertain ones.
   Output: `data/hitl/queue_maverick_stance_round6.csv`, 105 rows (80
   comments, split where multi-entity), all in the 0.740-0.819 range.
   **Built, not yet labeled.**
5. **Short-comment corpus indexed**: `data/processed/conspiracy_comments_short_lte100chars.parquet`,
   18,580,083 rows, exact complement of the 21.4M "usable" (char_length>100)
   corpus (21,408,577 + 18,580,083 = 39,988,660, matches
   `corpus_metadata.json`'s raw count exactly). Previously required a
   ~48s raw-JSONL scan every time; now <1s via parquet. Registered as
   `Paths().short_comments` in `utils/file_paths.py`. This is the
   ~18.6M-row population that has NEVER been touched by any classifier
   in this project (comments <=100 chars, e.g. "Alex Jones is a fed
   shill" at 21 chars) — a first look at it (16,063 Jones mentions)
   suggests it's qualitatively different, not just shorter: more jokes,
   more one-line dunks, more fragments that only make sense with parent-
   comment context the pipeline doesn't have wired in.

## What's NOT done -- pick one

1. **Label `queue_maverick_stance_round6.csv`** (105 rows) -- human task,
   not delegatable. Use the `other` category now too (it's a legitimate
   4th option: hostile / endorsement / other / wrong_match, following
   `queue_consensus_stance_CODEBOOK.md`'s existing neutral+ambiguous
   definitions, both of which now fold into `other`). Once labeled, add
   it to `train_stance_classifier.py`'s `QUEUES` list (follow the
   round2-5 pattern already there) and retrain with `--classes 3`; check
   specifically whether held-out endorsement recall improves and whether
   `other`'s recall improves (it's currently weak, n=146, never
   specifically targeted by active learning) -- look at the per-class
   breakdown in the classification_report, not just the kappa headline.
2. **Not a list/enumeration problem after all -- checked, corrected
   2026-07-21.** Initially suspected the `dnmaxng` "PsyOp like Julian
   Assange, Edward Snowden... David Seaman, George Webb" comment was a
   name-enumeration miss the URL filter didn't catch. Verified against
   the actual filter and it's WRONG -- that window contains 2 YouTube
   URLs and IS already caught by `is_list_or_link_dump_window`. Checked
   all 24 quality-check misses instead: 17 aren't list/link-dumps at all.
   The real remaining pattern is (a) missed explicit-agreement phrasing
   ("Alex Jones is **not wrong**", "I **agree** with a lot of what Alex
   says" -- both scored hostile-leaning) and (b) sarcastic meme-callback
   mockery using Jones's own famous claims as a punchline with no
   hostile-coded vocabulary ("thrown in with Alex Jones's **gay frogs**"
   scored 0.72, confidently *endorsing*). Neither is fixable with a cheap
   deterministic filter the way the URL one was -- these need either
   lexicon expansion or, more likely, just more labeled examples (i.e.
   round 6, item 1 above) since they're genuinely context-dependent, not
   structural. Don't build a name-enumeration filter without first
   checking round 6's labels for whether that pattern actually recurs --
   it didn't show up as a real failure mode in this 99-row check.
3. **Done (2026-07-21, later still).** Reran both scripts with the
   3-class model. Alex Jones: 73.0% hostile / 14.7% endorsement / 12.3%
   other (`data/processed/per_entity_stance_breakdown_unfiltered.csv`),
   stable-majority-hostile every year 2008-2026 with no reversal
   (`per_entity_stance_over_time.csv`), same qualitative finding as
   before but a materially different (more defensible) number. The
   `--population pure` variant of `per_entity_stance_breakdown.py` has
   NOT been rerun yet -- only `unfiltered` -- do that too before citing
   the "stable across populations" claim with the new numbers.
4. **Decide the short-comment-corpus scope question**: extending the full
   entity/stance pipeline to all 18.6M short comments is a real, sizeable
   compute decision (not delegatable without sign-off). Less urgent now
   that (1)/(2)/(3) landed, but still worth deciding deliberately rather
   than just running it.
5. **Done (2026-07-21, later still).** `ANTIGRAVITY_HANDOFF.md`'s
   headline finding now cites the 3-class numbers (73.0/14.7/12.3),
   marked as superseding the old 85.8% binary figure.

## Relevant files

- `src/build_jones_stance_quality_queue.py`, `src/score_jones_stance_quality_check.py`
- `data/hitl/queue_jones_stance_quality_check.csv` (labeled, has `bucket`/
  `stance_prob`/`model_predicted_label`/`correct` columns added for review)
- `data/hitl/queue_jones_stance_quality_check_REVIEW.csv` (full text,
  worst-misses-first)
- `data/hitl/queue_maverick_stance_round6.csv` (built, unlabeled)
- `src/per_entity_stance_over_time.py`, `data/processed/per_entity_stance_over_time.csv`,
  `data/processed/per_entity_stance_reversal_summary.csv`
- `data/processed/conspiracy_comments_short_lte100chars.parquet`,
  `utils/file_paths.py`'s `Paths().short_comments`
- `src/stance_window_utils.py` (quote-stripping + list/link-dump filter,
  both new this session)
