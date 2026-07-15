# Antigravity Handoff — Epistemic Credibility in Online Conspiracy Communities

Written 2026-07-13 by Claude, at Nash's request, so a fresh Antigravity session (or
any other agent) has real, on-disk context instead of re-deriving it or guessing.
**Read this whole file before touching anything.** If a previous Antigravity
session wrote its own handoff/plan docs, they lived only in that session's chat
"artifacts" pane and are gone — this is the one that persists.

## READ THIS FIRST — current state as of 2026-07-15 (later session), supersedes
## reading §13/§14/§15 in file order

The section numbering below is out of order (§15 physically appears before
§14 — both were appended live during the same working session and never
renumbered). Both are complete and internally correct; you don't need to
read them in numeric order. This section exists so you don't have to
untangle that yourself — read this, then dip into §13/§14/§15 only for the
specific detail/reasoning you need.

**The July 13 data-loss incident (§-1 below) is RESOLVED.** Nash
recovered the full raw posts archive (`data/raw/r_conspiracy_posts.jsonl`,
1,831,271 posts). `src/compute_thread_elasticity.py` was repointed at it
and rerun — `data/processed/thread_quality_metrics.csv` now covers all
1.83M posts, not the 17,057-post partial file the rest of §-1 describes.
Don't re-run any "restore the data" steps from §-1; they're done.

**`consensus_experts_verified.py` is now the authoritative
`consensus_expert` entity list** (82 name-variants / ~57 people as of this
entry) — NOT the contaminated 147-entity residual catch-all that
`refine_thesis_models.py::load_entities_split()` still produces natively.
Always use `rerun_refined_regressions_v2.py::load_entities_split_corrected()`
or import `VERIFIED_CONSENSUS_EXPERTS` directly — never
`refine_thesis_models.load_entities_split()` on its own, its `consensus`
output is known-bad and kept only for the `canon`/`mavericks` outputs
(those two are fine).

**Pipeline status, in dependency order:**
1. `src/build_politics_control_sample.py` — DONE. 30,881 comments,
   20 evenly-spaced months, `data/raw/r_politics_comments.jsonl`.
2. `src/score_comparisons.py` — DONE for politics (and the pre-existing
   askreddit/topmindsofreddit/conspiracy_commons corpora).
3. `src/compute_thread_elasticity.py` — DONE, rerun against the full
   posts archive (see above). `data/processed/thread_quality_metrics.csv`
   and `data/processed/comment_brigade_flags.csv` are current.
4. `src/consensus_experts_verified.py` — DONE, 82 name-variants, built
   from a direct wp_description scan across the WHOLE entity file (not
   bucket-filtered) plus a verified CDC/FDA/Surgeon-General office-holder
   roster pull. Deliberately excludes Jay Bhattacharya (current CDC
   Director but a lockdown-contrarian for nearly the whole corpus
   window — unresolved time-varying-status edge case, see §14/§15 body).
5. `src/rerun_refined_regressions_v2.py` — the main analysis script.
   **CONFIRMED CURRENT as of this entry** (last rerun completed
   2026-07-15 ~2:50pm, ~29 min — the context-extraction/keyness phase
   scales with both population size and entity-list size, especially
   after adding a very-high-frequency entity like WikiLeaks; this is
   expected, not a hang). This run also includes the maverick-entity fix
   below (435 mavericks, up from 418 — WikiLeaks/Assange/Manning/Snowden/
   Ellsberg/Kiriakou added, see `verified_maverick_additions.py`).
   `data/processed/refined_regression_results_v2.csv` and
   `data/processed/refined_semantic_keyness_results_v2.csv` are current
   and reflect this run. `has_maverick` coefficient moved from +0.238 to
   **+0.246** (p<0.001, z=25.7 — even more precisely estimated, not just
   different) after adding WikiLeaks et al. — a modest, expected
   strengthening, not a direction/significance change, consistent with
   these being genuine correctly-classified maverick entities rather than
   noise. `has_consensus_expert` essentially unchanged (+0.533, N=1,780)
   since that list wasn't touched this run — same stability-check logic
   as the earlier 63-vs-82 comparison. Full current r/conspiracy
   coefficient table: pe_prob +0.305 p<0.001, ps_prob +0.207 p<0.001,
   has_link -1.052 p<0.001, has_maverick +0.246 p<0.001 (N mavericks=435),
   has_canonical_expert +0.038
   p=0.457 (ns), has_consensus_expert +0.533 p<0.001. If you change
   `consensus_experts_verified.py` again, rerun this script (~5-30 min
   depending on entity-list size) before trusting those two CSVs.
6. `src/run_pure_population_analysis.py` — DONE, rerun against full
   elasticity data. `data/processed/pure_population_regression_results.csv`
   and `data/processed/insider_presence_threshold_sweep.csv` are current.

**Still open, not started or only staged (see §14/§15 for detail on
each):**
- (c) `has_maverick` is still a bare string-match, no evidentiary-function
  check. `src/combined_maverick_detector.py` exists but was never
  finished/validated against the current entity lists.
- (d) The "authoritative mainstream source" construct (news outlets via
  NELA-GT, journals via SJR, .gov agencies) — candidate entities are
  staged in `data/processed/institutional_source_candidates.csv` (526
  rows) but nothing has been joined against NELA-GT or SJR yet, and no
  new regression predictor has been built.
- The larger citation-based/academy-based scale-up described in the
  "mainstream_expert_corpus_briefing" (PetScan pulls for NAS/Royal
  Society membership, broader OpenAlex sweeps beyond the one
  proof-of-concept virology pull, full international officeholder
  rosters) — explicitly scoped in that briefing as "hand to Antigravity"
  work, not yet started. Seed pools to build from:
  `data/processed/mainstream_expert_seed_pool.csv` (77 rows, health/
  climate/aerospace/science-communication, UNVERIFIED — no source_url/
  tenure yet, needs the same treatment the CDC/FDA/SG rosters got) and
  `data/processed/institutional_authority_seed_pool.csv` (20 rows,
  intelligence/security/election domain, kept deliberately SEPARATE from
  `consensus_expert` per Nash's explicit decision — do not merge these
  two categories).
- r/politics-side `has_consensus_expert` is still thin (~41-70 positive
  cases depending on latest count) since the posts-archive fix didn't
  affect it — needs a bigger r/politics pull if that comparison matters,
  same script, just more months/comments.

## -1. ACTIVE DATA LOSS INCIDENT (2026-07-13) — read this before running anything

Nash accidentally deleted the majority of the primary raw corpus via macOS's
Storage-settings "Documents" cleanup panel (which surfaces large files
system-wide by size, not literally `~/Documents`) while trying to free disk
space. **Recovery is in progress from a Kaggle-hosted backup Nash believes he
has — not yet done as of this writing.**

**Confirmed intact (do not touch, do not "clean up"):** `data/hitl/` (all
human labels), `data/llm_batches/`, `data/processed/factappeal/`, everything
this session produced (`research_corpus_staged_scores_full21m.parquet`,
`staged_pipeline_models.joblib`, `maverick_authority_entities.csv`,
`sample_2k_id_map.csv`, etc.), `data/processed/monthly_partitions/` (the one
thing that actually was safe to delete — untouched, ironic but harmless).

**Confirmed missing, `data/raw/`** (9 files, was 14GB, now 1.9GB):
`r_conspiracy_comments.jsonl.gz`, `r_conspiracy_comments2.jsonl.gz`,
`r_conspiracy_comments5.jsonl.gz`, `r_conspiracy_comments6.jsonl.gz`,
`r_conspiracy_comments7.jsonl.gz`, `r_conspiracy_comments9.jsonl.gz`,
`r_conspiracy_posts.jsonl.gz`, `r_topmindsofreddit_comments.jsonl`,
`r_topmindsofreddit_posts.jsonl`. This is most of the primary r/conspiracy
comment archive and the biggest comparison-corpus file — not incidental.

**Confirmed missing, `data/processed/`**: `empath_scores_full.parquet`
(2.9GB, the 21.4M-row length-filtered corpus — see §2, this was the corpus
tier every construct-scoring task in this handoff assumes exists),
`lexical_scores_full.parquet` (2.9GB), `filtered_candidates.parquet`
(840MB), `research_corpus_enriched.parquet` (1.6GB, the 4.78M evidential
subset). All four are downstream of the missing raw files, **so none of them
can be regenerated locally until the raw archives are restored** — this
isn't a quick DuckDB re-run, it needs the source data back first.

**What this blocks**: any task in §9 that needs `empath_scores_full.parquet`
or the raw comment archives — most importantly the maverick-entity Stage-1
filter (`src/filter_maverick_entity_mentions.py`, started 2026-07-13 ~17:4x,
**failed with `FileNotFoundError` mid-run, not actually completed** — rerun
it once `empath_scores_full.parquet` exists again, don't trust
`data/processed/maverick_entity_mention_candidates.parquet` if that file
exists at all, it wasn't produced). Anything working only from `data/hitl/`,
`data/llm_batches/`, or this session's own outputs (§4, §8) is unaffected
and safe to continue.

**New guardrail from this incident**: never delete or move files to free
disk space based on macOS's (or any OS's) automatic "large files"/cleanup
suggestions inside this project directory, or suggest Nash do so, without
listing the exact files and getting itemized confirmation per file. A
system-level "these look unused" heuristic has no idea which multi-GB file
is a load-bearing pipeline input.

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

## 8. NER seed list for maverick_authority (2026-07-13)

`src/extract_maverick_entities.py` runs spaCy NER over
`data/hitl/queue_maverick_authority.csv`, split by human label, and ranks
entities by lift (how much more common in positive vs negative comments,
Laplace-smoothed). Output: `data/processed/maverick_authority_entities.csv`
(227 candidates, 26 with ≥2 positive mentions).

**Important negative result, don't skip past this**: at n=90 positive/100
negative, counts per entity are tiny (2-3 mentions typical) so this is noisy
— but big alternative-authority names like `Assange` (lift 0.64) and `NSA`
(lift 0.54) are actually *more* common in negative comments, not less.
`WikiLeaks` (3.22) and `Julian` (2.17) do show real lift. **Conclusion: mere
entity presence is not the maverick_authority signal — it's the rhetorical
framing around the mention** (self-authorizing "he was right and they lied"
vs. just being part of ordinary discussion). This was run on whole-comment
text because the current queue has no span data; if `best_spans`-equivalent
data becomes available for this construct (the original `cascade_maverick_authority.csv`
has a `final_spans` column, but joining it to the queue's row-index `id`
would need the same real-Reddit-ID resolution as `sample_2k_id_map.csv` —
not yet done for this candidate pool), re-running entity extraction
localized to the triggering span rather than the whole comment would be a
much sharper signal.

## 8b. FactAppeal status (checked 2026-07-13) — better than remembered, but has a real bug

`data/processed/factappeal/` is a genuine external academic dataset: "FactAppeal:
Identifying Epistemic Factual Appeals in News Media," 3,226 hand-annotated
news sentences, CC BY 4.0 (see its own `README.md` and `.git` history — it
was cloned in, not built here). Annotation scheme has span-level
`<Fact_Appeal:Direct_Quote/Indirect_Quote>` and `<Source:Named/Unnamed:Type>`
tags, where Type ∈ {Official, Expert, Witness, Active_Participant,
Direct_Evidence, Expert_Document}. **This Source-Type taxonomy is close to
exactly what's needed for a maverick-expert vs. ordinary-expert distinction
— check it before designing a new taxonomy from scratch.**

Two classifiers were trained on it (master notebook cell 12-13):
- `factappeal_classifier.pkl` + `factappeal_vectorizer.pkl` — binary
  (has-epistemic-appeal vs not), TF-IDF+LogReg. Reported: 83% accuracy,
  F1=0.73 on the positive class, n=483.
- `factappeal_multiclass_classifier.pkl` + `factappeal_multiclass_vectorizer.pkl`
  — exists on disk, **never referenced anywhere in `ConspiracyMaster_Refactored.ipynb`**
  (grepped, zero hits). Unknown provenance/performance — check what it was
  trained on (likely the Source-Type multiclass labels) before building
  a new maverick-expert classifier; it may already do most of this.

**Bug found and verified 2026-07-13, root-caused 2026-07-15**:
`data/processed/factappeal/val.csv` and `test.csv` are **byte-identical
files** (confirmed via `diff`, both 496 lines). **This is an upstream bug
in the source dataset, not a local error** — verified 2026-07-15 by
checking git blob MD5 hashes back to the original "Add files via upload"
commit (`332dcf4`) on `github.com/guymorlan/factappeal`: both files had
the identical hash (`d5c239d4...`) from the moment the author uploaded
them, and the local clone is fully up to date with `origin/main` (nothing
new to fetch). The README claims a proper 70/15/15 train/val/test split,
but the actual public release only contains two genuinely distinct files
(train + one held-out set uploaded twice under different names). **There
is no "re-download the real test set" fix available** — the correct held-
out test set was apparently never published. So the notebook's "Final
Test Set Performance" (cell 13) is not an independent confirmation — it's
the same held-out split scored twice under different names. The 83%/
F1=0.73 numbers are real (genuine held-out validation once) but not
test-confirmed the way the notebook output implies, and can't be made so
without either contacting the paper's author for the missing split or
manually carving a fresh held-out set out of `train.csv` (accepting a
smaller effective training set). Simplest defensible option: disclose
the single-split limitation explicitly in the write-up rather than try to
manufacture a fix. Also still unmeasured: this model is trained on formal
news-media sentences and applied to informal Reddit comments (cell 16) —
that domain shift has never been checked with a Reddit-specific held-out
sample.

