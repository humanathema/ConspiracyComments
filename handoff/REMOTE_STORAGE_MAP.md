# Remote storage map — where files live when they're not under `data/processed/`

Built 2026-08-03 after repeatedly hitting the same confusion this project
keeps generating: a script references a file, it's not on this 8GB-RAM
laptop, and nobody remembers whether that's because it never existed
locally, was deleted after a verified Kaggle backup, or lives in a
GitHub Actions artifact. **Read this before assuming a missing file
needs regenerating** — check here first, since several "missing" files
turned out to already exist remotely with zero rebuild needed (see
`cited_urls_ranked.csv` below, found and pulled down same-day this doc
was written).

## Why this keeps happening

Two real, ongoing constraints combine to produce this pattern:
1. **8GB RAM / limited local disk** ([[machine_constraints]] memory) —
   several large corpus files (multi-GB parquets) were deliberately
   moved to Kaggle-only storage during disk-cleanup passes, sometimes by
   a session that verified a byte-identical Kaggle copy first (real,
   deliberate), sometimes just because a concurrent session's own
   cleanup pass caught something another in-flight task still needed
   (the `empath_scores_full_mapped.parquet` deletion mid-
   `task_2026-07-28c_media_personality_candidate_list_in_progress.md` is
   the confirmed example of the latter).
2. **Multiple concurrent Kaggle accounts, each pushing its own kernel's
   inputs/outputs as separate small datasets** ([[kaggle_multi_account_orchestration]]
   memory) — there is no single "the canonical dataset," there are
   several, split by when/why they were created, not by any consistent
   naming scheme.

## How to check yourself, before asking

```bash
# Find which dataset (if any) has a specific file, across all 4 accounts:
for tok in access_token access_token0 access_token1 access_token3; do
  export KAGGLE_API_TOKEN=$(cat ~/.kaggle/$tok)
  kaggle datasets list -m 2>&1  # lists that account's own datasets
done
# Then, for a specific dataset ref:
kaggle datasets files <owner>/<dataset-ref>

# Download one file from a dataset without pulling the whole thing:
kaggle datasets download <owner>/<dataset-ref> -f <filename> -p /tmp/dl --force
# Kaggle sometimes zips single-file downloads, sometimes doesn't -- check before assuming unzip is needed:
unzip -o /tmp/dl/<filename>.zip -d data/processed/ 2>&1 || cp /tmp/dl/<filename> data/processed/
```

Account -> token file mapping (from `~/.surge-compute/providers.yaml`):
`tobiasnashws`=`access_token` (main), `tobiasnash`=`access_token0`,
`manawatusamaritans`=`access_token1`, `tobiasnashktc`=`access_token3`.

