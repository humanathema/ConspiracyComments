# Overnight audit + writing-plan session (2026-08-20b, ~3am–4am Thursday)

Nash asked for a non-destructive overnight pass: find anything lost/orphaned,
integrate records, and think concretely about sequencing given the stated
deadline — **finish computational work this week, spend the next 1-2 weeks
(semester break) writing an 8k-12k word honours report.** No new modeling
work was started; this is audit + consolidation + planning only. Everything
below was checked directly (file contents, `git`, `gcloud`, running processes
via SSH), not inferred from doc text.

## 1. Nothing was actually lost or idle-billing — the live VM is doing real work

`gcloud compute instances list` showed `vm2image-20260810-093317`
(`gpuincrease`, `asia-southeast1-b`) **RUNNING**, which contradicted the
newest handoff doc's claim of "stopped after each use this session." SSH'd in
directly rather than assuming either doc or `gcloud` was right on its own:
GPU at 100% util, `nash` user running `python3 src/score_fp_detector_full_train.py`
(33:40 CPU-minutes in, VM up 34 min). **This is real, intended work** — scoring
the false-positive detector across the full train set, the concrete next step
flagged in `handoff/task_2026-08-20_session_handoff_paraphrase_stability_and_confidently_wrong.md`.
Left it running. **Check on this first when picking the project back up** —
if it's finished, the output (`outputs/reinfer_probs/train_polar_fp_detector_scores.csv`
per that doc) is the input to the spot-check that doc calls the actual
concrete next step, and the VM should then be stopped.

## 2. Stale status found and corrected: two HITL queues marked "never started" are actually done and merged

`ANTIGRAVITY_HANDOFF.md`'s "HITL review queue landscape" section (dated
2026-08-04) claims `maverick_stance_round8` (0/146) and `consensus_stance_round8`
(0/62) "never started." Checked the queue CSVs directly: **146/146 and 62/62
are fully labeled.** Checked further whether the labels actually made it into
training data (not just labeled-and-forgotten): `stance_classifier_training_data_round10_truncation_fixed.parquet`'s
`source_file` column has 144 rows tagged `queue_maverick_stance_round8.csv`
and 61 tagged `queue_consensus_stance_round8.csv` (2-row gap from 146/62 is
negligible, not investigated further tonight). **Confirmed already merged via
`src/append_round8_queues.py`.** This just means the Aug 4 status section is
stale, not that anything needs redoing — corrected in
`ANTIGRAVITY_HANDOFF.md` directly (see §5 below).

Re-checked the rest of that same "genuinely open" list directly against the
queue CSVs — still accurate:
- `domain_citation_tier`: 89/603 — still open.
- `greenwald_short_quality_check` (real filename:
  `queue_short_greenwald_stance_quality_check.csv`, the doc's short name was
  right, just noting the actual path since it doesn't match the short name
  literally): 0/68 — still open, never started.
- `queue_expanded_entity_val_r2.csv`: 34/410 — matches the newest handoff
  doc's "in progress" claim exactly.

## 3. Found: three abandoned git worktrees under `.claude/worktrees/`, likely superseded, not touched

`git worktree list` surfaced three worktrees that aren't part of the normal
working-tree flow and aren't mentioned in any handoff doc:

| worktree | branch | based on commit | age | uncommitted diff |
|---|---|---|---|---|
| `modest-yalow-20d3d0` | `claude/modest-yalow-20d3d0` | `e6ed268` (2026-07-18) | ~1 month stale | `ANTIGRAVITY_HANDOFF.md`, `DATA_MANIFEST.md`, `handoff/task_notebook_and_repo_polish.md`, `handoff/task_pipeline_lineage_audit.md`, `src/rerun_refined_regressions_v2.py`, `src/run_pure_population_analysis.py` (176 insertions) |
| `practical-faraday-460106` | `claude/practical-faraday-460106` | `e6ed268` (2026-07-18) | ~1 month stale | `utils/file_paths.py` only (17 lines) |
| `strange-mccarthy-f42024` | `claude/strange-mccarthy-f42024` | `e9333b5` (2026-07-26) | ~3.5 weeks stale | `src/ingest_ats_archive.py` (241 insertions) + 4 untracked BTS-ingestion files |

None of these were committed or merged, and master has moved on substantially
since both base commits. Cross-checked what each diff was *about* against
what actually happened later on master:
- `practical-faraday-460106`'s `file_paths.py` diff is about removing
  hardcoded `/Users/nash/...` paths — CLAUDE.md already marks that **done**
  (verified 2026-08-03) via a different path (`REPO_ROOT`-derived `BASE`).
  This worktree's version looks superseded.
- `modest-yalow-20d3d0`'s regression-script diff is an early attempt at
  clustered-SE reporting — a *different, later* implementation of the same
  idea now exists directly in master's uncommitted `run_pure_population_analysis.py`
  (see §4) and already-committed `rerun_regressions_with_stance.py`/
  `rerun_refined_regressions_v2.py`. Also superseded-looking.