**`src/combined_maverick_detector.py` is stale and disconnected from all
entity-curation work done since it was written (checked 2026-07-15)**:
its `CURATED_MAVERICK_ENTITIES` is a hardcoded 24-name placeholder list
(Assange, Snowden, Manning, Ellsberg, Hersh, plus raw agency acronyms
CIA/FBI/NSA/DEA/DIA/CSPAN) that predates and has no connection to the
properly-curated 418-entity `maverick_authority` bucket in
`entity_final_review.csv` this session (and `consensus_experts_verified.py`
for the 82-name-variant consensus side) actually rely on. It was written
as an explicit placeholder "pending curation of entity list" and never
updated once that curation happened. **It also has a logic gap beyond the
stale list**: it flags a comment positive if an entity match and *some*
FactAppeal-detected epistemic appeal both occur in the same sentence — it
never checks that the appeal is actually attributed to that entity as its
source. A sentence can contain both independently without the entity
being what's cited. Before this script is trustworthy: (1) swap in the
real entity list, (2) tighten the match to require the FactAppeal
Source-span to actually overlap with the matched entity (the annotation
schema already has `<Source:Named:Type>` spans for exactly this — see
above — currently unused for this purpose), (3) re-run against
`queue_maverick_authority.csv` and report κ before trusting it at scale.

**Nash's proposed next step (2026-07-13), write-up for whoever picks this
up**: combine (a) the NER entity list from §8, grown and manually
curated/split into maverick-expert vs. ordinary-figure categories, with (b)
FactAppeal-style appeal detection, to specifically catch "appeals to
maverick/alternative-authority figures" as a distinguishable sub-pattern of
epistemic appeal — rather than trying to detect `maverick_authority` from
bag-of-words alone (which failed, κ=-0.068, see §4). Concrete steps, roughly
in order:
1. Check what `factappeal_multiclass_classifier.pkl` actually is/does before
   building anything new (see above).
2. Fix or work around the val/test duplication — either find the real held-out
   test split from the original FactAppeal dataset release, or explicitly
   note in any write-up that only a single validation split was used.
3. Grow the entity list from `data/processed/maverick_authority_entities.csv`
   (§8) — more HITL data will help since current lift estimates are noisy at
   n=90/100 — and have Nash manually tag entities as maverick-figure vs.
   generic-political-figure (§10, human judgment call).
4. Detect comments where a FactAppeal-style appeal's Source overlaps with the
   curated maverick-entity list — this is the actual maverick-authority
   detector, not raw NER presence and not bag-of-words alone.
5. Validate against the existing `queue_maverick_authority.csv` human labels
   before trusting it (same rigor as everything else — n_human, κ, not just
   accuracy).

**Update 2026-07-13, Nash's revised plan**: do this in two stages rather than
building the combined detector directly — (1) a lightweight, cheap raw-NER-mention
filter first, to narrow the corpus, (2) the more sophisticated FactAppeal-based
pass on top of that narrowed set later. `src/filter_maverick_entity_mentions.py`
implements stage 1: plain substring match against the entity list from §8,
thresholded by `--min-mentions`/`--min-lift` (defaults 2 / 1.0). Includes a
`--check-only` flag that sanity-checks the filter against
`queue_maverick_authority.csv` before running it at corpus scale — **do this
sanity check any time the entity list or thresholds change, don't just trust
a new threshold blindly.**

Sanity-check results at different thresholds (n=197 HITL-labeled):

| min-lift | entities kept | precision | recall | κ | flagged |
|---|---|---|---|---|---|
| 1.0 (default) | 22 | 0.510 | 0.578 | 0.109 | 102/197 |
| 1.5 | 17 | 0.562 | 0.500 | 0.174 | 80/197 |
| 2.0 | 12 | 0.586 | 0.456 | 0.188 | 70/197 |
| 2.5 | 10 | 0.603 | 0.422 | 0.193 | 63/197 |

**For a Stage-1 filter, bias toward recall, not precision** — the job is to
not throw away true positives before the expensive stage 2 pass cleans up
false positives, so `min-lift=1.0` (the default) is the right choice for
stage 1 despite its lower κ. Note even at the loosest threshold, recall is
only 58% — this entity list (built from n=90 positive HITL examples, §8) is
still small; expect meaningfully better recall once more HITL data goes into
`src/extract_maverick_entities.py`.

Full-corpus run status: started 2026-07-13 ~17:4x, background, log at
`/tmp/maverick_entity_filter.log`, output
`data/processed/maverick_entity_mention_candidates.parquet` (just a list of
matched `id`s against `empath_scores_full.parquet`, the 21.4M-row corpus —
see §2 for why that corpus, not the 4.78M evidential-filtered one). **If this
process is not still running / the output file doesn't exist when you pick
this up, re-run:** `python src/filter_maverick_entity_mentions.py` (defaults
are already sane, takes on the order of 20-30 min given the staged pipeline's
comparable Stage-1 regex pass took ~24 min over the same corpus).

## 9. Antigravity task queue — scoped, gated, safe to hand over

Each of these is mechanical enough to delegate, **provided the relevant
guardrail from §0 is followed** (noted per task). Report back with what was
found before treating any result as final — none of these are "run and
forget."

- **Correlation matrix across all constructs** (source_citation, hedged_suspicion,
  personal_experience, procedural_skepticism, maverick_authority, plus
  first-gen lexicon counts from `empath_scores_full.parquet`). Read-only
  analysis over existing scored data, writes a new notebook cell or standalone
  script + output file. No pipeline files touched. Low risk.
- **Rank-based upvote/controversiality regression** on `pe_prob`/`ps_prob`
  from `research_corpus_staged_scores_full21m.parquet`, given the probability
  compression noted in §5 (rank/quantile-based, not raw magnitude). Read-only,
  low risk.
- **Platt-scaling recalibration script** for the staged pipeline models — must
  be fit only on the random Gen-2 HITL sample (§0.15), output as a new
  diagnostic file/plot, not silently swapped into `staged_pipeline_models.joblib`
  without Nash reviewing the before/after calibration curve.
- **r/AskReddit discriminant-validity baseline**: run the staged pipeline on
  the r/AskReddit corpus. Must follow §0.9 (verify whatever AskReddit file
  gets used isn't pre-filtered in a construct-incompatible way, same check
  done for `research_corpus_enriched.parquet` in §2) and §0.5 if it touches
  paid API calls at any real scale.
- **Prep (not execute) more HITL queues**: a top-`pe_prob`/`ps_prob`
  active-enrichment queue, and/or a forced-choice `hedged_suspicion` vs
  `procedural_skepticism` boundary queue. Antigravity can build the queue
  file; only Nash does the actual rating.
- **Span-localized re-run of `src/extract_maverick_entities.py`**, if/when
  `cascade_maverick_authority.csv`'s `final_spans` gets properly joined to
  the queue via a real-ID resolution (mirroring `sample_2k_id_map.csv`).
- **FactAppeal reconnaissance** (§8b, steps 1-2 only): inspect
  `factappeal_multiclass_classifier.pkl`/`factappeal_multiclass_vectorizer.pkl`
  to determine what it was trained on and how it performs — report back,
  don't wire it into the pipeline unasked. Also check whether the original
  public FactAppeal dataset release has a real (non-duplicate) test split
  available, to fix the val/test bug. Read-only investigation, low risk.
  **Steps 3-5 of §8b (curating the entity list, building the combined
  detector) are NOT mechanical — step 3 is reserved (§10), steps 4-5 should
  wait until step 3 is done by Nash.**

## 10. Reserved — do this with Nash/Claude, not Antigravity

These require scientific judgment calls this project has already been burned
by delegating carelessly (construct definitions, sampling-method trust
calls, what a metric is allowed to mean). Antigravity can gather inputs for
these but should not decide them unilaterally:

- **The `maverick_authority` / "alternative-outsider-source" hierarchy
  decision** (§7) — whether to formally split into a superset/subset
  structure, and where the line falls, is a construct-definition call for
  the thesis, not a mechanical refactor.
- **Interpreting the entity-lift list** (§8) — deciding which entities are
  genuine maverick-authority markers vs. incidental political figures needs
  a human reading actual example comments, not just trusting the ranking.
- **Any go/no-go on using a recalibrated probability, or a newly-labeled
  construct, in the actual thesis write-up.**
- **All HITL rating itself** — always Nash, never automated, never Antigravity
  guessing labels.
- **Whether a completed HITL batch is a "validation sample" or "training
  enrichment"** — this determines what statistics are allowed to be computed
  from it (§0.15) and has been the source of two separate mistakes already
  this project (circular `_best`-column validation, prevalence-inflated F1).

## 11. Practical notes

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
  bare 3.9 without pyarrow installed. **Separately**, `python3.12` (pyenv,
  `/Users/nash/.pyenv/versions/3.12.0/bin/python3.12`) is what the entity-
  curation scripts in §12 actually use — it has `spacy`, `pyahocorasick`,
  `requests` installed (miniforge3's base env does NOT have spacy/
  pyahocorasick). Check which packages a script needs before assuming either
  interpreter has them; `pip install <pkg>` into python3.12 as needed, it's
  a normal user-writable pyenv version.
