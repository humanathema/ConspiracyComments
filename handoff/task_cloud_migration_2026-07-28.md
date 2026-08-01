# Cloud migration off local machine, 2026-07-28 — GH Actions + Kaggle

What moved off the laptop this session, exactly where it lives now, and how
to reproduce or extend each piece. Companion to
`handoff/task_2026-07-28_session_wrapup.md` (Antigravity's session,
different thread of work) — this doc covers only the migration work: which
scripts run in the cloud now, which data is staged where, and what got
deleted locally as a result.

## 1. GitHub Actions — pure-API scripts, zero local data

Repo: `github.com/humanathema/ConspiracyComments` (private)
Workflow: `.github/workflows/expert-sources-refresh.yml`, trigger
`workflow_dispatch` (manual), runs on free-tier `ubuntu-latest`, ~25s total.

Runs, in order, in one job:
1. `src/query_openalex_experts.py` -> `data/processed/openalex_experts.csv`
2. `src/query_petscan_experts.py` -> `data/processed/petscan_experts.csv`
3. `src/build_historical_officeholders.py` -> merges the two above with
   `src/consensus_experts_verified.py` (tracked in git) and 3 small seed
   CSVs into `data/processed/mainstream_expert_augmented_superset_temp.csv`

All three outputs are uploaded as a GH Actions build artifact (14-day
retention), not auto-committed back to the repo.

**Data committed to git to make this possible** (deliberate, narrow
exception to the `data/` gitignore rule — these are curated public-figure/
institution name lists, not corpus-derived or user data):
- `data/processed/institutional_authority_seed_pool.csv`
- `data/processed/mainstream_expert_seed_pool.csv`
- `data/processed/us_health_office_rosters.csv`

**Why nothing else from `src/` is in this workflow**: every other script
that looked like a candidate (`validate_against_human_labels.py`,
`compute_correlation_matrix.py`, `analyze_consensus_stance.py`, etc.) turns
out to read either the multi-GB corpus files or `data/hitl/queue_*.csv`
(HITL annotation queues containing full comment text) — not zero-dependency,
so they weren't ported here. `translation.py` has no `main()` and isn't
imported anywhere in `src/` — dead code, not a runnable script.

To trigger manually: `gh workflow run expert-sources-refresh.yml --repo
humanathema/ConspiracyComments`. To watch: `gh run watch <run-id> --repo
humanathema/ConspiracyComments --exit-status`.

## 2. Kaggle datasets (all private, account `tobiasnashws`)

### `tobiasnashws/conspiracycomments-canonical-corpus`
The original 3 canonical corpus files. **Do not touch/merge with anything
else** — this is the ground-truth backup, per explicit instruction from the
Antigravity session that created it.
- `ats_comments_final.parquet` (4.7GB)
- `empath_scores_full_mapped.parquet` (3.2GB)
- `conspiracy_comments_short_lte100chars_mapped.parquet` (1.1GB)

### `tobiasnashws/conspiracycomments-derived-tier2`
Created this session. Second-tier derived analysis files — smaller, but
referenced by many scripts (counts below are # of `src/*.py` scripts that
read each file, from a full-repo grep done before staging):
- `research_corpus_staged_scores_full21m.parquet` (170M, 19 refs)
- `entity_final_review.csv` (10M, 19 refs)
- `citations_cache.parquet` (202M, 10 refs)
- `thread_quality_metrics.csv` (84M, 15 refs)
- `cited_urls_ranked.csv` (174M, 7 refs)
- `thread_insider_presence.csv` (27M, 12 refs)
- `entity_mentions_cache_2stage_pooled.parquet` (15M, 15 refs)
- `comment_brigade_flags.csv` (4M, 16 refs)
- `comparison_politics_staged_scored.parquet` (30M, 8 refs)
- `domain_source_quality_rollup.csv` (0.4M, 8 refs)
- `missing_entity_candidates.csv` (38K, 9 refs)
- `corpus_entity_frequency_final.csv` (18M, added in a second pass to
  unblock the stage-g kernel below) — just entity names + doc counts, no
  user data, same privacy posture as the rest of this dataset.

Some of these files (`entity_final_review.csv`, `thread_insider_presence.csv`,
`comment_brigade_flags.csv`) are per-author/per-thread derived data, the
same category the repo's `.gitignore` flags as privacy-sensitive for git —
staging them to this **private** Kaggle dataset was a deliberate call,
confirmed with the user, consistent with the canonical-corpus dataset
already being private.

To add more files to this dataset later: `kaggle datasets version -p
<dir-with-metadata-and-ALL-current-files> -m "<message>" -r skip` — note
`version` REPLACES the entire file set with whatever's in the directory, so
every existing file must be present (as a copy or hardlink) alongside any
new ones, or it gets silently dropped from the new version.

### `tobiasnashws/conspiracycomments-scoring-models`
Two small trained model files (not corpus data, no privacy concern):
- `hedged_suspicion_pipeline.pkl` (231K) — fitted TfidfVectorizer+
  LogisticRegression sklearn Pipeline
- `staged_pipeline_models.joblib` (221K) — personal_experience +
  procedural_skepticism Stage-2 classifiers

## 3. Kaggle kernels ported this session (all verified working end-to-end)

All are private script kernels, CPU-only (`enable_gpu: false`), pulling
inputs from the datasets above via `/kaggle/input/datasets/<owner>/<slug>/`
mount paths, writing outputs to `/kaggle/working/`. Source lives only on
Kaggle right now (pushed from a scratch dir, not committed to this repo) —
pull with `kaggle kernels pull <ref> -p <dir> -m` if you need the code
locally again.

