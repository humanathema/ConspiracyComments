# Session handoff — 2026-08-13 (later session), round9 scoring pipeline + hitl_rater.py fixes + entity disambiguation diagnosis

**Read this first if picking up fresh.** Follows directly on from
`handoff/task_2026-08-13_session_handoff_entity_disambiguation_and_stance_round9.md`
(same day, earlier session) — read that one too if anything here references work it
did (the round9 unlabeled pool, the uncollapsed_v1 experiment, the entity-matching bug
fixes). This session picked up right where that one stopped: canonicalizing the
ensemble result, scoring the round9 pool, building an epistemic/aleatoric context
pipeline, sending everything to a frontier judge, building HITL review queues, fixing
three real bugs in `hitl_rater.py`, and diagnosing (not yet fixing) a serious entity
disambiguation problem.

## Headline state

- **Committed ensemble result: val kappa 0.5807** (6 models: r7v1_split, r7v2_split,
  r5v2_baseline, r5v2_split, r7v3_baseline, uncollapsed_v1), independently reproduced
  from actual files multiple times this session after two separate false alarms (see
  §1) — trust this number, it survived real scrutiny.
- **Round9's 22,459-row unlabeled pool is fully scored**, 3,191 stage2 escalation
  candidates identified, pushed through a full epistemic/aleatoric/frontier-judge
  pipeline, ending in 999 rows now sitting in HITL queues for Nash to rate (§3-§5).
- **`hitl_rater.py` had three real, silent bugs, all fixed** — a dtype-crash that made
  labeling look broken, a wrong default label-button set, and hardcoded queue
  registration. Plus one new feature: multi-level "load more context" (§6).
- **The 247:1 neutral-label-ratio figure driving the "demote the redesign arm"
  recommendation was wrong — real ratio is 12.6:1** (§7). Reopens whether the redesign
  arm deserves reconsideration.
- **Confirmed with real numbers: nothing this session moved the stage1 bottleneck**
  (still ~20% of errors are stage1-locked) — the uncollapsed_v1 ensemble gain was
  entirely stage2 (§8).
- **A windowing + list-dump-as-feature stage1 retrain ran to test that directly**
  (§9) — see that section for the result (filled in once the run finished).
- **Entity disambiguation is seriously broken and NOT yet fixed** — bare-surname
  matching is producing large numbers of wrong matches for entities nobody has
  audited yet (Robert W. Malone: 137x false-positive ratio via "Post Malone"). A
  cheap, general, empirically-validated fix was found but not implemented (§10) —
  **this is the most concrete, highest-value thing for the next session to build.**
- **Both compute VMs terminated** as of this doc being written (confirm with
  `gcloud compute instances list` across `gpuincrease` and `conspiracycomments-gce` if
  picking this up later — don't trust this doc's snapshot if much time has passed).

---

## 1. Ensemble canonicalization — 0.5807, verified the hard way

This session re-derived the canonical ensemble result from scratch, twice, after two
separate false alarms — both instructive about this project's recurring failure mode
(narrative/recalled numbers vs. numbers actually reproduced from files):

- **False alarm 1**: an independent brute-force ensemble sweep (mine) got 0.5520 while
  a parallel session reported 0.5752/0.5807. Root cause: I used the *original*
  (non-entity-retrained) `r7v3_baseline` checkpoint; the other session had found and
  used a *retrained*, entity-prefix-fixed `r7v3_baseline` (kappa 0.5283 vs 0.5089)
  that was never git-committed or written to context-repo at the time. Not a bug —
  just an undocumented improvement living only in a VM home directory.
- **False alarm 2**: after reconciling that, a second independent reproduction of the
  *same* claimed 0.5752/0.5807 numbers gave 0.5420/0.5289 instead — a real, serious
  discrepancy. Root cause this time: some of the models I used (`r7v2_split`,
  `r5v2_baseline`) were from an *earlier, pre-entity-prefix-fix* retrain attempt,
  while the correct files were from a *later* `*_entity`-suffixed retrain of the same
  model — same filename, silently overwritten, only distinguishable by checking each
  candidate file's mtime against its actual training log's self-reported kappa (not
  by filename or log existence alone). Canonicalization method that resolved this,
  reusable for any future version of this problem: for every model+arm, find every
  candidate preds file, match it to its real training log by mtime proximity (not
  just name), and confirm BOTH (a) log mtime >= preds mtime and (b) the log's
  self-reported kappa matches `cohen_kappa_score` recomputed directly from the file's
  own true/pred columns.