- **CSV quoting gotcha**: any script that writes raw corpus text/comment
  excerpts into a CSV column (e.g. `example_1`, context windows) can produce
  files that crash pandas' default C parser with `ParserError: ... Buffer
  overflow` on read-back, even though the file was written correctly by
  `to_csv`. Cause: a single row with a stray/unbalanced quote character in
  the raw Reddit text can desync the C parser's quote-tracking for a large
  chunk of subsequent rows. Fix: read with `engine="python", on_bad_lines=
  "skip"` (slower, but robust) — this recovers effectively all rows in
  practice (e.g. 610,558/~610,600 on one such file). Better yet, avoid
  writing raw free-text into CSVs you'll need to read back reliably at all
  — several files in §12 dropped their example-text columns for exactly
  this reason after multiple parse failures.

## 12. Maverick-authority entity list: bottom-up mining + disambiguation
   pipeline (started 2026-07-13/14, in progress)

Context: §8/§8b/§10 covers the *top-down* seed list (Wikipedia lists of
whistleblowers/conspiracy-theorists/etc., cross-referenced against corpus
frequency — see `src/build_maverick_candidate_list.py`,
`data/processed/maverick_candidate_entities_scored.csv`, ~446 candidates).
This section is the complementary *bottom-up* pass: mine every named entity
that actually appears in the corpus, independent of any presupposed list,
then narrow ~600K raw finds down to something reviewable. Two things
converge here: candidate discovery (catching real maverick-authority figures
the top-down list missed — confirmed hits so far include Whitney Webb, Art
Bell, Luc Montagnier, Michael Yeadon, John Kiriakou, Elon Musk) and general
entity-role tagging (mainstream_source / alternative_source /
mainstream_expert_authority / maverick_authority / villain / hero /
mainstream_figure_not_source / other) for the broader corpus.

**Hard constraint: no LLM API calls without explicit sign-off.** Nash hit an
unplanned $100 bill from LLM API usage on 2026-07-13. Every step in this
pipeline is deliberately free/deterministic (spaCy NER locally, Wikipedia/
Wikidata's free public APIs, local wordlists, regex, corpus co-occurrence
counting) — do not introduce a paid API call (OpenAI/Anthropic/Gemini/etc.)
into this pipeline without asking first and stating expected call volume.

### Pipeline stages and current status

1. **NER mining** (`src/mine_corpus_entity_frequency.py`) — spaCy NER over
   ~2.65M rows (all 1.6M rows where `alt_authority_count>0` or
   `evidence_count>0`, exhaustively, plus a random ~1M-row sample of the
   rest). Found 683,635 raw (entity,label) pairs. **Note on the sampling
   asymmetry**: the "flagged" stratum was scanned exhaustively, not
   sampled — so for any entity whose mentions mostly occur in
   evidence/authority-appeal-flagged comments (i.e. exactly the citation
   behavior `maverick_authority` cares about), its observed count is close
   to the TRUE full-21.4M-corpus count, not a scaled-down estimate. Done.

2. **Cleanup passes** — dropped NORP/chat-filler noise (→610,558), then
   stripped 84,259 URL/markdown/bot-artifact rows (found via this: Reddit's
   AmputatorBot auto-reply signature was being NER-mistagged as an entity —
   worth knowing bot-generated boilerplate is present in the corpus at all,
   possibly relevant beyond just this entity task) and merged ~17 obvious
   alias clusters (Trump/Trumps/Donald Trump → one row). Result:
   `data/processed/corpus_entity_frequency_final.csv`, 526,202 entities,
   with a best-effort (not exhaustive) `already_triaged` flag on ~70 already-
   confirmed mainstream/villain names. Done.

3. **Frequency floor** `doc_count>=20` on the untriaged set →
   `data/processed/entity_wikidata_tier1.csv` input list, 15,923 entities.
   This is the big lever (526K→16K); see the 2026-07-14 conversation for the
   full reasoning on why this threshold is less lossy than "20 out of
   millions" sounds, given point 1's sampling asymmetry. Done, but a
   judgment call — could be lowered (e.g. to 10, ~29,721 entities) if more
   coverage is wanted later, at ~2x the review cost.

4. **Tier 1: Wikipedia/Wikidata resolution**
   (`src/wikidata_entity_lookup.py`) — for each entity, Wikipedia search +
   summary API call, with a token-overlap/acronym-match confidence gate
   (catches wrong matches like "Whitney Webb"→"Whitney Blake") and keyword
   rules on the description text to auto-bucket into the taxonomy above.
   **Rate-limit gotcha**: Wikipedia will 429 you; the first full run (15
   workers, no backoff) silently failed on ~98% of requests — always use
   `get_with_backoff()` (exponential backoff already in the script) and
   keep workers modest (6 was reliable, 15 was not). A clean run takes
   ~11-20 min at 6 workers if not rate-limited, ~130 min if it is (still
   completes, just slow — don't kill and restart, that loses all progress
   since results aren't checkpointed incrementally). Result:
   `data/processed/entity_wikidata_tier1.csv` — 96.6% resolved, 2,126
   auto-bucketed (100 of those are `maverick_authority`, worth reviewing
   directly: Michael Yeadon, John Kiriakou, Thomas Drake, Sidney Powell,
   Wayne Madsen, Mike Cernovich, Jack Posobiec are new finds not on the
   top-down list; watch for false positives like Peter Strzok, who got
   auto-bucketed via a "former FBI officer" keyword match but is actually
   villain-coded in this corpus, not cited as an authority). Done.

5. **Disambiguation refinement**
   (`src/wikidata_disambiguation_refine.py`) — **must check ALL resolved
   entities for the Wikipedia `disambiguation` pageprop flag, not just the
   ones Tier 1 scored low-confidence.** A bare name whose Wikipedia page is
   itself titled identically to the query (e.g. "Bill" → disambiguation
   page literally titled "Bill") passes the token-overlap confidence check
   trivially, so confidence and disambiguation-page status are NOT mutually
   exclusive — the first version of this script scoped to low-confidence
   only and missed 2,833 of 2,911 true disambiguation pages as a result.
   Phase 1 (batch pageprops check, 50 titles/request) is cheap either way,
   ~3 min for the full 15,923. Phase 2 (pageviews-based ranking of each
   disambiguation page's linked candidates) is the slow part, ~137 min for
   2,911 entities at 5 workers — **also has a real false-positive mode**:
   ranking candidates by their own page's raw pageviews (not by relevance
   to the query) let "Bill"→"Alice's Adventures in Wonderland" through with
   high "confidence" (a tangential link to a globally-famous page beat the
   actually-intended-but-less-famous referent). Fixed by re-applying the
   same token-overlap sanity check from Tier 1 to the refined result too —
   this is pure local recomputation on already-fetched data (no new API
   calls), caught 945/1,708 "confident" resolutions as nonsensical. See
   `refined_confident_sane` column (the corrected one — `refined_confident`
   alone is NOT trustworthy). Result: 763 genuinely confident+sane
   resolutions. Done.

6. **Context-window extraction**
   (`src/extract_entity_context_windows.py`) — the original NER-mining pass
   (step 1) stored `doc.text[:200]` (first 200 chars of the WHOLE comment)
   as each entity's "example", not a window around the actual mention — so
   only 27.4% of those examples even contained the entity name. This
   redid it properly: single Aho-Corasick pass over the full 21.4M-row
   corpus (~7.6 min), capturing ±100 chars actually centered on each match.
   Result: `data/processed/entity_context_windows.csv`, 98.6% of entities
   now have a real, relevant example. Read this file with
   `on_bad_lines="skip", engine="python"` (see the CSV-quoting gotcha
   above). Done.

7. **Stage A: dictionary-word junk filter**
   (`src/stage_a_dictionary_filter.py`) — flags single-token entities that
   are ordinary English words (spaCy NER misfires: "Universe", "GTFO",
   "Funny") using the local macOS wordlist (`/usr/share/dict/words`, no
   internet/API needed). **Gotcha**: that wordlist mixes true common nouns
   with a biographical-names supplement (alphabetized together, casing in
   the source file is the only way to tell them apart — "universe"/"funny"
   are lowercase-only entries, "Bernie" is capitalized-only, "Bill"/"bill"
   is both). A naive case-insensitive check wrongly flagged real people
   (Hunter, Bernie, Donald, Paul, Cheney...) as junk. Fixed by only
   counting lowercase-only entries as "ordinary words". Even after that
   fix, dictionary-word status alone is too noisy to exclude on (Tucker
   Carlson, Seth Rich, Bernie/Sarah Sanders, Delta, The Times, The Sun are
   all real frequently-cited entities that also happen to be common
   words/surnames) — the script cross-references against Tier 1's
   Wikipedia-resolution status: `likely_pure_junk` = dictionary word AND no
   Wikipedia match at all (51 entities, genuinely safe to deprioritize);
   `dual_purpose_word` = dictionary word BUT has a real Wikipedia match (not
   junk, just flagged as ambiguous — 2,441 entities). Result:
   `data/processed/entity_stage_a_filtered.csv`. Done.

8. **Stage B: consolidated corpus pass**
   (`src/stage_b_consolidated_corpus_pass.py`) — DONE, ~10.5 min. Two
   things in one pass over the full corpus:
   (a) word-bag collection for Yarowsky-style per-instance disambiguation
   (see step 9) — for each ambiguous cluster in the `AMBIGUOUS_CLUSTERS`
   dict at the top of the script (bill, hunter, kennedy, clinton, sanders,
   rich, tucker), collects surrounding words separately for full-name
   ("labeled") instances and bare-name ("unlabeled") instances, capped at
   2,000 samples/candidate. **This dict is the main thing worth extending**
   if more ambiguous clusters turn up — it's a plain Python dict, not
   derived from anything. Output: `data/processed/stage_b_word_bags.json`.
   **Known collision bug**: "Bill Clinton" is a candidate under both the
   `bill` and `clinton` clusters, but the script's single shared alias->
   candidate dict means only one survives (bill.Bill Clinton got 0 samples,
   clinton.Bill Clinton got all 2000) — Stage C works around this by
   borrowing clinton's data into bill's candidate set at load time. If you
   add more clusters that share a candidate name, expect the same issue.
   (b) credential-pattern regex extraction: `(former|ex-|retired) (CIA|
   FBI|NSA|DIA|DEA|MI5|MI6|KGB) (officer|agent|analyst|...)` plus whatever
   capitalized name is nearby. Raw output is noisy (picks up month names,
   sentence-starters, the trigger word itself) — see
   `data/processed/stage_b_credential_pattern_hits_cleaned.csv` for the
   stopword-filtered version. Real new finds surfaced this way: Michael
   Levine (DEA whistleblower/author), Howard Hunt (Watergate/CIA), Hector
   Berrellez (DEA, Camarena case), Yuri Bezmenov (KGB defector), Ted
   Gunderson (ex-FBI), Kevin Shipp (ex-CIA whistleblower), Vang Pao
   (CIA-Laos drug-trafficking narrative) — none of these were on the
   top-down candidate list (§8/§10) or found by the bottom-up frequency
   mining (steps 1-4 above), because individually they're too rare to
   clear the doc_count>=20 floor; the credential-pattern is what makes
   them findable despite low individual frequency. **Not yet merged into
   the main candidate list** — that's part of Stage E.

9. **Stage C: per-instance disambiguation classification**
   (`src/stage_c_classify_ambiguous.py`) — DONE. For each candidate,
   builds "signature words": words disproportionately concentrated in ITS
   labeled bags vs. the other candidates in the same cluster (ratio test,
   >=70% concentration, >=3 raw occurrences, top 40 kept). Classifies each
   bare-name instance by word-overlap against these signature sets, only
   when the winner beats the runner-up by >=1.5x margin — ties/close calls
   left unresolved by design (this was explicitly NOT to be a global
   majority vote — see the design note that was here before this stage was
   built, still accurate, kept below for context). **Known bug found and
   fixed**: raw word bags include URL/markdown-link fragments, which are
   unique-per-occurrence and therefore trivially score 100%-concentrated
   for whichever candidate happened to co-occur with one copypasted link —
   this corrupted the Kennedy cluster's signature words entirely on the
   first run (almost all http:// fragments instead of real vocabulary).
   Fixed with a `clean_bag()` filter (drops URL-like and pure-numeric
   tokens) applied before profile-building AND before classifying bare
   instances — pure local fix on the already-saved JSON, no corpus rescan
   needed. Motivating case confirmed: of 827 resolved bare "Hunter"
   instances, 558 classified as Hunter S. Thompson and 269 as Hunter
   Biden — confirms the original `hunter_biden`-only alias-cluster
   assumption was wrong (see step 6), but also that Biden isn't a
   non-factor, which is exactly why per-instance classification (not a
   blanket merge either direction) was the right call. Resolution rates
   varied a lot by cluster: sanders 47.5%, hunter 41.3%, clinton 15.4%,
   kennedy 12.8%, bill 7.8% — bill/clinton/kennedy having lower resolution
   isn't necessarily a flaw, short bare-mention comments often just don't
   carry enough local context to disambiguate confidently, and leaving
   those unresolved is the intended conservative behavior. **Known gap**:
   `rich` and `tucker` clusters were defined with only ONE candidate each
   (Seth Rich, Tucker Carlson) so the classifier has nothing to contrast
   against and skips them entirely — their bare mentions stay
   unclassified rather than being auto-attributed to the single known
   candidate, even though that's probably right most of the time (both are
   also Stage A `dual_purpose_word` flags, i.e. real English words too, so
   auto-attributing without any check isn't fully safe either). Not fixed;
   worth a decision if these two matter enough to handle specially. Output:
   `data/processed/entity_disambiguation_classified.csv` (per-instance),
   `data/processed/stage_c_signature_words.json` (for human sanity-check).
   Design note kept from before this was built, still holds: for each
   ambiguous bare-name instance, compare its word bag against each
   candidate's labeled-instance profile and classify that SPECIFIC
   INSTANCE — do NOT classify by global majority vote across all instances
   of a bare name (explicitly rejected earlier, would mislabel every real
   minority-referent mention).

10. **Stage D: send only the true residual to Wikipedia** (NOT YET
    BUILT) — whatever's left unresolved after Stages A-C (dictionary
    filter, word-bag disambiguation, credential-pattern additions) is what
    should go to the (slow, rate-limited) Wikipedia pipeline, reusing
    `wikidata_entity_lookup.py`'s backoff logic. This reorders the original
    (inefficient) approach, which sent all 15,923 entities to Wikipedia
    before trying any free corpus-internal signal first.

11. **Stage E: consolidate** (NOT YET BUILT) — merge Tier 1 + disambiguation
    refinement + Stage A-D outputs into one final review file for Nash's
    HITL pass: entity, doc_count, best-available identity/description,
    bucket guess, corpus example, blank final-decision column.

10. **Stage D: new-candidate Wikipedia resolution**
    (`src/wikidata_entity_lookup.py --input data/processed/stage_d_new_candidates.csv
    --output data/processed/stage_d_resolved.csv --min-doc-count 3 --workers 6`)
    — DONE, 1.1 min (small batch, no rate-limiting hit). The real "residual
    that needs Wikipedia lookup" turned out NOT to be the original 13,797
    unbucketed entities (those already went through Tier 1) — it's the
    NEW candidates Stage B's credential-pattern regex surfaced, which never
    touched Wikipedia at all. Input built by aggregating/cleaning
    `stage_b_credential_pattern_hits_cleaned.csv` (stripped role-word
    prefixes like "Agent ", merged surname-only mentions into matching
    full-name entries, dropped non-name phrases), floor doc_count>=3 → 121
    candidates. 118/121 resolved, 13 new `maverick_authority` finds:
    Andrew Bustamante, Ali Soufan, Asha Rangappa, John Guandolo, Joe
    Navarro, Amaryllis Fox are genuinely new (not on any prior list);
    Coleen Rowley, Annie Machon, John Kiriakou, Robert David Steele
    cross-validate entries already found elsewhere. The script now takes
    `--input`/`--output` flags (added for this reuse) instead of hardcoded
    paths. Two minor uncleaned dedup artifacts in the output ("Webster
    Tarpley Interview" should merge with "Webster Tarpley"; a garbled
    "Soufan\n\nAli" duplicates "Ali Soufan") — cosmetic, not fixed.

11. **Ground-up categorical bucketing via Wikipedia's category system**
    (`src/stage_e_wikipedia_categories.py`) — prompted by Nash asking how
    much bucketing can be done computationally/ground-up rather than by
    human review, and specifically what richer signal is available beyond
    the one-line description already used for `tier1_bucket_guess`.
    Motivating gap: of 15,493 entities resolved to a real Wikipedia page,
    only 2,154 (14%) got bucketed from description-text keyword matching —
    a one-sentence description is thin. Every Wikipedia article carries
    10-30+ community-maintained categories (e.g. Michael Yeadon's page:
    "British anti-vaccination activists", "COVID-19 conspiracy
    theorists", "Pfizer people", "British pharmacologists") which is a much
    richer, more specific, ground-up signal — Wikipedia's own
    categorization, not something being inferred from one sentence.
    **Real API gotcha found**: MediaWiki's `cllimit` for the `categories`
    property caps the TOTAL categories returned across an ENTIRE batched
    multi-title query, not per-title — unlike `pageprops` (used in step 5),
    which is small and fixed-size per page and batches fine. One title with
    ~50 categories (e.g. Alex Jones, Bill Gates) can silently starve every
    other title in the same batch — confirmed empty results even at batch
    size 3. Fixed by following the `clcontinue` pagination token per batch
    until exhausted (`batch_get_categories()`), then parallelizing across
    batches of 20 titles with 6 workers + the same 429 backoff pattern used
    elsewhere (`fetch_all_categories()`) — ~31 min projected for 15,493
    titles (smoke-tested at 100/100 resolved in 11.9s). Also filters out
    Wikipedia's internal maintenance/tracking categories (birth-year,
    "Living people", "CS1:...", "Articles needing...", etc. — see
    `MAINTENANCE_PATTERNS`) before matching substantive categories against
    an expanded keyword-rule set (`CATEGORY_BUCKET_RULES`, richer than the
    description-only rules since category names are more specific/
    compositional). **Check `stage_e_categories.log` for completion status
    and the actual before/after bucket-coverage numbers** — was still
    running as of this handoff entry. Output:
    `data/processed/stage_e_category_buckets.csv`.
    **Finished**: 11,752/12,152 titles fetched (24.8 min), 2,478 NEW bucket
    assignments beyond the 2,154 description-based ones. **Found and fixed
    a real precision bug**: matching on ANY SINGLE category out of a page's
    full list (often 30-50+) is too permissive — one incidental/
    controversy-related category can outvote everything else the page is
    actually about. Confirmed on real data: ADL (Anti-Defamation League,
    a mainstream anti-hate-speech org) got bucketed `maverick_authority`
    purely because one of its 50+ categories is "Armenian genocide denial"
    (a controversy about the org's historical position, not what it is);
    Bin Laden, Nixon, Giuliani, Michael Flynn — all villain-coded in this
    corpus, not cited authorities — got swept in the same way. 64% of all
    maverick_authority category-matches (500/782) turned out to be
    single-category-triggered. Fixed by requiring 2+ independently-matching
    categories before treating a bucket guess as reliable — see
    `category_bucket_n_matches` column (pure local recomputation on the
    already-fetched category data, no re-fetch needed). Reliable
    (n_matches>=2) totals: mainstream_figure_not_source 770, other 560,
    alternative_source 310, mainstream_source 285,
    mainstream_expert_authority 250, maverick_authority 214, villain 174 —
    all the previously-flagged bad cases (Bin Laden, Nixon, Giuliani,
    Flynn, Hezbollah) correctly dropped out of this tier. Single-category
    (n_matches==1) entities aren't discarded, just should be treated as
    weak hints, not trusted bucket assignments, in Stage E's consolidation.
    **Residual known limitation, not fixed**: some topic/event/concept
    pages still pass even the 2+ threshold (Roswell, Bilderberg Meeting,
    Flat Earth, Nibiru cataclysm) because Wikipedia legitimately applies
    "conspiracy theory"-type categories to articles ABOUT a theory, not
    just to people who promote it — this conflates "who cites something as
    an authority" with "what the citation is about". Easy for a human to
    spot in the final review pass, not worth over-engineering a fix for.

### Status: pipeline complete as of 2026-07-14

All steps 1-12 are DONE. Final deliverable:
`data/processed/entity_final_review.csv` (15,988 rows) — this is what Nash
should actually review; everything upstream is intermediate working data.

12. **Stage E: final consolidation** (`src/stage_e_consolidate.py`) —
    merges Tier 1 + Stage D + disambiguation refinement (using
    `refined_confident_sane`, NOT `refined_confident` — see step 5) + Stage
    A junk/dual-purpose flags + Stage C per-instance disambiguation
    (rendered as a human-readable `disambiguation_note`, e.g. "Sanders:
    47% Bernie Sanders (n=949), 0% Sarah Sanders (n=2), 52% unresolved" —
    the 7 known ambiguous cluster entities get `final_bucket_guess=
    "AMBIGUOUS_CLUSTER"` and this note instead of a single bucket, since
    they're genuinely multi-referent) + Stage E category buckets (using
    the 2+-corroborating-categories reliability threshold from step 11) +
    properly-centered corpus context windows (`entity_context_windows.csv`,
    NOT the earlier flawed first-200-chars version). Bucket-guess
    precedence: reliable categories (2+) > reliable description-text match
    > weak single-category hint > unresolved. **Known cosmetic gap**:
    "Rich" and "Tucker" get flagged `AMBIGUOUS_CLUSTER` but have an empty
    `disambiguation_note`, since Stage C's classifier skipped both (only
    one candidate each defined, nothing to contrast against) — affects 2
    of 15,988 rows, not fixed.
    Final numbers: 2,553 `reliable_categories` + 819 `reliable_description`
    = 3,372 entities with a trustworthy computed bucket, zero human review,
    zero LLM cost; 1,231 `weak_hint_single_category` (flagged uncertain,
    not discarded); 11,378 still `unresolved` but carry identity/context
    where available; 51 `likely_pure_junk`; 7 ambiguous-cluster entities.

If picking this up cold: nothing needs rerunning, the final file is done.
If Nash wants to extend coverage further (lower the doc_count>=20 floor
from step 3, add more ambiguous clusters to `AMBIGUOUS_CLUSTERS` in
`stage_b_consolidated_corpus_pass.py`, or push more entities through the
credential-pattern pipeline), rerunning any individual stage script is
safe and idempotent — see each step's notes above for gotchas specific to
that stage before rerunning it.

**Note (2026-07-14, later same day)**: the "final numbers" above are now
stale — subsequent work added Stage F (bottom-up category clustering),
Stage G (auto-discovered per-instance disambiguation, generalizing the
Bill/Hunter approach to ~181 more ambiguous names), a category-bucket
priority-tiering fix (generic occupational categories were wrongly
outvoting specific construct-defining ones — e.g. Graham Hancock was
briefly `alternative_source` via 5 "journalist" categories outvoting 2
"Pseudoarchaeologist" ones), a reliability-threshold recalibration for
sparse-category entities (fixed AE911Truth, which has few total categories
so was failing the naive ">=2 matches" bar despite having an unambiguous
signal), and two new cross-cutting flags (`has_expert_credential`,
`has_institutional_insider`) answering "which maverick_authority entities
are genuine/purported experts vs. media personalities". Don't cite the
specific counts above — read `data/processed/entity_final_review.csv`
directly for current numbers. See §13 for what this feeds into.

## 13. Grand synthesis: integrating insider-status signals, thread-quality
    filters, and construct scores into one analysis (planned 2026-07-14,
    not yet built)

### Goal

Nash's research question needs upvotes to be a *trustworthy* signal before
any construct-vs-engagement correlation means anything — a comment's score
reflects genuine community judgment only if the audience voting on it is
actually the community (not brigaded, not a viral crosspost pulling in
outside traffic, not passive drive-by approval). This section is the plan
for combining every "is this context/person genuine" signal already built
across this project into one filtered analysis dataset, then correlating
the credibility-construct scores (source_citation, maverick_authority,
hedged_suspicion, personal_experience, procedural_skepticism) against
upvotes *within* that filtered population — plus testing how sensitive any
finding is to the specific filter choices.

**This is an integration and tightening task, not a from-scratch build.**
Every piece below already exists in some form; none of it is wired
together, several pieces use stale file paths (fixed, see the two new
`src/repro_*.py` scripts), and one piece (stance detection) is genuinely
new.

### Inventory: what exists, where, how solid

**Insider-status signals (four independent dimensions, never combined):**

1. **Static activity threshold** — author has ≥21 lifetime r/conspiracy
   comments. Simplest, already live in `ConspiracyMaster_Refactored.ipynb`
   §9.6. No temporal or cross-community nuance at all.
2. **Cross-subreddit purity/affinity** — `conspiracy_ratio` (conspiracy
   comments / total Reddit comments) and Bayesian-shrunk `affinity_score`
   for related subreddits. Real data (293,755 authors × 161,459
   subreddits, Arctic Shift API crawl), real stats (empirical-Bayes
   shrinkage, not naive ratios). Reproducibility script:
   `src/repro_cross_subreddit_affinity.py`. Outputs:
   `data/processed/author_subreddit_footprints_async.csv`,
   `author_insider_metrics.csv` (not yet generated — script has the logic,
   hasn't been run standalone since it was extracted from the scratchpad;
   the *original* scratchpad run's outputs already exist under different
   filenames, check before re-deriving), `author_related_subreddits_bayesian.csv`.
3. **Temporal lexical-convergence trajectory** — monthly cosine-alignment
   score per author, tracked across their tenure (40,534-author "legacy"
   cohort, ≥12 active months). The only one of the four that ran to
   completion with a validated finding ("No Country for Old Members" —
   alignment *drops* with tenure, not the naive-hypothesis direction).
   Reproducibility script: `src/repro_temporal_lexical_trajectory.py`.
   Output: `data/processed/lifecycle_trajectories_local.csv`.
   **Resolved decision on the three-vocabulary-pipeline redundancy
   (2026-07-14)**: this script, `src/compute_baselines.py`'s on-demand
   `lexical_baseline_{month}.csv`, and the persisted 216-month
   `monthly_baselines/baseline_{month}.csv` series all independently
   construct "the month's community vocabulary" slightly differently (word
   counts close but not identical between the first two — e.g. "wiki" at
   30,586 vs. 15,836 for the same month — and this script alone uses a
   10%-sample vectorizer rather than an exhaustive count). Decided:
   **do not recompute or touch `lifecycle_trajectories_local.csv` /
   its `alignment_score` values** — leave this finding exactly as-is, a
   self-contained result on its own terms. Going forward, any *new* work
   needing monthly vocabulary should read from the persisted
   `monthly_baselines/` series (already covers all 216 months, so this
   also avoids ever needing to run `compute_baselines.py` fresh) rather
   than inventing a fourth construction. This quietly retires
   `compute_baselines.py`/`lexical_baseline_*.csv` for future use without
   deleting or modifying anything that already exists. Net effect: zero
   recomputation, zero changed numbers, no new redundant pipeline added.
4. **Single-month lexical-insider score** — cosine similarity to a single
   target month's vocabulary baseline (simpler snapshot version of #3,
   currently `TARGET_MONTH = '2025-01'`). Live in
   `ConspiracyMaster_Refactored.ipynb` §9.8. Outputs feed
   `df_users_live.csv`, `df_rankings_live.csv` (both dated 2026-06-20, i.e.
   pre-dating the recent Gen-2 HITL construct improvements in §4/§5 — the
   *lexical* scoring itself doesn't depend on those construct labels so
   probably doesn't need refreshing, but check before assuming).

**Thread-quality / "trustworthy upvotes" filters:**

5. **Brigading detection** — epistemic-signature shifts across upvote
   tiers (Trench/Intermediate/Viral). `ConspiracyMaster_Refactored.ipynb`
   §9.5. Output: `brigade_test.csv`.
6. **Cross-post/virality audit** — real external API sweep (Arctic Shift)
   identifying which outside subreddits linked to breakout threads, plus
   hour-by-hour insider/outsider ratio tracking showing whether viral
   threads attract "tourists" over time. §9.7. Outputs:
   `cross_post_audit_results.csv`, `unfiltered_viral_thread_ids.parquet`,
   `unfiltered_mid_high_thread_ids.parquet`. Only directly verified on 3
   known breakout threads + a 1,000-thread stratified sample — coverage is
   partial, not exhaustive.
7. **Upvotes-per-comment ratio** — NEW, defined and validated 2026-07-14
   (not in any notebook before today). `score / num_comments` at the
   post level; **low ratio = more discussion per upvote = genuine-insider
   signal** (confirmed: known viral/breakout threads have ~3x higher
   median ratio than the rest of the corpus — 2.44 vs. 0.85). Note:
   `view_count` (true viewer/impression data) does not exist anywhere in
   the raw Reddit dumps — always null, not a Reddit API field that gets
   populated. Not yet computed as a saved column anywhere; trivial to add
   from `RAW_POSTS`.

**Construct scores to correlate against upvotes, once the population is filtered:**

8. `source_citation` (κ=0.869, solid), `hedged_suspicion` dedicated-ML
   (κ=0.872, small n=47), `personal_experience`/`procedural_skepticism`
   (`pe_prob`/`ps_prob`, freshly re-scored on the full 21.4M-row corpus,
   §5 — but compressed/underconfident, not yet recalibrated), and
   `maverick_authority` (not usable as a bag-of-words score at all,
   κ=-0.068 — **use the entity-based approach instead**: §12's
   `entity_final_review.csv`, especially the `has_expert_credential`/
   `has_institutional_insider`-flagged reliable entries, matched against
   comment text).
9. **Stance detection in replies** — does NOT exist anywhere in this
   project. Genuinely new work, not an integration task. Nash wants this
   as a secondary reception signal alongside upvotes (agreement/
   endorsement/disagreement in child comments). Needs a lexicon/rule-based
   approach (no LLM calls per the budget constraint) — e.g. agreement
   markers ("this", "exactly", "well said") vs. disagreement/challenge
   markers ("source?", "no", "that's wrong") in direct replies to a parent
   comment. Scope and precision entirely undefined yet — this is design
   work, not extraction, flag for Nash before building.

### Staged integration plan

**Stage 1 — Composite insider score.** Combine signals #1-4 into one
per-author (and per-comment, via author lookup) insider classification or
continuous score. Not mechanical: deciding how to weight/combine four
partially-overlapping signals (two of which are both "lexical convergence"
at different granularities) is a construct-definition call. **Reserved for
Nash, not Antigravity to decide unilaterally** — same category as the
`maverick_authority` hierarchy decision in §10.

**Stage 2 — Trustworthy-thread flag.** Combine signals #5-7 into one
per-thread flag: not brigaded, not viral/crossposted, low upvotes-per-
comment ratio. Thresholds for each sub-signal need picking (e.g. what
upvotes-per-comment cutoff counts as "low enough" — today's validation
only established the *direction*, not a cutoff). Mechanical once
thresholds are set, but the thresholds themselves are Stage 6's job to
stress-test, not a one-shot decision.

**Stage 3 — Join.** Filter the corpus to comments in trustworthy threads
(Stage 2) written by insider-classified authors (Stage 1), join construct
scores (#8) and entity-based maverick_authority matches per comment.

**Stage 4 — Correlate.** Regression/correlation of each construct against
upvotes within the Stage 3 population. Compare against the same regression
on the *unfiltered* corpus as a check — does restricting to trustworthy
contexts change or strengthen the relationship? That comparison is
arguably the more interesting result than either regression alone.

**Stage 5 — Stance detection (new build).** Design and build the
agreement/disagreement-in-replies signal (#9), once Nash has scoped it.
Add as a secondary outcome variable alongside upvotes in Stage 4.

**Stage 6 — Sensitivity analysis.** Re-run Stages 2-4 varying the
threshold choices (insider bar at 10 vs. 21 vs. 50 comments; different
upvotes-per-comment cutoffs; with/without the brigading exclusion) to see
how robust any finding is to the specific narrowing decisions — this was
explicitly requested, not optional polish.

### What's genuinely safe for Antigravity to just do

Mechanical, well-specified once Stage 1/2's definitions are pinned down:
building the actual join/filter pipeline (Stage 3), running the
correlations (Stage 4), and the sensitivity sweep (Stage 6). Also safe:
running the two new `src/repro_*.py` scripts if the corpus ever changes
and re-derivation is actually needed (it isn't right now).

### Reserved for Nash — do not decide unilaterally

- How to combine/weight the four insider signals into one score (Stage 1)
- Exact thresholds for "trustworthy thread" (Stage 2) beyond the direction
  already established today

### §13 progress log (Antigravity actually built Stages 1-4, found post-hoc)

Antigravity independently built and ran Stages 1-4 (before this section
was fully staged) — `src/generate_insider_score.py`, `src/compute_thread_
elasticity.py`, `src/run_integrated_regressions.py`, output in
`data/processed/synthesis_regression_results.csv`. A "walkthrough" summary
was produced in Antigravity's chat panel but **not saved to disk anywhere**
— no `walkthrough.md` exists in the repo, so that narrative only exists in
whatever chat log produced it. Treat the actual CSV + scripts as the
source of truth, not any prose summary of them.

**Bug found and fixed (2026-07-14)**: `run_integrated_regressions.py`'s
`build_expert_regex()` built the `has_maverick` variable from entities
where `has_expert_credential OR has_institutional_insider` was True,
**without** requiring `final_bucket_guess == 'maverick_authority'`. Since
those two flags are deliberately cross-cutting (also true for
mainstream_expert_authority entities like Einstein, and
mainstream_figure_not_source entities like Hillary Clinton/Nixon/Kissinger,
tagged institutional_insider for being government officials), the original
"has_maverick" variable was really "mentions any credentialed-or-
institutional entity, maverick or mainstream" — 1,232 entities, not the
418 that are actually `final_bucket_guess == 'maverick_authority'`. This
directly produced the confusing/direction-flipping pattern Nash was
right to be suspicious of. **Fixed and re-run**: with the corrected 418-
entity filter, the "vanishes among insiders" story does not hold up — the
low-elasticity-stratum coefficient flips from negative (-0.0010, buggy) to
positive (+0.0004 OLS / +0.1585 Logit, correct), and in the sensitivity
table, tightening the insider threshold from `None` to `>1.5` makes
`has_maverick`'s coefficient **grow** (+0.0004 → +0.0029, becoming
significant at the strictest cutoff) rather than shrink toward zero or
flip negative. The honest finding is closer to "maverick-authority appeals
have a small, fairly consistent positive relationship with engagement that
doesn't wash out among insiders — if anything it strengthens" — not
"tourists reward sensationalism, insiders are skeptical of it." `has_link`/
`pe_prob`/`ps_prob` were essentially unchanged by the fix, confirming it
was isolated to the one contaminated variable.

**Two more issues found — both DONE as of this entry (2026-07-14, same
day)**:

1. **Crosspost/brigading exclusion — DONE.** `src/compute_thread_
   elasticity.py` now pulls `num_crossposts` (Reddit's own post metadata,
   complete for all 17,057 posts, unlike the ~1,000-thread Arctic-Shift
   audit) and derives `is_high_crosspost = num_crossposts >= 1` (1,237
   posts flagged — vs. only 19 the old sample-limited audit would have
   caught). Also added comment-level brigading flags reusing the EXACT
   definition from `ConspiracyMaster_Refactored.ipynb` cell 76 (not a new
   threshold): `brigade_upvote_flag` (score≥100 from a 1-comment author,
   722 rows) and `brigade_downvote_flag` (score≤-6 from a ≥21-comment
   regular, 82,326 rows) → `data/processed/comment_brigade_flags.csv`.
   `run_integrated_regressions.py`'s query now actually filters
   `WHERE is_high_crosspost=0 AND brigade_upvote_flag=0 AND
   brigade_downvote_flag=0` instead of pulling `is_crossposted` in and
   never using it. Sample dropped from 215,483 → 155,641 rows (~28%
   excluded) — output written to `synthesis_regression_results_filtered.csv`
   (kept separate from the entity-fixed-but-unfiltered
   `synthesis_regression_results.csv` so both remain comparable).
2. **Formal interaction-term test — DONE.** Added
   `run_interaction_regressions()`, a single pooled OLS with
   `(pe_prob + ps_prob + has_link + has_maverick) * C(elasticity_bin)`
   (Medium as reference category) on the same filtered population. Output:
   `data/processed/synthesis_interaction_results.csv`.

**Combined result — this changes the actual finding, not just the
robustness story.** With both fixes applied:
- `has_maverick` in the Low/trench stratum is now **positive** for both
  outcomes (+0.0008 OLS, +0.2318 Logit) and the Logit result is
  independently significant (p=0.021) — appeals to maverick authorities
  predict high-traction even within the stricter, non-viral/non-brigaded
  population.
- The formal interaction test is the real answer to "does the effect
  differ by stratum": `has_maverick:C(elasticity_bin)[T.Low]` = -0.0044,
  **p=0.362 — not significant**. There is no statistically defensible
  evidence that the maverick-authority effect is different in trench
  threads vs. the Medium baseline. `has_maverick:C(elasticity_bin)[T.High]`
  = +0.0097, p=0.044 — a real but modest strengthening in viral contexts,
  not a reversal.
- **What DID hold up as a genuinely robust, interaction-confirmed finding**:
  `has_link`'s penalty differs significantly by stratum in both directions
  (Low: +0.0117 p<0.001, i.e. *less* severe than Medium; High: -0.0090
  p<0.001, i.e. *more* severe than Medium relative to the reference) — this
  survived every fix and is the strongest-supported context-dependent
  result in the whole analysis. `ps_prob`'s High-stratum interaction is
  also significant (-0.0105, p=0.005).

**Bottom line for the thesis narrative**: the original "tourist dilution"
claim for maverick-authority appeals does not survive rigorous testing —
drop it or reframe it as null/inconclusive on this evidence. The
citation/link-penalty context-dependence is the actually-defensible
finding to lead with.

### Reframe + insider-presence addition (2026-07-14, later same session)

**Correction to the analytical framing, from Nash directly**: the insider/
elasticity filtering was never meant to set up a significance TEST between
"insider" and "other" populations — that framing (baked into the
interaction-term work above) was a misreading of the actual research goal.
The filtering exists as quality control: isolating a population trustworthy
enough that whatever effect appears within it can be taken as real
subreddit signal, not noise from tourists/brigading/virality. **The finding
is the direct coefficient + its own significance within that clean
population — not a between-group contrast.** A genuine control, if one is
wanted, should be an EXTERNAL baseline (r/AskReddit or similar, already a
known gap — §7) testing whether any relationship is r/conspiracy-specific,
not an insider-vs-other split within r/conspiracy itself.

**New signal added**: thread-level insider PRESENCE — what fraction of a
thread's distinct commenters are insider-classified (`insider_score >
0.0`) — computed per-thread via `data/processed/thread_insider_presence.csv`
(1.3M threads). **Confirmed genuinely complementary to elasticity, not
redundant**: correlation between `insider_presence_ratio` and
`elasticity_ratio` is only **r=-0.06** (nearly zero) across the 10,734
threads where both are available, though there IS a real, modest,
correctly-directioned trend (median insider presence 0.79 in Low-elasticity
threads vs. 0.68 in High). Elasticity alone was capturing only a small
fraction of what direct compositional presence measures.

**`src/run_pure_population_analysis.py`** (new, done, not yet a full
sensitivity sweep) — folds insider_presence_ratio into the population
definition (`>=0.75`, matching the observed median, not yet swept across
other thresholds the way the original insider_score sensitivity table
was) alongside low-elasticity + non-viral + non-brigaded, and reports
DIRECT coefficients (not a strata-difference test) for that combined
"genuine insider environment" population (N=27,312), with the less-strict
populations shown alongside purely for descriptive context. Output:
`data/processed/pure_population_regression_results.csv`.

**Results in the strictest population** (the actual answer to the research
question, per the corrected framing):
- `has_maverick`: high-traction coefficient **+0.4151 (p=0.0013)** —
  *larger* than in any less-strict population, not smaller. Directly
  contradicts any remaining "effect is diluted by non-insiders" framing —
  if anything the effect strengthens as the population gets purer.
- `has_link`: remains strongly negative (-1.7324 high-traction, p<0.001) —
  the single most robust finding across every population cut tried in this
  entire analysis, insider-filtered or not.
- `pe_prob`: **flips to significantly negative** here (-0.4347 high-
  traction, p=0.002) — looked neutral-to-positive in every less-filtered
  population. A genuinely new pattern only visible once the population is
  this clean; worth investigating further, not yet explained.
- `ps_prob`: loses significance entirely in this population — the negative
  effect visible elsewhere may be partly attributable to non-insider/
  non-clean contexts rather than a genuine insider-community pattern.

**Insider-presence threshold sweep — DONE.**
`sweep_insider_presence_threshold()` in the same script sweeps the
threshold across the data's own quantiles (0.0 to 1.0, within the low-
elasticity + non-viral base population) instead of committing to one fixed
0.75 cutoff. Output: `data/processed/insider_presence_threshold_sweep.csv`.
**Clean, monotonic dose-response result up to threshold 0.875**:
`has_maverick`'s Logit high-traction coefficient rises steadily as the
threshold tightens — 0.195 (p=0.027) at no filter → 0.207 → 0.241 → 0.251
→ 0.297 → 0.364 → 0.415 → 0.529 → **0.564 (p=0.0005) at threshold 0.875**
— then drops to 0.462 and loses significance (p=0.070) at the single most
extreme cutoff (threshold=1.0, fully-insider-only threads, N=10,016).

**Correction (Nash pushed back, rightly, on calling N=10,016 "underpowered"
without checking — it's a perfectly reasonable sample size on its face)**:
diagnosed properly with the actual SEs/positive-case counts rather than
asserting. Between threshold 0.875 (N=13,082) and 1.0 (N=10,016):
`has_maverick` positive-case count drops 217→171 (SE rises 0.2012→0.2549,
~27%, somewhat more than the ~14% pure-N-reduction would predict — logistic
regression precision for a binary predictor tracks the rarer class's count
more than raw N, so this part IS a real, if partial, power effect). But the
POINT ESTIMATE also genuinely shrinks (0.564→0.462, an 18% drop, not just a
wider interval around the same number) — and `has_maverick`'s own
prevalence stays flat (1.66%→1.71%) while the overall high-traction base
rate drops materially (7.45%→5.80%). That last part is the real signal:
threads where literally every commenter is insider-classified aren't just
a noisier sample of the 0.875+ population, they look like a genuinely
different, quieter slice (lower baseline chance of reaching high traction
at all) — a compositional difference, not pure sampling noise. **Honest
status: partly a real precision loss, partly a genuine compositional shift
at the 100% extreme — not confidently either "ignore it, power artifact"
or "this is a real reversal". Don't overstate the monotonic-strengthening
pattern past threshold 0.875 without digging into what's structurally
different about the fully-100%-insider thread population first.**

The OLS/log_upvotes coefficient stays small and mostly non-significant
throughout the whole sweep except right at 0.875 — the effect shows up far
more clearly in "does this get high traction" than in "how many upvotes
exactly", worth keeping in mind when choosing which outcome to lead with.

**Not yet done, staged for whoever picks this up next**:
- The external r/AskReddit control/baseline comparison (§7) — this is the
  right next step for testing whether these findings are r/conspiracy-
  specific, now that the within-subreddit population is as clean as
  reasonably achievable
- Investigating WHY `pe_prob` flips negative in the purest population —
  worth a qualitative look at example comments before treating this as a
  finding to write up, same rigor as everything else in this project
- Investigating what's structurally different about the 100%-insider-
  presence thread population (smaller threads? different topics? just
  fewer total commenters making 100% easier to hit by chance?) before
  treating the threshold-1.0 data point as either noise or a real ceiling
  effect — check a band like 0.9-0.99 as an intermediate data point, and
  look at thread-size distribution across the sweep, not just N and p
- Scope/precision target for stance detection (Stage 5) — this is a new
  construct needing the same care as the original 7-9 credibility
  constructs, not a quick add-on
- Any claim about what the final correlation results *mean* for the thesis
  argument

## 15. Four open problems raised by Nash 2026-07-15, staged for mechanical
## completion — session ran low on budget, Nash is recovering the missing
## posts archive himself in parallel

Nash's critique of everything in §14: the pure-population r/conspiracy
sample (21K comments) is sliced too fine, the consensus-expert list (19
people) is too narrow, `has_maverick` is a bare string-match with no check
that an evidentiary/citation function is happening, and the analysis needs
a broader "authoritative mainstream SOURCE" construct (not just individual
experts) covering news outlets, journals, and .gov agencies, ideally scored
against an existing external credibility metric rather than a hand-built
index. All four are legitimate. Status of each:

### (a) Sample size — ROOT CAUSE FOUND, needs Nash's action first

Not a filter-tuning problem. `data/processed/thread_quality_metrics.csv`
(elasticity) covers only 17,057 threads out of **1,482,764** distinct
threads in the full comment corpus (1.15%), because elasticity needs post-
level `score`/`num_comments`, and those only exist in
`data/raw/r_conspiracy_posts2.jsonl.gz` (17,057 posts) — the real archive,
`r_conspiracy_posts.jsonl.gz`, was deleted in the 2026-07-13 incident (§-1)
and Kaggle-backup recovery for it was unconfirmed as of that entry.
**Nash is redownloading/recovering the posts archive himself right now.**

Once `data/raw/r_conspiracy_posts.jsonl.gz` (or an equivalent full posts
file covering close to 1.48M threads) exists:
```bash
python3.12 src/compute_thread_elasticity.py   # rerun once RAW_POSTS points at the recovered file
```
Check `RAW_POSTS` at the top of that script — it currently points at
`r_conspiracy_posts2.jsonl.gz`; update it to whatever the recovered file is
named before rerunning. Then rerun `src/run_pure_population_analysis.py`
and `src/rerun_refined_regressions_v2.py` — population size should increase
by roughly two orders of magnitude, no threshold changes needed.

**Do NOT loosen the elasticity tercile / insider-presence 0.75 / brigade
filters as a workaround** before checking whether the real fix (recovered
posts data) is available — that's treating a data-completeness problem as
a methodology problem.

### (b) Consensus-expert list — CORRECTION (2026-07-15, later same day):
### the "maxed out at ~19-20" conclusion below was WRONG, caught by Nash
### pushing back. Anthony Fauci (doc_count 975, one of the highest-
### frequency entities in the entire corpus) had never been bucketed at
### all -- blank `final_bucket_guess`, invisible to any bucket-based
### search including the "systematic" one described below. Also found:
### Deborah Birx, Paul Offit, Scott Gottlieb, Jenny Harries, Peter Hotez
### -- all added to `src/consensus_experts_verified.py` (now 25 people,
### 35 name variants). A second bug then surfaced in
### `rerun_refined_regressions_v2.py::load_entities_split_corrected()`:
### it still pre-filtered candidates through `final_bucket_guess ==
### "mainstream_expert_authority"` before checking the allowlist, so the
### newly-added names were silently dropped again even after being
### allowlisted -- fixed, `consensus` is now built directly from the
### allowlist, no bucket-field dependency.
###
### **Important connecting finding**: re-running after both fixes only
### moved `has_consensus_expert` positive cases in the r/conspiracy pure
### population from 18 to 24 (still too thin for a reliable coefficient,
### CI spans -2.4 to +1.6) -- NOT the large jump Fauci's corpus-wide
### doc_count of 975 would suggest. This confirms (a) above is the real
### bottleneck: the "pure population" is only 21,091 comments drawn from
### 17,057 threads (1.15% of all threads), so even a heavily-discussed
### figure like Fauci only has a handful of surviving mentions in this
### slice. **Recovering the posts archive (a) should fix both problems
### at once** -- rerun this entity-search work AFTER (a) is resolved to
### see the real picture; don't conclude the consensus-expert construct
### is unusable based on results from the currently-tiny population.
###
### The original text below (search was scoped to already-bucketed
### entities only) is being kept as a warning, not a conclusion:

