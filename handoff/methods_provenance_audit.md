# Methods Provenance Audit

**Purpose.** The current `src/*.py` pipeline (81 scripts, well-documented via
its own docstrings) is the *final form* of methods that were actually
developed piecemeal across ~22 Jupyter notebooks and ~85 git commits over
several months (June–July 2026). Those notebooks and early commits are where
the real design decisions were made — what got tried, what got rejected, why
a threshold is what it is — and most of that reasoning is not repeated
anywhere in `src/`. This document is a single reference tracing each real
analytic construct in the project back to where it originated, what was
tried before the current design, and what (if anything) was built but never
carried forward.

**How this was built.** Full read of the two `notebooks/legacy_production/`
notebooks (42 + 61 cells) and a structured pass over
`notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb` (263
cells — read every markdown cell, and every code cell flagged by its
markdown header or by cross-reference from a `src/` docstring). Markdown
outline + gap-check of `ConspiracyMaster_Refactored.ipynb` (188 cells) and
`LatestDataCheck.ipynb` (30 cells). Light skim of `notebooks/pipeline/*`,
`notebooks/05_Comparison_Exploration.ipynb`, and the three
`notebooks/scratchpads/*.ipynb` prototypes. Full `git log --oneline` (85
commits) read for chronology, with `git show`/full commit-message pulls on
~35 commits whose one-line messages indicated a real methodological decision
rather than routine polish. Cross-referenced construct names against
`src/*.py` via `grep` to confirm what is/isn't currently wired into the live
regressions. The other ~11 notebooks in `notebooks/archive/` were skipped
per the task brief (renamed snapshots of the same evolving notebook, not
independent sources) — nothing else pointed at them specifically enough to
justify opening them.

---

## 1. Per-construct provenance

### 1.1 Lexical scoring (`hedge_count` / `certainty_count` / `evidence_count` / `authority_count` / `rhetorical_count`)

- **Origin**: `notebooks/legacy_production/Conspiracy_Pipeline.ipynb`, cells
  16–20 (17 June). Five DuckDB-SQL `LIKE`/`regexp_count` dictionaries run
  over the full ~40M-row raw comment file, written to
  `lexical_scores_full.parquet`. Two versions exist in the same notebook:
  cell 16 uses `regexp_count` with word-boundary regex; cell 17/18 is a
  simplified `LIKE '%term%'` rewrite of the same five dictionaries (likely
  for DuckDB performance — `LIKE` is cheaper than compiled regex at 40M-row
  scale).
- **Design decision**: five categories chosen by hand (hedging, certainty,
  authority-appeal, evidence-appeal, rhetorical-move), each a simple
  keyword-presence sum, not weighted or normalized by length at this stage.
- **Carried forward into**: `ConspiracyMaster_Final_Architecture copy.ipynb`
  Section 2 (same five dimensions, same SQL shape) and then
  `ConspiracyMaster_Refactored.ipynb` Section 2 verbatim — this is the
  "canon" lexical layer still presented in the live master notebook.
  Superseded operationally by the 11-dimension `epistemic_lexicon.py` +
  `empath_scores_full.parquet` (Section 9.1, see §1.2) for anything
  feeding the regression, but Section 2's 5-dimension version is still the
  first analysis a reader of the notebook sees and is still validated
  there (§2.1, manual spot-check of high/zero scorers).

### 1.2 Extended 11-dimension lexicon (`epistemic_lexicon.py` / `empath_scores_full.parquet`)

- **Origin**: `ConspiracyMaster_Final_Architecture copy.ipynb` §9.1. Notebook
  markdown states explicitly: *"Replaced Empath's `analyse()` with DuckDB
  `LIKE` patterns over the externalized lexicon"* — i.e. the project first
  tried the third-party `empath` library's category-expansion tool (visible
  in cell 156: `Empath().create_category("hedged_suspicion", seed_words,
  model="reddit", size=200)`, and cells 157–159 show the raw expanded word
  lists this produced, e.g. `aawb` for the authority-appeal category,
  `hswb`/`hswb2` for hedged-suspicion) and then abandoned Empath's runtime
  `analyse()` call in favor of externalizing the (Empath-generated, then
  hand-edited) word lists into a static `epistemic_lexicon.py` module run
  as plain DuckDB `LIKE` matching — much faster at 21M-row scale and
  removes a runtime dependency. A cautionary note in the same section flags
  that a prior "Gemini cleanup" pass had once truncated
  `epistemic_lexicon.py` to `lex = {}`, i.e. this file has been silently
  emptied by an automated edit at least once before — worth remembering if
  its category coverage ever looks suspiciously thin.
- **Design decision**: category vocabulary is Empath-seeded but not
  Empath-scored; final categorization is deterministic substring matching,
  consistent with the project's later "boring/deterministic wherever
  possible" preference (formalized as guardrail #1 in
  `ANTIGRAVITY_HANDOFF.md` after the $100 LLM bill, but visible here
  earlier as a practical performance/dependency choice, not yet a cost
  concern).
