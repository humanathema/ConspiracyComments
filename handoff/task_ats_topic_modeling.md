# ATS topic modeling to reddit-side parity (in progress, 2026-07-26)

**Status update (2026-07-26, later same day): the fit-new-vs-transfer
decision below is no longer open — it's been settled empirically, not
just flagged.** `src/verify_ats_topic_transfer.py` ran a rigorous
transfer diagnostic (50k stratified ATS sample vs. a 20k in-domain
reddit control, same 0.35 cosine-threshold rule): the reddit-trained
model transfers poorly — ATS's outlier rate is +7.8 to +9.3 percentage
points higher than the reddit control baseline, worse the older the ATS
era (pre-2008 worst at +9.30%, 2017+ least-bad at +6.30%, still a real
gap). Full report: `data/processed/ats_transfer_verification_report.md`
(also includes a residual-discovery K-means pass on the outlier/
ambiguous pool, and an exploratory dendrogram of the reddit topic tree).
This confirms option 1 below (fit a new model) rather than transferring,
per the era/vocabulary prediction already in this doc.

**Follow-on now in progress**: `src/train_bertopic_ats_overlap.py`
fits a native BERTopic model on a stratified 100k ATS sample restricted
to the 2008-2016 overlap era (same hyperparameters as the reddit-side
`train_bertopic.py`). As of this update its outputs
(`data/processed/bertopic_model_ats_overlap/`,
`ats_topic_centroids.npz`, `ats_train_topic_assignments.parquet`) don't
exist yet in `data/processed/` — check before assuming this step is
finished; it may still be running or may need a rerun. Note this first
pass is scoped to the 2008-2016 overlap window specifically, not the
full 1998-2020s ATS corpus — whether/how to extend to the full corpus
once this is validated is still open.

**Update 2026-07-27 (later same day): two-phase plan settled.**
Discussed and reasoned through with Nash directly (not defaulted
silently):
- **Phase 1, running now**: `train_bertopic_ats_overlap.py` against
  ATS alone, started specifically to use the wait time while BTS
  downloads, not because ATS-only was decided as final.
- **Phase 2, later**: a combined-corpus run once BTS is parsed. The
  case for combining isn't just volume — reddit's own topic model was
  trained on the *whole* r/conspiracy corpus, chitchat/banter included,
  not filtered down to "serious" content only, so filtering ATS down to
  its on-topic board while BTS (the same "Above Network" community's
  off-topic register, same operator/site family) sits out would make
  ATS *narrower* than reddit's population, not matched to it. Same
  logic extends to **AbovePolitics**: Nash's read is that r/conspiracy
  itself carries a lot of political content, so ATS's own politics-
  adjacent discourse (even via a small, ~67,633-comment sister board)
  may be more relevant to real parity than its size alone suggests —
  reopened for the combined run, not excluded.
- **Open, checkable assumption**: the "BTS is the same community as
  ATS, just a different register" premise rests on them being the same
  site operator, not on confirmed shared membership. Once BTS is
  parsed, worth a direct *exact*-username overlap check between ATS and
  BTS authors (unlike the ATS-reddit stylometry problem, if these share
  a login system a matching username **is** the same account, not just
  circumstantial evidence) — cheap, and confirms or complicates the
  premise the combined-run decision rests on.

**Do not treat the ATS-only run as the final answer for this task** —
check whether Phase 2 (combined) has been decided/started before citing
whatever Phase 1 produces as the finished topic model.

**Still needed after the model lands**: the topic-quality calibration
pass (see "Whichever path" below) hasn't been applied to whatever this
produces yet.

---

Sibling task to `task_ats_entity_disambiguation.md` and
`task_ats_stance_classification.md` — part of the same bigger push
(bringing ATS to full analytical parity so it's a genuine second
population, not just a browsable corpus). This is the biggest lift of
the three analytical pieces.

## What exists on the reddit side

`src/train_bertopic.py` — trains a global BERTopic model (sentence-transformer
embeddings via `all-MiniLM-L6-v2`, UMAP dimensionality reduction, CPU-only,
4 threads) against `data/processed/train_topic_comments.parquet`, producing
`data/processed/bertopic_model_new/` plus the downstream
`topic_centroids.npz` and `_audit_topic_quality_embeddings_cache.npy`
artifacts referenced by the seed-claim probe tool
(`handoff/task_seed_claim_probe_to_cloud_run.md`). The topic-quality
calibration and central-claim extraction work on top of this is described
in `handoff/task_topic_quality_and_claim_detection.md`.

## Why this doesn't just "rerun the same command on ATS"

Two real options, and this needs an actual decision, not a default:

1. **Fit a new BERTopic model on ATS text directly.** Almost certainly
   the right call — ATS spans 1998-2020s with a very different
   community/era mix than reddit's 2020s r/conspiracy, so the topic
   vocabulary genuinely differs (e.g. pre-9/11 conspiracy discourse,
   different UFO/JFK-era terminology, different platform-specific slang).
   A model fit on reddit vocabulary would likely either fail to find
   ATS's real topic structure or force ATS content into reddit-shaped
   buckets that don't fit.
2. **Test whether the existing reddit-fitted model transfers** (embed
   ATS comments with the same sentence-transformer, assign to nearest
   existing centroid, check cohesion) — worth doing as a *diagnostic*
   before committing to (1), since it's cheap and would settle the
   question empirically rather than by assumption. But go in expecting
   it likely won't transfer cleanly, per the era/vocabulary point above.

Whichever path, this needs the same topic-quality calibration work
already applied to the reddit side (`task_topic_quality_and_claim_detection.md`)
before trusting the topics as meaningful — don't skip that step just
because it's already been built once.

## Practical/resource note

`train_bertopic.py` is CPU-only by explicit design (4 threads, no GPU),
which is good given this machine's constraints, but 7.15M ATS comments is
larger than whatever reddit sample `train_topic_comments.parquet` used —
check that sample size before running the full corpus; this project has
hit real OOM kills before on full-corpus jobs (see the machine-constraints
memory note and `ANTIGRAVITY_HANDOFF.md`'s 8GB-RAM guardrail: fetch/hold
only the subset actually needed, free it as soon as done, don't hold full
`text` in memory for a population in the millions).

## Suitability for delegation

Good fit for a long-running Antigravity session — this is exactly the
shape of task Antigravity handles well (substantial, mostly-mechanical
once the fit-new-vs-test-transfer decision is made, doesn't need
step-by-step supervision). The one decision point Nash should weigh in on
first is which of the two options above to pursue — flag it and wait
rather than default to one silently, given the real cost difference
(fitting a new model is a much bigger compute job than a transfer test).

## Output needed for the bigger cross-platform push

A `topic_name` (or equivalent) column on ATS comments, in the same shape
as the reddit-side `topic_examples.parquet`, plus whatever topic-quality
calibration artifacts parallel the reddit side's.
