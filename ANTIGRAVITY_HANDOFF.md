# Antigravity Handoff — Index

Honours thesis: **"Epistemic Credibility in Online Conspiracy Communities."**
This file is short on purpose. Read it fully before doing anything, then
open exactly one task file from `handoff/` for whatever you're picking up.

**Full session narrative/history** (how every decision below was reached,
including corrections-to-corrections) lives in `handoff/ARCHIVE_full_session_history.md`
and in `git log`. You don't need it to execute a task — only read it if
you need to understand *why*, not just *what*.

## Guardrails — apply to every task, no exceptions

1. **No paid LLM/API calls without explicit sign-off.** A $100 unplanned
   bill already happened once. Free/deterministic methods only (DuckDB,
   regex, spaCy, Wikipedia/Wikidata/Arctic Shift/OpenAlex APIs) unless
   told otherwise.
2. **Never edit or delete anything under `data/raw/`.** If something
   there looks wrong, flag it, don't touch it.
3. **Entity-list judgment calls are not yours to make unsupervised.**
   Deciding whether a person/organization counts as `consensus_expert`
   or `maverick_authority` requires checking how they're actually framed
   in real corpus text (see `handoff/ARCHIVE_full_session_history.md` for
   why — the Ralph Baric case is the canonical example: real scientist,
   but corpus mentions are 100% accusatory, not citations). Produce a
   reviewable candidate list with a blank `decision` column instead of
   deciding and merging. This is the single most common way this project
   has gone wrong.
4. **Never overwrite a file that has real human ratings in it**
   (anything in `data/hitl/queue_*.csv`) without backing it up first and
   verifying row count / rating count are unchanged after.
5. **Before trusting a join, check for duplicate join keys.** This
   project has hit the same join-fanout bug three separate times
   (`empath_scores_full.parquet`, `research_corpus_staged_scores_full21m.parquet`
   both have ~58,669 duplicate `id`s; a HITL-queue migration script hit
   it too). Check `count(*)` vs `count(DISTINCT id)` before and after any
   join, not after something looks wrong.
6. **Report back and stop at task boundaries.** Don't chain into the next
   task or touch the core regression (`src/rerun_refined_regressions_v2.py`)
   based on your own judgment that a prior task's results look good
   enough — that decision belongs to Nash/Claude, not Antigravity.
7. **Never use `git push --force`, never amend a commit that isn't the
   one you just made, never delete a branch.**

## Current verified state (as of 2026-07-20)

- **Posts archive**: recovered (`data/raw/r_conspiracy_posts.jsonl`,
  1.83M posts). `data/processed/thread_quality_metrics.csv` covers all
  of it — this is what fixed the sample-size problem (pure r/conspiracy
  population went from 21K to ~2M comments).
- **`src/consensus_experts_verified.py`**: the authoritative
  `consensus_expert` allowlist. 82 name-variants / ~57 people. Use this,
  never `refine_thesis_models.load_entities_split()`'s own `consensus`
  output (contaminated, kept only for its `canon`/`mavericks` outputs).
- **`src/verified_maverick_additions.py`**: 17 name-variants (WikiLeaks,
  Assange, Manning, Snowden, Ellsberg, Kiriakou) that the automated
  entity-bucketing pipeline never promoted despite a correct weak-hint.
  Merged into the maverick regex in `rerun_refined_regressions_v2.py`
  and `combined_maverick_detector.py`.
- **Corpus duplicate-ID bug: FIXED at the source (2026-07-20)**, not just
  patched at query time. Both `empath_scores_full.parquet` and
  `research_corpus_staged_scores_full21m.parquet` rebuilt
  (21,408,577 -> 21,349,908 rows each, exactly matching unique `id`
  counts). Pre-rebuild originals kept as `.bak` files in
  `data/processed/`. `QUALIFY ROW_NUMBER() OVER (PARTITION BY id) = 1`
  guards were already present in `rerun_refined_regressions_v2.py` and
  `run_pure_population_analysis.py` (added 2026-07-18) and are now
  redundant-but-harmless against the clean files; `run_integrated_regressions.py`
  never had the guard and has been rerun against the clean corpus.