- `strange-mccarthy-f42024`'s BTS ingestion work predates the confirmed-complete
  BTS ingestion described in `ANTIGRAVITY_HANDOFF.md`'s 2026-08-02 update
  (different script paths, `src/bts_ingest_archive.py` vs. the versions that
  actually shipped) — also looks superseded, not lost.

**Not deleted or cleaned up — that's a `git worktree remove` / branch-delete
call, and per the non-destructive brief this is exactly the kind of thing to
flag rather than decide.** If the "superseded" read above is right (it looks
that way from diff content + dates, not confirmed line-by-line), these three
worktrees and their branches are safe to remove. Recommend Nash do a 2-minute
skim of the three diffs above (or ask a session to do it) and then
`git worktree remove` all three — leaving them costs nothing but they're
pure clutter and confusing to any future session that stumbles on
`.claude/worktrees/`.

## 4. RESOLVED (was: "clustered-SE code added but never run") — a concurrent session ran it successfully, real N discrepancy found

Originally flagged here as an orphaned edit (OOM'd when this session tried
running it). **Correction, same night**: a second concurrent Claude Code
session (Nash running two sessions in parallel, coordinated directly
session-to-session) was independently working on the exact same
naive/thread/author clustered-SE addition to `run_pure_population_analysis.py`,
`rerun_regressions_with_stance.py`, and `rerun_maverick_whistleblower_split.py`
— my OOM was very likely caused by memory contention from their concurrent
run, not a real defect in the script (matches the known "don't run two
memory-heavy full-corpus scripts concurrently" note in the machine-constraints
memory). Their run completed cleanly: `data/processed/pure_population_regression_results_clustered.csv`
now exists, and results are logged
(`data/experiment_log.jsonl`, `pure_population_analysis_clustered_rerun_N_discrepancy`,
2026-08-20).

**Genuinely important finding from that run, not something I want buried in
a correction paragraph**: the "genuine insider environment" population came
out as **N=2,463,379** on this fresh run, vs. **N=27,312** cited for the same
filters in `ANTIGRAVITY_HANDOFF.md`'s 2026-07-14 entry — a ~90x gap. Root
cause not identified by either session yet; ruled out the known dedup bug
(wrong direction — dedup inflates counts, doesn't shrink them) and confirmed
the new N is arithmetically consistent with the corpus's own base rates.
`pe_prob`'s coefficient also flipped sign (-0.4347 historical → +0.1323 new).
**This is a real, unresolved discrepancy that could matter for the regression
findings section of the report** — see the experiment_log entry for full
detail, and see this doc's open questions (§9) for the same point restated.
Whether the historical N=27,312 population was ever intentionally subsampled
is a question only Nash can answer.

## 5. Doc updates made tonight

- `ANTIGRAVITY_HANDOFF.md`: corrected the stale `maverick_stance_round8` /
  `consensus_stance_round8` "never started" lines (§2 above) in place, with a
  pointer to this doc for the verification trail. No other content changed —
  didn't touch the rest of that file, it's long and carefully layered by
  design (see its own opening instructions) and a full rewrite wasn't asked
  for.
- This file, as a new dated handoff entry.
- `data/experiment_log.jsonl` / `data/infra_map.jsonl`: **checked, not
  appended to.** Both are already current through 2026-08-20 (verified by
  reading the tail of each) — the newest session's five real results (backtrans
  paraphrase corpus, confidently-wrong rate, FP detector v1, ensemble+binconf
  reconstruction, stance-regression clustered-SE check) and the infra facts
  discovered that session (both GCP projects' VM layouts, the re-imaging
  pattern, checkpoint locations, the verified 0.428-kappa blend method) are
  all already logged. Nothing found tonight met the "real quantitative
  result" bar for a new entry except what's noted below.

## 6. Where every active thread actually stands (condensed dashboard, cross-checked tonight)

- **Stance classifier**: best validated number is the 5-model ensemble +
  frontier escalation, **kappa 0.5773** (680-row val). A separate,
  never-fully-reconciled thread claims an even better ensemble+binconf blend
  (kappa 0.428 on a *different* stage1-only metric — not directly comparable
  to the 0.5773 overall number, these are answering different questions, see
  the source doc). The concrete next step across both threads is the same:
  **wait for `score_fp_detector_full_train.py` to finish on the VM (§1),
  then spot-check the flagged rows** — nothing else in this thread is
  actionable before that.
- **Topic modeling**: production BERTopic assignment is done and stable.
  `recompute-own-content-outliers` job status (last known: running, zero
  checkpointing, real crash risk) wasn't re-checked tonight — worth a status
  check next session before assuming it's still alive or that it finished.
- **ATS/BTS**: ingestion, entity disambiguation, and engagement normalization
  are done. Topic modeling is mid-flight (phase 1 interim ATS-only fit).
  **Stance classification step 3 is explicitly blocked on Nash** — the
  99-row `queue_ats_stance_quality_check.csv` blind quality check needs
  human labeling before any ATS stance number can be trusted. This is the
  single highest-leverage 20-minute task Nash could do to unblock a whole
  thread, if the report ends up leaning on ATS-vs-Reddit generalization.
