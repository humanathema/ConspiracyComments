# Antigravity Handoff — Epistemic Credibility in Online Conspiracy Communities

Written 2026-07-13 by Claude, at Nash's request, so a fresh Antigravity session (or
any other agent) has real, on-disk context instead of re-deriving it or guessing.
**Read this whole file before touching anything.** If a previous Antigravity
session wrote its own handoff/plan docs, they lived only in that session's chat
"artifacts" pane and are gone — this is the one that persists.

## 0. Guardrails — read first, these are not suggestions

This project has already had several real incidents this session. Each rule below
exists because of a specific one — don't relitigate them.

1. **No git push, ever, without explicit human confirmation in chat.** There is
   currently no git remote configured, on purpose. Do not add one. Do not treat
   GitHub, or any web search result, as a source of truth for this project — the
   local working directory is canonical. If you find yourself about to fetch
   something from GitHub to inform a decision here, stop and ask instead.
2. **No destructive git operations** (`reset --hard`, force push, `branch -D`,
   `checkout --` that discards changes, `clean -f`) without asking first and
   explaining exactly what will be lost.
3. **No deleting data files without explicit confirmation**, even ones that look
   orphaned. `DATA_MANIFEST.md` has provenance notes but is dated 2026-07-06 and
   is already stale relative to today's work — don't treat it as ground truth
   without checking current state.
4. **Never hardcode GCP project IDs, Vertex endpoint IDs, or credentials into
   source files.** `src/classification.py` must always require `GCP_PROJECT_ID`
   and `VERTEX_ENDPOINT_ID` as env vars (gcloud CLI auto-discovery as a fallback
   is fine; a hardcoded literal ID is not). This regressed once already today
   (a session added `"conspiracycomments-499821"` and a literal endpoint ID as
   fallback constants) and was reverted. Do not reintroduce it, even for
   convenience — the README explicitly requires these scrubbed before any public
   push, and "no remote yet" is not a reason to get sloppy.
5. **Never make live paid Vertex AI / Gemini API calls beyond a trivial ~5-row
   smoke test without first stating the row count and a $ cost estimate in chat
   and getting an explicit go-ahead.** This project has already made real paid
   calls (e.g. a 350-row commons classification run) — that's fine when it's a
   visible, deliberate decision, not something that happens silently mid-session.
6. **Never let an exception in classification code fail silently.** Any
   try/except wrapping an API call must log the actual exception type and
   message. A silent-`None`-on-any-exception bug already cost a full debugging
   session once (see §3, Blocker A history).
7. **Never overwrite an existing working module with unrelated scratch code.**
   `src/validation.py` (the model-vs-human validation script) was overwritten
   wholesale with an unrelated HITL-server smoke test earlier today. It was
   recoverable only because a `_backup.py` copy happened to survive. Put ad hoc
   diagnostic/test scripts in their own clearly-named files (e.g.
   `scratch_*.py`, `test_*.py` at repo root) — never reuse an existing module's
   filename or path for unrelated throwaway code.
8. **Never re-rank or reorder a partially-labeled HITL queue without telling
   Nash explicitly, and never treat a re-ranked/actively-sampled queue as an
   unbiased validation sample.** Active-learning re-ranking (`src/re_rank_queue.py`)
   is a legitimate tool for building training data fast, but if rating stops
   before the queue is exhausted, the resulting labeled set is biased toward
   positives and must not be used to estimate prevalence or Cohen's κ against
   the wider population. (If the whole queue does get labeled, order doesn't
   matter — see §4.)
9. **Before pointing any classifier or analysis at a "pre-filtered" corpus,
   verify the filter actually fits the construct being measured** — don't just
   assume the existing filtered dataset is the right one. Check what fraction of
   real positive examples (from HITL labels) would survive the filter before
   trusting results built on it. This is not hypothetical: see §2, corpus tiers.
10. **`data/hitl/*human_label*` and `data/hitl/*queue*.csv` — never overwrite or
    reset a `human_label` column that Nash has already filled in.** Restructuring
    a queue file (adding columns, fixing truncation) is fine; touching completed
    labels is not, without saying so explicitly first.