- **Current core regression numbers** (`src/rerun_refined_regressions_v2.py`,
  re-verified 2026-07-20 against the fully deduped corpus, pure
  r/conspiracy population N=1,968,864 — down from the old, duplicate-
  inflated 1,985,823, coefficients moved by <0.01, not a substantive
  change): `has_maverick` +0.248 (p<0.001), `has_consensus_expert`
  +0.528 (p<0.001), `has_link` -1.049 (p<0.001), `pe_prob` +0.307
  (p<0.001), `ps_prob` +0.207 (p<0.001), `has_canonical_expert` +0.033
  (n.s.). r/politics control (N=30,881): `has_maverick` +0.544
  (stronger than in r/conspiracy — not conspiracy-specific),
  `has_consensus_expert` -0.158 (n.s. — but only 41 positive cases, this
  is "not detectable with this little data," not strong evidence of a
  true zero), `ps_prob` -0.404 (sign flip vs r/conspiracy), `has_link`
  -0.247 (penalized in both, ~4x weaker than in r/conspiracy).
  **Caveats not yet resolved, see `handoff/task_core_comparison_robustness.md`**:
  (a) this is two separately-fit models compared by eye, not a formal
  pooled interaction test; (b) 16.14% of the r/politics sample's comments
  (2,387 authors) are written by people who are also established
  r/conspiracy commenters — not yet accounted for; (c) no clustering of
  standard errors by thread/author anywhere in this pipeline.
- **Consensus-stance HITL queue: COMPLETE (238/238 rated, 2026-07-20)**.
  Final: 162 hostile (68%), 40 endorsement (17%), 21 neutral, 15
  ambiguous. Chi-square stance x traction-stratum: chi2=1.75, df=3,
  p=0.625 (all four stances); chi2=0.78, p=0.377 (hostile vs endorsement
  only). **Not significant** — stance does not predict traction. Read:
  the +0.528 coefficient is not explained by "attacking wins more";
  naming a consensus expert functions as an engagement lightning rod
  regardless of stance. See `src/analyze_consensus_stance.py`.
- **`src/attribution_confidence_scorer.py`**: local, deterministic
  evidentiary-function scorer (replaces bare entity-mention co-occurrence
  with ordering/proximity/competing-source logic). Validated against
  human labels but agreement is still low (kappa near zero, precision
  0.38-0.50, recall 0.03-0.07) — **NOT ready to wire into the core
  regression**, a fresh disagreement-sample review is the blocking step,
  see `handoff/task_attribution_scorer_wiring.md`. Do not treat "the
  scorer exists and is validated" as "ready to wire in" — it isn't yet.
- **Source authority construct (news outlets/journals via MBFC + Scimago
  Journal Rank): BUILT (2026-07-19)**, `data/processed/source_authority_scores.csv`,
  526 entities. Not wired into any regression yet — see
  `handoff/task_source_authority_regression_wiring.md`.
- **Topic/era stratification: redone properly (2026-07-20)** with
  Bonferroni correction across all 67 OLS tests fit
  (`src/run_pure_50k_topic_analysis.py`, 50k sample spanning the full
  unbrigaded pure population, not just high-upvote comments). Honest
  result: no epistemic-construct effect (`has_maverick`,
  `has_canonical_expert`, `has_consensus_expert`, `pe_prob`, `ps_prob`)
  survives correction in any topic or era cell — only `has_link` and
  `log_char_length` do. The pooled/aggregate effects above are real and
  well-powered; we don't yet have evidence they differ by specific topic
  or era. A prior draft of this report had "key discoveries" numbers
  hardcoded into the script, disconnected from its own regression output
  — fixed, the report is now fully data-driven.
- **Trump-era vs. classical-conspiracy topic split: NOT attempted.** The
  existing BERTopic super-topics are organized by subject domain, not
  political era/valence — see `handoff/task_trump_vs_classical_topic_split.md`.
