# Epistemic Credibility in Online Conspiracy Communities

Honours research project. **Research question:** what markers of epistemic
credibility do participants in r/conspiracy treat as legitimate, as indexed by
community engagement signals?

**Corpus:** complete r/conspiracy comment and submission archive (~40M raw
comments, ~21M after length filtering), queried in place with DuckDB, plus
comparison corpora (r/askreddit, r/TopMindsOfReddit, r/conspiracy_commons,
r/conspiracyNOPOL, r/topconspiracy).

## Layout

- `ConspiracyMaster_Refactored.ipynb` — the canonical analysis notebook (research map in its header)
- `utils/` — shared helpers: epistemic lexicon, DuckDB patterns, plotting, ML utilities
- `src/` — LLM classification pipeline (Vertex AI fine-tuned endpoints)
- `DATA_MANIFEST.md` — provenance map for every file in `data/processed/` (active / legacy / orphan)
- `data/` — raw JSONL archives and processed artifacts (gitignored: size + username privacy)
- `notebooks/archive/` — full lineage of superseded notebooks and one-off refactor scripts (gitignored, kept on disk for provenance)

## Environment

Runs on the miniforge base Python (pandas, duckdb, scikit-learn, spaCy,
sentence-transformers, BERTopic, statsmodels). The `.venv/` is vestigial.

## Data & ethics notes

Raw and derived data contain Reddit usernames and are not distributed with
this repository. Corpus derived from Pushshift/Arctic Shift archives; sharing
restrictions apply to redistribution of comment content.