- **Status**: still the production lexical layer (`empath_scores_full.parquet`
  is joined into the core regression's staged-scoring pipeline).

### 1.3 `pe_prob` (personal_experience) / `ps_prob` (procedural_skepticism)

- **Origin of the *construct***: the FACTAPPEAL dataset
  (`arxiv.org/abs/2510.10658`, `github.com/guymorlan/factappeal`) loaded
  first in `ConspiracyResearch1.ipynb` cell 27 (16 June) as a labeled corpus
  of fact-appeal/source-attribution annotation tags. `Conspiracy_Pipeline.ipynb`
  cells 27–29 explore its tag vocabulary (`Fact_No_Appeal`,
  `Fact_Appeal:Indirect_Quote`, `Appeal_Source:Named:Expert`, etc.) and cell
  29 PCA-projects sentence embeddings per tag to sanity-check separability
  before building anything on top of it (`factappeal_clusters.png`).
- **Origin of the *design pattern***: `src/staged_pipeline.py` (added
  60e9534, 13 July) — Stage 1 cheap regex filter (`PRONOUNS` +
  `LIFE_ANCHORS` for personal_experience; `SKEPT_TERMS`/`NEGATIONS` for
  procedural_skepticism) gates a Stage 2 local TF-IDF + `LogisticRegression`
  classifier trained on the HITL queues
  (`data/hitl/queue_personal_experience.csv`,
  `queue_procedural_skepticism.csv`), with probability thresholds at 0.30/0.70
  splitting Auto-Negative / Borderline / Auto-Positive. A Stage 3
  (`run_stage3_async` in the same file, calling Vertex AI Gemini on the
  Borderline band) exists in the same file but is the vestige of an earlier,
  much more LLM-heavy design (see §3.1 below) — it's present but not what
  the live pipeline actually calls at scale.
- **Design decision that changed after launch**: commit 60e9534's own
  message records that the *first* version of Stage 1/2 scoring ran only
  against a "4.78M evidential-filtered subset" and was found to exclude
  ~75% of true positives for these two constructs — fixed to run against
  the full 21.4M-row length-filtered corpus instead. This is a real,
  consequential correction (recall problem caught before it silently
  understated both constructs' prevalence), not visible anywhere except
  this commit message.
- **Status**: live, feeds the core regression (`pe_prob` +0.307 p<0.001,
  `ps_prob` +0.207 p<0.001 in r/conspiracy per `ANTIGRAVITY_HANDOFF.md`'s
  current-state section; `ps_prob` drops to p=0.053 once clustered by
  author — flagged there as worth a close read before citing as settled).

### 1.4 `hs_prob` (hedged_suspicion)

- **Already documented in `src/score_hedged_suspicion_full.py`'s own
  docstring** as originating in `ConspiracyMaster_Final_Architecture
  copy.ipynb` via a two-pass regex intersection. Confirmed by direct
  inspection: cell 242 (`"""TWO-PASS FILTER on tier2_scored_candidates.csv"""`)
  is the exact source of `SYNTACTIC_ANCHORS_HIGH_CONF` (hedging *form*) and
  `CONCEALMENT_MARKERS` (institutional-distrust *content*), reproduced
  near-verbatim in the current script. The cell's own comment records that
  an earlier, looser anchor set (`supposedly`, `just a coincidence`, `hard
  to believe`, `so-called`, `seems pretty obvious`, `could be nothing`) was
  deliberately dropped from the high-confidence list "since those showed
  high false-positive rates in prior testing" — i.e. this two-pass design
  is itself a second iteration, not the first attempt.
- **The first attempt**, visible earlier in the same notebook (cell 238,
  `clean_anchors`) and in `ConspiracyResearch1.ipynb` cell 24
  (`anchors_hedges`/`anchors_absolutist`/`anchors_evaluativist`), was a
  *single*-signal syntactic-coincidence regex with no concealment/content
  gate and no minimum-sentence-length filter — cell 238 shows this version
  being patched to add a `len(sentence.split()) >= 6` minimum before the
  two-pass redesign replaced it entirely.
- **Zero-shot embedding predecessor**: before either regex approach,
  `ConspiracyResearch1.ipynb` cell 22 and `Conspiracy_Pipeline.ipynb` cells
  1–11 built a `sentence-transformers` (`all-MiniLM-L6-v2`) cosine-similarity
  classifier against hand-written "high certainty" vs "low certainty"
  anchor sentences — the actual first attempt at *any* epistemic-stance
  signal in the project, predating even the FACTAPPEAL-informed anchors.
  `Conspiracy_Pipeline.ipynb` cell 9 batch-scores the full corpus this way
  to `epistemic_scores_full.parquet`, filtering to `confidence_score >= 0.35`.
  This zero-shot embedding approach does not appear anywhere in `src/` —
  effectively abandoned once the FACTAPPEAL-informed regex/ML staged
  pipeline outperformed it, though no commit explicitly says why it was
  dropped (inferred from absence, not stated reasoning).
- **Status**: live (`kappa=0.872`/`F1=0.933` against HITL labels per the
  script's own docstring), scaled to the full corpus in commit `42130a2`
  (2026-07-20, same day this pipeline gained clustered-SE support).

### 1.5 `has_maverick` (maverick_authority)

- **Origin**: `ConspiracyMaster_Final_Architecture copy.ipynb` cells 129–137
  — the *first* implementation was a Vertex AI Gemini structured-extraction
  call (`MaverickAuthoritySpan`/`MaverickAuthorityResult` Pydantic schema,
  `gemini-2.5-flash-lite`), not a regex or entity list. The prompt
  (reproduced in cell 129) explicitly defines the construct as "citing
  experts who specifically dissent from mainstream consensus, known
  whistleblowers, or former institutional insiders who are now defecting"
  and gives hard exclusions (pundits/alt-media personalities like Alex
  Jones/Rogan, comedians/philosophers, historical villains, insults) — this
  prompt's definition is the conceptual origin of the construct as it's
  still understood today.
- **Entity-list era**: `src/build_maverick_candidate_list.py` (13 July,
  commit `cb10466`) replaced the LLM-span approach with a Wikipedia-category
  candidate list (whistleblowers, conspiracy theorists by topic,
  pseudoarchaeology proponents, etc.) cross-referenced against corpus
  frequency via `pyahocorasick`. This produced the raw 418-entity
  `maverick_authority` bucket later found to be ~25.1% topic-noise
  ("New World Order", "Deep State" matched as if they were named entities)
  — fixed by `src/maverick_authority_verified.py` (Nash's full manual
  review of all 446 scored candidates, 20 July).
- **Two real bugs found and fixed in this construct's history, both
  documented richly in commit messages**:
  - `88da2c2`/`fa33461` (15 July): WikiLeaks/Assange/Manning/Snowden/Ellsberg
    were never bucketed at all despite a correct "weak hint" in the
    automated pipeline — fixed via `src/verified_maverick_additions.py` (17
    name-variants), confirmed to strengthen the `has_maverick` coefficient
    once merged in.
  - `20 July` (documented in `ANTIGRAVITY_HANDOFF.md`, not a single commit):
    after contamination cleanup dropped the qualifying population from
    36,116 to 21,041 comments, the *opposite* problem surfaced — 442/443
    multi-word verified entries have no bare-surname form ("Snowden" alone
    doesn't match "Edward Snowden"), and 86/90 human-labeled positive
    attribution examples had zero entity match at all. This is flagged as
    an active undercount, not yet fixed at time of writing — see
    `handoff/task_maverick_entity_disambiguation.md`.
- **Status**: contamination-fixed, recall-provisional. `+0.248` (p<0.001)
  in r/conspiracy, `+0.544` in r/politics control (stronger — not
  conspiracy-specific) per current-state numbers.

### 1.6 `has_consensus_expert` / `has_canonical_expert` (consensus_expert / canonical_expert split)

- **Origin**: `src/refine_thesis_models.py::load_entities_split()`, whose
  own docstring frames the goal as splitting mainstream-expert-bucketed
  entities into `canonical_expert` (a hardcoded list of historical/classical
  figures — Plato, Einstein, Darwin, Turing, Tesla, Feynman...) and
  `consensus_expert` (everything else in the mainstream-authority bucket).
  This split does not trace to a notebook — it's a `src/`-era design,
  built directly against an r/TopMindsOfReddit control-subreddit comparison
  baseline (also `refine_thesis_models.py`'s own stated purpose).
- **Contamination and fix**: the "everything else" `consensus_expert`
  catch-all silently absorbed genuine contrarians/skeptics (William Happer,
  Judith Curry, Peter Gøtzsche), mismatched journal names (JAMA Cardiology,
  BMJ Open), pre-1990s historical figures that belonged closer to `canon`
  (Oppenheimer, Karl Popper), non-scientific political/legal figures
  (Merkel, Dershowitz), and entities usually invoked as *villains* rather
  than trusted authorities (Yuval Noah Harari, Ralph Baric — the "canonical
  example" cited in `ANTIGRAVITY_HANDOFF.md` for why entity-bucketing needs
  human review of actual corpus framing, not just topic membership).
  `0a14e33` (15 July) fixed this at the corpus-recovery/contamination level;
  `src/consensus_experts_verified.py` replaced the catch-all with a
  hand-curated 82-name-variant/~57-person allowlist (Nash via Claude, 15
  July) — this is the file every downstream script is supposed to import,
  never `refine_thesis_models.py`'s own `consensus` output.
- **Status**: live. `has_consensus_expert` +0.528 (p<0.001) in r/conspiracy,
  n.s. in r/politics (only 41 positive cases at the time of the current
  coefficient — noted as "not detectable with this little data," not a
  true zero). `has_canonical_expert` +0.033, n.s.

### 1.7 Attribution classification / spaCy dependency-parse pipeline

- **Origin**: `Conspiracy_Pipeline.ipynb` cells 30–54 (17 June) — the
  earliest working version of the Stage 1 (keyword filter: `according to`,
  `said that`, `reported that`, quote+reporting-verb co-occurrence) → Stage
  2 (spaCy `en_core_web_sm` dependency parse + NER, hand-built
  `REPORTING_VERBS`/`NEWS_ORGS`/`OFFICIAL_ORGS`/`EXPERT_HINTS` lexicons,
  `classify_attribution_doc()`) design. This is the same shape later
  reused for `pe_prob`/`ps_prob`'s Stage-1-then-Stage-2 pattern.
- **A real bug caught and fixed in the same notebook**: cell 47–49 show the
  classifier initially missing "according to" as a reporting-verb signal
  because `REPORTING_VERBS` only listed inflected forms (`according`) not
  the lemma spaCy actually produces for "according to" constructions — a
  `# The missing link` comment marks the fix, and cell 50 reruns
  classification after correcting it.
- **Already documented as superseded** in `src/`'s own trail
  (`a194eaf`, 15 July): the FACTAPPEAL dataset's train/test split turned
  out to be a bug upstream in FactAppeal's own GitHub release (identical
  blob hashes since the original upload commit, confirmed not fixable by
  re-fetching), and `combined_maverick_detector.py` was found using a
  disconnected 24-name placeholder entity list plus a co-occurrence-only
  logic gap rather than real attribution logic — both documented as needing
  real work, not a quick patch.
- **What replaced it**: `src/attribution_confidence_scorer.py` (15 July,
  Nash's design) — fully local, deterministic, ordering/proximity/competing-
  source-aware scorer, explicitly built to fix the "Assange did X, according
  to CNN" misattribution case (CNN, not Assange, is the actual source).
  **Status: validated but not production-ready** — kappa near zero,
  precision 0.38–0.50, recall 0.03–0.07 against human labels (per
  `ANTIGRAVITY_HANDOFF.md`), blocked on a fresh disagreement-sample review,
  not wired into the core regression.

### 1.8 Link source-tier taxonomy (`epistemic_type` domain taxonomy → `link_source_tier`)

- **Origin of raw domain extraction**: `ConspiracyResearch1.ipynb` cells
  29–40 (16 June) — the very first domain-citation-frequency queries
  (regex URL/domain extraction over `lexical_scores_full.parquet`),
  including the Wikipedia-slug, YouTube-video-ID, and PubMed-ID drilldowns
  that persist essentially unchanged into `ConspiracyMaster_Refactored.ipynb`
  §4.1.1–4.1.4 today.
- **Origin of the categorical taxonomy**: `ConspiracyMaster_Final_Architecture
  copy.ipynb` §9.3 (cells 54–58) — a hand-built `taxonomy` dict
  (`mainstream_news`, `alt_media`, `academic_scientific`,
  `government_official`, `leak_whistleblower`, `legal_documents`,
  `fact_check`, `search_utility`, etc.), iteratively patched (cell 57,
  `additional_taxonomy`) to reduce the `other`/unclassified bucket from 79
  domains down to 1. **This hand-built taxonomy is still live** — it feeds
  `src/run_link_type_regressions.py` and (alongside the newer
  authority-score layer below) `src/run_link_source_tier_regressions.py`.
- **Newer, independent layer**: `data/processed/source_authority_scores.csv`
  (526 entities, built 19 July from Media Bias/Fact Check + Scimago Journal
  Rank) is a *separate* construct — a continuous/ordinal reliability score
  per outlet rather than a hand-labeled category — wired into
  `run_link_source_tier_regressions.py`'s 5-tier `link_source_tier`
  variable (`no_link` / `mainstream_reliable` / `mixed_or_low_reliability` /
  `aggregator_or_platform` / `unmatched_link`). The two taxonomies coexist:
  the hand-built categorical one for the Section 4/9.3 exploratory notebook
  analysis, the MBFC/SJR one for the actual regression's `link_source_tier`.
- **Status**: live. `has_link` −1.049 (p<0.001) in r/conspiracy (flat
  binary version); the MBFC/SJR-based tiered version is the one intended
  to replace the flat binary but per `ANTIGRAVITY_HANDOFF.md` the wiring
  task is listed as done for the crawl but the caveats (r/politics sample
  provisional at the time) still apply.

### 1.9 Entity disambiguation (Stage A–G pipeline)

- **Origin**: entirely `src/`-era work, not notebook-derived — first
  reference is `ANTIGRAVITY_HANDOFF.md`'s own staged work-program
  (referenced internally as "§10"/"§12" in script docstrings, i.e. this was
  planned and executed as a structured multi-stage pipeline from the start,
  not organically discovered in a notebook).
- **Stage A** (`stage_a_dictionary_filter.py`): flags single-token entities
  that are ordinary English words via the local macOS system dictionary
  (`/usr/share/dict/words`, 235,976 words, zero API calls) — a
  zero-cost, deterministic first pass at spaCy NER false positives
  ("Universe", "Funny", "GTFO").
- **Stage B/C** (`stage_b_consolidated_corpus_pass.py`,
  `stage_c_classify_ambiguous.py`): Yarowsky-style per-instance
  disambiguation — for an ambiguous bare name ("Bill"), pull word-bags
  around every *unambiguous* full-name instance ("Bill Clinton", "Bill
  Gates") to build per-candidate signature vocabularies, then classify bare
  instances against those profiles. Originally 7 hand-picked clusters
  (Bill/Hunter/Kennedy/Clinton/Sanders + 2 more), later extended to the
  maverick domain (9 new clusters, `ed2b6c5`/`b086959`, 20 July) after the
  recall-undercount problem in §1.5 above.
- **Stage F/G** (`stage_f_bottom_up_clusters.py`,
  `stage_g_auto_disambiguate.py`): generalizes Stage B/C from 7 manual
  clusters to as many of ~2,800 ambiguous-bare-name entities as have
  discoverable candidates, fully automated by mining the project's own
  already-collected 526,202-entity corpus frequency list for `<word>
  <Surname>` patterns — its docstring records that scraping Wikipedia's
  disambiguation-page structure directly was tried and abandoned first
  (inconsistent structure across names, confirmed on Harris/Jones/Barr
  before giving up on that approach).
- **Status**: live, actively extended as of the most recent commits
  (`ed2b6c5`, `b086959`, 20 July, uncommitted-until-reviewed per
  `ANTIGRAVITY_HANDOFF.md`).

### 1.10 Stance classification (hostile / endorsement)

- **Origin**: `src/train_stance_classifier.py`'s own docstring states it
  follows "the exact same architecture as the existing pe_prob/ps_prob
  staged classifiers" (TF-IDF + class-weight-balanced LogisticRegression),
  trained on four completed HITL stance queues. Purpose: `has_maverick`/
  `has_consensus_expert` are pooled "any mention" binaries that don't
  distinguish a hostile mention from an endorsing one, and the
  hostile/endorsement mix differs sharply and in *opposite* directions by
  subreddit/construct (r/conspiracy consensus-expert mentions are 68%
  hostile; r/politics maverick mentions are 55% hostile) — risking a
  pooled coefficient that dilutes two real, opposite effects into one
  middling number, "the same mechanism that diluted has_maverick before
  the Brand/Hawking/Ventura/Hancock/Kory entity-list fix" (the script's own
  framing).
- **Earlier prototype of the rating tool**:
  `notebooks/scratchpads/HITL.ipynb` (4 cells, 23 June) — an `ipywidgets`-
  based blind-rating loop, reading `hedged_suspicion_hitl_queue_deduped.csv`
  and `appeal_to_authority_candidates.csv` directly in-notebook. This is
  the direct predecessor of `src/hitl_rater.py`'s later standalone local
  server (which itself had two real bugs fixed in the most recent commits:
  `cb3f208` made its paths launch-directory-independent, `e74997e` fixed an
  invalid-JSON-NaN bug that broke loading any freshly-generated queue).
- **Formal analysis**: `src/analyze_consensus_stance.py` — completed
  consensus-stance queue (238/238 rated) found stance does not predict
  traction (chi²=1.75, df=3, p=0.625 across all four stance categories) —
  read: the `has_consensus_expert` +0.528 coefficient is not explained by
  "attacking wins more," naming a consensus expert functions as an
  engagement lightning rod regardless of stance.
- **Status, updated 2026-07-21 (this line was stale as of the original
  audit pass)**: classifier retrained through 5 active-learning rounds
  plus a redesign to entity-focused text windows (`src/stance_window_utils.py`),
  kappa 0.287 -> 0.345. Used in mention-only-subset regressions
  (`src/rerun_regressions_with_stance.py`,
  `src/run_stance_submodels_only.py`) — NOT folded into the pooled
  `has_maverick`/`has_consensus_expert` binaries directly (that was tried
  and abandoned, see those scripts' docstrings for the collinearity
  reason). See §5 below for a human-vs-AI agreement check on this
  classifier's underlying construct.

---

## 2. Dormant but not obsolete

Real, working analysis found in the legacy notebooks that never made it
into `src/` — specific enough to act on, not a vague "there's more stuff in
there" note.

1. **The multi-model LLM span-extraction cascade**
   (`ConspiracyMaster_Final_Architecture copy.ipynb` cells 129–136). Before
   the current cheap Stage-1-regex → Stage-2-local-ML design, the project
   built a genuinely elaborate Vertex AI Gemini pipeline: structured Pydantic
   schemas (`MaverickAuthoritySpan`, `InsiderEthosSpan`,
   `AppealToAuthorityResult`, `SourceCitationResult`,
   `ProceduralSkepticismResult`, `ReasonablenessPerformanceResult`) run
   through a **three-pass model cascade** (`gemini-2.5-flash-lite` →
   `flash` → `pro`, filenames `*_isolated_batch1/2/.jsonl`), reconciled
   across passes in cell 136's `ALL_PASSES` merge logic. This predates and
   is almost certainly the direct cause of the "$100 unplanned budget
   blowout" recorded in project memory — `notebooks/scratchpads/Untitled1.ipynb`
   cell 1 (`pre_flight_cost_estimate()`) and cell 0 (a Vertex AI
   `sft.train()` fine-tuning job against `gemini_tuning_dataset.jsonl`) are
   the same era of work, i.e. the project actually ran a full supervised
   fine-tune of a Gemini endpoint at one point (`tuned_endpoint_classified.csv`
   files referenced in cells 214–215 of the same archive notebook), not
   just prompted API calls. **Two constructs from this cascade never
   reappear anywhere in `src/`**: `insider_ethos` (community-membership/
   tenure-as-trust-heuristic — "I've been lurking on this sub for 5 years")
   and `reasonableness_performance` (name and prompt seen in cell 134's
   class definition, content not otherwise explored here). `appeal_to_authority`
   and `source_citation` *do* have trained local classifiers in
   `src/train_and_score_comparisons.py`/`src/score_main_corpus_staged.py`
   and get scored, but grep confirms neither appears in any regression
   script (`rerun_refined_regressions_v2.py`, `run_integrated_regressions.py`,
   etc.) — trained and scored, never actually analyzed downstream.
   `insider_ethos` in particular looks like a real, well-specified construct
   (the prompt is precise, with clear positive/negative examples) that
   simply never got carried into the cheaper local-classifier era. Worth
   revisiting if the thesis wants a "community-belonging as trust heuristic"
   angle — the prompt design work is already done.
   **Added 2026-07-21**: `source_citation` was subsequently validated
   (5-fold CV, kappa=0.655, AUC=0.859, `src/score_authority_appeal_full.py`)
   and given a blind human-vs-AI agreement check (kappa=0.884, n=25) — see
   §5 below. `appeal_to_authority` failed the same CV validation
   (kappa=-0.018) and was not carried into the blind check; still dormant.

2. **`master_thread_synthesis.parquet` / thread-level aggregation join**
   (`Conspiracy_Pipeline.ipynb` cells 56–58, also present as §6 "Master
   Thread Synthesis" in both archive and refactored master notebooks).
   Joins post-level submission metadata (title, domain, score) with
   comment-level lexical-score averages per thread (888,846 threads) —
   enables "does post topic/domain predict the epistemic *style* of its
   comment section" questions that comment-level regression can't answer.
   This exists as a real, already-built parquet and is presented in the
   master notebook's §6, but no `src/*.py` script consumes it — it's
   notebook-only, one level of analysis (thread-level rather than
   comment-level) that the current regression pipeline doesn't operate at.

3. **Zero-shot embedding epistemic-stance classifier**
   (`ConspiracyResearch1.ipynb` cell 22, `Conspiracy_Pipeline.ipynb` cells
   1–11, 14, `epistemic_scores_full.parquet`). The
   `sentence-transformers`/cosine-similarity-to-anchor-sentences approach
   that predates the regex-based `hs_prob` design entirely. Not wired into
   anything current, and no commit explains why it was dropped (best guess:
   the two-pass regex + trained classifier simply outperformed it, per the
   iterative anchor-tightening visible in the notebook cells, but this is
   inferred, not documented anywhere).

4. **`lambeq`/`BobcatParser` quantum-NLP exploration**
   (`ConspiracyMaster_Final_Architecture copy.ipynb` cell 259, one line:
   `parser.sentence2diagram("The government stated the claim.")`). A single
   isolated cell, no follow-through — genuinely a dead end, flagged here
   only so a future reader doesn't wonder if it's an unexplored thread. It
   isn't; it's one line and never used again.

5. **Cross-subreddit author-affinity analysis**
   (`notebooks/scratchpads/Untitled3.ipynb` cells 10–15) — computes a
   per-subreddit "affinity score" (shared users / total comments, weighted
   against global average) from `author_subreddit_footprints_async.csv`,
   the same file whose "corrected" 249-vs-2,387-overlap-author figure was
   later found to itself be wrong (recency-window crawl artifact, per
   `ANTIGRAVITY_HANDOFF.md`'s r/politics section). This notebook is a
   genuine prototype of the r/conspiracy/r/politics author-overlap logic
   that `run_core_comparison_robustness.py`'s task file is meant to
   formalize — worth a look if that task is revisited, since it shows an
   earlier, independently-built version of the same affinity computation.

6. **`LatestDataCheck.ipynb` — in-progress, not yet obsolete, not yet
   finished.** Added 20 July (untracked at session start), this is a
   working scratch notebook that consolidates *every* regression-results
   CSV the project has produced (`link_source_tier_regression_results.csv`,
   `trump_vs_classical_regression_results.csv`,
   `politics_overlap_excluded_comparison.csv`,
   `subreddit_interaction_results.csv`,
   `refined_semantic_keyness_results_v2.csv`,
   `refined_regression_results_v2.csv`,
   `topic_time_regression_results_pure_50k.csv`,
   `synthesis_regression_results_filtered.csv`, etc.) into one dict, and
   builds genuinely useful synthesis machinery that doesn't exist anywhere
   else in the project: automatic shape-detection per CSV
   (`classify_shape()`, including a `broken_broadcast_bug` self-flag for
   the known-broken `politics_overlap_excluded_comparison.csv`), a
   provisional-cohort flag for r/politics results predating the full crawl,
   forest plots across cohorts, Benjamini–Hochberg FDR correction applied
   across all regression p-values at once (`scipy.stats.false_discovery_control`
   — not used anywhere else in the pipeline, which elsewhere only applies
   Bonferroni), and paper-ready significance-starred tables
   (`paper_table()`). The notebook is unfinished (last cell is empty,
   several cells reference `master`/`recdat[0]` without full setup shown),
   but the synthesis logic itself — cross-CSV BH correction and the
   broken-file self-detection in particular — is worth either finishing in
   place or porting into `src/` as a proper script; it's the only place in
   the project that looks across *all* regression outputs at once rather
   than one script/one CSV at a time.

7. **`ConspiracyMaster_Refactored.ipynb`'s section-header gap claim is
   stale.** `handoff/task_notebook_and_repo_polish.md` (raised 17 July)
   describes the notebook's markdown headers as jumping from `## 0.` and
   `### 2.1` straight to `### 9.1`–`### 9.10`, with "sections 1, most of 2,
   and 3–8" apparently missing top-level headers. Direct inspection (20/21
   July) finds this is no longer true: the notebook currently has complete,
   matching `## 1` through `## 8` headers (Corpus Overview, Lexical Scoring,
   Attribution Classification, Source Citation Analysis, Post-Level
   Analysis, Master Thread Synthesis, Time Series, HITL Annotation), each
   with real content and (per commit `f8eeaaa`, "Add systematic
   introductory paragraphs to Sections 0, 1, 7, and 8") explanatory prose
   — these were filled in by an Antigravity polish pass (`bb1293b` through
   `0c95962`, "Polish Part 2", 17–18 July) *after* the task file was
   written but evidently before this audit. The remaining, still-accurate
   part of that task's framing is `ANTIGRAVITY_HANDOFF.md`'s own note that
   the notebook is "frozen before essentially all of" the 20-July work
   (r/politics control, corrected consensus list, stance resolution,
   topic/era stratification, source authority, dedup fix) — that gap is
   real and current, the header-gap description is not.

---

## 3. Chronology of major decision points

Dates from commit timestamps (`git log`), not necessarily when the
underlying work happened (some commits batch several days of prior
notebook work).

- **16–17 June** — Exploratory phase (`ConspiracyResearch1.ipynb`,
  `Conspiracy_Pipeline.ipynb`, not yet committed to git). Raw corpus
  ingestion via DuckDB streaming (5.48GB JSONL), first domain/URL citation
  extraction, FACTAPPEAL dataset adopted as the grounding for an
  epistemic-stance construct, zero-shot `sentence-transformers` classifier
  built and abandoned in favor of a five-dimension SQL lexicon, first
  spaCy attribution-classification pipeline built (with a real
  lemma-matching bug found and fixed mid-notebook).
- **19 June – 13 July** — The "ConspiracyMaster_*" notebook family
  (`archive/`) develops in parallel, not independently — same evolving
  notebook renamed/reorganized repeatedly (per task brief, skipped in this
  audit except the one flagged copy). `ConspiracyMaster_Final_Architecture
  copy.ipynb` (13 July) is the fullest snapshot: 11-dimension lexicon,
  BERTopic topic modeling, hand-built domain taxonomy, insider/outsider
  brigading analysis, lexical-convergence "insider score," and — critically
  — the LLM span-extraction cascade (§2.1 above) and its associated
  fine-tuning work.
- **2026-07-06 — `92f7e82` Initial commit.** First git commit of the
  project as a formal repo (canonical notebook, utils, manifest, README).
- **2026-07-06 — `bb51e61` "Milestone: Scientific robustness and technical
  debt cleanup"** and **`00d23fb` "Fix circular validation..."** — first
  documented methodological self-correction: the committed validation had
  compared model labels against human-*overridden* columns, producing a
  fraudulent F1=1.0 for dimensions with zero real human labels. Replaced
  with a genuine human-source join. Also the point where GCP
  project/endpoint IDs were hardened to require env vars (no hardcoded
  fallbacks) — an early guardrail against the cost/auth issues that recur
  later.
- **2026-07-13 — `73d38c9` "Add Stage-1 entity-mention filter, document
  active data loss incident."** Most of `data/raw/` and several core
  `data/processed/` corpora were accidentally deleted via macOS's
  storage-cleanup panel; recovered from external backup. New guardrail
  established here: never delete/move files based on OS "large files"
  cleanup suggestions without itemized per-file confirmation — this
  incident is the direct origin of `ANTIGRAVITY_HANDOFF.md` guardrail #2
  ("never edit or delete anything under `data/raw/`").
- **2026-07-13 — `60e9534` "Add staged local-model pipeline, HITL rater
  tooling."** The pivot commit: `pe_prob`/`ps_prob` moved from the
  4.78M-row evidential-filtered subset (found to exclude ~75% of true
  positives) to the full 21.4M-row corpus; `src/hitl_rater.py` and
  `src/re_rank_queue.py` added, replacing the notebook-embedded
  `ipywidgets` rating loop (`HITL.ipynb`); Vertex AI hardcoded fallback IDs
  reverted to env-var-required after "diagnosing a silent Vertex AI auth
  failure" (`classify_commons_queue.py`/`test_vertex.py`).
- **2026-07-15 — dense cluster of construct-validity fixes**, all same day:
  `4c32eae` credential-appositive pattern gap + entity-list contamination
  finding; `5f60fa2` attribution-scorer sampling bug fix;
  `7517920` rule-based `attribution_confidence_scorer.py` added, Baric/Harari
  blocklist gap fixed; `345b807` corpus-scale validation script for the
  scorer; `88da2c2`/`fa33461` WikiLeaks/Assange/Manning/Snowden/Ellsberg
  maverick-bucketing blind spot found and fixed, confirmed to strengthen
  `has_maverick`; `f07f670` Bhattacharya edge case reframed (second Trump
  admin breaks the "office = consensus" premise used to bucket some
  entities); `85583bb` pipeline validity audit, corrected for stale
  pre-recovery numbers; `0a14e33` consensus_expert contamination fixed,
  r/politics control added, posts archive recovered; `cf1d20b` final
  regression numbers confirmed with the full 82-entity consensus list;
  `a194eaf` FactAppeal val/test bug documented as upstream-unfixable, plus
  `combined_maverick_detector.py` staleness (disconnected 24-name
  placeholder list) documented. This single day is effectively when most
  of the current entity-construct validity story (§1.5, §1.6) was
  established.
- **2026-07-17–18 — notebook polish + inventory phase.** `450c33e` stages
  the full-lineage pipeline audit; `a141562` compiles
  `handoff/PROJECT_INVENTORY.md`; `bb1293b`–`0c95962` "Polish Part 2" series
  fills in the master notebook's section 1–8 headers/intro paragraphs and
  regenerates the GitHub Pages export (this is the work that makes §2.7
  above's finding — the header-gap task description is now stale).
- **2026-07-20 — the largest single day of methodological work in the
  project's history**: duplicate-ID bug traced and fixed at the source
  (`8fdef87`, root cause: `empath_scores_full.parquet` and
  `research_corpus_staged_scores_full21m.parquet` both had ~58,669
  duplicate `id`s from an upstream join-fanout, not query-time-patchable
  guards); Trump-vs-classical topic split found to have a silently-defeated
  review gate (`8d99e43`, blank `confirmed` cells passed through as
  approved) and redone with an actually-reviewed term list (`880ba60`);
  r/politics control sample scoped and expanded from 41 to ~180 positive
  consensus-expert cases (`5f60fa2`... `ffa3fda` full 140,824-row crawl
  completion); maverick Stage B/C entity-disambiguation extended to 9 new
  clusters (`b086959`, `ed2b6c5`); `hitl_rater.py` path-independence and
  invalid-JSON-NaN bugs fixed (`cb3f208`, `e74997e`); `hs_prob` scaled to
  the full corpus with clustered-SE support added to two regressions
  (`42130a2`). Nearly all of this was, per `ANTIGRAVITY_HANDOFF.md`,
  uncommitted at end of day and is reflected only in working-tree state at
  the time of this audit (`src/combined_maverick_detector.py`,
  `src/consensus_experts_verified.py`, `src/hitl_rater.py`,
  `src/maverick_authority_verified.py`, `src/rerun_refined_regressions_v2.py`,
  `src/run_integrated_regressions.py`, `src/stage_b_consolidated_corpus_pass.py`
  all show as modified-not-committed).

---

## 4. What this audit did *not* cover

Per the task brief: the ~11 other `notebooks/archive/*.ipynb` snapshots
(ConspiracyMaster_Cleaned, Organized, Architected, stripped, FINAL,
mechanical_clean, Archive, ConspiracyConcise, ConspiracyFindings,
ConspiracyMaster bare, Refactored_9_8, clean_notebook,
04_Master_Research_Sandbox) were not opened — nothing in the sources
actually read pointed at any of them specifically enough to justify
breaking the "renamed snapshot, not independent source" assumption.
`notebooks/pipeline/01_Data_Ingestion.ipynb` / `02_Network_Topology.ipynb`
/ `03_Semantic_Classification.ipynb` and
`notebooks/05_Comparison_Exploration.ipynb` were confirmed thin (2–12
cells) on file-size inspection but not individually transcribed here — if
a future audit needs them, they're small enough to read in full in one
pass. `notebooks/scratchpads/async_llm_scraper.ipynb` was not opened
(not in the task's priority list).

---

## 5. Human-vs-AI agreement checks (added 2026-07-21, after the original audit)

The two structurally weakest points identified when taking stock of the
project (2026-07-21) were (a) inter-rater reliability — no overlapping
human ratings exist anywhere in the project, labeling was pure division-
of-labor, so the IRR path has always been intra-rater self-recode only
(see `project-context` memory) — and (b) this methods/construct audit
itself. This section is a partial mitigation for (a): rather than a
second human rater (not resourced), Claude rated a sample blind and the
agreement with Nash's existing human labels was measured directly.

**Protocol**: for each construct, a sample was exported *without* the
label column and handed to Claude for independent rating; Claude's
ratings were committed to a working file before the true human labels
were revealed, so there was no opportunity for the comparison to
contaminate the rating pass itself. Working files (ephemeral, `/tmp`,
not part of the repo — may not survive a machine restart):
`/tmp/stance_blind_SAMPLE.csv`, `/tmp/stance_blind_TRUTH.csv`,
`/tmp/sc_blind_SAMPLE.csv`, `/tmp/sc_blind_TRUTH.csv`. Full writeup with
per-item disagreement notes: `handoff/task_irr_writeup_and_next_round.md`.

**Results**:

- **Stance classification** (maverick/consensus endorsement vs. hostility
  — see §1.10 above): Cohen's kappa = **0.422**, n=21 (out of a larger
  n=40 blind sample — the rest were used for other checks). "Moderate"
  agreement by conventional bands, well short of "substantial"/"almost
  perfect." The dominant disagreement pattern: Claude under-called
  "endorsement" for tonally-flat, purely factual citations of a maverick
  figure's claims (no explicit approving language, just repetition of the
  claim as fact) — Nash's human labels counted these as endorsement more
  often, on the reasoning that repeating a claim uncritically in this
  community functions as tacit endorsement even without evaluative
  language. This is a genuine construct-boundary disagreement, not
  obviously a Claude error — worth flagging in the thesis methods section
  as a documented source of measurement noise in the stance construct
  rather than resolving it silently.
- **`source_citation`**: Cohen's kappa = **0.884**, n=25. "Almost
  perfect" agreement — this construct (does the comment cite an external
  source/link/study, structurally) is comparatively unambiguous and the
  classifier's underlying human labels look reliable.

**How to read this**: this is a same-tool-different-instance check, not
a true independent second rater (Claude's ratings share whatever biases
the labeling instructions themselves have, unlike a genuinely naive human
second-rater), so it is evidence in favor of `source_citation` being
solid and stance being the shakier of the two named constructs — but it
does not fully substitute for real IRR if the thesis write-up needs to
make a formal reliability claim. `handoff/task_irr_writeup_and_next_round.md`
lays out the resourcing options for a real second-human-rater round if
Nash decides it's worth pursuing before submission.