- **Master notebook (`ConspiracyMaster_Refactored.ipynb`) is frozen
  before essentially all of the above** — no r/politics control, no
  corrected consensus list, no stance resolution, no topic/era
  stratification, no source authority, no dedup fix appear in it. Its
  HTML export is stale even relative to the notebook itself. Needs new
  sections (10+) presenting the already-computed CSVs above, not a
  rebuild — see `handoff/task_notebook_and_repo_polish.md`.

## Open task files — pick one, read it fully, do only that one

**Newest first — these are the priority queue as of 2026-07-20:**

| File | What it is |
|---|---|
| `handoff/task_stance_queues_expansion.md` | Build (don't rate) two more blinded HITL stance queues: maverick mentions in r/conspiracy, and both maverick + consensus mentions in r/politics. Mechanical, mirrors the completed consensus-stance queue exactly. |
| `handoff/task_core_comparison_robustness.md` | Harden the r/conspiracy-vs-r/politics comparison: (A) a formal pooled interaction test instead of eyeballing two separate models, (B) rerun r/politics excluding the 2,387 authors who are also established r/conspiracy commenters. Both mechanical reruns. |
| `handoff/task_source_authority_regression_wiring.md` | Wire the already-built `source_authority_scores.csv` (526 entities, MBFC + SJR) into a `link_source_tier` variable, replacing flat `has_link`. Mechanical. |
| `handoff/task_trump_vs_classical_topic_split.md` | Build two seeded lexicons (Trump-era vs. classical-conspiracy terms) from existing topic labels, tag the corpus, rerun the regression stratified by cluster. One short term-list review checkpoint, otherwise mechanical. |
| `handoff/task_notebook_and_repo_polish.md` | **Do before the next `git push`.** The master notebook is frozen before essentially all of this week's work (dedup fix, r/politics control, stance resolution, topic/era stratification, source authority) — needs new sections (10+) presenting the already-computed CSVs, not a rebuild. Also: wider dormant-work audit, README expansion, portable paths. |
| `handoff/task_pipeline_lineage_audit.md` | **Done** (2026-07-20) — duplicate-ID bug traced and fixed at the source; spaCy FactAppeal predecessor audited; `DATA_MANIFEST.md` regenerated. |
| `handoff/task_mainstream_expert_review.md` | Review the 453-name `mainstream_expert_augmented_superset.csv` candidate list (Musk, Duesberg, Chomsky, name-collisions flagged, not resolved); fix the domain/basis_type metadata bug. Blocked on Nash's judgment, not delegatable to Antigravity. |
| `handoff/task_attribution_scorer_wiring.md` | Validation agreement against human labels is still low (kappa near zero) — **not ready to wire in**. Next step is reviewing a fresh disagreement sample, which is judgment work for Nash/Claude, not Antigravity. |
| `handoff/task_source_authority_construct.md` | **Done** (2026-07-19) — see `task_source_authority_regression_wiring.md` for the follow-on (wiring it in). |
| `handoff/task_consensus_stance_completion.md` | **Done** (2026-07-20) — 238/238 rated, formal analysis run, see current-state section above. |
| `handoff/task_markdown_cleanup.md` | Small: add "superseded, see this handoff" banners to `walkthrough.md`/`research_notes/*.md`, fix two stale details in `README.md`. |
| `handoff/task_full_project_documentation_audit.md` | **Done** (2026-07-18) — produced `handoff/PROJECT_INVENTORY.md`. Spot-checked by Claude and found a systematic reference-search gap — see the follow-up task below before trusting its status/evidence columns. |
| `handoff/task_project_inventory_corrections.md` | Fix the confirmed reference-search blind spot in `PROJECT_INVENTORY.md` (never searched `notebooks/pipeline/`/`archive/`/`legacy_production/`/`scratchpads/` or root-level `.py` scripts — caused two confirmed-false "never imported" rows and a fabricated citation), investigate what `notebooks/pipeline/` actually is, and re-verify a sample of the existing citations. |

Each task file is short and self-contained on purpose — if it references
something it doesn't explain, that's a bug in the task file, flag it
rather than guessing.