11. **Don't cite a κ/F1/precision number without checking `n_human` first.**
    Several rows in `data/processed/classifier_performance_summary.csv` have
    tiny sample sizes (e.g. n=14) and are not meaningful — see §4.
12. **Write real deliverables to disk in the repo, not just to a chat tool's
    ephemeral "artifacts" pane.** A previous Antigravity session generated
    `antigravity_handoff.md`, `implementation_plan.md`, `task.md`, and three
    research-report markdown files — none of them exist anywhere in this
    repository. That work is gone except as text in a chat transcript. Any
    report, plan, or finding worth keeping goes in a file under the project
    root (or `notebooks/`, `data/processed/`) that `git status` can see.
13. **Long-running background jobs**: log to a named file under `/tmp` or
    similar, tell Nash the log path and the PID, and don't leave silent
    unlabeled background processes running.
14. **Quarantine: treat yourself as untrusted-by-default on anything that
    touches already-validated pipeline files, human labels, or committed
    code.** Concretely: prefer writing *new* files over editing
    `src/classification.py`, `src/validation.py`, `src/staged_pipeline.py`,
    `src/score_main_corpus_staged.py`, or anything under `data/hitl/` in
    place. If a genuine fix to one of those is needed, say what you're
    changing and why *before* doing it, not after. Nothing here has git
    commit protection (everything is uncommitted working-tree state — see
    `git status`), so there is no safety net except this rule and Nash
    actually reading what changed. Two incidents already happened this
    session from skipping this (an entire module overwritten, hardcoded
    credentials reintroduced) — both were caught only because Nash asked
    "where are we up to" and a diff got read line by line.
15. **Calibration/recalibration must be fit on a randomly-sampled held-out
    set, never on an actively-sampled (top-candidate / re-ranked) one.** If
    Nash does more HITL by rating top-`pe_prob`/`ps_prob` candidates from the
    21M-scored file, that new batch is for *training enrichment only* — mark
    it with a `sampling_method` column (`random` vs `active`) and never
    compute prevalence, κ, or a calibration curve against the `active` rows.
    The original 100-row Gen-2 `personal_experience`/`procedural_skepticism`
    queues are the only clean random calibration sets that exist right now.

## 1. What this project is

Honours thesis: **"Epistemic Credibility in Online Conspiracy Communities."**
Research question: what markers of epistemic credibility do r/conspiracy
participants treat as legitimate, as indexed by community engagement (upvotes,
low controversiality)? Corpus: r/conspiracy (~40M raw comments) plus comparison
subreddits (r/AskReddit, r/TopMindsOfReddit, r/conspiracy_commons,
r/conspiracyNOPOL, r/topconspiracy).

Four core construct families (the actual theoretical spine of the thesis):

1. **Evidential grounding** — `source_citation` (gold-standard, κ=0.869, n=1730
   human labels — this one is solid), domain/Wikipedia/PubMed citation,
   FactAppeal sentence-level attribution classifier.
2. **Experiential authority** — `personal_experience` (experience-as-warrant,
   not mere first-person) + `maverick_authority` (self-authorization intent,
   e.g. "as a veteran...").
3. **Skeptical stance** — `hedged_suspicion` + `procedural_skepticism` (funding
   audits, demands for experiments, source-motive analysis). Note: your own
   fresh HITL notes show real construct-boundary confusion between these two —
   worth a methodology-chapter discussion, not a bug to fix away.
4. **Insider positioning** — lexical convergence / `insider_ethos`.

Cut from scope: BERTopic-as-a-separate-axis (though BERTopic itself is still
live in the master notebook §9.2 for one specific epistemic-cluster use — don't
confuse "cut as standalone topic modeling" with "BERTopic is dead everywhere"),
full network analysis, demographics as a standalone axis, `reasonableness_performance`
(κ≈0, no unanimous positives, abandoned), `appeal_to_authority` as its own
construct (turned out to be a construct-split duplicate of `source_citation`
vs `maverick_authority` intent — κ=0.323 under honest validation).