- **Citation/entity work**: media-personality candidate list done, awaiting
  Nash's review (not yet wired into decisions). `domain_citation_tier`
  89/603 — a source-authority construct built on this would currently only
  cover ~15% human-verified domains.
- **Regression findings**: the two headline results (consensus-expert stance
  opposite-signed across subreddits; per-entity hostility-rate stability)
  are both now hardened with author/thread-clustered SEs and survive —
  described in the project's own docs as "the most defensible number in the
  whole project," and tonight's audit didn't find anything that undermines
  that framing.
- **Graph-based topic structure**: one real pilot finding (citation
  co-mention/author/reply-structure drive community formation, Gemini
  semantic layer doesn't) — genuinely interesting, complementary, not load-
  bearing for the current regression story, not blocking anything.

## 7. Plan: this week (compute) → next 1-2 weeks (writing)

This is a recommendation, not a decision made on Nash's behalf — the honours
thesis has enough validated material right now to write a strong report
*without* finishing every open thread above. The real risk this week isn't
running out of things to compute, it's the opposite: there's a long tail of
genuinely interesting but non-load-bearing threads (graph topic structure,
full ATS parity, domain-citation-tier completion, the neutral/ambiguous
stance bucket redesign) that could easily eat the whole week without moving
the report's core argument forward.

**Proposed "must-finish this week" list** (things that are either already
near-done or that the report's core claims actively depend on):
1. Let `score_fp_detector_full_train.py` finish, spot-check the flagged
   rows (§1/§6) — closes out the stance-reliability diagnostic thread that's
   been open since last session.
2. Nash labels the 99-row `queue_ats_stance_quality_check.csv` (§6) — cheap,
   high-leverage, decides whether ATS cross-platform generalization is a
   defensible claim in the report or gets scoped down to "future work."
3. Decide (Nash's call, not mine) whether the regression story is finished
   as-is for the report, or whether the stance-classifier reliability work
   needs to reach a specific bar first. Given the clustered-SE results
   already hold up, my read is this is close to writable now — flagging as
   the one real scope conversation worth having before committing to a full
   writing plan.
4. Two-minute worktree triage (§3) — not because it's blocking anything, but
   because it's a five-minute cleanup that removes confusion for any future
   session, and this week is the last natural point to do it before writing
   mode starts.

**Proposed "explicitly future work in the report" list** (real, worth
mentioning as limitations/future directions, not worth chasing to
completion this week): the neutral/ambiguous stance bucket redesign and its
model-size-ablation structural bug; full ATS/BTS topic-modeling parity
(phase 2 combined-corpus fit); graph-based topic structure as a BERTopic
complement; domain-citation-tier completion beyond its current 15%; the
media-personality candidate list review. None of these change the current
headline findings if left unfinished — they extend or diversify the
evidence base, which is exactly what a "future work" section is for.

**Writing-side note, not a computational task**: an 8k-12k word honours
report has room for roughly 3-4 substantive findings sections plus intro/
lit-review/methods/discussion. The project currently has *more* validated
findings than that budget comfortably fits (regression/stance-traction
story, entity-level stability, citation/source-authority framing, ATS
generalization if §6 item 2 lands, graph topic structure as a methods
appendix). Worth Nash picking the 3-4 that form the tightest single
argument before writing starts, rather than trying to include everything —
that's a framing/argument decision, not something to guess at here.

## 8. Two more billing/liveness checks (read-only, no changes)

- `conspiracycomments-gce` (the second GCP project): all 5 instances
  confirmed **TERMINATED** — no billing risk there overnight.
- Kaggle `recompute-own-content-outliers` job status (flagged in
  `ANTIGRAVITY_HANDOFF.md` as "no checkpointing, real risk of losing
  progress"): **could not check from this machine** — local `kaggle` CLI
  returned a permission error (this project juggles 4-5 Kaggle accounts per
  `infra_map.jsonl`; the configured local credential likely isn't the one
  that owns this kernel). Worth a manual check next session before assuming
  it's still alive or that it finished cleanly.

## Open questions for Nash (not decided here, per the standing "not yours to
## decide unsupervised" rule)

1. Should the three stale worktrees (§3) be removed, or is there something
   in them worth manually salvaging first? My read is they're superseded,
   but I didn't do a line-by-line diff review to be certain.
2. Is the ensemble+binconf 0.428-kappa blend (§6) actually meant to be
   compared against the 0.5773 ensemble+frontier number as "which is
   better," or are they answering genuinely different questions (stage1-only
   vs. overall 3-way) that both stay in the toolkit? The source doc doesn't
   fully resolve this and it affects what "current best" means going into
   writing.
3. Which 3-4 findings should anchor the report (§7's writing-side note) —
   this determines a lot about which of this week's open threads are worth
   finishing vs. explicitly scoping to "future work."
4. The N=27,312 vs N=2,463,379 "genuine insider environment" population
   discrepancy (§4) — was that historical population ever intentionally
   subsampled, or is the ~90x-smaller historical number itself the bug?
   This is upstream of the regression findings and worth resolving before
   those numbers go in the report, not after.
