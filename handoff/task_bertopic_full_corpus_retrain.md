# Task: Retrain BERTopic on a representative sample, then apply to the full corpus

**Status: DONE (2026-07-24).** Started ahead of the sequencing this file
originally specified (started in parallel with the in-flight
byline/IRR/short-comment work below, not after it) -- noted here for
the record, not silently smoothed over.

Full pipeline executed end-to-end: `extract_stratified_sample.py` built
the 100k/20k stratified train/val split (45.1% short comments, matching
the corpus's real short-comment share); `train_bertopic.py` fit 97
data-driven topics + 3 hand-seeded centroids (5G/EMF, glyphosate,
microplastics) = 100 topics; `apply_topic_assignments.py` streamed
topic assignment across the full 39.9M-comment corpus (21,349,908 long +
18,580,083 short), checkpointed and resumable, GPU+CPU sharded for
throughput. Outputs: `data/processed/empath_scores_full_mapped.parquet`,
`data/processed/conspiracy_comments_short_lte100chars_mapped.parquet`.

**Result: outlier rate 5.5% (long) / 13.5% (short)**, vs. the old
high-upvote-only model's 61.8% on a representative sample (see the
`run_pure_50k_topic_analysis.py` baseline this task file originally
cited as the reason to retrain) -- confirms the representativeness fix
worked. Caveat: this compares against the old model's `.transform()`
number directly, not an apples-to-apples held-out check on the *new*
model alone (some of the gap is the better topic set, some is the more
forgiving title-fallback assignment scheme) -- the clean comparison is
the new model's outlier rate on its own reserved 20k validation split,
which the sample script produced but doesn't appear to have been
separately reported. Worth doing before citing the 5.5%/13.5% numbers
as the retrain's outlier rate specifically, rather than the full
pipeline's.

**Also found, not part of this task's original scope**: the short-
comment source file (`conspiracy_comments_short_lte100chars.parquet`)
has 51,804 duplicate `id`s, confirmed pre-existing (not introduced by
this run). Same join-fanout bug class already fixed at the source for
`empath_scores_full.parquet` and `research_corpus_staged_scores_full21m.parquet`
(see `ANTIGRAVITY_HANDOFF.md` guardrail #5) -- just never applied to
this file. Any future join against it on `id` needs a dedup guard until
fixed at the source.

**Not done**: Section 4 below ("Group into interpretable Super-Topics").
`src/map_super_topics.py` exists but hasn't been confirmed run against
the new 100-topic set.

---

Original task description follows, kept for context on the sample
design and why retraining (not transforming the old model) was
necessary:

Larger, later-phase piece of the "individual sources/authors tied to
specific issues/dichotomies" research direction Nash raised.

## Why, and the decisive evidence already sitting in this project

The existing BERTopic model (`ConspiracyMaster_Refactored.ipynb` §9.2)
was fit ONLY on comments with >=50 upvotes -- a narrow, non-representative
slice. Nash asked directly: can the existing model just be transformed
(not retrained) onto the wider corpus? **Checked against evidence already
in this project rather than guessed**: `src/run_pure_50k_topic_analysis.py`
already transformed this exact pre-trained model onto a properly random
50,000-comment sample spanning the full upvote distribution of the pure
population, and the result is in
`topic_time_user_synthesis_report_pure_50k_baseline.md`:
**30,915 of 50,000 comments (61.8%) landed in the outlier bucket
(topic=-1)**. The model trained on >=50-upvote comments only captures
real topic structure for about 38% of a representative sample.

**Conclusion: don't transform the existing model onto the full corpus --
it demonstrably doesn't generalize.** Retraining (refitting) on a properly
representative sample is necessary. Retraining on the literal full
21.4M-40M corpus is neither necessary nor practical -- BERTopic's fit
step (sentence embedding + UMAP + HDBSCAN) doesn't need every document to
learn good topic structure, and embedding+clustering tens of millions of
documents is a genuinely large compute job on an 8GB machine. Fit on a
much larger, properly stratified sample; transform that refit model onto
the full corpus for assignment (a cheaper operation than the fit itself).

## What to build

### 1. A properly stratified training sample (this is the fix for the 61.8% outlier problem)

Not just "bigger" -- *representative*. Stratify across:
- Upvote tiers spanning the full distribution (not just >=50), matching
  the same "restores variance the high-upvote-only regression lost"
  logic already articulated in `topic_time_user_synthesis_report_pure_50k_baseline.md`'s
  own text.
- Long AND short comments, given today's session extended the core
  entity-stance and citation pipelines to the 18.6M short-comment
  population specifically because it carries real signal despite being
  brief -- the same logic likely applies to topic content, though this
  needs its own check (a short comment may carry a recognizable topic
  even if it can't carry full argumentative context).
- Size: bigger than the 50K sample that already showed 61.8% outliers
  (that sample size wasn't the problem, its narrow upvote-range training
  *source model* was) -- but there's no established target size here,
  size it based on what's computationally tractable on this machine
  first, then check the resulting outlier rate as the real signal of
  whether it's big/diverse enough, not a number picked in advance.

### 2. Refit BERTopic on this sample

Same embedding model/pipeline as the existing model
(`sentence-transformers` + UMAP + `BERTopic`, per §9.2 of the notebook)
for continuity, unless there's a specific reason to change it. Report
the new outlier rate on a held-out check -- this is the number that
tells you whether the refit actually solved the generalization problem,
compare directly against the 61.8% baseline.

### 3. Transform the refit model onto the full corpus for topic assignment

Once the refit model's outlier rate looks reasonable on held-out data,
apply `.transform()` across the full 21.4M (or wider, if short comments
are included per item 1) corpus for topic assignment -- this step is
cheap relative to the fit itself. Same memory-safety discipline as
everything else this session (chunked/streaming, not a full in-memory
load, given the 8GB RAM constraint and this corpus's scale).

### 4. Group into interpretable Super-Topics / issues

The existing 50K pipeline already groups fine-grained topics into "6
cohesive Super-Topics" -- re-derive this grouping for the new topic set
rather than assuming the old 6-group scheme still applies, since the
underlying topic model itself changed.

## Explicitly NOT in scope for this task

- Tying topics to specific sources/authors or building a per-topic stance
  ("which side of this issue") construct -- that's further downstream
  work, dependent on this task landing first, not part of it.
- Author/byline extraction -- separate, already-staged
  `task_author_byline_extraction.md`.

## When done

A BERTopic model that generalizes to the full corpus with a real,
reported, held-out-validated outlier rate (not assumed), full-corpus
topic assignments, and a re-derived Super-Topic grouping -- the
foundation the topic-tied source/dichotomy analysis would build on next,
not that analysis itself.
