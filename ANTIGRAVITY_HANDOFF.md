# Antigravity Handoff — Index

(Name kept for continuity, but this is the general-purpose handoff for
whatever AI/session picks this project up next — Antigravity, Claude
Code, or otherwise — not Antigravity-specific despite the filename.)

Honours thesis: **"Epistemic Credibility in Online Conspiracy Communities."**
This file is short on purpose. Read it fully before doing anything, then
open exactly one task file from `handoff/` for whatever you're picking up.

## Check context-repo before doing anything else

If the `context-repo` MCP server is available in this session, call
`context_checkpoint` for the compartment matching this project (e.g.
`conspiracycomments`) **before** starting or continuing any substantive
work — not just when something seems relevant. It returns the most
recently recorded decisions from other sessions (possibly Claude Code,
possibly a prior Antigravity session), newest first.

Treat what it returns as binding: if you're about to do something that
conflicts with a fact it surfaces, stop and raise the conflict with Nash
rather than deciding it yourself — same "not yours to decide unsupervised"
rule as everything else in this file. An empty result is itself
informative (nothing's been recorded yet), not a green light to improvise.

After any material decision — a scope call, something you chose to skip or
defer, a discovered blocker — call `context_write` for that same
compartment so the next session, whichever AI picks it up, has it without
needing to re-read the full handoff history.

If the MCP server isn't registered in this session, ignore this section;
it's not yet wired into every environment this file gets read in.
**Update 2026-07-28: context-repo now runs persistently on a dedicated
Oracle Cloud instance (`context.kahatahi.co.nz`), not a laptop-dependent
tunnel — should be reliably reachable going forward. `unified-gateway`
(same host, port 8423) additionally exposes `fs_*` filesystem tools
alongside `context_*`, proxied to the laptop on demand — see
`handoff/task_2026-07-28_session_wrapup.md` for the full infra picture.**

**RETRACTION, read this first**: the "88.2% ATS / 83.0% Reddit citation-
window contamination" finding in section 2 of
`handoff/task_2026-07-28_session_wrapup.md` (presented there as
"quantified at real scale") **is withdrawn**. It and the "32-45% non-
contaminated agreement" figure next to it were both produced by a judge
prompt later confirmed to anchor/inflate its own outputs (shown the
classifier's label, asked to grade it as "defensible" rather than judge
independently — see `task_2026-07-28b_...` section 6 for the full
diagnosis). A blind re-judge (label never shown to the model) found the
real numbers: **~43% contamination, 59.2% non-contaminated agreement**
(ATS 64.9% / Reddit 41.2%). Do not cite the original 88.2%/83.0%/32-45%
figures as settled in anything going forward — both retraction and
replacement numbers are in `task_2026-07-28_session_wrapup.md` section 2
(corrected in place) and `task_2026-07-28b_...` section 6.

**Update 2026-07-28 (later same day): a second Claude Code session ran
concurrently with the one that wrote the doc above — real Kaggle-account
duplicate work happened between them before either noticed. See
`handoff/task_2026-07-28b_kaggle_backlog_and_dedup.md` for what changed:
the unified-gateway TLS gap (now fixed and verified, plus a second
laptop-hosted connector built specifically for claude.ai since its
connector UI can't use the Oracle one — see that doc's section 1b),
the GCP-hosted corpus explorer going down (billing disabled on its
project — resolved, re-enabled with Nash's sign-off, that account is now
restricted to always-free-tier usage only), a bigger-model re-judge of
the entity-stance disagreement cases (confirmed the classifier reliability
problem is real, not a small-judge artifact), a verified entity-dedup
pass (683,635 -> 600,558 distinct strings), the source-stance
retraction above, and a correction
to an earlier claim (`corpus_entity_frequency_final.csv` was never
actually corrupted). Read that doc's "Cross-session coordination" section
before pushing anything else to Kaggle.**

**Update 2026-07-28 (later still): stance classifier fine-tuning
attempted, did not beat the baseline — see
`handoff/task_stance_classifier_finetune.md`. Three variants (bigger
model architecture, more context, class-balanced loss) all converged on
the same 0.32-0.35 kappa band as the original 0.345 baseline. That
convergence is itself the finding: points at genuine task/label ambiguity
as the ceiling, not fixable model capacity. Recommended next step is an
inter-rater-reliability check, not a fourth training variant. Also: two
real `project-fs-agent` bugs found and fixed while debugging a live
claude.ai connector session in parallel — an unbounded `fs_search` that
could peg the server at ~90% CPU and block every other request for
minutes (looks identical to "the laptop is asleep" from the caller's
side, but isn't), and `wake_poller.py` not detecting its own child
processes dying (workaround: restart the `com.nash.wake-poller` launchd
job, not yet fixed at the code level). Also: a domain-citation-tier human
review queue was built into `hitl_rater.py` (`data/hitl/queue_domain_citation_tier.csv`,
603 domains, sorted by citation volume — Reddit's top 400 domains alone
cover ~78% of all Reddit citation events) as a separate, arguably
higher-value thread than stance — see the same handoff doc's context for
why (citation coverage is currently <1% human-verified on both
platforms, a bigger gap than stance classifier accuracy).**

**Update 2026-07-30 (claude.ai chat session, not Antigravity/Claude Code):
stance classifier "other" class investigation + regression-with-zero-anchor
architecture-only arm run, staged plan step 2 of 4 now done.** Started from
review of a "Two-Stage Selective Confidence Gating" report claiming kappa
0.372 (argmax baseline) degrading to 0.252 under stricter threshold
gating. Found real methodological problems in that report before trusting
it: (a) it's not actually a full 2D grid search despite the name, only two
1D sweeps along each axis; (b) n=297 val set is small enough that its
kappa differences (0.372 vs 0.364 vs 0.360) are plausibly noise, no
bootstrap CI was reported; (c) "other" F1 (0.38) is genuinely weak and was
undersold relative to the polar-class wins.

**Dug into the actual labeling queue CSVs** (not just the report) and
found: (1) label taxonomy is inconsistent across queue files -- some use
endorse/hostile/none/unclear/ambiguous/"lean endorse", others use
neutral/hostile/endorsement/ambiguous; `queue_snowden_..._REVIEW.csv` has
both a 4-way `human_stance` and a 3-way `human_norm` where ambiguous AND
neutral both collapse into "other" -- i.e. "other" is currently absorbing
at least two conceptually different things. (2) `queue_topic_stance.csv`'s
`seed_stance` shows natural "other" prevalence is only ~8.4% (120/1,426),
lower than the 19% in the 297-row val set -- random sampling for more
"other" examples will be slow. (3) The REVIEW file (99 rows, has model
probabilities alongside human labels) showed only ~30% overall accuracy
(likely a curated hard-case/disagreement sample, not directly comparable
to the 60% validation accuracy) and, more usefully, that when the model
predicts "other" it's usually wrong in a specific direction: 25/33 "other"
predictions in that file were actually endorsement, not hostile and not
genuinely off-topic. Points at ambiguous-but-really-weak-endorsement
comments as the specific thing polluting "other", not valence ambiguity
in general.

**Corpus source correction**: earlier assumption that "the AboveTopSecret
archive" was the only/main corpus for this classifier was wrong --
`queue_maverick_stance_round8.csv` and `queue_short_snowden_..._check.csv`
have Reddit-format IDs (`t1_`/`t3_` prefixes on `parent_id`/`link_id`/
`comment_id`); only `queue_ats_stance_quality_check.csv` (no such ID
columns, forum-style `full_text`) looks like genuine ATS data. This
project is working across at least two separate corpora for this
classifier, not one -- worth confirming which corpus `queue_topic_stance.csv`
and the 21.3M-row unlabeled pool (see mining job below) actually draw from
before treating "other" prevalence numbers as corpus-general.

**Found `handoff/task_stance_irr_analysis_and_two_stage_proposal.md`
already existed with a more precise plan than what was being separately
proposed in-chat**: two-stage (aboutness gate + valence), Fleiss' kappa
0.48 human ceiling vs ~0.32-0.35 model (real headroom), and a
regression-with-zero-anchor design as the better-motivated architecture
change vs. full CORAL ordinal (CORAL puts "other" literally in the middle
of the hostile-endorsing continuum, re-conflating aboutness and valence --
the exact thing the two-stage split was built to avoid). Confirmed
sequencing already decided there: baseline (done, 0.405, CI excludes
zero) -> architecture-only -> data-only (mined "other" examples) -> both
together, specifically so a kappa change has one attributable cause.

**Ran step 2 (architecture-only) on Kaggle, `train_stance_classifier_twostage.py`**
(already had `train_regression_stage`/`RobertaRegressionModel`/
`build_regression_targets` fully written but never wired into `main()` --
trimmed `main()` to call only the regression arm, not full baseline+CORAL
retrain, to avoid burning GPU hours re-confirming what's already settled).
Real bugs hit and fixed along the way, worth knowing for future runs
against this same data:
- The training parquet (`stance_classifier_training_data.parquet`) has NO
  `id` column -- columns are `text/label/source_file/weight/is_human/split`.
  `build_regression_targets()` originally assumed a per-row `id` lookup
  into `ordinal_targets.csv`'s 99 genuine IRR fractional targets; that's
  not possible with this schema. Fixed to use the dataframe's own
  `weight` column instead (792/2,487 rows downweighted below 1.0,
  confirming real IRR-based weighting was already merged in upstream at
  data-build time) -- but this means the genuine fractional target_score
  override (0.33/0.67-style values) is NOT actually being used, only
  forced -1/0/+1 targets with IRR-informed sample weights. If a future
  run wants the real fractional targets, the join key problem needs
  solving first (id column added back to the training parquet, or a
  text-based match).
- The hand-rolled training loop (not HF Trainer) defaulted to `cuda:0`
  only despite 2 GPUs being available -- added `nn.DataParallel` wrapping
  + batch_size scaling (16->32) when `torch.cuda.device_count() > 1`, and
  fixed checkpoint save/load to strip the DataParallel `.module` prefix
  (otherwise the saved checkpoint would only reload cleanly into another
  DataParallel-wrapped model, breaking single-GPU inference later).

**Result**: best checkpoint (epoch 5 of 6, selected by lowest val MAE;
epoch 6 already showed clear overfitting -- train loss kept dropping while
val MAE/Pearson r/binned-kappa all reversed slightly) -- MAE=0.6395,
Pearson r=0.421, binned 3-way kappa (fixed +/-1/3 bin, explicitly NOT
tuned, only for rough comparability) = 0.307 vs the confirmed two-stage
binary baseline's 0.405. "Other" F1 still weak (0.34) at this fixed
binning. **Not yet conclusive that the architecture change underperforms**:
the baseline's 0.405 came from a full 6x6 threshold grid search, while
0.307 used one arbitrary fixed cutoff -- a `sweep_regression_threshold.py`
script was built (sweeps bin cutoffs 0.10-0.60 against the saved
checkpoint, no retraining needed) but has NOT been run yet. Do that before
concluding the regression arm is worse than baseline.

**Mining job for more "other" candidates** (`mine_other_candidates.py`,
targets the model's actual confusion pattern -- high-confidence-but-
heuristically-suspect predictions, plus boundary-confidence cases --
rather than easy/obvious non-stance text): first run crashed ~65 minutes
in with zero output saved (script only wrote the CSV at the very end, no
incremental checkpointing) -- lost that run's progress entirely. Rebuilt
with (a) a cached reservoir sample written to parquet so a restart skips
re-scanning the full 21.3M-row pool, and (b) genuine dual-GPU scoring via
two Python threads each pinned to a separate `cuda:{0,1}` (this is
inference-only, so plain threading works -- CUDA kernel launches release
the GIL -- no need for DDP complexity). Restarted successfully, running at
roughly 1,000-2,000 rows/min combined across both GPUs as of this
session's end; not yet finished, output not yet reviewed. Known follow-on
work once it does finish: the mined candidates only have `target_entity`
(plain string) + `text`, no `entity_spans` (character-offset JSON) that
`train_twostage_classifier.py`'s `load_data()` expects -- needs a
reconstruction step (locate the entity mention in text, build matching
spans) before this can be appended as a new queue file in the existing
convention.

**Full session narrative/history** (how every decision below was reached,
including corrections-to-corrections) lives in `handoff/ARCHIVE_full_session_history.md`
and in `git log`. You don't need it to execute a task — only read it if
you need to understand *why*, not just *what*.

## Update 2026-07-28 — large Claude Code session: ATS→Kaggle pipeline,
## cascade design, and shared infra (context-repo/wake-relay/gateway)

Full detail in `handoff/task_2026-07-28_session_wrapup.md` — read that
before picking up any of this. Headline summary only, here:

- **Major finding, not yet acted on**: an independent LLM-audit job found
  the entity-stance classifier underlying the "media figures vs
  whistleblowers" headline result only matches its own labels 33-36% of
  the time — close to random-chance for a 3-way classifier. This is a
  materially bigger reliability concern than anything previously flagged
  about that finding. See the task file for the full breakdown and what's
  been ruled out (sample size, entity-list contamination) as the cause.
- **Full-corpus sentence embeddings** (ATS 9.24M + Reddit 21.3M + 18.58M
  rows) now exist on Kaggle for all three corpora, plus a validated
  3-tier "cascade" design (cheap embedding classifier -> distilled small
  model -> full reasoning LLM, only the last tier ever touches genuinely
  hard cases) — Tier 1 built and empirically validated, Tiers 2-3 designed
  but not built.
- **Local disk**: cleaned up from 14GB to 53GB+ free; canonical
  corpus files consolidated to one source of truth each and backed up to
  a Kaggle dataset (`tobiasnashws/conspiracycomments-canonical-corpus`).
- **Shared infra now exists and is live**: context-repo + wake-relay +
  unified-gateway, all on one Oracle instance, systemd-managed, not
  laptop-dependent. `context-repo`'s own GitHub repo is now public
  (secret-scanned clean first). Compute patchwork: Kaggle (4-5 accounts,
  fallback-with-real-quota-ranking built), GCP Cloud Run (3 accounts,
  was broken all session on a missing pip package, now fixed), GitHub
  Actions (registered, not yet actively used).
- **Not done, explicitly deferred/handed off**: GCP billing hard-stop
  (Pub/Sub + Cloud Function disabling billing on threshold breach) handed
  to a separate session/agent, not built here. Entity-coverage two-sided
  problem (top-down expert-list gaps, bottom-up NER noise) was
  investigated and designed but the actual Kaggle job was never built —
  paused for the infra work, still open.

## Update 2026-08-02 — stance retrain rounds 3-5, embedding-model test
## (negative result), graph-based topic structure design

**Read this before `task_notebook_and_repo_polish.md` at the top of
CLAUDE.md if picking up mid-session — that task is still correctly the
next thing to do before any push, this update doesn't change that.**

- **Stance classifier round3 regressed (0.4922 -> 0.4694), root-caused,
  rounds 4/5 launched to test the fix.** Round3 added 4,998 frontier-
  judge-scored boundary-confidence rows to the training set
  (`merge_boundary_expansion_round3.py`) but thresholded the continuous
  frontier_score with NO "other"/no-stance bucket (`>=0 -> endorsement,
  <0 -> hostile`) despite the judge's own prompt defining `0.0 = no real
  stance`. Confirmed real, not theoretical: median frontier_score across
  all 4,998 rows was exactly 0.0, 25.3% scored within +/-0.15 of zero,
  ALL force-labeled into a stance category regardless. `other`-class
  training share collapsed from ~19% to ~6.4%, stage1 `other` recall on
  val crashed to 32% (round2 baseline: 55%). Two fixes tested in
  parallel (no new judge calls, same 4,998 already-scored candidates,
  re-merged from the pre-round3 backup): `merge_boundary_expansion_round4.py`
  (deadzone |score|<0.15 -> other, recovers 1,171 rows) and
  `merge_boundary_expansion_round5.py` (exact score==0.0 -> other,
  recovers 968 rows, purer but smaller -- the score distribution
  clusters at discrete ~0.05 increments and 0.0 is a real spike, 19.4%
  of all rows, not an incidental continuum midpoint). Both kernels
  (`stance-retrain-corrected-round4`/`-round5` on Kaggle) were still
  RUNNING when this session ended -- **check their status and pull
  results before doing anything else with the stance classifier.**
  Compare both against round2's kappa=0.4922/other-recall=55% (the real
  bar -- round3's 32% was the bug, not a baseline to merely beat).
- **A more principled fix for future rounds, not yet built**: instead of
  inferring has-stance/no-stance from a continuous score's proximity to
  zero (lossy -- the val diagnostic showed real overlap, e.g. true
  `endorsement` rows scoring as low as 0.00), a two-part frontier-judge
  prompt (explicit STANCE/NO_STANCE question first, THEN a strength
  score only if STANCE) would give a genuine categorical answer instead
  of an inferred one. Needs new Vertex AI calls (~$3-5 order of
  magnitude for ~5,000 rows) -- scoped in conversation, not started.
- **Embedding-model test for reddit topic modeling: genuine negative
  result for Gemini, not an artifact.** Tested whether Vertex AI's
  `gemini-embedding-2` (3072-dim, paid) beats the current
  `all-MiniLM-L6-v2` (384-dim, free) for BERTopic clustering on the
  100k-row `train_topic_assignments.parquet` sample
  (`src/compare_embedding_models_for_topics.py`). First pass looked like
  a huge win (0.82 vs 0.50 mean cohesion) but that was a measurement
  artifact -- raw cosine similarity and a fixed near-duplicate threshold
  aren't comparable across embedding spaces of different dimensionality
  (confirmed: near-dup pairs went 446->5,565 under a naive >0.5
  threshold on the SAME docs). Fixed methodology (dual-condition near-
  dup check matching `audit_topic_quality.py`'s own centroid-sim-AND-
  keyword-jaccard convention, percentile-relative cohesion): MiniLM 97
  topics/0.0% outliers/76 near-dup pairs vs. Gemini's best config
  (UMAP n_neighbors=30) 86 topics/**51.9% outliers**/**3,318 near-dup
  pairs**. Swept `n_neighbors` (15/30/50) and `n_components` (5/10/20)
  and tried PCA-pre-reduction before UMAP -- none closed the gap.
  Intrinsic-dimensionality check (Levina-Bickel MLE) found both
  embedding spaces have nearly identical true manifold dimensionality
  (~15.4 MiniLM vs ~16.6 Gemini), ruling out "Gemini needs more UMAP
  output room" as the explanation. **Conclusion: don't pursue paid
  embeddings for the reddit topic model as a drop-in BERTopic
  replacement** -- the UMAP+HDBSCAN pipeline itself may be the wrong
  tool for a higher-dimensional embedding space, not fixable by tuning
  its existing knobs. Gemini embeddings cached locally
  (`data/processed/_gemini_embedding_comparison_cache.npy`, 100k x
  3072) so no re-embedding cost if this gets revisited.
- **New direction from the above: graph-based topic/discourse structure,
  not another embedding-space clustering attempt.** Two new design docs,
  neither started: `handoff/task_thread_structure_census_embedding.md`
  (the original "map the whole subreddit as a structure, not a sample"
  idea) and `handoff/task_graph_based_topic_structure.md` (the concrete
  mechanism -- nodes=comments, edges=reply-thread structure + semantic
  k-NN similarity + temporal/event alignment + author connectedness,
  Leiden community detection instead of UMAP+HDBSCAN; also floats
  comparing this bottom-up result against a top-down theory-driven
  semantic tree built from embedded category-prototype descriptions,
  since the existing `map_super_topics.py`/`topic_super_topic_mapping.csv`
  "Super_Topic" scheme turned out to be a hardcoded 44-of-97-topics
  manual dict, not a real reusable classifier -- 55% of topics fall into
  its "Other" catch-all). `src/extract_thread_metadata.py` (new,
  metadata-only -- id/parent_id/link_id/author/created_utc/subreddit/
  score, NO body text, reads directly from the raw
  `data/raw/r_conspiracy_comments*.jsonl*` archive so it doesn't need
  the full-text corpus that only lives on Kaggle) was running when this
  session ended -- check `data/processed/reddit_thread_metadata.parquet`
  exists and has sane thread-count/top-level-comment numbers before
  building on it.
- **Not done**: git push. 152 already-modified/untracked files were
  sitting in git status at the START of this session (predates it, not
  caused by it) -- flagged to Nash rather than committed/pushed, since
  it's a large diff without full context and conflicts with the
  standing "path-portability fix before next push" instruction at the
  top of CLAUDE.md, which is itself still marked done-but-uncommitted in
  `task_notebook_and_repo_polish.md`'s own status line. Sort out what
  that 152-file diff actually is before pushing anything.

## Pick this up first if picking up fresh (raised 2026-07-26)

**Highest priority, raised 2026-07-26 (later same day): bringing the
AboveTopSecret corpus (7.15M comments, ingested this session) to full
analytical parity with the reddit side.** This is not a side project —
ATS is the direct answer to the standing methodological critique that
r/conspiracy is too heavily moderated to generalize from; whether this
thesis can talk about "conspiracy communities" broadly rather than just
"r/conspiracy specifically" depends on this actually landing. Five
sibling task files, meant to be picked up as separate sessions, in
roughly this dependency order. **Update 2026-07-27: four of the five
now have real progress (two fully done, one done-pending-Nash, one
done) — read each task file's own status update rather than trusting
"not started" in its title, those are stale.**
1. `handoff/task_ats_entity_disambiguation.md` — **done.** Stage B/C
   disambiguation ran end-to-end against the full 7.15M-comment corpus
   (`--ats` flags added to the existing, already-validated pipeline
   scripts, not reimplemented). `data/processed/ats_entity_examples.parquet`:
   30,998 rows, 423 entity keys, schema-identical to reddit's. 953
   new/community-specific candidates flagged for Nash's review in
   `ats_new_candidates_review.csv` (blank `decision` column, per
   guardrail), not auto-decided.
2. `handoff/task_ats_stance_classification.md` — **steps 1-2 done, step
   3 blocked on Nash (not delegatable).** `src/classify_ats_stance.py`
   applied the already-established two-stage cascade model to all
   30,998 disambiguated mentions (endorsement 50.8%, hostile 42.4%,
   other 6.8% — entity-level breakdown looks face-valid, e.g. Assange
   88.3% endorsement matching the known reddit-side whistleblower
   pattern). A genuinely balanced 99-row blind quality-check queue is
   built and waiting on Nash to label
   (`data/hitl/queue_ats_stance_quality_check.csv`) before any ATS
   stance number can be trusted — same "not yours to decide
   unsupervised" pattern as every other stance-transfer-validity check
   in this project.
3. `handoff/task_ats_topic_modeling.md` — **in progress, two-phase
   plan.** Fit-new-vs-transfer decision settled empirically
   (`src/verify_ats_topic_transfer.py`: reddit model transfers poorly,
   see `ats_transfer_verification_report.md`). **Phase 1 (running now)**:
   ATS-only fit via `train_bertopic_ats_overlap.py`, explicitly an
   interim run to use the wait time, not the final answer. **Phase 2
   (later, once BTS is parsed)**: combined ATS+BTS(+AbovePolitics,
   reopened for inclusion) corpus — the reasoning is that reddit's own
   model trains on all of r/conspiracy including chitchat/banter, so
   excluding BTS/AbovePolitics (same "Above Network" community, same
   operator) would make ATS's population narrower than reddit's, not
   matched to it. One assumption to verify once BTS is parsed: whether
   BTS truly shares ATS's user base (checkable via exact-username
   overlap, not fuzzy matching) rather than just being run by the same
   operator.
4. `handoff/task_ats_engagement_normalization.md` — **done.**
   `src/compute_engagement_normalization.py` added a verified
   `engagement_z` column to both `ats_comments_final.parquet` (mean≈0,
   stddev≈1, all 7,147,196 rows) and `empath_scores_full.parquet`
   (21,349,908 non-null, matching the known deduped row count) —
   confirmed by direct query, not just the build log. One open
   question left for the unified-schema task: reddit was z-scored
   against the *pure* population's stats while ATS was z-scored against
   its *entire* corpus (no pure/unfiltered distinction on the ATS side)
   — worth deciding whether that asymmetry is acceptable before treating
   `engagement_z` as directly comparable across platforms.
5. `handoff/task_ats_unified_cross_platform_schema.md` — not started,
   depends on all four above; the assembly step, do it last.

**`handoff/task_entity_frequency_recount.md`** — found and verified
2026-07-26 (direct corpus queries, not guessed): entity mention counts
across the project are systematically undercounted, for two independent,
confirmed reasons — the bottom-up NER frequency pass only ever scanned
~12% of the long-comment corpus (by explicit design, documented in its
own docstring), and a separate ~18.6M-row short-comment corpus with its
own cache infrastructure was never unioned into the "full corpus" entity
regex extraction. Has exact reference numbers (independently verified,
not from any existing pipeline) that a rebuild must reproduce as a
verification gate — read that before touching entity counts, and don't
trust a rebuild that doesn't match them.

**`handoff/task_topic_quality_explorer_integration.md`** — the topic
quality audit and central-claim extraction (previously flagged as
in-progress) finished in a follow-on session; this doc covers how to
integrate that finished work into the live corpus explorer (topic merge
review queue, claim-or-no-claim as a human flag rather than a universal
render, a seed-claim probing tool, noise-topic residual detection) —
scoped 2026-07-26, ready to build, with one architecture decision already
made (seed-claim embedding runs on Nash's local machine on demand, not
live on the VM).

**`handoff/task_belowtopsecret_ingestion.md`** — **UPDATE 2026-08-02: this
section was stale and wrong — download AND parsing are both actually
complete, verified directly against the filesystem (not against either
of two conflicting prior status claims, both since corrected).** Site
relationship confirmed (official ATS sister board, same "Above Network"
operator) and archive coverage checked
(`handoff/bts_ingestion_scoping_findings.md`): collapses almost entirely
by 2010-2011, ~1.2M estimated posts. Original volume-gap rationale
(closing the post-2016 ATS-vs-reddit gap) is a no-go — BTS never
reaches 2016. **AbovePolitics is fully ingested and cleaned**: 67,634
comments (off-by-one from the previously-cited 67,633, negligible),
`data/processed/bts_abovepolitics_comments_final.parquet` — note this is
the correct filename, the `_cleaned` variant cited previously never
existed as a separate file (the clean step writes back to `_final`
directly, only a `_PRE_FIX.parquet.bak` backup exists alongside it).
**BTS itself: download is 100% complete** (82,462/82,462 pages in
`data/raw/bts_raw_html/`, confirmed by direct file count against
`bts_metadata.json`'s queue — not the 47,876/82,462 "58%" this doc
previously claimed). **Parsing is also done**:
`data/processed/bts_comments_final.parquet` (713,422 rows) and
`bts_comments_final_cleaned.parquet` (713,414 rows) both exist; the
8-row gap between them was checked directly (6 are clearly correct
drops — scraped user-profile/signature sidebar text misattributed as
post body; 2 look like plausibly-real content also caught by the
cleaning step) — negligible either way at 0.001% of rows, but noting it
rather than claiming the cleaned version is unambiguously perfect. Use
`bts_comments_final_cleaned.parquet` as the default.
**No further downloading or parsing needed — this task is ready for the
combined-corpus build step, not still blocked on ingestion.**
**Scope decision, 2026-07-27**: Nash decided to combine all three
"Above Network" boards (ATS+BTS+AbovePolitics) into one corpus for
topic modeling specifically — this now BLOCKS `task_ats_topic_modeling.md`
until BTS finishes. Not merged into any other ATS-parity task (entity/
stance/engagement) unless Nash says so separately.

## Done — reference only, not a task list anymore

**`handoff/task_corpus_explorer_live_backend.md`** and
**`handoff/task_topic_quality_and_claim_detection.md`** — both fully
built and verified as of 2026-07-26 (a follow-on Antigravity session
finished the backend/multi-rater/outlier-assignment work; another
finished the topic-quality calibration and claim extraction). Kept for
design rationale, not as open work — see the two docs above instead for
what's actually next.

## Update 2026-07-21 — large Claude Code session, all uncommitted

Everything below is real, tested, and mostly cross-validated, but **none
of it is committed** (`git status` shows 7 modified + 10 new `src/*.py`
files, plus this doc and two new `handoff/*.md` files). Review before
committing. Headline items, newest-first-logic dropped in favor of
grouping by topic since there's a lot:

- **Two real headline findings, both stress-tested hard:**
  1. **Consensus-expert stance is genuinely opposite-signed across
     subreddits, and it's robust.** Hostility toward consensus experts
     (Fauci, CDC, etc.) predicts *more* traction in r/conspiracy;
     endorsement of them predicts more traction in r/politics. Confirmed
     across THREE population definitions (r/conspiracy pure, r/conspiracy
     unfiltered, r/politics) and TWO stance-classifier generations, via
     TWO independently-built pipelines that landed on the same story.
     This is the most defensible number in the whole project at this
     point — see `data/processed/regression_results_with_stance.csv`.
  2. **The pooled `has_maverick` stance-traction instability is now
     mechanistically explained, not just noticed.** Per-entity breakdown
     (`src/per_entity_stance_breakdown.py`, `data/processed/per_entity_stance_breakdown.csv`)
     shows individual entities' hostility rates are STABLE across
     populations (Alex Jones ~85-86% hostile whether pure or unfiltered —
     **SUPERSEDED 2026-07-21, see `handoff/task_stance_endorsement_blindspot.md`:
     a 99-row hand-labeled quality check found the binary classifier
     couldn't reliably detect endorsement (38.9% held-out accuracy on its
     own confident-endorsing predictions). Rebuilt as a 3-class model
     (hostile/endorsement/other) using the previously-discarded
     neutral+ambiguous labels; Jones is now 73.0% hostile / 14.7%
     endorsement / 12.3% other (`per_entity_stance_breakdown_unfiltered.csv`),
     a materially different and more defensible number than 85.8% —
     endorsement is now a real, visible share instead of near-zero. Use
     the 3-class numbers going forward, not 85.8%**;
     Wikileaks ~2.7-3.0% hostile either way) — what changes is which
     entities dominate which population. Bigger finding underneath this:
     leak-source whistleblowers (Wikileaks 41,881 mentions, Assange,
     Snowden) are near-universally ENDORSED; media-personality mavericks
     (Jones, Tucker Carlson 92.5% hostile, Roger Stone, Matt Gaetz 97%
     hostile) are near-universally ATTACKED. **Not a prominence effect**
     — Wikileaks is more-mentioned than Jones and gets ~opposite
     reception (Spearman corr(mention_count, pct_hostile) = -0.08 for
     maverick, i.e. no relationship). Fauci is the consensus-side extreme
     outlier (98-99% hostile across every name variant, also the
     most-mentioned consensus figure — weak positive corr = +0.29 there).
     **Confirmed 2026-07-21 (later same day) against the actual maverick
     stance regression** (`data/processed/regression_results_with_stance.csv`,
     `maverick_stance_prob` = P(endorsement), so a negative coefficient
     means hostility drives traction): r/politics -4.35 (p<0.001,
     hostility -> more traction), r/conspiracy unfiltered +0.66 (p<0.001,
     endorsement -> more traction, opposite sign from r/politics),
     r/conspiracy pure -0.21 (p=0.29, **no signal**). The pure-population
     null is a compositional artifact, not evidence the mechanism
     disappears: per-entity `pct_hostile` is essentially flat between pure
     and unfiltered for both entity types (media personalities stay
     hostile-dominant: Jones 85.8%->84.9%, Tucker Carlson 92.5%->92.2%,
     Stone 82.2%->81.4%; whistleblowers stay endorsement-dominant:
     Wikileaks 2.7%->3.0% hostile, Assange 5.3%->6.3%, Snowden
     15.9%->15.6% — see `per_entity_stance_breakdown_pure.csv` alongside
     the unfiltered file above) but the **mix ratio shifts**: summing
     mentions for Jones/Tucker/Stone/Gaetz (media) vs
     Wikileaks/Assange/Snowden/Greenwald/Swartz variants (whistleblower),
     the media:whistleblower ratio is ~0.49 in unfiltered vs ~0.78 in
     pure — pure has proportionally more hostility-coded media mentions
     competing against the endorsement-coded whistleblower mentions,
     netting the pooled coefficient down to non-significant even though
     neither sub-population's per-entity behavior actually moved. Same
     shape as the consensus-expert cross-subreddit story, but running
     through population composition rather than a true within-population
     sign flip. Not yet written up as its own task file — do that before
     citing the pure-population maverick-stance null as "no effect" in
     the thesis, since it isn't one.
- **Entity list further fixed**: dropped bare `"Brand"` alias entirely
  (0/57 hand-checked instances were Russell Brand); moved
  `"Ventura"/"Hancock"/"Kory"` (maverick) and `"Hawking"` (consensus) out
  of blind bare-form matching into the Stage B/C per-instance
  disambiguation machinery (generalized, now has 4 new clusters:
  `hawking`, `ventura`, `hancock`, `kory`, alongside the existing 15).
  Also fixed a silent case-sensitivity bug in `_duckdb_regex_mask()` (DuckDB's
  `regexp_matches` doesn't inherit Python's `re.IGNORECASE`, was
  undercounting lowercase mentions project-wide until an explicit `(?i)`
  prefix was added). Post-fix pure-population numbers:
  `has_maverick` r/conspiracy +0.274 (was +0.248), r/politics +0.371;
  `has_consensus_expert` r/conspiracy +0.563 (was +0.528), r/politics
  -0.373 (n.s., p=0.122, was -0.158) — **cleaning the contamination made
  every real effect STRONGER, not weaker**, i.e. the noise was diluting
  real signal, not creating a false positive.
- **`run_integrated_regressions.py` ("Grand Synthesis") is now fully
  wired and completed a full run**: corrected entities, the 5-tier link
  source-quality taxonomy (`link_mainstream_reliable` /
  `mixed_or_low_reliability` / `aggregator_or_platform` / `unmatched_link`,
  replacing flat `has_link`), `hs_prob` (hedged_suspicion, already
  two-pass-filtered per `src/score_hedged_suspicion_full.py`), and
  mention-only stance sub-models (`src/run_stance_submodels_only.py`).
  Outputs: `synthesis_regression_results_corrected.csv`,
  `_filtered_clustered.csv`, `synthesis_interaction_results_corrected.csv`,
  `synthesis_stance_submodels.csv`. **This is the r/conspiracy-only
  Unfiltered-population grid (16.7M rows), stratified by elasticity
  tercile x insider-presence threshold — do not confuse its numbers with
  `rerun_refined_regressions_v2.py`'s pure-population numbers above,
  they're deliberately different populations, see the stance findings
  above for why that distinction matters.** Hit two real OOM kills on
  this 8GB-RAM machine before landing (exit 137 twice) — root causes
  fixed both times: (1) don't select full `text` for a 16M+-row
  population, fetch text only for the small subset that needs it
  (has_link / has_maverick / has_consensus_expert rows); (2) don't hold
  that text in memory through the whole run, free the link-tier text
  immediately after use and only carry forward the much-smaller
  mention-text subset. Both fixes are now standard patterns in every
  script that touches the full/unfiltered corpus — copy them, don't
  reintroduce the anti-pattern.
- **Stance classifier**: `src/train_stance_classifier.py`, 5 rounds of
  active-learning uncertainty sampling
  (`src/build_stance_active_learning_queue.py`, rounds 2-5,
  `queue_maverick_stance_round{2,3,4,5}.csv`) plus a redesign from
  whole-comment-text TF-IDF to entity-focused text windows
  (`src/stance_window_utils.py`, +-15 words around the target entity,
  same convention as the existing Stage B/C disambiguation windowing).
  Kappa improved 0.287 -> 0.345 across rounds (mostly from the windowing
  fix + round 5, not a steady monotonic climb — rounds 2-4 were mostly
  noise at this sample size). **Multi-entity comments now get split into
  one queue row per entity** (`comment_id` vs `id` columns,
  `target_entity` shown to the rater) instead of one row with every
  entity highlighted at once and no way to tell which the rating targets
  — this was a real usability bug found via Nash's round-3 feedback, see
  `src/build_stance_active_learning_queue.py`'s docstring for the full
  fix history (also fixed: duplicate-content/copypasta spam inflating a
  small round's sample, and lookup-resolved bare-form rows showing zero
  highlight).
- **`appeal_to_authority`/`source_citation` (dormant constructs found via
  the methods audit, see below) resurrected and validated**:
  `src/score_authority_appeal_full.py`. **`source_citation` is solid**
  (5-fold CV kappa=0.655, AUC=0.859, local TF-IDF+LogisticRegression, no
  LLM calls) — scored against `research_corpus_enriched.parquet` (4.78M
  rows, the Stage-1-filtered population this project already built for
  exactly these two constructs). Striking result: of ~3M high-scoring
  comments, **97.8% match NEITHER `has_maverick` NOR
  `has_consensus_expert`** — most "cites something as authoritative"
  behavior in this corpus is invisible to the entity-based measures.
  **`appeal_to_authority` FAILED validation** (kappa=-0.018, worse than
  chance, predicted the negative class for everything) — its training
  labels were already known-noisy (see `data/processed/classifier_performance_summary.csv`,
  LLM-batch-label-vs-human kappa=0.323) and the small positive class
  (65/422) made it unlearnable. **Do not use `appeal_to_authority` for
  anything until it gets better training data.**
- **URL/citation-content investigation** (Nash's redirect from
  domain-level to specific-piece-and-author-level analysis, motivated by
  the "credentials problem" research question): `src/rank_cited_urls_by_author.py`
  ranks actual cited URLs by DISTINCT AUTHOR COUNT (not raw mentions) —
  despam-by-construction, since one person reposting the same link many
  times (confirmed real case: `Ok_Cartographer_6947` posted an identical
  comment across 5 threads in a 3-minute window) counts once, not N
  times. Output: `data/processed/cited_urls_ranked.csv` (1.76M distinct
  URLs). Fixed two real bugs found while curating the top of this list:
  scheme/trailing-slash splitting (ae911truth.org was wrongly two rows,
  139+116, merged to its true 313), and a regex bug truncating any URL
  containing a literal `(` at the first paren (silently merging
  DIFFERENT Lancet papers, whose URLs use PII codes with parens, under
  one wrong truncated identity — this one was a real data-integrity risk,
  not cosmetic). **Known remaining gap, not fixed**: DOI-path
  letter-casing (`nejmoa2034577` vs `NEJMoa2034577` are the same paper,
  split into two rows) — undercounts rather than wrongly-merges, lower
  severity. Top ~50 entries hand-curated and verified (mix of Claude's
  general knowledge + Nash directly checking anything uncertain/blocked
  by bot-detection) in `handoff/cited_content_curation_step2.md` — real
  finds include a 2002 pre-scandal Epstein profile, the Pfizer
  Ventavia-trial whistleblower story, a Microsoft patent being
  misattributed to coronavirus/vaccine tracking, and confirmed
  individual-platform citations (corbettreport.com, benjaminlcorey.com)
  that pure domain-level analysis had missed entirely. **Not yet done**:
  turning this into an actual regression variable / comparative finding
  — see `handoff/task_credentials_problem_integration.md`.
- **Methods provenance audit**: `handoff/methods_provenance_audit.md`
  (607 lines) — traces every real construct in the project back through
  ~22 legacy notebooks and ~85 commits to where it actually originated.
  Found real dormant work never ported to `src/`: `insider_ethos`
  (community-tenure-as-trust-heuristic, well-specified prompt, never
  built) and `reasonableness_performance` (name/prompt seen, not
  explored further) from an earlier 3-pass Vertex AI Gemini cascade —
  almost certainly the source of the documented $100 budget blowout.
  Also corrected a stale claim in `handoff/task_notebook_and_repo_polish.md`
  (the missing-section-headers issue it describes was already fixed by
  a later commit series).
- **AI-vs-human agreement check** (a substitute for true inter-rater
  reliability, which needs a second human Nash hasn't recruited yet):
  Claude blind-rated 40 already-rated stance rows and 25
  `source_citation` rows, committed ratings BEFORE seeing the true
  labels, then scored agreement. `source_citation`: kappa=0.884,
  96% exact match — higher than the trained classifier's own CV kappa
  (0.655), meaning the construct is very learnable and the classifier
  has headroom. Stance (hostile-vs-endorsement subset, n=21): kappa=0.422,
  71.4% agreement — also higher than the trained classifier's kappa
  (0.345), but only "fair" agreement in absolute terms, meaning stance
  has real inherent fuzziness even between two careful raters, not just
  classifier weakness. Specific, actionable pattern in the disagreements:
  Claude under-called "endorsement" for tonally-flat/factual citations
  that functionally back the commenter's argument (the codebook counts
  function over tone; Claude's default reading didn't). Not written up
  as a formal task file yet — do that before citing this in the thesis
  methods section.
- **8GB RAM is a real, recurring constraint on this machine.** Every OOM
  hit this session (3 total, across two different scripts) came from the
  same root cause: loading full comment `text` for a population in the
  millions-of-rows range and holding it for longer than immediately
  necessary. The fix pattern is now established (fetch text only for the
  small subset that needs it, free it as soon as that subset is
  processed) — apply it proactively to any new script touching the
  16.7M-row Unfiltered population or the 4.78M-row enriched corpus,
  don't wait to hit the OOM first.

**Update 2026-07-21, later same day (separate Claude Code session, not
Antigravity): stance classifier quality-checked and partially fixed, see
`handoff/task_stance_endorsement_blindspot.md` for full detail.** Short
version: built a 99-row hand-labeled quality-check queue for the Alex
Jones per-entity finding above (85.8% hostile) and found the classifier
is solid on confident-hostile predictions (87.5% held-out accuracy) but
badly unreliable on confident-endorsing ones (38.9% accuracy, worse than
chance -- reproduced in a second, totally separate population too, so
it's a real property not a training-sample fluke). Fixed two real bugs
this exposed (quote-stripping so a quoted stranger's words aren't
attributed to the commenter; a list/link-dump Stage-1 filter for
citation-dump comments with no real evaluative content), retrained the
classifier (kappa 0.345->0.352), and built (but did not label) an
active-learning round targeting the endorsement blind spot specifically.
Also built and indexed the ~18.6M-row short-comment (<=100 char)
population that's never been touched by anything in this pipeline --
`Paths().short_comments` in `utils/file_paths.py`. **Don't cite the
85.8%-hostile Jones number to that precision without reading the task
file first** -- the fresh ground truth here suggests the real rate is
likely closer to 76-80%.

**Update 2026-07-20, later same day: both of the sessions mentioned below
are now substantially done, uncommitted.** The r/politics crawl finished
(140,824 rows, all 20 months), rescoring and both `rerun_refined_regressions_v2.py`
and `run_link_source_tier_regressions.py` reran against it — only
`run_core_comparison_robustness.py` still needs a rerun (code's fixed,
output's stale). The maverick Stage B/C extension was built and run
(9 new clusters, classified output exists, wired into
`combined_maverick_detector.py`). All 3 new HITL stance queues
(`queue_maverick_stance.csv`, `queue_consensus_stance_politics.csv`,
`queue_maverick_stance_politics.csv`) are built AND rated by Nash. See
`handoff/task_fix_stale_politics_pipeline.md`,
`handoff/task_maverick_entity_disambiguation.md`, and
`handoff/task_stance_queues_expansion.md` for current detail — their
status headers were stale until this update, don't trust status text
elsewhere (e.g. exported summaries) that predates it. **Two bare-form
entity aliases (`"Brand"`, `"Hawking"`) were found producing noise
during queue rating** — Nash is examining/fixing, may rerun affected
queues; see `task_stance_queues_expansion.md` for detail. None of the
above is committed yet.

Original note, kept for context: two sessions were in flight (2026-07-20,
~2:30pm), both touching `rerun_refined_regressions_v2.py`,
`run_link_source_tier_regressions.py`, `run_core_comparison_robustness.py`,
and `combined_maverick_detector.py` — the concurrent-write risk that
motivated checking `ps aux` before launching either task no longer
applies now that both have landed, but if you're the one running
`run_core_comparison_robustness.py` to close out the remaining step,
still check nothing else is writing to its outputs first.

## Static site export pipeline (read this before touching HTML export/output-visibility)

The notebook has **three** artifacts, not two — easy to miss, and missing
it once already cost a wasted from-scratch reimplementation attempt
(2026-07-21) before this section existed:

1. **`ConspiracyMaster_Refactored.ipynb`** — source of truth. Code cells
   carry `metadata.jupyter.source_hidden = True` (an established
   convention, not something new) so Jupyter/VS Code/GitHub's native
   `.ipynb` viewer shows them collapsed-but-expandable. This metadata is
   cosmetic only for the live-viewer case — it has **no effect** on
   either HTML export below.
2. **`ConspiracyMaster_Refactored.html`** — a plain, unstyled
   `jupyter nbconvert` intermediate output, committed but not meant to
   be read directly. Regenerate with:
   ```bash
   jupyter nbconvert --to html --embed-images ConspiracyMaster_Refactored.ipynb
   ```
3. **`docs/index.html`** — **the actual public artifact**, served via
   GitHub Pages at the custom domain **https://kahatahi.co.nz/ConspiracyComments/**.
   Built from (2) by `scripts/postprocess_notebook_html.py`, which (all
   via BeautifulSoup DOM manipulation on the nbconvert 'lab'-template
   output, no custom JS toggle, no `TagRemovePreprocessor`):
   - wraps every code cell's input in a native `<details><summary>Show
     code</summary>...</details>` — collapsed by default, one click per
     cell to reveal, no tags/metadata needed since it operates on cell
     structure directly (`div.jp-CodeCell div.jp-Cell-inputWrapper`);
   - wraps every H2/H3/H4-headed section into **nested** collapsible
     `<details class="section-collapse">`, mirroring Jupyter's
     "collapsible headings" — note H1 is deliberately excluded (treated
     as document title, not a section) and stays always-visible, which
     is also why a from-scratch headline section should use H1 for
     itself, or be positioned so nothing depends on it opening/closing
     a stack level unexpectedly (see the Section -1 fix below);
   - wraps any output over 2,000 characters in a 350px scrollable box;
   - auto-builds a clickable, nested **table of contents**, inserted
     right after the *first* `<h1>` found in document order — inserted
     via JS that also auto-expands collapsed ancestor `<details>` on
     click before scrolling to the target;
   - applies a dark-mode-aware clean-documentation stylesheet (GitHub
     Pages strips most inline HTML styling, so don't rely on it for
     anything the postprocessor doesn't already handle).

   Regenerate with:
   ```bash
   jupyter nbconvert --to html --embed-images ConspiracyMaster_Refactored.ipynb
   python3 scripts/postprocess_notebook_html.py ConspiracyMaster_Refactored.html docs/index.html
   ```
   Always regenerate **both** files together, in that order, after any
   notebook edit intended to reach the public site — editing (2) alone
   does nothing for the live site, and editing (3) directly is
   pointless, it gets clobbered on the next regen.

**Gotcha hit and fixed 2026-07-21**: giving a new top-of-notebook
section its own `<h1>` (to make it visually match the document title)
breaks the TOC-insertion logic, since it picks the *first* `<h1>` in
the document — if that's now your new section instead of the real
title, the TOC lands in the wrong place. The eventual fix (Section -1,
see the task-index row above) was to let it stay `<h1>` deliberately
*because* that produces the desired final order (findings section →
TOC → title/pipeline block) — but this was arrived at by testing in a
real browser, not by reasoning about the script's stack logic in the
abstract; if you're rearranging top-level sections, verify the actual
rendered DOM order (`main.children` in a JS console, or just look),
don't assume from the source order.

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
   enough — that decision belongs to Nash/Claude, not Antigravity. **This
   explicitly covers finding an expected input file missing.** If a file
   a script needs isn't where you expect (e.g. it was deliberately moved
   aside by a prior task that's mid-flight), stop and report the blocker
   — do not restore an old backup or otherwise route around it to keep
   going. Confirmed 2026-07-20: a session did exactly this (silently
   copied a `_pre_expansion` backup back over the live path when the
   real file was missing), which caused three later, otherwise-correct
   scripts to silently run on stale data with no error and no visible
   sign anything was wrong — see `handoff/task_fix_stale_politics_pipeline.md`.
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
- **`has_maverick` construct validity: contamination FIXED (2026-07-20),
  recall problem found and NOT yet fixed (same day).** The old
  `maverick_authority` raw bucket (418 entities, ~25.1% of corpus matches
  were topic-noise like "New World Order"/"Deep State"/"Conspiracy
  Theory", no person or organization) has been replaced by
  `src/maverick_authority_verified.py` — Nash hand-reviewed the full
  446-entity `maverick_candidate_entities_scored.csv` directly (scoring
  criterion: organizations count too, e.g. AE911Truth; platform-driven
  commentators count too, e.g. Alex Jones/Rogan/Tucker Carlson,
  deliberately not disentangling opinion/research for now), wired into
  `load_entities_split_corrected()` (canonical definition + 5 importing
  scripts + a duplicate copy that got consolidated) and into
  `combined_maverick_detector.py` (the attribution-scorer's own,
  independently-contaminated entity source). Effect confirmed: the
  qualifying `has_maverick==1` population dropped from 36,116 to 21,041
  comments when the maverick-stance HITL queue was regenerated with the
  clean list.
  **But this surfaced a bigger, opposite-direction problem**: the
  verified list is almost all full names ("Edward Snowden"), and ~99%
  of multi-word entries (442/443) have no bare-surname/nickname/partial
  form ("Snowden") — confirmed to be undercounting real citations
  severely (86 of 90 human-labeled positive attribution examples in the
  validation queue had *zero* entity match at all). Fixing this isn't a
  simple list edit — it needs the same per-instance disambiguation
  machinery already built for the mainstream-expert side (Stage B/C,
  see `handoff/task_maverick_entity_disambiguation.md`) extended to the
  maverick domain, since some bare forms are genuinely ambiguous (a
  shared first name across two different real people, e.g. the existing
  `hunter` cluster) and can't just be added to the regex unconditionally.
  Every `has_maverick` coefficient below should be read as "contamination
  fixed, still an undercount" until that lands.
- **Current core regression numbers** (`src/rerun_refined_regressions_v2.py`,
  re-verified 2026-07-20 against the fully deduped corpus, pure
  r/conspiracy population N=1,968,864 — down from the old, duplicate-
  inflated 1,985,823, coefficients moved by <0.01, not a substantive
  change; **`has_maverick` numbers specifically are provisional, see
  above**): `has_maverick` +0.248 (p<0.001), `has_consensus_expert`
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
- **Trump-era vs. classical-conspiracy topic split: DONE (2026-07-20),
  redone after the first attempt's review gate turned out to be a no-op**
  (blank `confirmed` cells passed through as approved — fixed). Term
  list actually reviewed this time: dropped `trump`, `biden`, `hunter
  biden`, `burisma`, `fake news` (70% of the original trump_era match set
  was these alone) and `aliens`, `alien`, `dallas`, `nasa` (immigration/
  city-name/routine-news collisions). Current, trustworthy result in
  `data/processed/trump_vs_classical_regression_results.csv`: classical
  N=35,179, trump_era N=13,253 (down from the contaminated 49,118/44,876
  — that drop *is* the fix, not a problem). Classical `ps_prob`
  (procedural-skepticism) penalty is robust, survives Bonferroni
  before and after cleaning. The classical `has_maverick` "premium"
  lost even naive significance after cleaning — was likely an artifact
  of the contamination, don't cite it. `has_consensus_expert` newly
  reaches naive significance in cleaned classical (wasn't there before)
  but is now completely untestable in trump_era — that stratum's
  coverage loss dropped it below the sparsity threshold everywhere.
  Trump_era's "flat profile" for maverick/canonical-expert/procedural-
  skepticism still basically holds; its most robust surviving finding
  now is a `has_link` penalty (Bonferroni-significant, pooled and
  pre-ban). Do not cite the original walkthrough at
  `/Users/nash/.gemini/antigravity/brain/c67f482a-0056-4ddd-a994-286b7b505769/walkthrough.md`
  — superseded by the above. Full history and one open loose end
  (possible Logit-vs-OLS Bonferroni-labeling inconsistency in the
  script, not yet checked) in `handoff/task_trump_vs_classical_topic_split.md`.
- **r/politics data pipeline: silently stale, needs redo (found
  2026-07-20).** The sample-expansion crawl never finished (6 of 20
  months got zero or badly-short results), and a later session found the
  scored parquet missing (correctly moved aside mid-expansion) and
  silently restored the old `_pre_expansion` backup instead of stopping
  — confirmed via matching md5s. Three downstream scripts
  (`rerun_refined_regressions_v2.py`, `run_link_source_tier_regressions.py`,
  `run_core_comparison_robustness.py`) all inherited the stale N=30,881
  r/politics sample with no error or visible sign anything was wrong;
  their r/conspiracy-side numbers are unaffected and fine. Also found and
  fixed in passing: a dict-key bug in `run_core_comparison_robustness.py`
  that made `politics_overlap_excluded_comparison.csv` show identical
  values in every row (silently fixed, needs rerunning), a `../`
  path-prefix regression in `src/hitl_rater.py` that broke the documented
  invocation (fixed, verified via smoke test — the `maverick_stance` and
  `consensus_stance` queues both load correctly now), and a separate
  session's "audit" that "corrected" the author-overlap figure from
  2,387 to 249 authors — that correction is itself wrong (traced to a
  recency-window artifact in how `author_subreddit_footprints_async.csv`
  was crawled; the original 2,387 figure is the methodologically sound
  one). Full detail and fix plan: `handoff/task_fix_stale_politics_pipeline.md`.
  One genuinely new, unaffected finding survives from this batch of work:
  `data/processed/refined_regression_results_v2_clustered.csv`'s
  r/conspiracy-side numbers show the `ps_prob` (procedural skepticism)
  finding drops from p<0.001 (naive) to **p=0.053 (clustered by author)**
  — right at the edge of significance once a handful of prolific
  authors' influence is accounted for. Worth a close read before citing
  `ps_prob` as settled.
- **Master notebook (`ConspiracyMaster_Refactored.ipynb`) is frozen
  before essentially all of the above** — no r/politics control, no
  corrected consensus list, no stance resolution, no topic/era
  stratification, no source authority, no dedup fix appear in it. Its
  HTML export is stale even relative to the notebook itself. Needs new
  sections (10+) presenting the already-computed CSVs above, not a
  rebuild — see `handoff/task_notebook_and_repo_polish.md`.

## Open task files — pick one, read it fully, do only that one

**Newest first — these are the priority queue as of 2026-07-21, with one
2026-07-28 addition at the top (everything below it is still accurate,
just not the most recent thing to read first):**

| File | What it is |
|---|---|
| `handoff/task_2026-07-28_session_wrapup.md` | **New (2026-07-28), read this first if picking up fresh.** Full detail behind the "Update 2026-07-28" summary above — entity-stance classifier reliability finding, cascade design, shared infra (context-repo/wake-relay/gateway) now live on Oracle, compute patchwork status, and everything explicitly deferred/not-yet-built. |
| `handoff/task_media_personality_and_byline_review.md` | **New (2026-07-28), not started.** The whistleblower-vs-media-personality contrast is asymmetric (124-entity reviewed category vs. 4 hardcoded names); byline extraction's "100% precision" claim was validated against the same 30 rows it was fixed against, and a known bug still appears twice in the real output. |
| `handoff/task_citation_coverage_expansion.md` | **New (2026-07-28), not started.** Under 1% of citations are human-verified on either platform; concrete, no-new-labels-needed next step is extending the already-validated byline extractor to more URLs by volume. |
| `handoff/task_multi_entity_quality_check_queues.md` | **New (2026-07-21), not started, safe for Antigravity.** Generalizes the Jones quality-check queue builder to Wikileaks/Assange/Snowden/Greenwald — Nash's specific worry is that their high endorsement numbers (67-88% under the 3-class model) could have the same sarcasm/mockery blind spot the Jones check found ("limited hangout" accusations read like the "gay frogs" mockery pattern). Queue-building only, no labeling. |
| `handoff/task_short_comment_quality_check_queue.md` | **New (2026-07-21), not started, safe for Antigravity.** Same generalization, pointed at the newly-indexed short-comment (<=100 char) corpus instead of an entity — checks whether stance detection holds up on much shorter, lower-context text before any decision to extend the core regression to that population. Queue-building only. |
| `handoff/task_extend_citation_curation.md` | **New (2026-07-21), not started, safe for Antigravity WITH the guardrails read carefully** (real identification judgment per row, not pure mechanical transformation — explicit "flag uncertain, don't guess" instruction included given the self-graded-audit overclaiming problem found in `task_project_inventory_corrections.md` this same day). Extends `cited_content_curation_step2.md`'s top-~55 cited-URL table another ~100 rows down the tail. |
| `handoff/task_stance_endorsement_blindspot.md` | **New (2026-07-21, later same-day session), quality-checked + partially fixed, next step ready but needs a human label pass.** Fresh 99-row hand-labeled quality check found the stance classifier is good at confident-hostile (87.5% acc) but bad at confident-endorsing (38.9% acc, worse than chance) for Alex Jones specifically, reproduced in a brand-new short-comment population too. Quote-stripping + list/link-dump Stage-1 filter already built and applied (classifier retrained, kappa 0.345->0.352); active-learning round 6 targeting the blind spot is built (`queue_maverick_stance_round6.csv`, 105 rows) but not yet labeled. Also ships a new short-comment (<=100 char) corpus index, `Paths().short_comments` -- the ~18.6M-row population never before touched by any classifier in this project. |
| `handoff/task_credentials_problem_integration.md` | **New, not started.** The actual "credentials problem" research question is still open — everything so far (per-entity breakdown, `source_citation`, URL curation) is scaffolding, not yet assembled into the comparative finding (does anti-consensus/conspiracy-position sourcing lean on differently-credentialed sources than consensus-aligned sourcing, not just less-cited-by-name sources). See the 2026-07-21 update above for what's already built to reuse. |
| `handoff/task_entity_fixed_effects_regression.md` | **New, proposed not executed.** Would make the per-entity finding (leak-source whistleblowers endorsed, media-personality mavericks attacked) quantitatively rigorous via entity fixed-effects instead of just descriptive tables. Nash said "could do, idk" — genuinely undecided, worth revisiting. |
| `handoff/task_topic_era_rerun_corrected_constructs.md` | **New, not started.** The Bonferroni-corrected topic/era analysis (see below, "done 2026-07-20") is now stale relative to today's entity-list fixes, link source-tier taxonomy, and hedged_suspicion — needs a rerun with corrected constructs, keeping the Bonferroni correction intact. Do NOT merge this into `run_integrated_regressions.py`'s elasticity/insider grid — different, deliberate design tradeoff, see the 2026-07-20 conversation history for why (sparsity + multiple-comparisons integrity). |
| `handoff/task_irr_writeup_and_next_round.md` | **New, partially done.** Claude did a blind AI-vs-human check (stance kappa=0.422, source_citation kappa=0.884, both above their respective classifiers — see 2026-07-21 update above) but it's not written up formally, and true human-vs-human IRR (a second rater) is still unaddressed — that's a resourcing decision, not something to delegate. |
| `handoff/task_maverick_entity_disambiguation.md` | **Done (2026-07-21), superseding the 2026-07-20 "nearly done" note below.** The `"Brand"`/`"Hawking"` bare-form noise this task file used to flag as "under investigation" is now fully resolved — Brand dropped, Hawking/Ventura/Hancock/Kory disambiguated via the generalized Stage B/C pipeline (19 clusters total now). See the 2026-07-21 update above for the before/after regression numbers. |
| `handoff/task_maverick_authority_list_cleanup.md` | **Done** (2026-07-20) — see current-state section above. |
| `handoff/task_fix_stale_politics_pipeline.md` | **Done (2026-07-21).** Crawl finished (140,824 rows, all 20 months), rescored, all regressions rerun against it multiple times over the course of 2026-07-21's work (pure population, unfiltered population, 3-way stance comparison all use this sample). |
| `handoff/task_expand_politics_control_sample.md` | **Done**, see `task_fix_stale_politics_pipeline.md`. Kept for original design rationale only. |
| `handoff/task_stance_queues_expansion.md` | **Done** (2026-07-20/21) — all base queues rated, plus 4 additional active-learning rounds (see 2026-07-21 update above). The `"Brand"`/`"Hawking"` noise this file flagged is resolved, not just "under investigation" anymore. |
| `handoff/task_core_comparison_robustness.md` | **(A) and (B) both done (2026-07-21, session `69436207`, missed in this doc until 2026-07-24).** Interaction test: `has_consensus_expert:subreddit[politics]=-0.949, p<0.001`; `ps_prob:subreddit[politics]=-0.666, p<0.001`. Overlap-exclusion rerun against the *expanded* r/politics sample (140,824 rows): 7,194 overlap authors (12.84%, not the pre-expansion 2,387/16.14%), residual N=118,318, core finding robust (`has_consensus_expert` -0.373->-0.399, still n.s. either way). See `data/processed/politics_overlap_excluded_comparison.csv` / `data/processed/subreddit_interaction_results.csv`. Being rerun again 2026-07-24 as a reproducibility check against current data. |
| `handoff/task_clustered_standard_errors.md` | **Done** — `run_integrated_regressions.py` fits naive/thread-clustered/author-clustered cov types for every cell (see `_filtered_clustered.csv`), same pattern already used in `refined_regression_results_v2_clustered.csv`. |
| `handoff/task_source_authority_regression_wiring.md` | **Done (2026-07-21).** `has_link` replaced by the 5-tier `link_source_tier` taxonomy in `run_integrated_regressions.py`, using `source_authority_scores.csv` + `run_link_source_tier_regressions.py`'s domain-classification logic. See 2026-07-21 update above for the aggregator/platform penalty finding. |
| `handoff/task_trump_vs_classical_topic_split.md` | **Done** (2026-07-20) — redone with an actually-reviewed term list after the first attempt's review gate turned out to be a no-op. See current-state section above for the result and what changed. One open loose end: possible Logit-vs-OLS Bonferroni-labeling inconsistency in the script, not yet checked. |
| `handoff/task_general_epistemic_style_test.md` | Test whether the topic-null result reflects a general "monological belief system" epistemic style rather than topic-specific content, via an author-level (not comment-level) regression using `user_topic_specialization.csv`. Needs the framing read carefully before building, but mechanical once scoped. |
| `handoff/task_notebook_and_repo_polish.md` | **Done (2026-07-21), uncommitted like everything else in this batch.** Path portability (Part 4) turned out to already be fixed (`65885c6`, 2026-07-18) — verified, not redone. Dormant-work audit (Part 1) done via `methods_provenance_audit.md` cross-reference: confirmed `insider_ethos`/`reasonableness_performance` genuinely absent from the notebook, §9.10 flagged stale (pre-dedup-fix, pre-verified-entity-list) with an inline pointer to the corrected numbers, §3 spaCy section left as-is (already self-caveated, a real methods-history section not silently dormant). Notebook restructured: new **Section -1** headline-findings TL;DR (stance sign-flip, entity-type split + compositional explanation, link-tier taxonomy, `source_citation`, open next-steps) sits before everything else, including the document title — deliberately numbered -1, not 0, since "0. Imports and File Paths" already owns that number; new **Sections 10-14** present the entire 2026-07-21 batch (previously nowhere in the notebook) reading cached CSVs per the notebook's existing convention, not inlining computation. Added missing summary-CSV dumps to `score_authority_appeal_full.py` and `train_stance_classifier.py` (the latter also gets a new round-over-round active-learning kappa curve, 0.301→0.345, cleaner than the previously-cited 0.287→0.345 since it's methodologically consistent across all rounds). README.md expanded with the stance/link-tier/credentials findings and pointers into the new sections (Part 3), plus documents the export pipeline (see new subsection below). **Not done**: no cells with existing output were re-run (per explicit instruction — reorg/renumber only), so this is a structural + narrative pass, not a refresh of every number. **Correction to an earlier version of this row**: initially tried a from-scratch `TagRemovePreprocessor`/global-JS-toggle approach to hiding code in the HTML export, not realizing an established pipeline for this already existed (`scripts/postprocess_notebook_html.py`, live at kahatahi.co.nz — see "Static site export pipeline" below) — discarded that approach and used the existing one instead once Nash pointed at the live site.
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
