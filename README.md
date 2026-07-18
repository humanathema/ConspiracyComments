# Epistemic Credibility in Online Conspiracy Communities

Honours research project. **Research question:** what markers of epistemic
credibility do participants in r/conspiracy treat as legitimate, as indexed by
community engagement signals?

**Corpus:** complete r/conspiracy comment and submission archive (~40M raw
comments, ~21M after length filtering), queried in place with DuckDB.

## Current findings

Core weighted regression on the pure r/conspiracy population
(N=1,985,823 comments; see `src/rerun_refined_regressions_v2.py`):

| Predictor | Coefficient | p-value | Reading |
|---|---|---|---|
| `has_maverick` (cites a whistleblower/leaker/anti-establishment figure) | **+0.246** | <0.001 | Rewarded |
| `has_consensus_expert` (cites a mainstream institutional/scientific authority) | **+0.533** | <0.001 | Rewarded |
| `has_link` (external URL) | **−1.052** | <0.001 | Penalized |

Both entity effects also show up in a r/politics control sample — `has_maverick`
is actually *stronger* there (+0.650) — so this isn't presented as a
r/conspiracy-specific effect without qualification. A preliminary read of the
in-progress `consensus_stance` human-rating queue (152/240 rated) suggests the
`has_consensus_expert` reward may partly reflect *hostile/attacking* framing of
consensus figures rather than approving citation (~3:1 hostile:endorsing so
far) — not yet final. Full current-state detail, caveats, and the entity
allowlists behind these numbers: **`ANTIGRAVITY_HANDOFF.md`**.

## Comparison / control corpora

r/askreddit and r/TopMindsOfReddit were both tried and rejected as baseline
controls — r/TopMindsOfReddit turned out to be a mockery/meta-community that
quotes and ridicules r/conspiracy content rather than a neutral baseline (see
`handoff/PROJECT_INVENTORY.md` §2D). **r/politics** (temporally-stratified
sample, `src/build_politics_control_sample.py`) is the current valid control.
r/conspiracy_commons, r/conspiracyNOPOL, and r/topconspiracy remain
secondary/exploratory comparison corpora.

## Layout

- `ConspiracyMaster_Refactored.ipynb` — the canonical analysis notebook (research map in its header)
- `utils/` — shared helpers: epistemic lexicon, DuckDB patterns, plotting, path resolution
- `src/` — the working pipeline: entity curation (Wikipedia/Wikidata/OpenAlex/PetScan),
  Wikidata-based entity disambiguation, HITL rating tooling, the core regression engine,
  and the original LLM (Vertex AI) semantic classification pipeline — that last piece is
  one part of this directory now, not the whole of it
- `ANTIGRAVITY_HANDOFF.md` — current verified project state, guardrails, and open task index (start here for a status snapshot)
- `handoff/PROJECT_INVENTORY.md` — file-by-file audit of every script in `src/`/`utils/`, with design-lineage history (what was superseded, and why)
- `DATA_MANIFEST.md` — provenance map for every file in `data/processed/` (active / legacy / orphan; predates the 2026-07-13+ entity/regression work, being refreshed)
- `mainstream_expert_corpus_briefing.md` — methodology for scaling the consensus-expert list past hand-curated Wikipedia pages (institutional gatekeeping over fame; citation/office-based sourcing)
- `research_notes/`, `walkthrough.md` — early-stage research notes and a session walkthrough, now superseded by the corrected entity list and control group; kept for historical reference only (each carries a banner noting this — do not cite numbers from them)
- `data/` — raw JSONL archives and processed artifacts (gitignored: size + username privacy)
- `notebooks/pipeline/` — the original numbered ingestion/network/classification notebooks (`01`–`03`), still active and imported by `src/ingestion.py`, `src/network.py`, `src/classification.py`
- `notebooks/archive/`, `notebooks/legacy_production/` — full lineage of superseded notebooks and one-off refactor scripts (gitignored, kept on disk for provenance)

## Environment

Runs on the miniforge base Python (pandas, duckdb, scikit-learn, spaCy,
sentence-transformers, BERTopic, statsmodels). The `.venv/` is vestigial.

All scripts and the master notebook resolve paths relative to the repo root
(no hardcoded machine-specific paths) — run them with the repo root as the
working directory, or from anywhere inside the repo tree, and they'll find it.

## Data & ethics notes

Raw and derived data contain Reddit usernames and are not distributed with
this repository. Corpus derived from Pushshift/Arctic Shift archives; sharing
restrictions apply to redistribution of comment content.