**Do not rebuild a full local index/copy of anything corpus-scale to
work around a missing file** — this has crashed the disk once already
(`build_local_context_db.py`'s abandoned 44M-row local DuckDB attempt,
~18GB against ~20GB free). Targeted, scoped extraction
(`build_targeted_context_cache.py`'s pattern) or just downloading the
specific file from wherever it already lives is the correct fix.

## Known Kaggle dataset locations (checked directly, 2026-08-03)

### `tobiasnashws/conspiracycomments-canonical-corpus` (9.5GB, created 2026-07-30)
The consolidated "one source of truth per file" backup from the
2026-07-28 disk cleanup. Contains:
- `ats_comments_final.parquet`
- `conspiracy_comments_short_lte100chars_mapped.parquet`
- `empath_scores_full_mapped.parquet` — **the file whose absence caused
  the `hitl_rater.py` context-lookup bug (fixed 2026-08-03 via a
  targeted cache instead) and the `rank_cited_urls_by_author.py` upvote
  join gap.** If a script needs this file's data and a small/targeted
  extraction won't do, this is the dataset to pull from.

### `tobiasnashws/conspiracycomments-derived-tier2` (484MB, created 2026-07-28)
Smaller derived analysis files, also consolidated during the 2026-07-28
cleanup. Contains:
- `citations_cache.parquet`
- **`cited_urls_ranked.csv`** — confirmed present here, downloaded and
  restored to `data/processed/` 2026-08-03 (1,763,439 rows, matches the
  known count in `handoff/cited_content_curation_step2.md` exactly —
  no regeneration was needed, it was never actually lost).
- `comment_brigade_flags.csv`
- `comparison_politics_staged_scored.parquet`
- `corpus_entity_frequency_final.csv`
- `domain_source_quality_rollup.csv`
- `entity_final_review.csv`
- `entity_mentions_cache_2stage_pooled.parquet`
- `missing_entity_candidates.csv`
- `research_corpus_staged_scores_full21m.parquet`
- `thread_insider_presence.csv`
- `thread_quality_metrics.csv`

### `tobiasnash/conspiracycomments` (14.9GB, created 2026-06-18 — the oldest, original backup)
Predates the canonical-corpus consolidation; some files here are older/
un-mapped versions of files that now also exist in the canonical-corpus
dataset above (e.g. `empath_scores_full.parquet` here is the pre-
`_mapped` version — check which one a script actually needs, they are
NOT interchangeable, `_mapped` has real `parent_id`/`link_id`, the plain
version doesn't). Also holds the raw `r_conspiracy_comments*.jsonl`
shards and older derived files (`lexical_scores_full.parquet`,
`master_thread_synthesis.parquet`, several `lexical_baseline_*`/
`lexical_keyness_*` snapshot files). Listing is long/paginated — use
`kaggle datasets files tobiasnash/conspiracycomments --page-token <token>`
for more if the first page doesn't have what you need.

### `tobiasnashws/ats-topic-assignment-data` (2.2GB, created 2026-07-27)
ATS-specific topic modeling inputs/outputs: `ats_comments_body.parquet`,
`ats_thread_topic_map.parquet`, `ats_topic_centroids.npz`,
`ats_topic_names.csv`.

### `tobiasnashws/conspiracycomments-scoring-models` (153KB, created 2026-07-28)
Trained sklearn/joblib pipeline artifacts, not corpus data:
`hedged_suspicion_pipeline.pkl`, `staged_pipeline_models.joblib`.

### Many smaller, task-specific datasets — NOT canonical, treat as ephemeral kernel I/O
`stance-classifier-training-data*`, `stance-round{2,6,7}-*`,
`entity-noise-data`, `media-personality-wikipedia-candidates`,
`domain-epistemic-data`, `entity-stance-*-sample`, etc. (full list via
`kaggle datasets list -m` on each of the 4 accounts). These are inputs/
outputs for one specific kernel run each, named ad hoc per-task — do
not assume any of these is "the" canonical copy of anything; check the
canonical-corpus/derived-tier2 datasets above first for corpus-scale
files.

## GitHub Actions — ephemeral, NOT permanent storage

`.github/workflows/expert-sources-refresh.yml` (manual `workflow_dispatch`
trigger only, not scheduled) runs `query_openalex_experts.py` ->
`query_petscan_experts.py` -> `build_historical_officeholders.py` and
uploads `openalex_experts.csv` / `petscan_experts.csv` /
`mainstream_expert_augmented_superset_temp.csv` as a workflow artifact
named `expert-sources-<run_id>`. **`retention-days: 14`** — these
artifacts expire and disappear after 2 weeks. If one of these three
files is missing locally and the run that produced it was more than ~14
days ago, it's gone and the workflow needs re-running (`gh workflow run
expert-sources-refresh.yml`), not searched for.

## Checked and NOT found in any of the above (2026-08-03) — genuinely unresolved

These are referenced by scripts but weren't in any dataset file listing
checked this session. Most likely either dead code paths from
superseded pipeline stages (the various `ats_comments_*.json`
intermediate files look like this — pre-parquet scraping stages, almost
certainly superseded by `ats_comments_final.parquet`) or something that
never got backed up before being cleaned locally. Don't assume "on
Kaggle somewhere" for these without checking further — flag to Nash if
one of these turns out to be actually needed:
- `active_learning_kappa_log.csv`
- `full_corpus_suspicion_scores.parquet`
- `reddit_control_sample.parquet`
- The pre-parquet ATS JSON intermediates (`ats_comments.json`,
  `ats_comments_cc*.json`, `ats_comments_master.json`,
  `ats_comments_legacy_complete.json`, `ats_cc_index.json`,
  `ats_metadata.json`) and the BTS equivalents (`bts_comments.json`,
  `bts_abovepolitics_comments.json`)

## Maintenance note

This doc is a snapshot (2026-08-03) of dataset contents that will keep
changing as new kernels push new datasets. If a file genuinely isn't
where this doc says, re-run the "how to check yourself" recipe above
rather than trusting this file forever — but update this doc too once
you've found the new location, so the next confusion gets shorter, not
repeated from scratch.