### FULL FIX COMPLETE (2026-07-15, later same day): posts archive
### recovered, elasticity recomputed, everything rerun

Nash recovered `data/raw/r_conspiracy_posts.jsonl` (1,831,271 posts, vs.
the 17,057-post partial file). `src/compute_thread_elasticity.py`'s
`RAW_POSTS` was updated to point at it and rerun --
`data/processed/thread_quality_metrics.csv` now covers 1,831,271 posts
instead of 17,057 (~107x). Consensus-expert list also expanded further
(broadened the wp_description keyword scan beyond health/COVID terms to
economics, climate science, space science, general "never-bucketed"
entities regardless of `final_bucket_guess` -- see corrected/expanded
docstring in `src/consensus_experts_verified.py`): now 43 people / 63
name-variants, up from 19/26. Added: Anthony Fauci, Deborah Birx, Paul
Offit, Scott Gottlieb, Jenny Harries, Peter Hotez, Tedros Adhanom
Ghebreyesus, Janet Woodcock, Marty Makary, Frank DeStefano, Robert
Kadlec, Katalin Karikó, Stanley Plotkin, Carl Sagan, James Hansen, Kevin
Trenberth, Satoshi Ōmura, Janet Yellen, Alan Greenspan, Ben Bernanke,
Lawrence Summers, Paul Krugman, Gary Becker, John Kenneth Galbraith.
Explicitly considered and rejected (contrarian/critical figures with
scientist-sounding descriptions, not neutral consensus voices) listed at
the bottom of that file -- don't re-add them without re-litigating the
same judgment call. Also pulled 526 news-outlet/journal/.gov-agency
entities into `data/processed/institutional_source_candidates.csv` (up
from 440) for the still-not-yet-built (d) construct.

