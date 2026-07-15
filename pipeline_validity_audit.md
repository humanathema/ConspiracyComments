# Epistemic Credibility Pipeline Validity & Documentation Audit

> **CORRECTION NOTE (Claude, 2026-07-15, same day as the original audit)**:
> This audit was run before Antigravity's own read of the codebase caught
> up to the raw-posts-archive recovery earlier that day. It described
> `has_consensus_expert` as sparse/zero-traction (N=18/21,091, "quasi-
> complete separation") — that was true of a temporary, artificially
> tiny population and is **no longer true**. The corrected finding is the
> opposite: N=1,780, coefficient +0.533, p<0.001 (significant POSITIVE
> effect). Corrections are marked inline below in the Executive Summary,
> Section 7, and Section 10 — **read those before citing anything from
> this document**. Everything else in the audit (the HITL κ/F1 findings,
> the BERTopic orphan finding, the NER disambiguation validation, the
> FactAppeal attribution-logic gap, the 2025-2026 officeholder guardrail)
> was checked against file paths that do exist and appears sound; only
> the population-size-dependent numbers were stale.

This audit evaluates the 10 core pipeline components of the Honours thesis research program: **"Epistemic Credibility in Online Conspiracy Communities."** Each component is evaluated across an 8-part scientific questionnaire to establish its technical robustness, construct validity, and academic defensibility.

---

## Executive Summary of Key Findings

1. **The 2025–2026 Trump Administration Transition (NEW & CRITICAL)**: The standard sociological assumption that "official state office = institutional consensus authority" breaks down in the 2025–2026 window. The installation of historically maverick-aligned or contrarian figures (e.g., RFK Jr. as HHS Secretary, Jay Bhattacharya as CDC Director, and vaccine-skeptical ACIP appointees) directly threatens naive officeholder rosters. Adding these figures to `consensus_expert` based on title alone would launder contrarians into the consensus bucket. Roster pulls for this era **must** undergo a qualitative review.
2. **The Base-Rate Inflation Trap**: In the HITL constructs, reporting $F_1$ scores without Cohen's Kappa ($\kappa$) is a severe methodological defect. For example, `procedural_skepticism` achieved an $F_1$ of 0.852, but because its base rate in the sample was 73%, a naive model predicting "positive" most of the time scores high on $F_1$ by default. Its true chance-corrected agreement is a weak $\kappa = 0.143$.
3. **[CORRECTED 2026-07-15 by Claude — this audit was run against a stale snapshot, see note below] `has_consensus_expert` is NOT sparse and does NOT have zero traction.** The N=18/21,091 quasi-separation this audit describes was from BEFORE the raw posts archive (`data/raw/r_conspiracy_posts.jsonl`) was recovered on 2026-07-15 — the "pure" population was artificially tiny (21,091 comments) because elasticity data only covered a 17,057-post partial file. After recovery, the pure population is **1,985,823 comments**, and `has_consensus_expert` has **N=1,780 positive mentions with a coefficient of +0.533 (p<0.001, z=7.84)** — a real, significant, POSITIVE effect on traction, not zero/quasi-separated. **This audit's Section 10 and its "Next Steps" recommendation to write "consensus experts have zero traction" into the thesis are WRONG and must not be used** — see the corrected Section 10 below and `ANTIGRAVITY_HANDOFF.md`'s "READ THIS FIRST" section for the authoritative current numbers.
4. **The TopMinds Rejection**: r/TopMindsOfReddit is rejected as a neutral control corpus due to intense sarcasm, quotation of r/conspiracy threads, and temporal bias. A temporally stratified r/politics sample has been validated as a robust control.
5. **Orphaned BERTopic Branch**: Section 9.2 of the refactored master notebook selected "Topic 13" as the "epistemic credibility" cluster via embedding search. This branch is entirely unused in the final regressions. It was a side-exploration that should be formally rejected in the thesis text.

---

## Individual Component Evaluations

### 1. Empath Custom Lexicons (11 Epistemic Dimensions)

* **1. Description**: An 11-dimension custom dictionary-based text analyzer capturing specific epistemic, argumentative, and rhetorical categories (evidence, adversarial, hedge, certainty, alt_authority, intuitive, pattern, meta, demand, anecdotal, quantitative).
* **2. Location**: `utils/epistemic_lexicon.py`, applied via `src/score_comparisons.py` and joined in `src/compute_correlation_matrix.py`.
* **3. Derivation**: Raw text is normalized to lowercase with non-alphanumeric characters replaced by spaces (`clean_text`). DuckDB executes SIMD-optimized string-contains queries:
  $$\text{contains(clean\_text, ' } \text{word} \text{ ')::INT}$$
  The occurrences of all matching words within each of the 11 dictionary lists are summed to produce a category count.
* **4. Validation**: Core correlation analysis in `data/processed/construct_correlation_matrix.csv` confirms that the Pearson correlation coefficients across these 11 dimensions are mostly $<0.2$, quantitatively proving that they represent distinct lexical categories rather than weak lexical overlaps.
* **5. Limitations**: Bag-of-words exact matching is subject to standard NLP limitations:
  * No handling of negation (e.g., "no proof" increases `certainty_count`).
  * No word sense disambiguation (e.g., "state" as government vs. "state" as declare).
  * Highly sensitive to the completeness of the seed lists in `utils/epistemic_lexicon.py`.
* **6. Construct Validity**: High lexical construct validity for identifying explicit rhetorical strategy markers. However, it measures the *presence* of vocabulary, not semantic alignment or intent.
* **7. Analytical Impact**: Serves as baseline continuous covariates across comparison subreddits. It provides descriptive statistics on cross-subreddit differences.
* **8. Next Steps**: Keep as a baseline covariate. For future work, transition from string matching to sentence-level semantic embeddings to handle negation and context.

---

### 2. HITL-Refined Classifiers (Staged Hybrid Pipeline)

* **1. Description**: Five machine-learning classifiers trained on Human-in-the-Loop (HITL) ground truth to predict specific qualitative constructs: `source_citation`, `hedged_suspicion`, `personal_experience`, `procedural_skepticism`, and `maverick_authority`.
* **2. Location**: `src/staged_pipeline.py`, `src/score_main_corpus_staged.py`, `data/processed/staged_pipeline_models.joblib`, human labels in `data/hitl/`.
* **3. Derivation**: A 3-stage cascade model:
  * **Stage 1**: Binary regex pre-filter (e.g., pronouns + life anchors for `personal_experience`). Non-passing comments are auto-assigned $p = 0.0$ (`Auto-Negative`).
  * **Stage 2**: A TF-IDF Vectorizer + Logistic Regression model fit on the HITL queues scores the remaining comments. 
    * $p < 0.3 \rightarrow$ `Auto-Negative` (label 0)
    * $p \ge 0.7 \rightarrow$ `Auto-Positive` (label 1)
  * **Stage 3**: Borderline cases ($0.3 \le p < 0.7$) are sent to Gemini API via Vertex AI for high-fidelity classification (`LLM-Verified`).
* **4. Validation**:
  * `personal_experience`: $\kappa = 0.203$, $F_1 = 0.441$ ($n_{human} = 94$ Gen-2 sample).
  * `procedural_skepticism`: $\kappa = 0.143$, $F_1 = 0.852$ ($n_{human} = 92$ Gen-2 sample).
  * `maverick_authority`: $\kappa = -0.068$, $F_1 = 0.429$ ($n_{human} = 190$ Gen-1 sample).
  * `source_citation`: $\kappa = 0.869$, $F_1 = 0.896$ ($n_{human} = 1730$ LLM-batch label).
  * `hedged_suspicion`: $\kappa = 0.872$, $F_1 = 0.933$ ($n_{human} = 47$ dedicated ML pipeline).
* **5. Limitations**:
  * Severe performance collapse for `maverick_authority` under standard bag-of-words modeling ($\kappa$ below zero, worse than random chance). It cannot be modeled using local lexical vectors.
  * Base-rate inflation for `procedural_skepticism`: the high base rate (73%) in the sample inflates $F_1$ scores, hiding the weak chance-corrected agreement ($\kappa = 0.143$).
* **6. Construct Validity**: Excellent for `source_citation` and `hedged_suspicion`. Weak for `procedural_skepticism` because it has a major construct-boundary overlap with `hedged_suspicion` (the community often expresses skepticism using hedging).
* **7. Analytical Impact**: `pe_prob` and `ps_prob` serve as the central continuous independent variables in the core regressions.
* **8. Next Steps**: Always report $\kappa$ alongside $F_1$. Never evaluate `personal_experience` or `procedural_skepticism` against the 4.78M "enriched" subset—doing so excludes over 73% of true positives. They must be scored on the full 21.4M length-filtered corpus.

---

### 3. BERTopic Modeling (Topic 13 Cluster)

* **1. Description**: A top-down semantic clustering analysis designed to group comments by latent topic embeddings and identify an "epistemic credibility" cluster.
* **2. Location**: `ConspiracyMaster_Refactored.ipynb` Section 9.2.
* **3. Derivation**: Fit on a subset of comments with $\ge 50$ upvotes. "Topic 13" was selected as the "epistemic credibility" cluster via embedding similarity search.
* **4. Validation**: Selected using an automated embedding search. No human-labeled validation or cross-coder agreement was performed.
* **5. Limitations**: Highly sensitive to the upvote threshold, hyperparameter tuning, and embedding model. Highly biased toward viral posts, failing to generalize to the other 99% of comments.
* **6. Construct Validity**: Weak. Topic models capture *thematic* co-occurrences (e.g., vaccine names, election terms) rather than specific *epistemic* or rhetorical strategies.
* **7. Analytical Impact**: **Orphaned.** This branch is entirely unused in the final regressions. It was a side-exploration that never fed into the final numbers.
* **8. Next Steps**: Formally reject this component in the thesis text as an exploratory dead-end. Rely instead on the supervised lexical and staged classifiers.

---

### 4. NER & Disambiguation (Yarowsky-Style Context Windows)

* **1. Description**: A programmatic entity extraction and disambiguation pipeline designed to resolve ambiguous bare names (e.g., "Bill", "Hunter", "Clinton") to specific candidates based on surrounding context words.
* **2. Location**: `src/stage_b_consolidated_corpus_pass.py`, `src/stage_c_classify_ambiguous.py`, and `src/stage_g_auto_disambiguate.py`.
* **3. Derivation**: 
  * Unambiguous full-name occurrences (e.g., "Bill Gates", "Bill Clinton") in the 21.4M corpus are scanned to build "labeled" context word bags (15 words on each side of the match, excluding stopwords).
  * "Signature words" are calculated for each candidate in a cluster (concentration ratio $\ge 0.7$, count $\ge 3$, capped at top 40 words).
  * Bare name instances are scored against these signature words and classified if the winning candidate beats the runner-up by a ratio $\ge 1.5$. Ties are left unresolved.
* **4. Validation**: Empirically validated on ambiguous clusters. For example, ~67.3% of bare "Hunter" mentions were successfully resolved to Hunter S. Thompson, and only ~32.7% to Hunter Biden.
* **5. Limitations**: Relies on sufficient full-name occurrences to build robust context profiles.
* **6. Construct Validity**: High. Successfully prevents severe conflation (e.g., attributing Hunter S. Thompson's drug-related counterculture quotes to Hunter Biden).
* **7. Analytical Impact**: Critical. Directly populates the binary mention variables (`has_maverick`, `has_canonical_expert`, `has_consensus_expert`) in the core regressions.
* **8. Next Steps**: Expand the ambiguous dictionary to include other highly active, multi-referent names in the corpus.

---

### 5. Domain/Source Taxonomy ("Et cetera" Link Anomaly)

* **1. Description**: An empirical analysis of external URLs linked in comments, mapping them to specific domains to evaluate information-seeking behaviors.
* **2. Location**: `data/processed/domain_epistemic_performance.csv`, `data/processed/wikipedia.csv`.
* **3. Derivation**: Regex patterns parse URLs from raw comment text and extract domains and Wikipedia slugs.
* **4. Validation**: Validated via domain-level summary statistics.
* **5. Limitations**: Static link counting. Does not capture comment sentiment toward the linked domain (e.g., linking to CNN to mock it vs. linking to cite it).
* **6. Construct Validity**:
  * **The "Et cetera" Link Anomaly Resolved**: The Wikipedia article for the word "et cetera" (`/wiki/Et_cetera`) appears 276 times. This is due to users writing standard markdown lists (e.g., `[etc.](https://en.wikipedia.org/wiki/Et_cetera)`) as an inline abbreviation. This is a formatting habit rather than an intentional citation of "et cetera" as a conceptual authority.
  * **2025–2026 Officeholder Guardrail (CRITICAL)**: Standard assumptions break down in 2025–2026 because contrarian figures (RFK Jr, Jay Bhattacharya) held high office. Naive roster expansion will mistakenly classify them as "consensus experts." 
* **7. Analytical Impact**: Used to build link-type covariates and document the high traction of alternative domains like WikiLeaks (average upvotes = 14.58).
* **8. Next Steps**: Document the "et cetera" anomaly as an empirical artifact. Implement a Claude qualitative review for any officeholder rosters covering 2025–2026.

---

### 6. Insider/Outsider Signals

* **1. Description**: A continuous composite `insider_score` measuring an author's integration and alignment with the r/conspiracy community.
* **2. Location**: `src/generate_insider_score.py`, `src/compute_divergence.py`, `data/processed/author_insider_metrics.csv`.
* **3. Derivation**: Standardizes and averages up to four dimensions:
  1. `log_conspiracy_comments`: Volume of r/conspiracy comments.
  2. `conspiracy_ratio`: Ratio of conspiracy comments to total crawled Reddit comments.
  3. `z_lexical_insider_score`: Snapshot lexical convergence similarity to established community language.
  4. `z_mean_alignment_score`: Trajectory of lexical alignment over time.
  $$\text{insider\_score} = \text{mean}(Z_{\text{volume}}, Z_{\text{ratio}}, Z_{\text{snapshot}}, Z_{\text{trajectory}})$$
* **4. Validation**: Standardizing individual features before merging prevents missingness in lexical trajectories from biasing Z-scores.
* **5. Limitations**: Lexical snapshot/trajectory convergence scores require heavy historical crawls, meaning they are missing for a large subset of newer authors.
* **6. Construct Validity**: High. Successfully combines behavioral, temporal, and semantic signals into a single continuous metric.
* **7. Analytical Impact**: Critical. Used to calculate the thread-level `insider_presence_ratio` (number of comments written by authors with `insider_score` $\ge 0.0$ / total comments).
* **8. Next Steps**: Retain as a core population filtering variable.

---

### 7. Crosspost/Virality Exclusions

* **1. Description**: Filters designed to exclude viral, brigaded, or externally promoted threads to isolate the organic "pure" conspiracy community discourse.
* **2. Location**: `src/compute_thread_elasticity.py`, `data/processed/comment_brigade_flags.csv`.
* **3. Derivation**:
  * `is_high_crosspost`: `num_crossposts >= 1` (Reddit's official post metadata).
  * `brigade_upvote_flag`: comment score $\ge 100$ and total global comments = 1.
  * `brigade_downvote_flag`: comment score $\le -6$ and total global comments $\ge 21$.
* **4. Validation**: Reuses definitions established in the master notebooks (cell 76 structural cohort query).
* **5. Limitations**: `is_crossposted` only covers ~1,000 threads. Using `is_high_crosspost` provides complete coverage for all **1,831,271 posts** [CORRECTED 2026-07-15: this audit's original "17,057 posts" figure was the stale pre-recovery partial-file count — see note in Executive Summary].
* **6. Construct Validity**: High. Weeds out external brigades, ensuring that we analyze community-endorsed engagement rather than external reactions.
* **7. Analytical Impact**: Central filtering rule used to construct the "pure" conspiracy community sample.
* **8. Next Steps**: Ensure `is_high_crosspost` is used as the primary virality exclusion.

---

### 8. Attribution/Evidentiary Passes (FactAppeal Integration)

* **1. Description**: A sentence-level hybrid classifier designed to detect Maverick Authority by checking if a sentence mentions a maverick entity and appeals to alternative sources.
* **2. Location**: `src/combined_maverick_detector.py`, `src/filter_maverick_entity_mentions.py`.
* **3. Derivation**: Comments are segmented into sentences using spaCy's `sentencizer`. For sentences that match a maverick entity regex, the pre-trained `FactAppeal` classifier predicts if the sentence contains a source attribution. If yes, the comment is flagged `has_maverick = 1`.
* **4. Validation**: Leverages the 418-entity curated list from `entity_final_review.csv` plus manual additions from `verified_maverick_additions.py`.
* **5. Limitations**: **The Co-occurrence vs. Attribution Logic Gap**: Checks for co-occurrence in a sentence, not true attribution (e.g., "Assange was arrested, but according to CNN, the charges are real" will flag "Assange" as the source of the appeal).
* **6. Construct Validity**: Weak. Conflates literal entity mentions with source endorsement.
* **7. Analytical Impact**: Populates the binary `has_maverick` variable in regressions.
* **8. Next Steps**: Maintain this limitation in the audit. For future work, design a dependency-parsing or LLM-based check to verify that the FactAppeal span `<Source>` actually overlaps with the matched maverick entity.

---

### 9. External Comparison Corpora

* **1. Description**: Baseline control corpora used to contrast conspiracy discourse with general online political and casual discussions.
* **2. Location**: `src/refine_thesis_models.py`, `src/rerun_refined_regressions_v2.py`.
* **3. Derivation**:
  * r/AskReddit: rejected due to broad casual topics.
  * r/TopMindsOfReddit: rejected due to sarcasm, thread-quoting, and intense temporal bias.
  * r/politics: validated as political discussion control.
* **4. Validation**: TopMinds was empirically proven to be a meta-discussion mocking community, making its co-occurrences highly biased. Replaced with a temporally stratified r/politics sample.
* **5. Limitations**: The pipeline caps sampling at 50,000 comments, but the actual r/politics pull (20 evenly-spaced months via Arctic Shift) only produced 30,881 comments total — the cap exists but is never actually reached, all 30,881 are used.
* **6. Construct Validity**: High. r/politics is a robust political baseline with high alignment on mainstream news.
* **7. Analytical Impact**: The main comparative baseline in the regressions.
* **8. Next Steps**: Formally cite the r/politics control as the primary baseline.

---

### 10. Core Regressions (Formula & Complete Separation)

* **1. Description**: Logit models predicting comment traction (`high_traction`) using epistemic constructs and entity mentions.
* **2. Location**: `src/rerun_refined_regressions_v2.py`.
* **3. Derivation**: 
  $$\text{high\_traction} \sim \text{pe\_prob} + \text{ps\_prob} + \text{has\_link} + \text{has\_maverick} + \text{has\_canonical\_expert} + \text{has\_consensus\_expert} + \text{log\_char\_length}$$
* **4. Validation**: Tested on both pure r/conspiracy and r/politics populations.
* **5. Limitations [CORRECTED 2026-07-15]**: This audit originally described a "Quasi-Complete Separation" problem (N=18/21,091, 0% high traction) — **that was measured against a stale, artificially tiny population from before the raw posts archive was recovered**. With the recovered archive (1,831,271 posts, pure population 1,985,823 comments), `has_consensus_expert` has N=1,780 positive mentions and fits normally — no separation problem exists in the current pipeline. The automated sparsity-detection safeguard in `rerun_refined_regressions_v2.py` (drop the variable and refit if fewer than ~20 positive cases) is still real and still worth documenting as a general safeguard, but it does not currently trigger for `has_consensus_expert` in r/conspiracy. It does still trigger for r/politics (N=41 positive mentions there as of this entry — that side of the comparison remains genuinely thin).
* **6. Construct Validity**: Excellent.
* **7. Analytical Impact**: The core empirical proof of the thesis.
* **8. Next Steps [CORRECTED 2026-07-15]**: **Do NOT write "consensus experts have zero traction in pure conspiracy spaces" into the thesis — this is false.** The current, correct finding is the opposite: `has_consensus_expert` coefficient +0.533 (p<0.001) in the pure r/conspiracy population — citing a genuine consensus figure (Fauci, CDC, WHO, Fed chairs, etc.) is associated with significantly HIGHER traction, not zero. Report this alongside `has_maverick`'s +0.246 (p<0.001) — both alternative and consensus authority citation predict higher engagement in this population; see `ANTIGRAVITY_HANDOFF.md` for the full current coefficient table and the caveat that `has_maverick`'s effect replicates (and is even larger) in the r/politics control, so it isn't cleanly r/conspiracy-specific — worth checking whether the same is true for `has_consensus_expert` once the r/politics-side sample is large enough to test it (currently too thin, N=41).

---

## Thesis Recommendations & Structural Insights

### 1. The Natural Experiment of the Second Trump Administration
We recommend floating a new empirical section to Nash's supervisor. The 2025–2026 window represents a fascinating natural experiment: **"Does a conspiracy community's engagement with a maverick figure change once that figure is formally installed in institutional office?"** 
Since RFK Jr., Jay Bhattacharya, and ACIP appointees are active in this timeframe, we can track their engagement before and after their official appointments. This shifts the 2025–2026 issue from a data-cleaning nuisance to a core thesis finding.

### 2. Tabular Comparison of Control Corpora

| Corpus | Pros | Cons | Decision |
| :--- | :--- | :--- | :--- |
| **r/politics** | Robust political talk, aligned with mainstream news, no sarcasm bias. | High volume, requires temporal stratification. | **APPROVED** (Primary baseline) |
| **r/AskReddit** | Large volume, general baseline. | Lacks political/credibility focus, high casual noise. | **REJECTED** |
| **r/TopMindsOfReddit**| Easy access. | Severe temporal bias, mocking/sarcasm, quotes r/conspiracy. | **REJECTED** |