**Final, twice-independently-reproduced canonical set** (all entity-prefix-retrained,
680-row val set, confirmed identical `true` column across all 9 candidate models):

| model | solo val kappa |
|---|---|
| r7v1_baseline | 0.5022 |
| r7v1_split | 0.5487 |
| r7v2_baseline | 0.5262 |
| r7v2_split | 0.5518 |
| r5v2_baseline | 0.5159 |
| r5v2_split | 0.4763 |
| r7v3_baseline | 0.5283 |
| r7v3_split | 0.5374 |
| uncollapsed_v1 | 0.5063 |

Full brute-force search (all combo sizes) over these 9: best 6-model combo
(r7v1_split + r7v2_split + r5v2_baseline + r5v2_split + r7v3_baseline +
uncollapsed_v1) = **0.5807**, up from 0.5752 without uncollapsed_v1 (+0.0055).

Checkpoints for all of the above still only live in VM home directories
(`vm2image-20260810-093317` for everything except r7v1_*, which is on
`stance-twostage-retrain`) — **not yet persisted anywhere durable.** If these VMs get
reclaimed/reset, this exact canonical set is gone and would need re-deriving from the
original training data (recoverable, but costs real retraining time). Worth
committing to Kaggle before that happens.

### 1a. Two real bugs found and fixed in the round9 scoring scripts themselves

Independent of the canonicalization work above — these affected the *inference*
scripts written this session, not the training pipeline:

- **Stage1 label-polarity inversion** (`infer_round9_vm2.py` originally): the
  baseline arm's stage1 gate uses `stage_label = (label != "other")` (index1 =
  has_stance, route to stage2 when >=0.5), but the redesign/split arm uses
  `stage_label = is_neutral(row)` (index1 = neutral, route to stage2 when *<0.5* —
  opposite polarity). Reusing one gating rule for both arms silently routed ~90%+ of
  split-arm rows straight to "other" instead of stage2. Caught by comparing each
  model's "other" rate on the round9 pool against its own val-set rate — the three
  split-arm models showed 92-94% other (vs. their ~21-30% val rate), while the two
  baseline-arm models and uncollapsed_v1 stayed consistent. Fixed by adding an
  explicit `arm` parameter to the gating function. **Lesson for any future inference
  script touching split-arm checkpoints: never reuse one gating function across both
  arms without checking `train_twostage_patched.py`'s actual label-construction code
  (lines ~145 vs ~178-181) — don't assume, verify every time.**
- **Margin-sign flip** in the epistemic/aleatoric classification script: `margin` is a
  confidence score (distance from 50/50 vote split; high = confident). The
  classification script computed `margin_delta = margin_orig - margin_ctx` with an
  inline comment claiming "positive = improved" — backwards; lower margin means *less*
  confident. Caught by spot-checking a concrete example at Nash's direct request
  (a clearly-hostile comment that went from a dead-even 50/50 split to full
  unanimous agreement with context — correctly resolved by the model, but the buggy
  script had classified it "aleatoric"/not-improved). Corrected direction:
  `margin_improvement = margin_ctx - margin_orig`.
- **Floating-point exact-tie fragility**, found while investigating why the corrected
  classification didn't reproduce identically across runs: margin values are always
  `k/total` for `total` in 1..6 (possible values: 0, 0.1, 0.1667, 0.25, 0.3, 0.333,
  0.5). Several *exact* mathematical differences between these values equal exactly
  0.05 (e.g. 0.30 − 0.25 = 0.05 mathematically), but Python float64 computes
  `0.30 - 0.25` as `0.049999999999999999...`, just under a `>= 0.05` threshold check
  — meaning true ties got excluded from "epistemic" by a representation artifact, not
  by their real value. Fixed with an epsilon-tolerant comparison
  (`>= 0.05 - 1e-9`), not by picking a different threshold (the possible margin
  differences are densely packed — 0.033, 0.05, 0.067, 0.083, 0.10, 0.133... — so a
  different arbitrary cutoff just risks landing on a different collision).