Reran `src/rerun_refined_regressions_v2.py` with everything fixed.
**Population went from 21,091 to 1,985,823 pure r/conspiracy comments
(~94x)** -- this is now a real, adequately-powered sample, not a sliver.
Results changed substantially, not just narrower confidence intervals:

| variable | old (N=21,091) | new (N=1,985,823) |
|---|---|---|
| has_consensus_expert | too sparse, excluded (N=18) | **+0.526, p<0.001** (N=1,767) |
| has_maverick | +0.361, p=0.0002 | +0.238, p<0.001 (smaller but still robust) |
| has_link | -1.476, p<0.001 | -1.052, p<0.001 |
| pe_prob | -0.122, p=0.49 (ns) | **+0.305, p<0.001** (sign flip, now significant) |
| ps_prob | +0.081, p=0.55 (ns) | **+0.208, p<0.001** (now significant) |
| has_canonical_expert | +0.049, p=0.91 (ns) | +0.038, p=0.45 (still ns) |

**`pe_prob`/`ps_prob` flipping from null to significantly positive is a
big deal, not a footnote** -- the small population wasn't just
underpowered, it was giving a genuinely different (and apparently wrong)
picture of these two constructs. Don't cite any pe_prob/ps_prob result
from the small-population runs anymore; this is the number to use, but
also don't skip asking why they were previously null -- that's worth
understanding, not just switching to the new number silently.