Canonical notebook: `ConspiracyMaster_Refactored.ipynb` (repo root) — has its
own research map in the header cell, treat that as authoritative for section
numbering. It runs by loading pre-computed parquet/CSV, not by recomputing from
raw data each time.

## 2. Corpus tiers — READ BEFORE SCORING ANYTHING AT SCALE

There are multiple nested corpora and picking the wrong one silently breaks an
analysis. In order of size:

| Tier | File | Rows | What it is |
|---|---|---|---|
| Raw | `data/raw/*.jsonl(.gz)` | ~40M | Everything, including deleted/removed/spam |
| Length-filtered | `data/processed/empath_scores_full.parquet` | 21.4M | Raw minus deleted/removed/too-short. Has `id`, `text`, and first-gen lexicon counts (`evidence_count`, `has_link`, `alt_authority_count`, `quantitative_count`, etc.) |
| Evidential-filtered | `data/processed/filtered_candidates.parquet` → `data/processed/research_corpus_enriched.parquet` | 4.78M | **21.4M filtered to `evidence_count>0 OR has_link=1 OR alt_authority_count>0 OR quantitative_count>0`, then joined with FactAppeal + spaCy attribution metadata.** Built specifically for the evidential-grounding / source-citation analysis (thesis §3–5). |

**Verified fact, not a guess:** this evidential filter excludes **77% of true
`personal_experience` positives and 73% of true `procedural_skepticism`
positives** (checked directly against fresh HITL labels, joined to real Reddit
IDs via `data/processed/sample_2k_id_map.csv`). `maverick_authority` fares
better (only 40% excluded) because it naturally correlates with citing
alternative authorities. **Conclusion: never run `personal_experience` or
`procedural_skepticism` scoring against `research_corpus_enriched.parquet`.**
Use `empath_scores_full.parquet` (21.4M) for those two. This is exactly what
`src/score_main_corpus_staged.py` now points at (see §5) — if that gets
reverted to the 4.78M file, that's a regression, not a fix.

If you're about to run a new construct's classifier over "the" corpus, check
this table first, and if genuinely unsure, do the same empirical check: pull
the construct's HITL-labeled positives, resolve their real Reddit IDs via
`sample_2k_id_map.csv` (or the equivalent for your candidate pool), and see
what fraction would survive whatever filter you're about to apply.

## 3. Classification pipeline history — what actually works

Three generations exist. Know which one you're looking at.

- **Cascade / ensemble era (Jun 21–23)** — multi-pass Gemini Flash/Pro pipeline,
  files named `cascade_*.csv`, `ensemble_*.csv`, `*results.csv` in
  `data/processed/`. **These were validated using a circular bug**: the old
  `src/validation.py` scored model output against `{dim}_best` columns, which
  are human-overridden where human labels exist and *model-derived everywhere
  else* — so unlabeled dimensions scored near-perfect against themselves. Fixed
  2026-07-06 (commit `bd71352`). Under honest validation, cascade-era batch-LLM
  output is weak for everything except `source_citation`. The isolated
  single-category prompt redesign within this era (fixing false positives like
  tagging bare insults as `anti_establishment_stance`) is a good technique
  worth keeping conceptually — the *scores* it produced are not trustworthy
  ground truth, only spot-hand-validated on 6-7 examples.
- **Dedicated `hedged_suspicion` ML pipeline** — separate from the cascade,
  spot-checked at κ=0.872, n=47 (`data/processed/hedged_suspicion_final_hitl_scored.csv`).
  This is the one to trust for `hedged_suspicion`, not the cascade output.
- **Staged hybrid pipeline (current, `src/staged_pipeline.py` /
  `src/score_main_corpus_staged.py`)** — 3 stages: cheap regex pre-filter →
  local TF-IDF+LogReg model trained directly on fresh HITL labels → paid
  Vertex API only for probability-borderline cases (0.30–0.70). This is the
  right architecture going forward. Models live in
  `data/processed/staged_pipeline_models.joblib`.

