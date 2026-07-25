# Project capability inventory (2026-07-24)

Full trace of everything substantive this project has built, not just the
last two days. Organized by theme. For each: the **current, valid** dataset
(not the superseded intermediates -- `data/processed/` has 300+ files, most
of them candidate lists, `_pre_fix` snapshots, or pipeline-stage intermediates
that fed into a final output and shouldn't be read directly), its status,
and whether it's in the corpus explorer artifact yet.

Cross-referenced against `ANTIGRAVITY_HANDOFF.md` (the authoritative
current-state doc) and the raw file listing -- where they disagree,
`ANTIGRAVITY_HANDOFF.md` wins, since it's been kept current all session.

---

## 1. Stance & entity attribution (who's cited, how they're received)

- **Current construct**: two-stage cascade stance model (hostile/endorsement/
  other), `entity_mentions_cache_2stage_pooled.parquet` (long) /
  `entity_mentions_cache_short.parquet` (short). Superseded: the original
  flat 3-class classifier (`stance_classifier_3class.joblib`), several
  earlier ensemble/cascade intermediate CSVs (`ensemble_*`, `cascade_*` --
  these are pipeline scaffolding, not final outputs).
- **Per-entity breakdown**: `per_entity_stance_breakdown_pure.csv` /
  `_unfiltered.csv` -- the whistleblower-vs-media-personality split. **In
  explorer** (Named Entities tab, deduplicated).
- **IRR (inter-rater reliability)**: `data/hitl/irr_responses/irr_summary.md`
  -- 3 human raters, kappa 0.34-0.48 depending on weighting. Done, not yet
  written up anywhere citable (still gitignored `data/` only). **Not in
  explorer.**
- **Entity taxonomy gap, found this session**: Gates/Clinton are genuinely
  absent from both `has_maverick`/`has_consensus_expert` -- correctly
  bucketed `villain`/`mainstream_figure_not_source` in the older
  `entity_final_review.csv`, never built into a usable construct. Real,
  scoped, undecided.

## 2. Citations & sources (not just `has_link` -- actual domains, quality, bylines)

- **Per-citation cache**: `citations_cache.parquet` (long, 4.67M rows) /
  `citations_cache_short.parquet` (short) -- url, domain, category,
  `credentials_taxonomy_tier`, `link_source_tier`, `mbfc_reliability_label`,
  `sjr_quartile` per citation. **Partially in explorer** (topic x credentials
  crosstab uses this) -- the raw per-citation/per-domain browsing view is
  NOT in the explorer yet.
- **URL ranking**: `cited_urls_ranked.csv` (182MB, 1.76M distinct URLs,
  ranked by distinct-author count, despammed-by-construction). **Not in
  explorer** -- too large to embed as-is, scoped for Antigravity
  (`handoff/task_domain_source_encyclopedia_export.md`).
- **Byline extraction**: `byline_extraction_results.csv` -- real-world
  article authors for ~352 of 500 attempted URLs, covering 0.74% of citation
  *events* (not URLs) so far. **Not in explorer.** Extending coverage is
  also scoped in the same Antigravity task.
- **Hand-curated top citations**: `handoff/cited_content_curation_step2.md`
  -- top ~55 URLs manually verified (real Epstein docs, Pfizer whistleblower
  story, misattributed Microsoft patent, etc.), extended further down the
  tail per `handoff/task_extend_citation_curation.md`. Narrative document,
  not tabular -- would need conversion to be embeddable.
- **Source authority (institutional)**: `source_authority_scores.csv`, 526
  entities via MBFC + Scimago Journal Rank. Wired into
  `run_link_source_tier_regressions.py`'s 5-tier taxonomy. **In explorer**
  indirectly (feeds `link_source_tier` used in regression results).
- **Credentials-problem integration**: `credentials_problem_integration_report.md`
  -- the comparative finding (anti-consensus sourcing leans more
  movement-internal/anonymous). **In explorer** (topic-level crosstab), the
  aggregate report itself is not reproduced verbatim.

## 3. Population construction (insider/outsider, brigading, cross-posting)

- **Insider presence**: `thread_insider_presence.csv` -- per-thread ratio of
  comments from established r/conspiracy commenters. Used as a *filter*
  (>=0.75 threshold) to build the "pure" population throughout, including
  today's full-corpus topic/era regression. **Not separately explorable** --
  it's baked into population definitions, not a browsable dataset of its own.
- **Brigade detection**: `comment_brigade_flags.csv` -- per-comment
  brigade-upvote/downvote flags, used as an exclusion filter in every core
  regression. Same status as insider presence -- a filter, not yet a
  standalone explorable view (e.g. "which threads got flagged and why" isn't
  surfaced anywhere).
- **Author cross-posting / subreddit footprints**:
  `author_subreddit_footprints_async.csv` (7.6M rows, author x subreddit x
  comment_count) -- used to build the r/politics author-overlap-excluded
  regression (today's rerun confirmed the July 21 finding: 12.84% overlap,
  core result unchanged either way). **Not in explorer** as its own view --
  today's "author interests" tab is topic-engagement, not
  subreddit-crossover.
- **Elasticity/thread-quality filtering**: `thread_quality_metrics.csv` --
  the elasticity-ratio tercile filter, also baked into population
  definitions rather than separately browsable.

## 4. Topics (this session's work, mostly new)

- **Full-corpus BERTopic retrain**: done today, 5.5%/13.5% outlier rates
  (long/short), superseding the old >=50-upvote-only model's 61.8% outlier
  rate. **In explorer** (Topics over time, Author interests -- both tabs).
- **Topic/era Bonferroni regression**: rebuilt today at full-corpus,
  granular-topic level (superseding the old 50k-sample/6-super-topic
  version, whose super-topic map used stale topic IDs from the retired
  97-topic model). Real update to the "no effect survives correction"
  headline -- several cells now do. **In explorer** (Regression browser).
- **Known topic-quality issues, found this session, not fixed**: BERTopic
  split vaccine discourse into 3 near-duplicate topics (correlated, not
  independent evidence for Bonferroni purposes, though the 3rd topic's
  effect direction/magnitude matches the other two, which is reassuring).
  `2_vaccine_vaccines_vaccinated_covid` genuinely blends pre-2019 and
  COVID-era content under one label (60,456 real pre-2019 comments, 4.7% of
  its volume). Neither is fixed -- both need a caveat when cited.

## 5. Attribution / evidentiary-function scoring

- **First attempt (superseded, never wired in)**:
  `src/attribution_confidence_scorer.py` (2026-07-15) -- deterministic
  scorer using spaCy dependency-parse proxies. Validated against human
  labels: kappa near zero, precision 0.38-0.50, recall 0.03-0.07. **Not
  usable, correctly never wired into the core regression.**
- **Second attempt (current, validated)**:
  `src/score_authority_appeal_full.py` (2026-07-21) -- local TF-IDF +
  LogisticRegression, no spaCy, no LLM calls. This IS `source_citation`
  (kappa=0.655, AUC=0.859), scored against the 4.78M-row enriched corpus.
  **In explorer** (feeds the topic x credentials crosstab).
- **A third, separate, FAILED construct**: `appeal_to_authority` --
  different from both of the above, kappa=-0.018 (worse than chance),
  training labels were noisy, small positive class. **Do not use, and it
  isn't in the explorer.**

## 6. Core regressions (the actual headline findings)

- `rerun_refined_regressions_v2.py` -- the core pure-r/conspiracy vs
  r/politics comparison. Current numbers already cited throughout
  `ANTIGRAVITY_HANDOFF.md`. **Partially in explorer** (r/politics
  interaction + overlap-excluded results are in the Regression browser; the
  base pure-population coefficients are not separately listed).
- `run_integrated_regressions.py` ("Grand Synthesis") -- the elasticity
  tercile x insider-presence-threshold grid, r/conspiracy-only, 16.7M-row
  unfiltered population. **Not in explorer at all.**
- Topic/era stratification -- see section 4, in explorer.
- Trump-era vs classical-conspiracy split:
  `trump_vs_classical_regression_results.csv`. **Not in explorer.**
- General epistemic-style test (author-level, not comment-level) --
  `handoff/task_general_epistemic_style_test.md`, scoped but not built.

---

## What this means for the explorer, given where budget is at

**Cheap, high-value, could add without much risk next session:**
- r/politics base regression coefficients (data already sits in files
  already embedded, just needs a table)
- IRR summary (tiny, already computed, just needs writing into the bundle)
- Author cross-subreddit footprint view (data exists, needs one aggregation
  pass roughly the size of what today's "author interests" tab already did)

**Real but needs real aggregation work first (staged for Antigravity):**
- Domain/subdomain source-quality browsing (already scoped,
  `handoff/task_domain_source_encyclopedia_export.md`)
- `run_integrated_regressions.py`'s full elasticity/insider grid --
  large output (`synthesis_regression_results_corrected.csv`, 64KB, actually
  not huge -- could probably go in a future session directly)
- Brigade/insider-presence as a *browsable* view rather than an invisible
  filter (would need a fresh aggregation, e.g. "brigade rate by month" or
  "insider-presence distribution across threads")

**Needs a human decision before it's buildable at all:**
- The Gates/Clinton "villain" entity category
- The ~5 entity name-variant merges flagged but not auto-applied (Fauci,
  Tedros, Summers, Hawking)
- Whether/how to fold the ATS (AboveTopSecret) archive data into any of this
  -- it's a live, committed sub-project with its own extraction pipeline,
  but nobody's decided whether it's in scope for the explorer at all