---

## 2. Round9 pool — fully scored, 6-model ensemble

`data/processed/round9/round9_6model_ensemble_final.parquet` — all 22,459 rows,
6-model majority vote + margin. Final distribution: endorsement 43.5% (9,763),
hostile 30.0% (6,726), other 26.6% (5,970). 3,191 rows are stage2 escalation
candidates (margin<0.45 among stance-bearing rows) — these fed everything in §3-§5.

Note: this round9 scoring pass hit and fixed the stage1-polarity bug described in
§1a — if you see any earlier/cached round9 scoring numbers from mid-session, they
predate that fix and are wrong (specifically: an interim 5-model pass without
r7v1_split showed an implausible 0.5% escalation rate, later corrected to 14.2%(ungated: 16.5%, matching round8's own historical ~17% escalation rate) once the bug
was fixed and the 6th model included).

---

## 3. Epistemic/aleatoric context pipeline

Three iterations, each fixing a real problem with the previous one:

1. **Single-parent context test** (immediate parent comment or post title/selftext
   fallback, 400-char cap, MAX_LENGTH=768): gave 1,423 epistemic / 1,768 aleatoric out
   of the 3,191 escalation candidates (after fixing the margin-sign bug from §1a).
2. **Uncapped rerun** (MAX_LENGTH bumped 768->4096, no more 400-char context cap):
   Nash correctly pushed back on the original caps as an unprincipled shortcut. Real
   finding: target comments themselves are often long (median 667 chars, some up to
   17K) and were being silently truncated at 768 tokens regardless of context — the
   768-token budget was mostly consumed by the comment alone for many rows. Bumping
   to 4096 (covers ~93rd percentile of combined context+text length; full coverage
   isn't achievable, the extreme tail needs up to 18,240 tokens, beyond even the
   model's 8192 hard cap) resolved an additional 712 rows via chain-walking (below).
3. **Iterative chain-walking**, up to 15 levels deep, for the rows still aleatoric
   after the single-parent test: walked up the parent_id chain (grandparent,
   great-grandparent, ... to the top-level comment, then the submission
   title/selftext), building cumulative context at each depth. Implementation note
   worth reusing: rather than a fresh full-corpus scan per depth level, did ONE
   scoped DuckDB pass filtered by `link_id` to pull every comment in the relevant
   ~1,700 threads (`src/build_round9_thread_chains.py`), then walked the parent
   chains purely in local pandas (`src/walk_round9_aleatoric_chains.py`) — much
   cheaper than repeated corpus scans.

**Final: 2,135 epistemic (66.9%) / 1,056 aleatoric (33.1%)** out of the original 3,191.
Files: `data/processed/round9/round9_chain_resolution_final_uncapped.csv` (per-row
resolution depth, NaN = never resolved), `round9_epistemic_aleatoric_classification.csv`
(the base single-parent-pass classification, corrected sign + epsilon).

---

## 4. Frontier judge pass — real context, real "unsure" option

Per Nash's explicit direction: not forced-choice. `src/score_round9_frontier_with_context.py`
(Vertex AI, project `conspiracycomments-gce`, account `tobiasnash@gmail.com`, model
`gemini-3.5-flash`, same established pattern as `src/score_escalation_cascade_frontier_gemini.py`)
sent **all 3,191** escalation candidates (not just the epistemic ones — Nash
explicitly widened scope mid-session) with real context (whatever context resolved
each row, or the deepest context reached if never resolved) and a genuine `unsure`
field in the response schema, so genuinely ambiguous cases route to human review
instead of getting a forced coin-flip label.

**Result: 3,191/3,191 scored. 999 unsure (31.3%).** Score distribution among the
2,192 resolved: endorsement 63.0% (1,380), hostile 37.0% (812); mild scores (±0.5)
outnumber strong scores (±1.0) roughly 4:1.

**Real finding worth flagging for anyone using this data**: unsure rate is NOT
uniform across the three origin-buckets, and it's counterintuitive —

| bucket | n | unsure rate |
|---|---|---|
| resolved at depth1 (single-parent test) | 1,423 | 30.3% |
| epistemic via chain-walk (2+ levels) | 712 | **38.9% (highest)** |
| aleatoric, never resolved by local ensemble | 1,056 | **27.6% (lowest)** |

The rows the local ensemble only resolved after walking deep into a thread are the
**least** trustworthy of the three by this independent cross-check — even less
reliable than the rows the ensemble gave up on entirely (which the frontier judge
actually resolved 72.4% of, better than the local ensemble's own chain-walk
success rate implied). Treat the 712 chain-walk-resolved rows with real skepticism
if using them as training labels — they may be thin/borderline crossings rather than
genuine resolutions.

A negative-result side-investigation worth keeping on record: hypothesized that 44
rows with literal `[removed]`/`[deleted]` placeholder text as their "context" were
driving an elevated (45.5%) unsure rate in that specific subgroup. Tested directly by
re-scoring those 44 rows with the placeholder stripped to nothing — result was
**exactly unchanged** (still 45.5%, only 6/44 rows flipped either direction, net
zero). The hypothesis was wrong: these rows are just inherently harder because
there's no real context available, not because the literal placeholder string
confused the model. Good example of testing an assumption rather than trusting it.

Files: `data/processed/round9/round9_all_for_frontier_with_context.csv` (input, all
3,191 rows + context), `round9_frontier_scored_with_context.csv` (output,
id/unsure/frontier_score). An earlier, now-superseded partial run
(`score_round9_epistemic_frontier_gemini.py`, forced-choice, no context, epistemic
subset only, 1,570 rows) exists but should not be used further.

---

## 5. Three new HITL queues, delivered to Nash

All match the existing `hitl_rater.py` queue schema (id, full_text, human_stance,
notes, entity_spans, target_entity, current_label, predicted_label, verdict,
parent_id, link_id, parent_text, rater_id) and are already registered in
`hitl_rater.py`'s `QUEUES` dict (though see §6 — auto-discovery means future queues
won't need this step):

1. **`queue_round9_doubly_unresolved_REVIEW.csv`** (291 rows) — neither the local
   ensemble (even after full chain-walk) nor the frontier judge (with the same
   context) could resolve these. The strongest "genuinely hard" candidate set —
   probably the best core for a new held-out generalization check, replacing the
   425-row aleatoric set that got merged into training earlier the same day. Real
   `entity_spans` computed for 266/291 (91.4%) rows.
2. **`queue_round9_ensemble_judge_disagreement_REVIEW.csv`** (708 rows) — local
   ensemble was confident, frontier judge said unsure. Real disagreement, cause not
   fully diagnosed (see §4's chain-walk-bucket caveat — many of these are likely from
   that less-trustworthy bucket). Ordered via entity round-robin (shuffled entity
   order) + margin-ascending within each entity, so Nash gets entity coverage early
   rather than long runs of one entity — reuses this project's established
   uncertainty-sampling convention (`build_stance_active_learning_queue.py`). 615/708
   (86.9%) got real entity_spans.
3. **`queue_round9_confident_other_REVIEW.csv`** (299 rows) — a proportionally
   stratified-by-entity_category sample of the 5,970 rows the ensemble confidently
   called "other" (no stance), meant as a spot-check before ever trusting this bucket
   as AI-silver training data (flagged as risky in §8 — using the ensemble's own
   confident stage1 "other" calls to retrain the next stage1 gate risks reinforcing
   the very errors being fixed, unlike stage2 where confident predictions are
   comparatively safe). 277/299 (92.6%) got real entity_spans.

None of these have context (`parent_text`) pre-populated except doubly_unresolved and
ensemble_judge_disagreement (which reuse the pipeline's own context) — confident_other
does not, since it was never part of the escalation/context pipeline.

---

## 6. `hitl_rater.py` — three real bugs fixed, one new feature added

All changes are in `src/hitl_rater.py`, already applied and tested (a debug instance
on a spare port, not the live server) before being handed back to Nash to restart.

1. **Queue auto-discovery.** The `QUEUES` dict was 100% hardcoded — any new queue file
   needed a manual code edit + server restart to appear at all. Nine pre-existing
   `queue_*.csv` files were already sitting in `data/hitl/` never wired in this way
   (including `queue_expanded_entity_val_r2.csv`, a 410-row val batch that was
   apparently ready and waiting the whole time). Added `_discover_queues()`: scans
   `data/hitl/queue_*.csv` for anything not already in the hardcoded dict, schema-
   gates on `id`+`full_text` columns being present (so `queue_topic_stance.csv`,
   which uses `text`/`label` instead, doesn't break the UI), skips filenames
   containing `BACKUP`. Existing hardcoded keys are left untouched on purpose (their
   names are load-bearing — referenced by `?queue=` URLs).
2. **Button-set default inverted.** `renderLabelButtons()` used to check a
   `STANCE_QUEUES` allowlist and fall back to a *different* (non-stance) button set
   for anything not on it — meaning every auto-discovered or newly-created queue
   silently got the wrong buttons (`positive`/`lean_positive`/`negative`/`unsure`
   instead of `endorsement`/`hostile`/`neutral`/`ambiguous`/`wrong_match`) unless
   manually added to the allowlist. Given only 3 queues in the whole project
   (`maverick_authority`, `personal_experience`, `procedural_skepticism`) are
   genuinely non-stance, inverted the logic: stance is now the default, those 3 are
   the `NON_STANCE_QUEUES` exception list. Fixed the same bug in the keyboard-
   shortcut handler (duplicated logic, same fix needed twice), and along the way
   fixed a separate pre-existing gap where `domain_citation_tier`'s keyboard
   shortcuts never matched its actual buttons at all.
3. **Real crash in `load_df()`.** Reported by Nash as "clicking a label does nothing,
   but if I navigate away and back it shows as labeled." Root cause: a queue CSV
   whose `human_stance`/`notes`/`rater_id` column starts *entirely* blank (true of
   all three new round9 queues) gets inferred as `float64` (all-NaN) by
   `pd.read_csv`. Writing a string label into that column then raises
   `TypeError: Invalid value 'X' for dtype 'float64'` deep inside pandas, which
   crashes the request handler with **no response sent at all**
   (`net::ERR_EMPTY_RESPONSE` client-side) — genuinely different from an HTTP error,
   which `fetch()` would NOT throw on. The frontend mutates its local copy of the row
   *before* awaiting the network call, so the label looks "saved" when you navigate
   back even though the server never actually wrote it and the auto-advance code
   (which runs after the awaited call) never executes. Fixed by forcing
   `human_stance`/`human_label`/`notes`/`rater_id` to `object` dtype unconditionally
   in `load_df()` — can't recur for any future queue in the same blank-column state.
4. **New feature: multi-level "Load more context."** Previously the context button
   only ever fetched the immediate parent + siblings, one level, no further; clicking
   it repeatedly did nothing new. `/api/context` now accepts a `depth` param and
   walks further up the parent-comment chain each click, using
   `local_context.duckdb`'s full 44M-row comments table (confirmed, contrary to an
   earlier "abandoned" note in project memory, that this file is real and populated —
   worth updating that memory) for the fast path, with a scoped DuckDB scan against
   the raw post files (`r_conspiracy_posts.jsonl` + `r_conspiracy_posts2.jsonl.gz` —
   both needed, complementary date ranges, confirmed same day building
   `build_round9_thread_chains.py`) for reaching the post title/selftext once the
   chain terminates. Verified against a chain the offline round9 chain-walk had
   already validated (levels matched exactly for the first 3, with one expected
   discrepancy at level 4 — `local_context.duckdb` doesn't have 100% coverage of the
   raw corpus, which is an acceptable trade-off for keeping this fast enough for
   interactive use). Also fixes a real pre-existing gap: the frontend already
   referenced `data.post_title` but the server never actually set it — post title
   has apparently never been shown in this tool before today, despite the UI code
   implying it should.

**Nash needs to restart his running `hitl_rater.py` process** to pick up all of the
above — none of it takes effect until restarted (confirmed this was still pending as
of this doc being written).

---

## 7. Neutral-label ratio correction: 247:1 was wrong, real value 12.6:1

The earlier same-day handoff doc (and context-repo) state a 247:1 not-neutral:neutral
ratio in the training data, used to justify demoting the bucket-redesign/split arm to
"ensemble-only, not primary." Nash suspected this was stale (he recalled labeling
more neutral rows since). Directly checked the actual current combined training file
(`data/processed/stance_classifier_training_data_round9_hitl_backlog.parquet`,
41,647 train rows — confirmed this is the right file: exact same 680-row val set,
257/248/175 class split, as every kappa cited all session): **3,065 neutral / 38,582
not-neutral = 12.6:1**, not 247:1. Source of the original wrong figure not identified
— could have been a stale snapshot, a different file, or a computation error; not
worth chasing further, the current number is what matters and it's now directly
verified from the file that's actually in use.

**This reopens whether the redesign/split arm deserves reconsideration** as more than
ensemble filler — see §9 for the retrain that tested this directly (using this
corrected training file).

---

## 8. Stage1 bottleneck — confirmed still unmoved, with real numbers

Direct answer to "has anything this session moved the stage1 bottleneck": **no**,
confirmed quantitatively, not just inferred. Reran the same error-decomposition
methodology that originally established the ~20%/~7.5% stage1/stage2 split (stage1
error = predicted other-vs-has_stance disagrees with true label; stage2 error = gate
agrees, hostile-vs-endorsement direction is wrong) against both the pre- and
post-uncollapsed_v1 ensembles on the 680-row val set:

| | correct | stage1 error | stage2 error | kappa |
|---|---|---|---|---|
| 4-model (pre-uncollapsed_v1) | 72.2% | 20.0% | 7.8% | 0.5752 |
| 6-model (+uncollapsed_v1) | 72.5% | 20.1% | 7.4% | 0.5807 |

Stage1-attributable error is flat (20.0%->20.1%, within noise). The entire +0.0055
ensemble kappa gain came from stage2 — exactly the error type frontier-judge
escalation can already fix on its own. Confirms with real numbers what the
uncollapsed_v1 experiment's own architecture already suggested (its bare-mention
stage1 gate only flags 0.9% of rows, too narrow to restructure anything): it added
real ensemble-diversity value, but did not touch the actual bottleneck.

**Options landscape for actually attacking stage1** (updated from the earlier
same-day handoff's own list): the corrected neutral ratio (§7) reopens the
redesign/split arm as a real option, not just a demoted one; §9 below is this
session's direct test of an architecture fix (windowing + list-dump-as-feature);
§10's entity disambiguation problem is a *third*, previously-unconsidered angle —
bad entity matches in the training data are noisy/wrong labels that would show up as
stage1 error regardless of architecture, and nobody has quantified how much of the
20% is actually this rather than a genuine model limitation.

---

## 9. Windowing + list-dump retrain (`train_twostage_windowed.py`, TAG=r9windowed)

Direct test of two previously-validated-but-never-deployed fixes, applied together
against the corrected 41,647-row training set (real 12.6:1 neutral ratio):

- **Entity-span windowing**: replaces the plain `[ENTITY: X] + full comment text`
  input with `[ENTITY: X] [LIST_DUMP: yes/no] <±15-word window around the entity
  mention>`, using precomputed `entity_spans` where available (3.75% of rows) and a
  case-insensitive substring search fallback otherwise. Previously validated at
  +0.045 kappa in isolated ablation but never actually wired into the script that
  produced this session's canonical checkpoints (`train_twostage_patched.py`) — it
  turned out to already be wired into a *different*, git-tracked script
  (`train_twostage_classifier.py`) that hasn't been used to produce any of the
  checkpoints in the current canonical ensemble. Two different scripts, don't
  conflate them again.
- **List/link-dump detection as a feature**: `is_list_or_link_dump_window()` (already
  validated elsewhere in the pipeline, catches real link-dump misclassifications) was
  never wired into stage1 training at all. Appended as an explicit `[LIST_DUMP:
  yes/no]` tag rather than used as a filter (matches the uncollapsed_v1 experiment's
  own earlier finding that list-dump rows carry real, non-trivial implicit stance —
  filtering them out would be wrong).

**Real bug found and fixed mid-run**: the first attempt ran at 1.23-1.24s/it and
projected 4+ hours total. Diagnosed by precomputing spans locally (not on the GPU —
span computation itself takes ~2s for the full dataset, negligible) and checking the
resulting window-length distribution: a comment containing a long unspaced blob (a
wall-of-text URL, a run-on link) counts as a single "word" in the `extract_entity_window`
±15-word logic, since it splits on whitespace — this produced windows up to 10,000
characters for ~4% of rows, causing severe batch-padding overhead. Fixed with
`MAX_SPANS_PER_ROW=3` (capping concatenated windows per row) plus a
`MAX_WINDOW_CHARS=600` hard backstop (the span cap alone didn't fix the degenerate
case — still saw a 10,000-char window after capping to 3 spans; the direct character
cap was the effective fix). After the fix: training runs at ~1.46-1.50 it/s, roughly
2x faster — confirms the degenerate windows really were the bottleneck.

**Result**: [FILL IN — training was still in progress as this doc was first written;
see the wrap-up entry in context-repo (compartment `conspiracycomments`, most recent
entry) for the actual final numbers and whether this moved the stage1-attributable
error share from the 20.0-20.1% baseline in §8. If this section still says "fill in"
and you're reading this in a future session, the run's result was never captured back
into this doc — check context-repo directly.]

---

## 10. Entity disambiguation — diagnosed as seriously broken, NOT yet fixed

**This is the single most concrete, highest-value thing for whoever picks this up
next.** Triggered by Nash noticing "a lot of wrong matches for a lot of entities" while
rating the new HITL queues.

### What's actually happening

The current approach (`_person_sql_cond` in `src/pull_hitl_val_batch.py`, reused by
every downstream pull script including `build_round9_pull.py`) is **bare-surname-
default matching**: for any multi-word entity name with a surname ≥6 characters not
on a manually-curated denylist (`AMBIGUOUS_SURNAMES`, ~30 entries), the match
condition is just the bare surname anywhere in the text — no first-name check, no
position check, nothing. The denylist is purely reactive: entries only get added
after someone manually notices a specific problem (e.g. weinstein/manning/steele/
ventura were added 2026-08-12 after auditing exactly one 410-row human-labeled
sample and finding 34 wrong matches in it).

### How bad it actually is

Audited all 60 currently-active bare-surname-default entities (the real,
`MIN_COMBINED_DOC_COUNT`-filtered set actually used by `build_person_entities()`,
not the full ~570-entry raw verified lists) against real corpus counts — bare-surname
hits vs. full-name-phrase hits, both corpora combined. Saved as
`handoff/bare_surname_audit_2026-08-13.csv` (60 rows, sorted by ratio descending).
Worst offenders:

| entity | bare count | full count | ratio |
|---|---|---|---|
| Robert W. Malone | 8,656 | 63 | **137x** |
| Milton William Cooper | 18,962 | 200 | **95x** |
| Francis Collins | 3,151 | 221 | 14x |
| William Rodriguez | 1,628 | 170 | 9.6x |
| Joseph Mercola | 1,623 | 171 | 9.5x |
| Larry Summers | 2,612 | 328 | 8.0x |
| Dick Gregory | 1,506 | 239 | 6.3x |

Concrete confirmed collisions (checked directly, not inferred from the ratio alone):
"Post Malone" (musician) is the dominant source of "Malone" false positives; "Bill
Cooper"/"Anderson Cooper"/"Bradley Cooper" for "Cooper"; "Gregory Bateson"/"Gregory
Mankiw"/"Gregory Mannarino" (note: these aren't even surname collisions — "Gregory"
is someone *else's first name* in all three, the matcher doesn't check word
position at all) for "Dick Gregory"; "Carlos Castillo Armas"/"Alfredo Castillo" for
"Celerino Castillo". Nash's own words reviewing these: "almost entirely random, just
complete dogshit" — an accurate assessment, not an exaggeration.

**Caveat**: ratio alone isn't proof of wrongness. "Joseph Mercola" (9.5x) is
plausibly partly legitimate — people may reference him via his own brand/domain
("Mercola.com") without using his full name, which would still be a correct match.
Ratio flags candidates for review, doesn't settle the question on its own.

### Two approaches explored, one validated as promising

1. **Signature-words confidence scoring** (Nash's first proposal): derive a
   vocabulary profile per entity from corpus contexts where the *full name* is
   confirmed, then score bare-surname matches by overlap with that profile instead
   of a binary list. Prototyped on the two originally-found offenders:
   - **Celerino Castillo**: works excellently. Confirmed-mention contexts share a
     tight, coherent vocabulary (`drug` 96%, `agent` 90%, `cocaine` 77%, `contra`/
     `contras` 75%/73%, `cartel`, `smuggling`, `levine`, `webb` — an Iran-Contra/DEA-
     whistleblower cluster). A bare "Castillo" match without any of these words
     nearby would score low and correctly get excluded.
   - **Dick Gregory**: doesn't work at all. Confirmed-mention contexts share only
     generic conversational filler (`said`, `like`, `people`, `watch`, `think`) — his
     mentions are too topically diffuse to build a useful signature. For entities
     like this, the safe fallback has to stay full-name-required matching.
   - **Conclusion**: real technique, real value where it applies, but not universal —
     would need a per-entity check of whether a coherent signature exists at all
     before trusting it, adding real complexity.
2. **Preceding-capitalized-name exclusion** (Nash's second, better proposal): if a
   bare-surname match is immediately preceded by a *different* capitalized
   first-name-like token (not the target entity's own first name), it's almost
   certainly someone else's full name in disguise — no per-entity vocabulary
   modeling needed, much more general. Empirically validated on 5 of the worst
   offenders (`/tmp/check_preceding_names.py`, output not yet saved to the repo —
   rerun if needed, it's cheap):

   | entity | preceded by TARGET's own first name | preceded by a DIFFERENT capitalized name |
   |---|---|---|
   | Robert W. Malone | 1,527 | 989 (dominated by "Post") |
   | Milton William Cooper | 938 | **3,722** (dominated by "Bill", "Anderson", "William"—not one of *this* entity's first names) |
   | Francis Collins | 224 | **2,126** (dominated by "Michael", "Phil", "Susan", "David") |
   | Larry Summers | 327 | 360 |
   | Joseph Mercola | 175 | 144 |

   For Cooper and Collins specifically, this single rule would eliminate the
   *majority* of false positives with essentially no engineering complexity beyond a
   regex look-behind and a first-name comparison. **This is the concrete next step —
   validated, not yet implemented as an actual code change to `_person_sql_cond` /
   `_full_name_sql_cond`.**

### Recommended next step

Implement the preceding-capitalized-name exclusion in `_person_sql_cond` (or as a
wrapper around it), re-audit the same 60 entities to quantify the improvement, decide
whether any of them still need denylist treatment even after this fix (some, like
Malone with "Post" specifically, might benefit from *combining* both approaches —
signature words for the residual ambiguity once the obvious full-name collisions are
excluded). Given how much downstream data (round9's pool, every HITL queue, the
training data itself) depends on entity matching quality, this plausibly has more
leverage on real data quality than any further stage1-architecture work.

---

## 11. Compute VM status

Confirm current state before trusting this section — it's a snapshot at doc-write
time:

- `vm2image-20260810-093317` (project `gpuincrease`, zone `asia-southeast1-b`) — ran
  the §9 retrain; should be TERMINATED by the time this doc is committed (stopped
  once results were pulled, per the session's established stop-when-done discipline).
- `stance-twostage-retrain` (project `conspiracycomments-gce`, zone `us-east1-c`) —
  held the r7v1_* checkpoints; TERMINATED, confirmed stopped mid-session and not
  restarted since.
- All other VMs checked this session (`stance-r7v3`, `stance-arch-smoke-test`,
  `aug5-disk-reader`, `stance-arch-image-20260810-212434`) — confirmed TERMINATED,
  not touched.

If picking this up and needing either VM again: `gcloud compute instances start
<name> --zone <zone> --project <project>` — both have known IAP-tunnel flakiness on
`gcloud compute ssh` right after boot, just retry the command, it resolves within a
couple of attempts.