**The canonical-vs-consensus keyness comparison is finally usable and
coherent** (con_con context base went from 199 words to 29,063).
Canonical-expert contexts cluster around abstract/historical/
philosophical vocabulary (plato, cave/allegory, socrates, aristotle,
relativity, tesla). Consensus-expert contexts cluster tightly around
COVID-era institutional-response vocabulary (fauci, covid, cdc,
coronavirus, pcr, director, federal, health, deaths). This is a genuinely
interpretable, thesis-usable pattern now -- "Inherited Canon vs.
Contemporary Resistance" language may be defensible after all, but
re-derive the framing from this real result, don't resurrect
Antigravity's original narrative wholesale (it was built on the
contaminated entity list AND the invalid TopMinds control, even if the
new numbers happen to rhyme with the old claim).

**r/politics side unchanged and still sparse** (`has_consensus_expert`
N=41, not significant) -- r/politics wasn't affected by the posts-archive
fix since it doesn't use `thread_quality_metrics.csv` at all. If the
r/politics-side consensus-expert comparison matters later, that needs a
larger r/politics pull (more months and/or more comments/month via
`src/build_politics_control_sample.py`), a separate task from everything
above.

Files updated by this fix: `data/processed/thread_quality_metrics.csv`
(regenerated, old 17K version backed up to
`thread_quality_metrics.csv.bak_17k`), `data/processed/comment_brigade_flags.csv`
(regenerated), `data/processed/refined_regression_results_v2.csv`,
`data/processed/refined_semantic_keyness_results_v2.csv`.

