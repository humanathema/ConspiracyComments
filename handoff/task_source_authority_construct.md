# Task: Build the "authoritative mainstream source" construct

**Status: not started. Mechanical enough for Antigravity to execute
directly once briefed — this is building a new data construct, not
making judgment calls about existing ones.**

## Why

The current `consensus_expert`/`maverick_authority` constructs are
person-based. Nash's point (2026-07-15): the "credentials problem" this
thesis studies isn't only about individual experts — media outlets and
academic journals can be credentialed too (a New York Times citation
functions differently from a random blog citation; a Lancet citation
differs from a fringe journal). This needs its own construct, not folded
into the person-based ones.

## Seed data (already exists, don't rebuild)

`data/processed/institutional_source_candidates.csv` — 526 candidate
entities (news outlets, journals, .gov agencies) already pulled from the
entity corpus with real doc_counts (Washington Post, NYT, WSJ, Lancet,
NEJM, BMJ, EPA, TSA, GAO, Associated Press, etc.).

## Steps

1. **News outlets**: download NELA-GT-2022 (Harvard Dataverse, DOI
   10.7910/DVN/AMCV2H) — aggregates Media Bias/Fact Check reliability
   labels (reliable/mixed/unreliable) for 361+ outlets. Extract the
   outlet-level labels. Match against `institutional_source_candidates.csv`
   by name — handle variants ("the New York Times" / "NY Times" /
   "NYTimes" are the same outlet, check the existing entity-disambiguation
   patterns in `src/stage_c_classify_ambiguous.py` for how this project
   handles name-variant clustering elsewhere).
2. **Journals**: download SJR (Scimago Journal Rank,
   scimagojr.com/journalrank.php, free CSV export, free for
   non-commercial use with citation) for journal-level percentile ranks.
   Match against the same candidate file.
3. **.gov agencies**: no external dataset needed. Candidates whose
   `wp_description` contains "federal government agency" or similar are
   already flagged in the seed file — treat as their own maximum-
   authority tier directly.
4. **Output**: `data/processed/source_authority_scores.csv` — entity,
   matched dataset (nela/sjr/gov/none), reliability_label or rank,
   source_url. This is a new file, not a modification to any existing
   one.

## Do not

- Build a new regression predictor from this or touch
  `src/rerun_refined_regressions_v2.py` — that's separate work, once
  this data exists and gets reviewed.
- Hand-build a credibility index from scratch — the whole point is using
  NELA-GT/SJR instead of reinventing that wheel.