`src/classification.py` is the raw async Vertex AI calling layer (used
directly by the cascade era and by `classify_commons_queue.py`); keep the env-var-required
config (see §0.4).

## 4. Validation status per construct — check `n_human` before trusting anything

| construct | validated κ | n | source | status |
|---|---|---|---|---|
| `source_citation` | 0.869 | 1730 | `labeled_2k_with_scores.csv`, human_1 | Solid |
| `hedged_suspicion` (dedicated ML) | 0.872 | 47 | `hedged_suspicion_final_hitl_scored.csv` | Solid, small n |
| `hedged_suspicion` (cascade/batch) | 0.224 | 331 | `labeled_2k_with_scores.csv` | Weak, don't use as ground truth |
| `appeal_to_authority` | 0.323 | 422 | `labeled_2k_with_scores.csv` | Weak — actually a construct split with `source_citation`/`maverick_authority`, not pure noise |
| `anti_establishment_stance` | 0.472 | 14 | `labeled_2k_with_scores.csv` | **n=14, not meaningful, don't cite** |
| `personal_experience` | **κ=0.203, F1=0.441** (5-fold CV, TF-IDF+LogReg) | 94 fresh HITL (Gen-2, well-sampled) | `data/hitl/queue_personal_experience.csv` | Weak-fair. Real, better than nothing, not strong. See note below on F1 vs κ. |
| `procedural_skepticism` | **κ=0.143, F1=0.852** (5-fold CV) | 92 fresh HITL (Gen-2, well-sampled) | `data/hitl/queue_procedural_skepticism.csv` | **F1 looks great but is inflated by 73% base rate — κ says only weak real signal.** Also has genuine construct-boundary overlap with `hedged_suspicion`, noted repeatedly in Nash's own rating notes. |
| `maverick_authority` | **κ=-0.068, F1=0.429** (5-fold CV) | 190 fresh HITL (Gen-1 lexicon-hit-count sample) | `data/hitl/queue_maverick_authority.csv` | **Essentially undetectable by TF-IDF bag-of-words — κ below zero (worse than chance-corrected).** Biggest labeled set of the three and the worst model fit; this construct is probably semantic/rhetorical rather than lexical (fits Nash's own hunch about needing embeddings/NER rather than bag-of-words — see §7) |
| `insider_ethos` | none | 0 | — | Gen-1 `HITL_insider_ethos.csv` (70 rows) exists unlabeled |
| `reasonableness_performance` | ~0 | — | — | Abandoned, out of scope |

**F1 vs κ warning, don't repeat this mistake**: `procedural_skepticism`'s 85%
F1 looks like a win but its positive rate is 73%, so a model that just
predicts "positive" most of the time scores well on F1 by construction. κ
corrects for this and shows only weak-fair real agreement (0.14-0.20 range
for all three fresh constructs, comparable to the cascade-era numbers we
already discounted for being unreliable). **Always report κ alongside F1 for
these three, never F1 alone** — this project has now been burned by
prevalence-inflated metrics twice (once via the circular `_best`-column bug,
now via base-rate-inflated F1).

Numbers above were computed independently (not taken from a prior session's
self-report) via `sklearn.model_selection.StratifiedKFold(5)` +
`TfidfVectorizer(max_features=3000, ngram_range=(1,2), min_df=2)` +
`LogisticRegression(class_weight='balanced')` — reproducible, not a one-off
claim to take on faith. A previous session's self-reported numbers for these
same constructs (personal_experience F1=0.356, procedural_skepticism
F1=0.837/κ=0.283) were in the same ballpark but not identical — different
vectorizer/seed choices, not a discrepancy worth chasing.

`data/hitl/HITL_anti_establishment_stance.csv` (483 rows) and
`HITL_insider_ethos.csv` (70 rows) are Gen-1, unlabeled, available if Nash
wants to extend coverage — flag the sampling-method caveat if he does.

## 5. In-flight work as of this handoff

- **Done**: `src/score_main_corpus_staged.py` re-scored `personal_experience`
  and `procedural_skepticism` across the full 21.4M-row
  `empath_scores_full.parquet` (corrected from the 4.78M evidential-filtered
  corpus — see §2). 21,408,577 rows, 24.1 minutes, zero errors. Output:
  `data/processed/research_corpus_staged_scores_full21m.parquet`
  (`pe_prob`/`ps_prob` continuous scores + `pe_decision`/`ps_decision` +
  `pe_label`/`ps_label`). **Do not delete or overwrite
  `data/processed/research_corpus_staged_scores.parquet`** (the old
  4.78M-corpus run) — still potentially useful for `maverick_authority` later.
- **Known limitation in that output, verified not a bug**: `pe_prob` never
  exceeds 0.636 and `ps_prob` never exceeds 0.678 anywhere in 21.4M rows, so
  "Auto-Positive" (≥0.70 threshold) fired for 0% of rows — the small
  (~90-100 row) training set produces compressed, underconfident
  probabilities at full-corpus scale. Not wrong, just don't expect the raw
  probability magnitude to mean much yet — see §7 for the recalibration plan.
  Stage-1 auto-negative filtering (89%/87%) is unaffected and working as
  intended.
- **Not yet run**: Stage 3 (paid LLM verification on borderline-probability
  rows: ~2.35M `personal_experience` + ~2.86M `procedural_skepticism`,
  projected ~$58 total on Gemini 1.5 Flash). Do not trigger without stating
  the row count and cost estimate in chat first and getting a go-ahead
  (§0.5) — and re-derive the estimate from this run's actual borderline
  counts, don't reuse an older projection.
- **Span truncation fix**: done (Work Program 1, 2026-07-13) — 27 `cascade_*`/
  `ensemble_*`/`*results.csv` files rewritten with untruncated `target_text`
  mapped via `data/llm_batches/credibility_signals_batch_v2_tightened.jsonl`.
  Legitimate fix, not a regression.
- **`commons_llm_results.csv`**: 350-row live Vertex AI classification of
  r/conspiracy_commons, complete, all 7 dimensions populated. Real paid API
  run, already happened, nothing to redo.
- **`notebooks/05_Comparison_Exploration.ipynb`**: the active workspace for the
  r/conspiracy vs r/conspiracy_commons vs r/AskReddit comparison chapter. This
  is where the newly-scored data should eventually get joined and analyzed.

## 6. Things worth porting from archived notebooks (not yet done)

From an earlier legacy-notebook survey, still outstanding:

- `notebooks/archive/ConspiracyConcise.ipynb` — per-user monthly
  alignment-to-community-lexicon trajectory (individual insider-convergence
  over tenure, not just a static score). Logic is sound even though its data
  file is stale; worth re-deriving.
- `notebooks/archive/ConspiracyMaster_Organized.ipynb` §16 — monthly
  vocabulary-baseline construction (`lexical_turnover.csv`,
  "disruption events") that feeds the above.
- `ConspiracyMaster_Organized.ipynb` §14 (Agreement Bias) / §15 ("Reconsideration
  Signature") — on-topic for skeptical-stance/evidential-grounding, but nobody
  has verified the code cells actually ran to completion. Check before porting.

Confirmed dead (don't resurrect): the full cascade/ensemble/Vertex-HITL
multi-pass lineage's *output data* (technique ideas noted above are fine to
reuse), all sequential `ConspiracyMaster_*` snapshot notebooks superseded by
`_Refactored`, the archived notebooks' own separate BERTopic prototyping
sections (distinct from the BERTopic use still live in the master notebook).

## 7. Backlog / ideas raised 2026-07-13, not yet started

- **More HITL, active-learning style, on the 21.4M-scored file**: rate
  top-`pe_prob`/top-`ps_prob` candidates to enrich the training set. Fine to
  do even without completing the whole candidate pool this time (unlike the
  `maverick_authority` case, this is explicitly *not* meant to become a
  validation sample) — but tag rows with `sampling_method=active` and keep
  them out of any prevalence/κ calculation (§0.15).
- **Recalibration (Platt scaling / isotonic regression)** once more HITL data
  exists: Platt scaling fits a sigmoid mapping raw score → calibrated
  probability, works fine with small calibration sets (tens to ~100 rows);
  isotonic regression fits a non-parametric monotonic step function, more
  flexible but needs hundreds+ rows to avoid overfitting/noisy calibration
  curves. At current n (~90-100), Platt is the safer choice; revisit
  isotonic once the random-sample calibration set grows past a few hundred.
  **Must be fit on the random Gen-2 sample, never on actively-sampled rows**
  (§0.15) — fitting calibration on a positive-enriched sample would just
  bake in a new, differently-shaped bias.
- **Correlation matrix across all 7-9 constructs** (plus first-gen lexicon
  counts from `empath_scores_full.parquet`) — cheap, standard, worth doing:
  confirms/quantifies the `procedural_skepticism`/`hedged_suspicion` overlap
  Nash's HITL notes already flagged qualitatively, and is a natural
  discriminant-validity check across the whole construct set.
- **`maverick_authority` restructure**: Nash's hypothesis is a broader
  superset construct — "alternative/outsider source" — with
  `maverick_authority` (esp. a `maverick_expert` sub-type: named
  whistleblowers/experts positioned against institutional consensus) as a
  fine-grained subset. This would mirror how the `appeal_to_authority` /
  `source_citation` split got resolved earlier (see §1). Given
  `maverick_authority`'s κ=-0.068 under bag-of-words (§4), this construct
  may need semantic (embedding) or named-entity features rather than TF-IDF
  regardless of the hierarchy question.
- **Named-entity list of maverick-authority figures** (Assange, Snowden,
  named whistleblowers/independent experts etc.), seeded from the positive
  rows already in `data/hitl/queue_maverick_authority.csv` — both a
  qualitative deliverable on its own and a potential dictionary-based
  feature to supplement/replace TF-IDF for this construct.
- **Other ideas worth considering**: (a) now that `pe_prob`/`ps_prob` exist
  on the correct 21.4M corpus, a first-pass upvote/controversiality
  regression against the continuous scores (rank-based, given the
  compression issue above) could show whether there's *any* engagement
  signal before investing more in calibration; (b) the r/AskReddit
  discriminant-validity baseline is still missing (see `notebooks/05_Comparison_Exploration.ipynb`,
  noted in an earlier legacy survey) — needed before any "these constructs
  are conspiracy-specific" claim; (c) a dedicated small HITL pass explicitly
  targeting the `hedged_suspicion`/`procedural_skepticism` boundary (show
  pairs, force a forced-choice rather than independent yes/no) could turn
  Nash's qualitative observation into a measurable overlap statistic.

## 8. Practical notes

- `src/hitl_rater.py` — local rating server, `python src/hitl_rater.py`, then
  `http://localhost:8420`. Writes `human_label`/`notes` straight back to the
  CSV on every submission (survives crashes/restarts). Currently serves
  `personal_experience`, `procedural_skepticism`, `maverick_authority` tabs.
- `src/re_rank_queue.py <dim>` — active-learning re-rank of a queue's
  remaining unlabeled rows by predicted-positive-probability, using embeddings
  matched via `data/processed/labeled_2k_with_scores.parquet` (works for ~85%
  of rows in practice, not the "100%" a previous session claimed — verified
  directly). Good for building training data fast; see §0.8 for the validation
  caveat.
- Full-text ↔ Reddit-ID resolution for the 2k HITL sample: `sample_2k_id_map.csv`
  (`row_idx` → `reddit_id`), 1968/2000 resolved. The `id` column in HITL queue
  CSVs is a **row index into that sample space, not a real Reddit ID** — don't
  join it directly against `empath_scores_full.parquet` or any raw corpus file
  without going through this map first.
- Python environment: use `/Users/nash/miniforge3/bin/python3` (has
  pandas/pyarrow/duckdb) — the default `python3` on PATH in some shells is a
  bare 3.9 without pyarrow installed.