**`src/run_pure_population_analysis.py` also rerun, same day** -- picked
up the population expansion automatically (no code changes needed, it
reads the same `thread_quality_metrics.csv`). This resolves the
"threshold=1.0 might be a power artifact" open question flagged earlier
in §13: the threshold sweep now spans populations from 6.6M down to
920,400 (was 21K down to 10,016) -- at every single threshold including
the most extreme (insider_presence=1.0, fully-insider-only threads),
`has_maverick`'s Logit high-traction coefficient stays significant
(+0.20 to +0.26, p<1e-18 even at the extreme) across the WHOLE sweep.
**The earlier N=10,016 data point's apparent loss of significance at the
extreme was the sample-size artifact all along** -- with the real
population size, it isn't lost. Superseded outputs:
`data/processed/pure_population_regression_results.csv` and
`data/processed/insider_presence_threshold_sweep.csv` (both regenerated
in place, old versions not preserved separately -- if you need the old
21K-population numbers for comparison, they're in this document's git
history / earlier in this file's revision, not on disk anymore).

**Bottom line for the thesis**: the core `has_maverick` finding is now
about as well-evidenced as this corpus allows -- consistent sign and
significance across a 94x range of population sizes, all four quality
filters (elasticity, crosspost, brigade, insider-presence) independently
and jointly, and now also (with appropriate caveats about the shared
"general Reddit dynamic" pattern from §14) replicated directionally in an
external r/politics control. The consensus-expert finding
(has_consensus_expert +0.526, p<0.001) is new and well-powered but has
NOT been through the same multi-angle robustness treatment yet -- worth
the same scrutiny before leaning on it as hard.

Systematically rescanned `entity_final_review.csv` (all entities with
`final_bucket_guess`, `weak_hint_bucket_guess`, or `has_expert_credential`
pointing at `mainstream_expert_authority`, ~700 candidates total) excluding
what's already canon, maverick, or clearly political-office-holder. Found
almost nothing more to add safely as an individual "consensus expert
person" beyond the current 19 (`src/consensus_experts_verified.py`) — the
higher-doc_count residue is mostly pipeline miscategorization noise
(Batman and the Joker got tagged `mainstream_expert_authority` by the
Wikipedia-category matcher), already-correctly-excluded skeptics, or media
personalities, not missed genuine institutional-consensus figures. **Don't
force more additions here just to grow the number** — the list only
contains what the corpus actually supports.

**The real expansion is a separate, much richer category**: news
outlets/journals/agencies. Pulled 440 candidates (entity, doc_count,
wp_description) into
`data/processed/institutional_source_candidates.csv` — Washington Post,
Guardian, NYT, WSJ, Lancet, NEJM, BMJ, EPA, TSA, GAO, Associated Press,
etc., all already present in the entity corpus with real doc_counts (WaPo
alone: 2,827+1,804+2,608 across name variants), just never given their own
construct because the old pipeline only had person-level expert buckets.
This is the raw material for (d) below — do not try to force these into
`consensus_experts_verified.py`, they need their own construct (a source
is not a person).

### (c) `has_maverick` needs an evidentiary-function check, not bare string match

Currently: `regexp_matches(text, maverick_entity_pattern)` — true if the
entity string appears anywhere, no matter how (mockery, unrelated mention,
homonym collision). Antigravity already built the fix and never finished
validating it: `src/combined_maverick_detector.py` combines the FactAppeal
source-attribution classifier (detects citation syntax: "X says," "according
to X," "as X pointed out") with the entity list, so a match only counts if
BOTH the entity is present AND the sentence is doing citation work.

**Before trusting it**: check whether the FactAppeal val/test bug
documented in §8b is actually fixed — that section describes a real,
specific bug, not just "needs review." If unresolved, fix that first, then
re-run `combined_maverick_detector.py` restricted to the now-curated
`maverick_authority` entity list (418 entities, not whatever list it was
validated against originally), and only then substitute this
evidentiary-checked flag for the bare-regex `has_maverick` in
`src/rerun_refined_regressions_v2.py` and `src/run_pure_population_analysis.py`.

### (d) New construct: authoritative mainstream SOURCES (not just experts)

Confirmed via live web research (2026-07-15) that external, free,
non-LLM credibility datasets exist and are current — use these, don't
hand-build an index:

- **News outlets**: [NELA-GT](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/AMCV2H)
  (NELA-GT-2022, Harvard Dataverse, DOI 10.7910/DVN/AMCV2H) — aggregates
  Media Bias/Fact Check factuality ratings (reliable/mixed/unreliable) at
  the outlet level for 361+ outlets. Download, extract the outlet-level
  reliability labels, join against the outlet-name entities in
  `data/processed/institutional_source_candidates.csv` by name matching
  (Washington Post, Guardian, NYT, WSJ, Daily Mail, NY Post, etc. are
  almost certainly all in NELA-GT's outlet list).
- **Journals**: [SJR (Scimago Journal Rank)](https://www.scimagojr.com/journalrank.php) —
  free CSV export per year, covers virtually all indexed journals with a
  percentile rank. Download, match Lancet / NEJM / BMJ / other journal
  entities from the candidate list against it by name. Free for
  non-commercial use with citation.
- **.gov agencies**: no external dataset needed. EPA, TSA, GAO, and
  similar are already flagged in the candidate list via
  `wp_description` containing "federal government agency" — treat as
  their own maximum-authority tier directly, no scoring needed. Also
  reuse the `has_institutional_insider` regex pattern
  (`src/stage_e_wikipedia_categories.py`) which already flags 555 related
  entities (mostly political office-holders — a good source pool for a
  "government/official figure" sub-tier of this same construct, separate
  from the *person*-based consensus-expert category above).

**Not yet built, this is genuinely new work, not a mechanical fix**: the
join/scoring script itself (`institutional_source_candidates.csv` ×
NELA-GT × SJR → a `has_authoritative_source` + weighted
`source_authority_score` construct), and deciding the regression formula
change once it exists (add as a new predictor alongside `has_maverick`,
`has_canonical_expert`, `has_consensus_expert`). Scope this as its own
task, same rigor as the original construct-validation work in §4 — don't
skip validating it against a human-labeled sample before trusting it in a
regression, same lesson as everything else in this document.

## 14. Fixing Antigravity's "refined" analysis: contaminated consensus_expert
## + invalid TopMinds control (2026-07-15) — MECHANICAL, run these commands in order

**Do not use `data/processed/refined_regression_results.csv`,
`data/processed/refined_semantic_keyness_results.csv`, or any narrative in
`walkthrough.md` / `research_notes/*.md` for the thesis.** Audited on
2026-07-15 and found to rest on two compounding problems:

1. **r/TopMindsOfReddit is not a neutral control.** It's a
   mockery/meta-subreddit whose entire purpose is to quote and ridicule
   r/conspiracy (and similar) content — confirmed via its AutoModerator
   "linked threads" rule and by reading sample comments (sarcastic, framed
   as "can you believe this take"). Any "r/conspiracy vs r/TopMinds"
   contrast is comparing r/conspiracy against people making fun of
   r/conspiracy, not against a baseline population. r/AskReddit was tried
   earlier and rejected too (that pull was a single day, temporally
   skewed to whatever was being discussed that day).
2. **`consensus_expert` was a contaminated residual catch-all.**
   `load_entities_split()` in `src/refine_thesis_models.py` puts every
   `mainstream_expert_authority`-bucketed entity that isn't a string match
   against the hardcoded `CANONICAL_EXPERTS` list into "consensus" —
   i.e. "everything left over." That silently pulled in: genuine
   contrarians/skeptics (William Happer, Judith Curry, Richard Lindzen,
   Sucharit Bhakdi, Sunetra Gupta, Martin Kulldorff, Denis Rancourt,
   Avi Loeb, Vandana Shiva, Karen Hudes...), academic journal names
   mismatched into the entity list (JAMA Cardiology, BMJ Open, MDPI, the
   Annals of Internal Medicine...), a corrupted string ("W]e"), historical
   pre-1990s figures who are closer to "canon" than "contemporary
   consensus" (Oppenheimer, Karl Popper, Albert Sabin, Milton Friedman...),
   political/legal/intelligence figures (Angela Merkel, Alan Dershowitz,
   Robert Mercer, Elena Kagan...), and figures who are usually cited in
   r/conspiracy as **villains/targets of suspicion**, not trusted
   authorities (Yuval Noah Harari, Ralph Baric). Full 147-entity list and
   the reasoning behind every keep/exclude decision is in the docstring of
   `src/consensus_experts_verified.py`.

### The fix — already written, staged, and (partially) executed as of this
### handoff entry. Three new files, zero edits to Antigravity's original
### script (so the original TopMinds-based run stays intact for comparison):

- `src/consensus_experts_verified.py` — hand-curated 26-entity allowlist
  (19 real people, all name variants) of genuine contemporary
  institutional/scientific consensus figures. Replaces the 147-entity
  contaminated residual list. **This curation is done — do not redo it or
  second-guess individual inclusions without the same level of review
  documented in that file's docstring.**
- `src/build_politics_control_sample.py` — pulls a temporally-stratified
  r/politics sample via the Arctic Shift API (20 evenly-spaced months
  spanning the exact same 2008-07 to 2026-06 range as
  `data/processed/monthly_baselines/`, ~1,500 usable comments per month
  target, checkpointed per-month so it's safe to re-run/resume).
  **r/politics was Nash's proposal to replace both AskReddit (too narrow a
  window) and TopMinds (not neutral) — it's a large, active, non-mockery
  subreddit with continuous activity across the whole timespan.**
- `src/rerun_refined_regressions_v2.py` — identical logic to
  `src/refine_thesis_models.py` (same personal-experience/procedural-
  skepticism scoring pipeline, same regex construction, same r/conspiracy
  "pure population" query, same regression formula, same keyness
  methodology) except: (a) uses the verified consensus allowlist instead
  of the residual catch-all, (b) uses the r/politics sample instead of
  TopMinds. Writes to `_v2` suffixed output files, does not overwrite the
  originals.

### Exact commands, in exact order — **this is the entire remaining task,
### there should be no judgment calls left**:

```bash
# 1. Pull the r/politics sample (resumable — safe to re-run if interrupted,
#    already-completed months are skipped automatically). Takes several
#    minutes: 20 months x up to 15 API pages each x ~1s politeness delay.
python3.12 src/build_politics_control_sample.py

# 2. Score it through the same DuckDB/empath-lexicon pipeline used for the
#    other comparison corpora (askreddit, topmindsofreddit). "politics" is
#    already registered in this script's `corpora` dict — do not add any
#    other subreddit here without the same neutrality check done for
#    r/politics above.
python3.12 src/score_comparisons.py

# 3. Run the corrected regression + keyness comparison.
python3.12 src/rerun_refined_regressions_v2.py
```

**Expected outputs** (check these exist and are non-empty before reporting
this done):
- `data/raw/r_politics_comments.jsonl` (~20,000-30,000 raw lines)
- `data/processed/comparison_politics_scored.parquet`
- `data/processed/comparison_politics_staged_scored.parquet`
- `data/processed/refined_regression_results_v2.csv`
- `data/processed/refined_semantic_keyness_results_v2.csv`

**If `src/build_politics_control_sample.py` fails with HTTP 400 errors**:
check the error message in the response body first — Arctic Shift already
rejected one field name during testing (`controversiality` is not valid,
already fixed in the current version of this script by not requesting it
and defaulting it to 0 locally). If a *different* field gets rejected,
remove it from `FIELDS` the same way rather than guessing — do not retry
blindly.

**Do not**: change `INSIDER_PRESENCE_THRESHOLD`, the elasticity tercile
cutoff, the brigade-flag logic, `TARGET_PER_MONTH`, or the `MONTHS` list
without flagging it — those are all deliberate choices already validated
elsewhere in this document (§13) or documented in this section, not open
parameters to tune for a "better-looking" result.

**Status: DONE as of 2026-07-15.** All three steps ran successfully.
30,881 usable r/politics comments pulled across the 20 months, scored,
and regressed. Results below — report these plainly, do not spin them.

### Results (data/processed/refined_regression_results_v2.csv)

Logit `high_traction ~ pe_prob + ps_prob + has_link + has_maverick +
has_canonical_expert + [has_consensus_expert] + log_char_length`, run
separately on r/conspiracy (pure population, N=21,091) and r/politics
(N=30,881):

| variable | r/conspiracy coef (p) | r/politics coef (p) |
|---|---|---|
| has_maverick | **+0.361 (p=0.0002)** | **+0.650 (p=0.0000002)** |
| has_link | **-1.476 (p<0.001)** | **-0.248 (p=0.00002)** |
| has_canonical_expert | +0.049 (p=0.91, ns) | +0.152 (p=0.75, ns) |
| pe_prob | -0.122 (p=0.49, ns) | +0.070 (p=0.52, ns) |
| ps_prob | +0.081 (p=0.55, ns) | **-0.404 (p=0.00003)** |
| log_char_length | -0.246 (p<0.001) | -0.082 (p<0.001) |
| has_consensus_expert | too sparse, excluded (18/21,091 positive, ALL 18 non-high-traction) | too sparse, excluded (4/30,881 positive) |

**The uncomfortable finding, report it as such**: `has_maverick` is
significantly positive in BOTH subreddits — and the coefficient is
*larger* in r/politics (+0.650) than in r/conspiracy (+0.361), not
smaller. This is the same direction Antigravity's invalid TopMinds
comparison showed (TopMinds coef was 0.599, also larger than
r/conspiracy's 0.363) — so this isn't an artifact of TopMinds being a
bad control, it replicates with a genuinely valid one. **Citing an
alternative/contrarian authority correlating with higher engagement
looks like a general Reddit dynamic, not something distinctively
r/conspiracy-specific.** Don't present the r/conspiracy has_maverick
effect as if the control ruled out that explanation — it didn't. What
IS clearly different between the two subreddits is `has_link`: a much
stronger traction *penalty* in r/conspiracy (-1.48) than in r/politics
(-0.25) — links behave very differently across the two communities,
consistent with the earlier interaction-term finding in §13. `ps_prob`
also behaves differently (null in r/conspiracy, significantly negative
in r/politics) — not yet investigated further.

**`has_consensus_expert` / "canonical vs. consensus" comparison is NOT
usable as a modeled finding, in either subreddit.** Even with the
corrected, non-contaminated 26-entity allowlist, genuine consensus-
expert mentions are too rare to fit a coefficient: 18/21,091 (0.09%) in
the r/conspiracy pure population, all 18 non-high-traction; 4/30,881
(0.01%) in r/politics. The keyness/log-likelihood comparison
(`data/processed/refined_semantic_keyness_results_v2.csv`) has the same
problem underneath it — only 199 total context words behind the entire
"consensus" side of the r/conspiracy canonical-vs-consensus comparison,
drawn from those same 18 comments, so patterns like "astrophysicists /
stars / according" are the idiosyncratic vocabulary of a small handful
of individual comments, not a generalizable pattern. **Do not use
"Inherited Canon vs. Contemporary Resistance" language or present the
canonical/consensus keyness split as a finding** — the corrected data
doesn't support it at this sample size. If this comparison matters to
the thesis, it needs either a much larger r/conspiracy sample (relax the
elasticity/insider-presence filters, at the cost of population purity)
or acceptance that this particular sub-question isn't answerable from
this corpus.

**NOTE on the two paragraphs directly above**: these numbers (18/21,091,
4/30,881) are STALE — from before the posts-archive recovery. See the
"READ THIS FIRST" section at the top of this document for the current
numbers (has_consensus_expert now N=1,767+ and significant). Left as-is
here rather than rewritten, to avoid touching text under time pressure —
the top-of-file section is the one to trust.

## 16. Full pipeline validity/documentation audit — STAGED FOR ANTIGRAVITY,
## READ-ONLY, DO NOT MODIFY ANYTHING

Nash's request (2026-07-15, relayed via Claude): after using LLM-assisted
tooling across many different sessions/tools/agents in many different
ways over months, he needs the whole derived-artifact stack -- every
lexical dimension, model, classifier, entity list, filter, and metric --
reviewed for construct validity, accuracy, impact on final conclusions,
and methodological justification, with everything documented clearly
enough to defend in a thesis write-up. **This is a read-only audit and
documentation task. Do not change, fix, retune, or re-run anything as
part of this task** -- if something looks broken or invalid while
auditing it, document that finding, don't silently patch it. Flag it and
stop; fixing things is separate work with its own review, not something
to bundle into an audit.

### Why this matters right now

Nash's supervisor (A/Prof Stephen Hill, Massey University) has
repeatedly told him, across the whole supervision relationship, to
"keep a track of all of the methods decisions you're making for your
write up" -- this audit is that instruction, done properly, in one pass,
rather than reconstructed from memory at write-up time. The thesis title
(per the approved ethics application) is **"Markers of Epistemic
Credibility in Online Conspiracy Theory Subreddits."** Every artifact
below should ultimately be assessed against that framing: does it
actually help measure a marker of epistemic credibility, or was it an
exploratory side-branch that didn't end up load-bearing for the final
argument? Both answers are fine outcomes of this audit -- the point is
having the honest answer on record, not proving everything was useful.

### Required format per artifact

For each component below, produce a written entry (append to a new file,
`data/processed/pipeline_validity_audit.md`, don't edit this handoff
file) covering:

1. **What it is** -- one or two sentences, plain language.
2. **Artifact location(s)** -- exact file paths (script, model file,
   output data). If you can't find something described here, say so
   explicitly rather than guessing a substitute path.
3. **How it was derived** -- method, key parameters/thresholds, and
   *why* those choices were made if that reasoning is recorded anywhere
   (this handoff doc, code comments, notebook markdown cells).
4. **Validation status** -- any human-labeled agreement metric (κ, F1,
   precision/recall), or explicit confirmation that no such validation
   exists. Don't report an F1 score without also checking whether it's
   confounded by class-prevalence inflation -- this project has been
   burned by that twice already (see §4), check for it explicitly, don't
   just copy a headline number.
5. **Known limitations already on record** -- pull from wherever they're
   already documented in this handoff (§4, §8b, §12, §13, and this
   session's additions all have relevant caveats scattered through them)
   rather than re-deriving from scratch.
6. **Construct validity assessment** -- does this artifact measure what
   it claims to measure? Note any conflations found (Nash's own email
   flagged one: NER entity-mention detection conflates "comment quotes
   this person" with "comment is about this person," not yet fixed) or
   confounds not yet resolved.
7. **Impact on the final analysis** -- is this artifact actually used in
   the current core comparison (the low-elasticity/high-insider-presence
   `has_maverick`/`has_consensus_expert` regression against r/politics),
   or is it a side-exploration that never fed into the final numbers? Be
   honest if something is currently orphaned/unused.
8. **Open questions / recommended next step** -- if there's an obvious
   gap, name it. Don't fix it here.

### Full component inventory (compiled from this session + Nash's own
### methods summary to his supervisor, 2026-07-15 email)

**Lexical/construct dimensions:**
- Empath custom 11-dimension lexicon (evidence, adversarial, hedging,
  certainty, alternative_authority, intuitive, pattern, meta_debate,
  anecdotal, quantitative + one more) -- `utils/epistemic_lexicon.py`,
  applied via `src/score_comparisons.py` and elsewhere. Nash reports the
  correlation matrix across these dimensions is mostly <0.2 (see
  `data/processed/construct_correlation_matrix.csv` if it exists --
  verify, and check whether it was ever actually validated as reflecting
  independent constructs vs. just weak lexical overlap).
- HITL-refined constructs: hedged_suspicion, source_citation,
  maverick_authority, procedural_skepticism, personal_experience --
  staged classifier models in `data/processed/staged_pipeline_models.joblib`,
  human labels in `data/hitl/`. §4 already has partial validation status
  (κ/F1 per construct, prevalence-inflation warnings) -- start there, fill
  gaps, don't redo what's already documented.

**Topic modeling:**
- BERTopic -- `ConspiracyMaster_Refactored.ipynb` section 9.2, fit on
  comments with ≥50 upvotes, output `bertopic_model/` and
  `high_upvote_with_topics.parquet`. Notebook says "Topic 13 was selected
  as the 'epistemic credibility' cluster via embedding search" -- audit
  whether that selection was validated or just eyeballed, and whether
  this topic-modeling branch actually feeds into the current core
  analysis at all (Nash's email suggests he moved toward lexical/semantic
  matching instead of topic modeling as the main approach -- confirm
  whether BERTopic is a live input or an abandoned exploration).

**Named entity recognition & disambiguation:**
- Full pipeline documented in §12 already (top-down candidate list +
  bottom-up spaCy mining, Yarowsky-style disambiguation via covariate/
  context-window analysis). Nash's email adds color worth folding in:
  Hunter Biden vs. Hunter S. Thompson disambiguation (~67.3% of "Hunter"
  mentions were reportedly Thompson, not Biden -- verify this figure is
  recorded somewhere and matches what the disambiguation pipeline
  actually produced), "Clintons" plural initially resolving to a UK
  greeting-card chain via Wikipedia lookup (a good concrete example of
  the disambiguation-pipeline failure mode already documented generally
  in §12 -- worth citing as a specific illustrative case in the write-up),
  Bill/Clinton/Gates/Kristol disambiguation, JFK/JFK Jr/RFK Jr as three
  separately-resolved covariate clusters.
- `consensus_experts_verified.py` (this session, 82 name-variants) and
  the "READ THIS FIRST" section's account of how it was built --
  audit this the same way as everything else, don't just take my
  (this session's Claude's) word for it being correct.

**Source/domain taxonomy:**
- `data/processed/domains.csv`, `data/processed/domain_epistemic_performance.csv`
  -- top linked domains/subdomains (YouTube, WikiLeaks, Wikipedia,
  Twitter, Internet Archive, PubMed per Nash's email) and their
  upvote/reception patterns. Nash flagged specific findings to verify are
  still reflected in the data: WikiLeaks links tend to be favorably
  received; top Wikipedia articles skew toward "historic uncovered
  conspiracies" plus the Haavara Agreement page; one anomalous top hit
  was the Wikipedia article for the word "et cetera" (Nash flagged this
  as unexplained and wanted another look -- if you can figure out why,
  document it, don't just leave it as a curiosity).

**Insider/outsider detection (multiple independent signals):**
- Cross-subreddit posting footprint / affinity -- `src/repro_cross_subreddit_affinity.py`,
  Bayesian-shrunk affinity score.
- Lexical/vocabulary convergence to subreddit norms -- monthly baselines
  (`data/processed/monthly_baselines/`, 216 months × 5000 keywords) +
  `src/repro_temporal_lexical_trajectory.py`.
- Elasticity ratio (upvotes/comments) -- `src/compute_thread_elasticity.py`,
  fixed this session (see "READ THIS FIRST").
- Composite `insider_score` -- `src/generate_insider_score.py`.
- Thread-level `insider_presence_ratio` -- see §13.
- Audit whether these signals are actually as independent as claimed
  (§13 states insider_presence_ratio and elasticity_ratio correlate at
  only r=-0.06 -- verify this still holds with the corrected elasticity
  data, don't assume the old correlation carries over unchanged).

**Crosspost/virality analysis:**
- `data/processed/crosspost_strata_posts_meta.csv`,
  `data/processed/crosspost_strata_raw_comments.csv`,
  `data/processed/cross_post_audit_results.csv`. Nash's email describes
  a stratified-sample-then-census "dragnet" methodology (start from the
  top of the highly-upvoted-comment distribution, work down) and an
  important additional finding not yet confirmed as operationalized
  anywhere in code: **some high-engagement posts get outside traffic
  WITHOUT being crossposted anywhere** -- organic front-page breaking-news
  posts (Trump assassination attempt, election results, Charlie Kirk).
  Check whether this "organic virality without crosspost" case is
  actually captured by the current `is_high_crosspost`/`num_crossposts`
  filter (§13) or whether it's a false-negative gap in the current
  virality exclusion -- this could mean some viral-but-not-crossposted
  threads are currently being wrongly treated as "clean" insider
  population when Nash's own prior research says they shouldn't be.
  **This is a real, specific, checkable gap -- prioritize it.**

**Evidentiary/attribution detection:**
- FactAppeal-based detection -- trained on the FactAppeal corpus (claim +
  attribution categories: expert, location, named_official, unnamed),
  status and a known bug documented in §8b, further context in Nash's
  email (zero-shot embedding approach on FactAppeal's own phrases didn't
  cluster well; lexical/syntactic pattern matching on attribution
  syntax -- "according to" etc. -- worked better). `src/combined_maverick_detector.py`
  combines this with the entity list but was never finished/validated
  (see "READ THIS FIRST", item (c)).

**External comparison corpora:**
- r/AskReddit -- rejected (single-day sample, documented this session).
- r/TopMindsOfReddit -- rejected (mockery subreddit, documented this
  session and in Nash's email independently -- both arrived at the same
  conclusion separately, worth noting as corroboration in the write-up).
- r/TopConspiracy -- downloaded (`data/raw/r_topconspiracy_*.jsonl`) but
  per Nash's email its purpose/status is unclear ("some highlight reel of
  the conspiracy subreddit perhaps") -- audit whether this is used
  anywhere or just sitting as unused raw data; if unused, say so.
- r/politics -- current valid control (this session), 30,881 comments,
  20 evenly-spaced months.

**Core comparison / final regression:**
- `src/rerun_refined_regressions_v2.py` -- the current main analysis.
  Audit whether the formula and population-construction choices
  (elasticity tercile, insider_presence≥0.75, non-crosspost, non-brigade)
  are justified/documented well enough to defend as-is, given they were
  arrived at through a long iterative process this session and in prior
  ones -- the reasoning is scattered across §13/§14/§15/READ-THIS-FIRST,
  collecting it into one clear justified paragraph per choice would
  itself be valuable output of this audit.

### What NOT to do as part of this task
Do not retune any threshold, do not "fix" anything found broken, do not
rerun any regression, do not add or remove entities from any list. If
the audit surfaces something that clearly needs fixing (the crosspost
gap above is the most likely candidate), document it clearly with enough
detail that fixing it is a well-scoped follow-up task, and stop there.

## 17. Task board for the multi-agent workflow (2026-07-15)

Nash's setup: a free Claude instance drafts/supervises instructions,
Antigravity does mechanical execution (under hard guardrails, sometimes
read-only for project awareness), findings get fed back to a Claude
instance to review and produce code. Everything below is sorted by which
of those roles actually fits it — using the wrong one is how this project
already got burned once (Antigravity making unsupervised judgment calls
on entity curation, walkthrough.md's overclaimed narrative). Also new
this entry: **combined_maverick_detector.py's entity list was fixed**
(see `src/verified_maverick_additions.py`) — the same never-promoted-
despite-correct-weak-hint pattern found for consensus_expert also hit
maverick_authority. WikiLeaks (doc_count 9,502 alone) plus the Assange/
Manning/Snowden/Ellsberg/Kiriakou whistleblower cluster were entirely
absent from `has_maverick` until this fix. A rerun to confirm the updated
coefficient is in progress as this entry is being written — check
`data/processed/refined_regression_results_v2.csv`'s timestamp against
this commit before trusting it.

### Pattern A — Antigravity read-only, findings go back to Claude
- §16, the full pipeline validity audit. Already fully specified, use
  as-is.

### Pattern B — well-specified enough for Antigravity to execute directly
(mechanical, low-judgment, but NOT read-only — these produce new files)

**B1. Mainstream-source authority construct (§14/§15 item (d))**
Starter prompt for the free-Claude-instance role to hand to Antigravity:
> Build a `source_authority_score` construct for the ConspiracyComments
> project. Read `data/processed/institutional_source_candidates.csv`
> (526 candidate entities: news outlets, journals, .gov agencies). Steps:
> (1) Download NELA-GT-2022 (Harvard Dataverse, DOI 10.7910/DVN/AMCV2H)
> and extract its outlet-level Media Bias/Fact Check reliability labels
> (reliable/mixed/unreliable). (2) Download SJR (Scimago Journal Rank,
> scimagojr.com/journalrank.php, free CSV export) for journal-level
> ranks. (3) Match candidate entities against both by name (handle name
> variants: "the New York Times" / "NY Times" / "NYTimes" are the same
> outlet). (4) For entities matching neither dataset but whose
> `wp_description` contains "federal government agency" or similar,
> flag as a separate `is_gov_agency` tier — no external score needed. (5)
> Output `data/processed/source_authority_scores.csv`: entity, matched
> dataset (nela/sjr/gov/none), reliability_label or rank, source_url. Do
> not build a new regression predictor or touch any existing regression
> script — that's a separate task once this data exists and gets
> reviewed by Claude first.

**B2. Citation/academy-based entity scale-up (mainstream_expert_corpus_briefing)**
Already has its own full spec in that briefing document (not reproduced
here — ask Nash for it if it's not already in this repo). Division of
labor already defined there: PetScan category pulls, broader OpenAlex
sweeps, full international officeholder rosters are the "hand to
Antigravity" tasks; use `data/processed/mainstream_expert_seed_pool.csv`
and `data/processed/institutional_authority_seed_pool.csv` as the
starting seed pools, not a blank slate.

### Pattern C — judgment work, needs a Claude instance directly, NOT Antigravity alone
(Antigravity making unsupervised calls here is exactly the failure mode
that produced the contaminated consensus_expert list and the invalid
TopMindsOfReddit control earlier this project — don't repeat it)

**C1. The 351-entity maverick "weak-hint but never promoted" pool.**
Same root cause as the consensus_expert contamination, found 2026-07-15:
`weak_hint_bucket_guess == "maverick_authority"` but `final_bucket_guess`
is blank, for 351 entities (53,634 total doc_count). This pool is
genuinely mixed — alongside real misses like WikiLeaks (already fixed,
see above) it also contains clear non-mavericks that were wrongly
weak-hinted: Bin Laden, Nixon, Giuliani, ADL, Exxon, Hezbollah, Adolf
Hitler, the Trilateral Commission, the Heritage Foundation (villains,
institutions, and historical/political figures, not "alternative-
credentialed-authority" figures). Needs the exact same individual-review
treatment `consensus_experts_verified.py` got — query
`entity_final_review.csv` for this mask, sort by doc_count, review from
the top. **Do not have Antigravity do this pass unsupervised** — hand it
to a Claude instance (paid or free) to review and produce a verified
additions list the same shape as `verified_maverick_additions.py`, THEN
Antigravity can mechanically merge it in.

**C2. `has_maverick` attribution-logic fix (§8b, §14/§15 item (c)).**
Requires designing how to check that a FactAppeal-detected appeal's
`<Source>` span actually overlaps the matched maverick entity, not just
co-occurs in the same sentence — a real design decision, not a mechanical
patch. Draft the approach with a Claude instance first, then Antigravity
can implement/test the resulting spec.

**C3. RE-FRAMED 2026-07-15 (Nash's correction, this is the sharper
version, use this not the earlier framing below) — "second Trump
administration" as a period where institutional office stops being
evidence of consensus status.** The original framing of this item
("Bhattacharya is time-varying, tenure-date him") undersold the problem.
It isn't one entity's status changing at a fixed date — it's that the
whole `consensus_expert`/institutional-gatekeeping operationalization
("holds official office → speaks for institutional consensus," the
premise the entire mainstream-expert-corpus-briefing methodology in §17
B2 rests on) breaks down specifically for 2025-2026, because the second
Trump administration installed maverick-aligned figures INTO the
gatekeeping apparatus itself: RFK Jr. as HHS Secretary (the department
containing CDC/FDA/NIH), ACIP reconstituted with vaccine-skeptical
appointees, Bhattacharya (Great Barrington Declaration co-author) as CDC
Director, extraordinary CDC leadership churn in this exact window
(Monarez confirmed and fired within four weeks — see §14/§15's "FULL FIX
COMPLETE" entry). These aren't noise; they're the same underlying thing:
the institution's traditional epistemic alignment being actively
contested from inside during this period.

The classification should track the community's actual epistemic stance
toward a figure, not their job title. When r/conspiracy sees "our guy is
now CDC Director," the plausible read is "an outsider finally broke in
and vindicated us" -- a maverick-coded narrative wearing institutional
clothes, not evidence the figure now speaks for institutional consensus.
**This directly threatens the planned PetScan/OpenAlex office-roster
expansion (§17 B2)**: mechanically pulling "current HHS Secretary, CDC
Director, ACIP roster" and adding them to `consensus_expert` would
launder RFK Jr. and Bhattacharya into the consensus bucket by title alone
-- close to the opposite of correct. **Any office-roster pull covering
2025-2026 must get a Claude judgment pass checking whether the office-
holder is actually a formerly/currently maverick-identified figure before
being added as consensus** -- this is not safe to fully mechanize even
with a clean roster source.

**Possible genuine thesis angle, not just a cleanup problem**: "does
r/conspiracy's engagement with a maverick figure change once that figure
is formally installed in institutional office" is a testable empirical
question sitting inside this corpus as a natural experiment (RFK Jr.,
Bhattacharya, reconstituted ACIP members all being installed within the
corpus's own timeframe) -- worth floating to Nash as a possible finding
in its own right, not purely a data-quality nuisance to route around.

*Original framing, superseded by the above, kept for context*: needs a
design decision on how (or whether) to represent tenure-dependent entity
classification in the current binary maverick/consensus architecture
before any code gets written.

## 18. Attribution confidence scorer — three mechanical Antigravity tasks,
## then STOP before touching the core regression

`src/attribution_confidence_scorer.py` (built 2026-07-15, fully local,
no LLM calls) replaces bare entity+appeal-language co-occurrence with a
scored check (ordering, proximity, competing-source rejection). Validated
against 400 real corpus comments via `src/validate_attribution_scorer.py`
-- 94.2% of maverick-entity mentions (533/566) show NO attribution
pattern at all, confirming `has_maverick`'s bare-mention approach is far
looser than "cites this figure as evidence." Spot-check of 10 "none"
cases confirmed the scorer's core logic is sound.

**Three tasks ready for Antigravity, in this order, each mechanical and
well-specified:**

1. **Quantified validation against human labels.** Run
   `attribution_confidence_scorer.py` against
   `data/hitl/queue_maverick_authority.csv` (the same human-labeled
   ground truth `combined_maverick_detector.py` uses) and compute Cohen's
   κ / precision / recall between attribution-confidence tier and the
   human label. This is the number that should decide whether this
   scorer is good enough to use — not an assumption.
2. **Add the credential-appositive pattern.** Exact spec already in the
   scorer's docstring: catches "X is a [Dr./PhD/professor/scientist] who
   studies/works on Y" constructions, missed by the current reporting-
   verb/pre-nominal pattern lists (real example found: "Dr. Eugene
   McCarthy is a Ph.D. geneticist who has made a career out of studying
   hybridization..." used to back a pseudoscience claim). After adding,
   re-run `validate_attribution_scorer.py` and check the "none" rate
   drops without the Baric-style accusation examples in that script's
   `__main__` block flipping to a false positive.
3. **Flag (don't remove) non-person contamination in `maverick_authority`.**
   The validation sample surfaced "debunked", "Nibiru", "the New World
   Order" matching as if they were named authority figures — produce a
   candidate-removal CSV (entity, wp_description, doc_count, reason
   flagged) with a blank `decision` column, same reviewable-not-auto-
   applied pattern as `mainstream_expert_augmented_superset.csv`. Do not
   remove anything from `entity_final_review.csv` directly.

**STOP after these three and report back — do not wire the scorer into
`has_maverick`/`rerun_refined_regressions_v2.py` or re-run the core
thesis regression yet.** The scorer isn't validated against human labels
yet (task 1), is missing at least one real pattern class (task 2), and
depends on a contaminated entity list (task 3). Rerunning the headline
regression on top of an unvalidated signal risks repeating the exact
mistake this session kept finding and fixing elsewhere (measuring the
wrong thing and trusting it because the pipeline ran without erroring).
Report the κ from task 1 and get it reviewed before anyone decides
whether/how to integrate this into the core analysis.
