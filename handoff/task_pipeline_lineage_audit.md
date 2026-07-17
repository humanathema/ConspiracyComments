# Task: Full-lineage pipeline audit + duplicate-ID root cause

**Status: staged, not started. Large — break into the 4 numbered pieces
below, don't try to do it all in one pass.**

## Why this task exists

Two separate things converged into one task:

1. Nash's complaint: the existing `pipeline_validity_audit.md` (repo
   root) only covers the 10 pipeline components currently in use. It
   never explains the project's actual history — approaches that were
   tried, found flawed, and replaced. Concrete example: an early
   spaCy-based FactAppeal approach exists on disk
   (`data/processed/spacy_attributed_comments.parquet`, 279.9MB per
   `DATA_MANIFEST.md`, plus `spacy_audit_scratchpad.csv`) that predates
   and was replaced by the current TF-IDF+LogReg FactAppeal classifier —
   nothing on record explains *why* it was replaced or what was
   specifically wrong with it.
2. A real, found-but-not-fully-traced data quality bug: the two
   foundational corpus files every regression in this project depends on
   — `data/processed/empath_scores_full.parquet` and
   `data/processed/research_corpus_staged_scores_full21m.parquet` — each
   have **~58,669 duplicate `id`s**, causing 0.85% pseudo-replication in
   the actual regression population (confirmed 2026-07-17: pure
   r/conspiracy population is 1,985,823 rows, only 1,968,864 unique ids).

## What's already been ruled out (don't re-check these)

- `empath_scores_full.parquet`'s own construction does NOT introduce the
  duplication — confirmed via `ConspiracyMaster_Refactored.ipynb` cell
  50: it's a single-source DuckDB `COPY (SELECT ... FROM LEXICAL) TO
  OUTPUT_FILE`, no join at all.
- `research_corpus_staged_scores_full21m.parquet`'s own construction
  does NOT introduce it either — confirmed via `src/score_main_corpus_staged.py`
  line 169 (`final_df.to_parquet(output_parquet)`): straight passthrough
  from `empath_scores_full.parquet`, same row count in and out.
- So the duplication is inherited from `lexical_scores_full.parquet`'s
  own construction, or from raw comment ingestion further back.

## Piece 1: trace the duplicate-ID root cause

17 archived notebooks reference `lexical_scores_full.parquet`'s
construction (grep for `lexical_scores_full` across
`notebooks/archive/*.ipynb` and `notebooks/legacy_production/*.ipynb` to
get the current list — it may have grown). The largest and most likely
candidates to check first: `ConspiracyMaster.ipynb` (6.8MB),
`ConspiracyMaster_Final_Architecture.ipynb`, `ConspiracyMaster_Organized.ipynb`.

Find the actual cell that builds `lexical_scores_full.parquet`. Check:
- Does it join against anything with a non-unique key?
- Does it read raw comments via a glob pattern
  (`data/raw/r_conspiracy_comments*.jsonl*`)? If so, check whether that
  glob could double-count — this project's raw archive is split across
  numbered files (`r_conspiracy_comments1.jsonl.gz` through `...10`, with
  some numbers missing due to a 2026-07-13 data-loss incident and
  partial Kaggle-backup recovery) — verify there's no overlap between
  numbered files (e.g. same date range covered by two different files).

Once found: either fix it and note the fix, or (if fixing means
rebuilding a 21M-row file, expensive) document the exact mechanism
clearly enough that the cheap interim fix (dedup at query time, see
below) can be trusted as sufficient without a full rebuild.

**Interim fix, not yet applied, cheap, do this regardless of what Piece 1
finds**: add `QUALIFY ROW_NUMBER() OVER (PARTITION BY id) = 1` (or
equivalent) to the `s`/`e` join in `src/rerun_refined_regressions_v2.py`
and `src/run_pure_population_analysis.py` before trusting any future
rerun's exact N. At 0.85% duplication this is very unlikely to overturn
any existing finding's significance, but it's a real independence-
assumption violation.

## Piece 2: audit the spaCy FactAppeal predecessor

Same 8-part questionnaire as the existing `pipeline_validity_audit.md`
(what it is / location / derivation / validation / limitations /
construct validity / analytical impact / next steps), applied to:
- `data/processed/spacy_attributed_comments.parquet`
- `data/processed/spacy_audit_scratchpad.csv`
- Whatever notebook cells produced them (search archived notebooks for
  `spacy_attributed`)

Specifically answer: why was this replaced? What did the TF-IDF+LogReg
version fix? Is anything live still reading these two files (should not
be — verify, don't assume).

## Piece 3: broaden the pipeline audit document

Produce a NEW file, `pipeline_lineage_audit.md` (repo root) — don't
overwrite the existing `pipeline_validity_audit.md`, which is already
correct for the 10 current components. This new document should cover
the succession of notebooks leading to `ConspiracyMaster_Refactored.ipynb`
— not equal depth on all 17 archived notebooks, but enough to answer:
what major approaches were tried and abandoned, and why. This is
literally what Nash's supervisor has repeatedly asked him to track for
the thesis write-up.

## Piece 4: regenerate `DATA_MANIFEST.md`

It's dated 2026-07-06 and predates essentially everything from the most
recent work (the r/politics control, the recovered posts archive, the
mainstream-expert augmentation files, the consensus-stance queue, the
attribution scorer, all of it). Check whether the original generation
script still exists (search for anything producing a per-file
ACTIVE/legacy/orphan table) before writing a new one from scratch.

## When done

Report back per-piece, don't wait until all 4 are finished. Piece 1 in
particular may turn up something that changes how urgent the interim
dedup fix is — surface that immediately, don't sit on it.