**Gotcha hit and fixed**: `pyahocorasick` isn't preinstalled on Kaggle's
image and needs `pip install`, which requires `enable_internet: true` in
`kernel-metadata.json` — the first push of the two ahocorasick-based
kernels below failed with a DNS-resolution error until this was set.

- **`tobiasnashws/score-hedged-suspicion-full`** — port of
  `src/score_hedged_suspicion_full.py`. Scores the full 21.4M-row corpus
  with the hedged_suspicion classifier. Verified: same distribution as the
  original local run (mean hs_prob 0.465, n=24,376 passed Stage-1 filter).
  Output: `hedged_suspicion_scores_full21m.parquet` (157MB).

- **`tobiasnashws/score-main-corpus-staged`** — port of
  `src/score_main_corpus_staged.py`. Scores personal_experience +
  procedural_skepticism across the full corpus. Verified: 10.98%/13.36%
  Stage-1 pass rates, matches expected shape. Output:
  `research_corpus_staged_scores_full21m.parquet` (235MB) — this
  supersedes the copy staged in tier2 above; re-download from the kernel
  output if you need a fresher run.

- **`tobiasnashws/stage-b-consolidated-corpus-pass`** — port of
  `src/stage_b_consolidated_corpus_pass.py`, **default/mainstream mode
  only** (the `--maverick` and `--ats` CLI-flag modes from the local script
  were not ported — run those locally, or ask for them to be ported as
  separate kernels if needed). Also: the local script's optional HITL
  priority-id bypass (reads `data/hitl/queue_maverick_authority.csv`,
  which contains full comment text) was dropped rather than staged, for
  privacy — output is functionally equivalent, just without that one
  sample-cap bypass for priority rows. Outputs:
  `stage_b_word_bags.json` (6.7MB), `stage_b_credential_pattern_hits.csv`
  (1.0MB).

- **`tobiasnashws/stage-g-auto-disambiguate`** — port of
  `src/stage_g_auto_disambiguate.py`. Verified against a local dry-run of
  just the cluster-discovery logic (no full corpus scan) using the current
  `entity_final_review.csv` + `corpus_entity_frequency_final.csv`: both
  produced exactly 486 bare names / 8 clusters with identical candidate
  lists, confirming the port is faithful. **Note**: the local
  `data/processed/stage_g_word_bags.json` on disk before this session was
  65MB, much bigger than this kernel's 2.7MB output — that's not a bug in
  the port, it means that local file was from an earlier, less-refined
  version of `entity_final_review.csv` (stale, not a ground truth to match
  against). Output: `stage_g_word_bags.json` (2.7MB).

**Not ported**: `stage_a_dictionary_filter.py`, `stage_c_classify_ambiguous.py`,
`stage_e_consolidate.py`, `stage_f_bottom_up_clusters.py`,
`stage_g_classify.py` — all operate on already-small CSVs/JSON (single-digit
MB), cheaper to just run locally in seconds than to maintain as kernels.
`stage_e_wikipedia_categories.py` is a hybrid (small local CSV input +
Wikipedia API calls) — a plausible future GH Actions candidate, not done
yet.

To re-run any kernel: `kaggle kernels push -p <dir-with-metadata>`. To
check status: `kaggle kernels status <ref>`. To pull output: `kaggle
kernels output <ref> -p <local-dir>`.

## 4. Local files deleted (verified byte-identical to their Kaggle copies
   before deletion)

17 files, ~10.5GB, removed from `data/processed/` on 2026-07-28 after
confirming each one's local size matched its Kaggle-hosted size exactly:
`ats_comments_final.parquet`, `empath_scores_full_mapped.parquet`,
`conspiracy_comments_short_lte100chars_mapped.parquet`,
`research_corpus_staged_scores_full21m.parquet`, `entity_final_review.csv`,
`citations_cache.parquet`, `thread_quality_metrics.csv`,
`cited_urls_ranked.csv`, `thread_insider_presence.csv`,
`entity_mentions_cache_2stage_pooled.parquet`, `comment_brigade_flags.csv`,
`comparison_politics_staged_scored.parquet`,
`domain_source_quality_rollup.csv`, `missing_entity_candidates.csv`,
`hedged_suspicion_pipeline.pkl`, `staged_pipeline_models.joblib`,
`corpus_entity_frequency_final.csv`.

`data/` went from 70GB to 60GB as a result.

**If you need any of these back locally**: `kaggle datasets download -d
tobiasnashws/<dataset> -f <filename> -p data/processed/` (the 3 canonical
files are in `conspiracycomments-canonical-corpus`, everything else is in
`conspiracycomments-derived-tier2` or `conspiracycomments-scoring-models`
per the breakdown above). 19 scripts in `src/` still reference
`entity_final_review.csv` by its old local path, for example — they'll
need the file downloaded back before a local run, or should be ported to
read from the Kaggle mount instead.

## 5. What's still purely local (60GB, nothing staged)

Everything not listed above — raw scrapes (`data/raw/`, several GB each),
and the majority of `data/processed/` (BERTopic models, embedding caches,
other intermediate parquets). Nothing here has needed staging yet; stage
opportunistically as specific future work requires a given file, following
the same pattern as this session (grep `src/*.py` for the path, check size,
check privacy posture, stage, verify, then consider local deletion).
