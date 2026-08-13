# Session handoff — 2026-08-13, entity disambiguation overhaul + stance round9 prep

**Read this first if picking up fresh.** Long session (stretched into 2026-08-13). Two
real, silent-failure bugs were found and fixed in the entity-matching pipeline — if
anything about entity coverage looks wrong downstream, check the "Two critical bugs"
section below before assuming it's a new problem.

**STOP — read §0 before trusting ANY stance-classifier kappa number in this doc,
including 0.5752/0.5807 stated below.** A checkpoint/preds-file provenance crisis was
found at the very end of this session (VM2's `retrain_r7v2.log` has an mtime *earlier*
than the preds files it supposedly produced, and its own self-reported final kappa
doesn't match those files) — not yet resolved. Do not build on any ensemble number from
this doc, or from `round8_state_v4.md`, until §0's canonicalization pass is done.

## Headline state

- Entity disambiguation logic properly fixed and validated (two real bugs, both silent
  — no errors, just wrong/missing data).
- `maverick_authority_verified.py` expanded from 446 → 458 entries (12 new alt-right/IDW
  media personalities, Nash's direct call).
- HITL labeling backlog merged into training: 1,254 rows processed → 703 genuinely new
  + 77 AI-silver-to-human upgrades + 23 label corrections. Train 40,944 → 41,647.
- Round9 unlabeled pool built: 22,459 rows across 152 entities, coverage-driven sampling
  (150/entity target), both long+short corpora. **Not yet ensemble-scored** — that's the
  next step, not done this session.
- New val batch (r2) rebuilt clean after both bugs fixed: 410 rows, 149/153 entities
  represented, **not yet labeled**.
- Stage1 "un-collapsed other" architecture experiment run and evaluated: **negative-ish
  result** (kappa 0.5063, see below for why the comparison isn't fully apples-to-apples).
- **Two VMs currently RUNNING AND IDLE, billing for nothing** — see Infrastructure
  section, stop them if not immediately continuing.

---

## 0. UNRESOLVED — checkpoint/preds-file provenance crisis (found end of 2026-08-13 session, top priority for next session)

Two independent ensemble-sweep attempts (this session, and a Nash-run cross-check) got
different "best ensemble" numbers for the same nominal question (does the uncollapsed_v1
model, §8, add value to the ensemble). Chasing the discrepancy down found something worse
than either side's math being wrong: **evidence that at least one "final" preds file on
VM2 doesn't actually correspond to its own training log.**

### What's confirmed

- `/home/nash/preds_r7v2_split.csv` on `vm2image-20260810-093317` (standard location,
  used throughout this session as `vm2_preds_r7v2_split.csv` locally) reproducibly gives
  kappa=0.5518 — checked directly, multiple times, matches everything reported this
  session.
- `/home/nash/retrain_r7v2.log` (the training log that, by its `TAG=r7v2` header and file
  save calls, is supposed to be the record of the run that produced that exact preds
  file) self-reports a **different, lower** final kappa: `"bucket_redesign (split):
  combined 3-way kappa (ambiguous->other for scoring) = 0.4886"`.
- The training script (`train_twostage_patched.py`) computes the printed kappa and the
  saved CSV from the *same* `true_ids`/`pred_ids` variables on adjacent lines — there is
  no code path for these two numbers to differ if the log genuinely records the run that
  wrote that specific file.
- **The log's mtime (Aug 11 11:22) is *earlier* than the preds files it's supposed to
  have produced (`preds_r7v2_baseline.csv` Aug 11 15:43, `preds_r7v2_split.csv` Aug 11
  17:11)** — backwards, a log being written by a live process should never be older than
  files that process saves near the end of its run. The log itself looks internally
  complete and self-consistent (4 model loads = stage1+stage2 × baseline+split, single
  `TAG=r7v2` header, no sign of two runs concatenated into one file) — so this isn't
  simply "the log has two runs in it," it's that **the log and the preds file at that
  path are very likely from two different runs entirely**, and whichever run actually
  produced the 15:43/17:11 files either logged elsewhere (not yet found) or didn't
  capture a log at all.
- Separately (but same underlying mess): there are **6+ differently-timed candidate
  files** for what should be one canonical preds file per model — e.g. for
  `r7v2_split`/`r5v2_split` alone: `/home/nash/preds_*.csv`,
  `/home/nash/vm1_preds/preds_*.csv`, `/home/nash/retrain_oldgen/preds/preds_*.csv`,
  `/home/nash/outputs/preds/preds_*.csv`, plus two more sets created *during this
  session's own verification attempts* (`/home/nash/verify_ensemble/`,
  `/home/nash/verify_ensemble2/`). Different mtimes across Aug 9–13, at least one
  (`retrain_oldgen/preds/preds_r7v2_split.csv`) has a completely different schema
  (`pred`-only, no `true` column, different byte size) — a genuinely different artifact,
  not a duplicate.

### What this means for every kappa number in this document

**Every ensemble kappa reported this session (0.5752, 0.5807), and by extension the
context-repo entry written about them (key
`r7v3_retrain_vs_original_and_uncollapsed_v1_ensemble_reconciliation_2026-08-13`), should
be treated as unconfirmed, not settled** — not because the arithmetic was wrong (it
wasn't; both 0.5752 and 0.5807 reproduce cleanly and repeatedly from the files used), but
because **it's no longer clear the input files themselves are what they claim to be**.
The same concern applies to the alternative numbers found by the other investigation
(0.5520, 0.5639, 0.5743, in `/home/nash/verify_ensemble2/`) — they were built from files
in the same suspect ecosystem and haven't been through the mtime-consistency check below
either.

### The canonicalization pass — not yet done, this is the next task

For every model currently used in any ensemble (r7v1/r7v2/r5v2/r7v3, baseline+split
arms, across both VMs — `vm2image-20260810-093317` and `stance-twostage-retrain`):

1. Find every candidate preds file for that model+arm (glob broadly — `find /home/nash
   -iname 'preds_*<model>*<arm>*'` across both VM home directories, not just the
   standard location).
2. Find the training log that claims to correspond to it.
3. **Check the log's mtime is at or after the preds file's mtime** — if the log is
   older, they're not from the same run, discard that pairing and keep looking.
4. **Check the log's own self-reported final kappa matches
   `cohen_kappa_score(true, pred)` recomputed directly from the preds file** — if it
   doesn't match, same conclusion, wrong pairing.
5. Only once a preds file passes both checks against its own log, treat it as canonical.
   Archive or delete the others (or at minimum, rename them out of the way) so this
   exact confusion can't recur next time someone runs an ensemble sweep.
6. Recompute the ensemble sweep once, from the canonical set, and only then write a
   result to context-repo/this doc — superseding both this session's numbers and the
   alternative numbers found chasing the discrepancy down.

Nash is handing this off to a separate session/agent (already has
`/home/nash/verify_ensemble2/` open on VM2) specifically so it doesn't get done under
this session's dwindling context — if you're that session, start here, not with §1.

---

## 1. Two critical bugs found and fixed in entity matching (`src/pull_hitl_val_batch.py`)

Both were **silent** — no crash, no error, just systematically wrong output that looked
plausible until checked directly against known ground truth (Joe Rogan, Jesse Ventura,
David Duke all have real, large corpus presence and were returning zero rows).

### Bug 1: case-sensitivity in `_full_name_sql_cond`

Built the regex pattern from the entity's **original-case** string but matched against
`lower(text)`. `'Joe Rogan'` → pattern `\bJoe\s+Rogan\b`, matched against lowercased
corpus text — can never match. Affected **every entity requiring full-name-phrase
matching** (anything with a short surname, or on the `AMBIGUOUS_SURNAMES` list — Rogan,
Icke, Ventura, and more). Fixed: `parts = entity.strip().lower().split()` before escaping.

Verified directly: `_person_sql_cond('Joe Rogan')` went from 0 real matches to 17,004
(long corpus alone) after the fix.

### Bug 2: category-level flat random subsampling could zero out real entities

`main()`'s final subsample pooled ALL rows within an `entity_category` (e.g. "maverick",
~90+ distinct entities each already capped at up to 10 rows) and took one flat
`chunk.sample(n=per_cat, ...)` draw across the whole pool — no guarantee any specific
entity survives. With per-entity representation this thin relative to the pool, individual
entities could and did get randomly zeroed out of the final batch despite having
thousands of real corpus matches (confirmed: Jesse Ventura and David Duke, both with
1,500+ real matches, both appeared 0 times in the first "fixed" r2 rebuild).

Fixed: guarantee 1 row per matched entity within each category's budget first, then fill
remaining budget randomly. Verified on synthetic data (90 entities, 900-row pool, 102-row
budget → 90/90 covered, vs the old approach's no guarantee at all).

### Related fix: exclusion logic was excluding by bare ID, not (id, entity) pair

`_collect_excluded_ids()` excluded any comment ID already present in training/HITL data
for **any** entity — wrongly discarding a comment as a candidate for a *different*
entity's `[ENTITY: X]` conditioning, even though that's a genuinely distinct training
example. Renamed to `_collect_excluded_pairs()`, returns `(excluded_id_pairs,
excluded_text_pairs)` — two sets because the canonical training parquets
(`stance_classifier_training_data*.parquet`) have **no `id` column at all**, only `text`
— confirmed directly, don't assume `id` exists on those files. HITL queue CSVs do have
`id`. `pull_all_entities()` and `build_round9_pull.py`'s `scan_corpus()` both updated to
check both pair sets.

**Anything pulled before this session's fixes landed should be treated as suspect** — r1
(`queue_expanded_entity_val_r1.csv`, labeled, 34 wrong_match) predates all of this and
its "88 distinct entities" figure is very likely undercounting real coverage the same
way r2 was, though it's already labeled so not worth rebuilding.

---

## 2. `entity_frequency_full_corpus.csv` is the authoritative corpus-frequency source

**Not** `entity_final_review.csv` (stale since 2026-07-14, confirmed via its own doc
comment elsewhere in this project) and **not** `entity_mentions_cache_2stage_pooled.parquet`
(built from a narrower Wikipedia-category candidate pipeline that silently missed Bill
Gates entirely — confirmed 62,417 real combined mentions via the frequency file, zero
in the mention cache's per-entity output).

`data/processed/entity_frequency_full_corpus.csv` — built 2026-07-26
(`handoff/task_entity_frequency_recount.md`), proper full-corpus regex over long+short
unioned corpora, independently verified against reference numbers (trump/AOC/Netanyahu/HRC)
at build time. 16,534 candidate entity strings, columns `entity, long_count, short_count,
combined`.

**Corrected corpus-size numbers** (earlier in this session I stated 30,168 for the old
11-entity list using the wrong source — that number is wrong, ignore it if it surfaces
in old transcript/memory):

| | Combined mentions (long+short, `entity_frequency_full_corpus.csv`) |
|---|---|
| Old 11-entity list | **224,494** |
| New 458-maverick + 81-consensus list (minus old 11) | **200,471+** (432/529 names matched in the frequency file; 97 not found there — likely need alias variants, not necessarily zero real presence) |

## 3. `maverick_authority_verified.py` expanded (446 → 458 entries)

Added to the `conspiracy_general` section (2026-08-12, Nash's direct call, real corpus
presence confirmed via the frequency file before adding): Charlie Kirk (837 mentions),
Ben Shapiro (365), Jordan Peterson (356), Andrew Tate (198), Richard Spencer (112),
Stefan Molyneux (60), Steven Crowder, Dave Rubin, Milo Yiannopoulos, Gavin McInnes
(these four were previously auto-bucketed `other`/`alternative_source`/`mainstream_source`
by the Wikipedia-category pipeline — overridden per Nash, "definitely not mainstream" on
McInnes specifically), Candace Owens and Eric Weinstein (already auto-bucketed
`maverick_authority` by the pipeline but never promoted into this file — same "never
promoted" gap `verified_maverick_additions.py` was built to fix for other entities).

`SKIP_PERSONS` also expanded: added `"Stephen Hawking", "Carl Sagan"` alongside the
existing Tesla/deGrasse Tyson/Hicks exclusions (Nash's direct call). **Important**:
`consensus_experts_verified.py` has deliberate alias variants of these names ("Steven
Hawking" misspelling, "Sagan"/"Carl Sagan's" bare/possessive aliases) that a literal
`name in SKIP_PERSONS` check misses — `build_person_entities()` now resolves through
`best_identity` (via `entity_final_review.csv`) before checking against skip lists, not
literal string match. If you add more people to `SKIP_PERSONS` in the future, this
resolution already handles alias variants — don't re-add a literal-string-only check.

## 4. Media-personality category — still open, not touched this session beyond flagging

`data/processed/media_personality_candidates_scored.csv` (1,504 Wikipedia-sourced
candidates, 774 with nonzero corpus mentions) exists, built 2026-07-28. **`decision`
column is 0/1,504 filled — Nash's review pass has never happened.** `media_personality_verified.py`
does not exist. This directly undermines the "whistleblowers endorsed / media
personalities attacked" headline finding (124-entity reviewed whistleblower category vs.
zero reviewed media-personality category — the 12 additions above are inside
`maverick_authority_verified.py`'s flat catch-all, not a proper reviewed
`media_personality` construct). Doc known-limitation: several top-scoring candidate rows
are common-word collisions ("Spirit" 44,273, "Kennedy" 25,966 — near-certainly JFK/RFK not
a talk-show host, "Michael Jackson" 4,619 — near-certainly the singer). Multi-word
distinctive names flagged as safe to trust without spot-checking: Charlie Kirk, Candace
Owens, Ben Shapiro, Jimmy Dore, Rachel Maddow, Tim Pool, Sean Hannity, Bill Maher, Rush
Limbaugh, Jon Stewart, Glenn Beck.

## 5. HITL labeling backlog — merged (`src/merge_round9_hitl_backlog.py`)

Full audit found **1,264 real, correct-construct, previously-unmerged labeled rows**
across 10 HITL queue files (much more than initially estimated at 208 — do a full
`data/hitl/queue_*.csv` sweep with label-value spot-checks before trusting any "X rows
unmerged" estimate, filenames alone aren't reliable). Excluded from the merge: files
using a different construct entirely (`queue_maverick_authority.csv`,
`queue_personal_experience.csv`, `queue_procedural_skepticism.csv` — negative/lean_positive/
positive/unsure taxonomy, not stance) and base (non-REVIEW) quality-check files whose
REVIEW counterpart is already in training (would duplicate).

Ran, output: `data/processed/stance_classifier_training_data_round9_hitl_backlog.parquet`
(NOT an overwrite of `round8_combined.parquet` — new file, reviewable alongside).

- 1,254 rows after id-level dedup across sources
- 222 dropped — overlapped with the frozen 680-row val pool (would have leaked val into train)
- 329 rows matched existing train text: 229 confirmed (already human, agreed), **23
  corrected** (two human labels disagreed — per Nash, the backlog label wins, applied in
  place), 77 upgraded (was AI-silver, now human-labeled)
- **703 genuinely new rows appended**
- Train: 40,944 → 41,647. Val: unchanged, still 680.

`queue_jones_stance_quality_check_REVIEW.csv`'s `human_norm` column (already built by a
prior session — don't re-derive) used directly for label normalization; one row
("unclear, lean hostile?") given weight=0.5 per Nash rather than full weight, reflecting
the original rater's own hedged uncertainty.

**Important**: `queue_escalation_round8_aleatoric.csv` (425 rows) — the file used ALL
session as the held-out generalization/overfitting check (how the split-arm
overfitting finding was made) — is now **merged into training**, per Nash's explicit
direction. **There is currently no held-out generalization-check set anymore.** If
that kind of check matters for a future round, a new one needs to be built.

## 6. Round9 unlabeled pool (`src/build_round9_pull.py`)

Coverage-driven sizing, not volume-driven: **398 of 539 verified entities have <10
training rows** (model has near-zero signal for ~74% of what it's supposed to classify,
despite the entity list expansion). Target: 150 rows/entity floor (tunable — the 29,466
row estimate from the planning conversation moves proportionally with this number),
capped-per-entity sampling (not category-pooled, so immune to bug 2 above by
construction), scanning **both** long and short corpora with corpus-appropriate min-length
filters (long: >50 chars, short: >5 chars — the val-pull script's own >50 threshold would
silently drop ~half the short corpus, mean length 48.7 chars).

Final run (both bugs fixed): **22,459 rows across 152 entities**. Breakdown: maverick
15,650 / alt_media 3,414 / consensus 2,332 / leak_whistleblower 1,063. Population: long
14,944 / short 7,515. Only `governmentattic.org` (13) and `Steven E. Jones` (85) came in
meaningfully under the 150 cap — genuine corpus scarcity, not a bug.

Output: `data/processed/round9/round9_unlabeled_pool.parquet`.

**Not yet done — the actual next step**: ensemble-score this pool with the current best
models, apply a confidence threshold, route below-threshold rows through the
epistemic/aleatoric context test (add thread/parent context, re-score; confidence
improves → send to frontier judge; doesn't improve → human queue). This needs
frontier-escalation cost sign-off before any Gemini calls, same as every prior round.

## 7. New val batch (r2) — rebuilt clean, not yet labeled

`data/hitl/queue_expanded_entity_val_r2.csv` — 410 rows, built with both bugs fixed
(went through 3 iterations this session: original had bug 1, first "fix" only addressed
bug 1 and still had bug 2, current version has both fixed). **149 of 153 candidate
entities represented** (up from 102 before any fix, and up from a broken run where major
entities like Joe Rogan/Jesse Ventura/David Duke/Chelsea Manning/Russell Brand all
showed zero rows despite thousands of real matches each). 0/410 labeled — ready for
Nash to start whenever.

**Val superset plan** (established earlier in session, still the plan): existing 680 +
r1 minus its 34 `wrong_match` rows (~376) + r2 once labeled (410) ≈ 1,466 rows.

## 8. Stage1 "un-collapsed other" architecture experiment — run, negative-ish result

Tested the 2026-07-30 decision that was reasoned out and never built (see context-repo
key `session_update_2026-07-30_regression_and_other_mining`): stage1 gates on
content-detectable bare-mention status (NOT the scarce human "neutral" `raw_label` the
existing split/bucket-redesign arm depends on), stage2 is a continuous/ordinal score
rather than discrete, `is_list_dump` is a **feature** appended to the model input, not a
filter (validated first: list-dump rows split 967 endorsement / 648 hostile / 887 other
among training rows — genuinely NOT mostly non-stance, confirming Nash's hypothesis that
evidence-presentation-via-citation carries real implicit stance).

Scripts: `build_uncollapsed_targets.py` and `train_uncollapsed_v1.py` (both currently
only in the session scratchpad, not yet in `src/` — copy over if this gets picked up
again). Real bug hit and fixed: transformers 5.14.1 strips unrecognized dict keys
(`sample_weight`) from the batch before `compute_loss` is called — needs
`TrainingArguments(remove_unused_columns=False, ...)` explicitly, wasn't needed in
whatever older transformers version the original `train_twostage_patched.py` runs were
on.

**Result**: stage1 kappa=0.4455 (real, non-trivial learning — not a majority-class
collapse). Stage2 MAE=0.4485. Combined pipeline, properly threshold-swept (0.10–0.60,
not one arbitrary cutoff): best kappa **0.5063** at threshold=0.30.

**This is below the committed 0.5773, but that's not a fair comparison** — 0.5773 is a
5-model ensemble plus frontier escalation; this experiment is a single model, no
ensemble, no escalation. Against a single baseline-arm model's own kappa (~0.50–0.53,
e.g. r7v2_baseline), 0.5063 is roughly at parity, not a clear loss. **Honest read**: the
bare-mention gate only flags 0.9% of rows — far too narrow to meaningfully help, since
the vast majority of "other"-labeled content is genuine ambiguity, not empty context. The
hypothesized benefit (stage1 handling only non-content, stage2 handling direction
cleanly) doesn't show up much in practice at this scale. **Not validated as an
improvement over baseline as implemented.** Not pursued further — parked pending a
decision on whether to try more epochs, add escalation for a fair comparison, or
abandon.

### 8a. Post-mortem: why it likely didn't work, and what to try instead (2026-08-13)

Two candidate explanations, not mutually exclusive:

1. **The bare-mention gate is too narrow to matter structurally** (0.9% catch rate, see
   above) — stage1 is close to a no-op, so stage2 ends up doing almost the same job the
   old collapsed "other" class had to do, with little real structural help.
2. **The continuous score forces a bad assumption**: that "no stance" sits at the linear
   midpoint between hostile and endorsement. This isn't new — the 2026-07-30 notes
   flagged it before this was ever built: *"near-zero-for-uncertain is a modeling
   assumption, not verified fact — hedged/coded/sarcastic stance can be genuinely strong
   but hard to detect, which would NOT be near-zero."* "Other" is categorically different
   from a weak/median stance (absence of directional content, not an interpolation
   point), and forcing it onto a single -1↔+1 axis may be actively wrong for exactly the
   hardest cases (sarcasm, coded language).
3. **Smaller, fixable gap**: the design called for feeding cited-domain *category*
   (mainstream vs alt-media vs leak-whistleblower — the richer signal that would tell the
   model something about implied direction) as part of the list-dump feature, but the
   implementation only passed a binary yes/no flag. Real miss, not a fundamental problem
   with the idea.

**Ensemble inclusion**: worth testing cheaply (add this model's val predictions to the
existing `ensemble_sweep.py` pool — structurally different decision mechanism than
anything currently in the ensemble, real potential for error-diversity value even at
solo-parity kappa). **But**: the 425-row aleatoric set — the only held-out generalization
check this session had — is now merged into training (§5). Any ensemble-diversity result
right now would be val-only, and this session's own split-arm finding (val gains
collapsing on the aleatoric check) is the exact cautionary tale for trusting that blind.
Build a new held-out check before leaning on any ensemble-diversity conclusion from this
model.

**Options for another attempt, roughly by cost**:

1. **Decouple "is there a stance" from "which direction"** — two axes (a 0–1
   stance-confidence score, a separate -1→+1 direction score only meaningful when
   confidence is high) instead of one blended scalar. Closer to what the original
   two-stage cascade already does structurally; may mean the fix isn't "go continuous"
   at all, it's "keep the binary gate, give stage2 a proper 3-way ambiguous class instead
   of squeezing it onto a line between the two poles."
2. **Actually wire in the domain-category signal** (item 3 above) — cheap, direct.
3. **Ensemble the gates themselves, not just final predictions** — three different
   stage1 conceptions now exist (baseline has_stance-vs-other, split neutral-vs-not,
   bare-mention-vs-not), each with different failure modes; combine their votes for the
   routing decision itself.
4. **Bake parent/thread context into training directly**, not just escalation routing —
   round9's plan already uses context to distinguish epistemic vs aleatoric uncertainty
   for escalation; never tried as actual model input at training time for genuinely
   ambiguous cases.
5. **Give this architecture a fairer shot**: more epochs / real hyperparameter attention
   before writing it off — this was a deliberately cheap 3-epoch validation run, and
   stage1's real kappa (0.4455) even at a 0.9%-positive rate suggests stage2 may just be
   undertrained relative to what's needed to prove the hypothesis fairly.
6. **Progressive/distillation cascade loop** (already tracked below) — still the most
   concrete previously-designed, never-built option, independent of which architecture
   variant wins.
7. **More human labels on stage1 boundary cases** — direct, no-engineering lever, costs
   Nash's time not compute.

### 8b. Ensemble contribution test — real, positive, val-only (2026-08-13)

Checkpoints and val predictions from the uncollapsed_v1 run survived on VM2
(`/home/nash/uncollapsed_v1/{stage1,stage2}/` + `val_predictions_uncollapsed_v1.csv`,
also pulled to the local scratchpad). Converted to final discrete labels at the
already-found best threshold (0.30) — reproduces the 0.5063 solo kappa exactly — then
fed into the same `ensemble_sweep.py` majority-vote methodology used earlier this
session, alongside the 8 existing two-stage models (r7v1/r7v2/r5v2 baseline+split,
r7v3_retrain baseline+split).

**Result: adding uncollapsed_v1 to the ensemble pool lifts the best combo from 0.5752 →
0.5807 (+0.0055)** — despite uncollapsed_v1 having the *lowest* solo kappa (0.5063) of
all 9 models. Best combo: `r7v1_split + r7v2_split + r5v2_baseline + r5v2_split +
r7v3_retrain_baseline + uncollapsed_v1` (6 models). This is a genuine, direct
confirmation of the ensemble-diversity hypothesis from §8a — uncollapsed_v1's errors are
different enough from the existing models' errors (different stage1 gate mechanism,
continuous vs discrete stage2) that majority voting benefits from including it even
though it's individually the weakest model in the pool.

**Caveat, same one as everywhere else this session**: val-only. No held-out
generalization check currently exists (§5's aleatoric-set merge) to verify this against.
Treat +0.0055 as a real but unconfirmed signal, not a settled result, until a fresh
held-out set exists — this session's own split-arm finding is the direct cautionary
tale for trusting val-only ensemble gains without an out-of-distribution check.

### 8c. Independent reproduction found a DIFFERENT number (0.5520) — reconciled, not a bug

A separate, independent verification (Nash-run, methodical: pulled files fresh from VM2,
reproduced the committed 0.5311 baseline exactly against `git show 5bf8f0b`, fixed a real
search-range bug in its own sweep script) found the best uncollapsed_v1 ensemble combo to
be **0.5520** (`r7v2_split + r7v1_baseline + uncollapsed_v1`, 3 models, +0.0209 over
0.5311) — not 0.5807. This looked like a direct contradiction and was flagged as
possible provenance drift. **It isn't drift — the two investigations used two genuinely
different `r7v3_baseline` files**, confirmed as different physical files with different
mtimes on VM2:

- `/home/nash/preds_r7v3_baseline.csv` (Aug 8) — the **original** r7v3, kappa 0.5089.
  This is what's baked into the git-committed 0.5311/0.5773 baseline, and what the
  independent reproduction correctly anchored to.
- `/home/nash/outputs/round8/preds/preds_r7v3_baseline.csv` (Aug 10) — a **retrained**
  r7v3 with entity-prefix, kappa 0.5283 (split arm 0.5374). Found and reported earlier
  in *this same session*, before the entity-disambiguation work even started — confirmed
  again just now via `r7v3_retrain.log`: `SKIP_BASELINE=False` (ran through the original,
  entity-prefix-intact `train.py`), explicit log line `"baseline (collapsed): combined
  3-way kappa = 0.5283"`. **This was never git-committed or written to context-repo at
  the time it was found — that gap is exactly why an independent, git-anchored
  verification had no way to discover it.** Their skepticism about provenance drift was
  the right instinct in general; it just doesn't apply to this specific case once traced.

Both results are real. Both independently confirm uncollapsed_v1 adds ensemble value
regardless of which baseline it's added to (that part was never in dispute). Since
0.5807 > 0.5520 in absolute terms, and 0.5752 > 0.5311 using an objectively better r7v3
checkpoint (0.5283 > 0.5089, direct log evidence above), **treat 0.5752 / 0.5807 as
current-best, not 0.5311 / 0.5520** — but the val-only caveat in §8b applies equally to
both.

**Real action item, not yet done**: neither the retrained r7v3 checkpoint/preds, the
0.5752 ensemble, nor the 0.5807 uncollapsed_v1 result have been git-committed or made
durable anywhere outside a VM home directory and this session's local scratchpad. Full
reconciliation also written to context-repo (`conspiracycomments` compartment, key
`r7v3_retrain_vs_original_and_uncollapsed_v1_ensemble_reconciliation_2026-08-13`) — but
the underlying files themselves are still only one disk failure away from being lost
again. **Commit/persist these properly before the next session** — this exact kind of
gap (a real, validated improvement existing only in an ephemeral location) is what made
today's reconciliation necessary in the first place, and will recur if left as-is.

## 9. Stage1 bottleneck — full options landscape for whoever picks this up

22.4% of errors are stage1-locked (wrong other-vs-has-stance), escalation structurally
can only ever fix stage2-shaped errors (see context-repo key
`stance_classifier_stage1_bottleneck`).

- **Split/bucket-redesign arm's structural problem confirmed worse, not fixed**: its
  stage1 gate depends on the human `raw_label=="neutral"` count, which is fixed
  regardless of round (every AI-silver generation path structurally cannot produce
  "neutral") while total training volume grows every round. Ratio was 146:1
  (2026-08-04 diagnosis) — **now 247:1** (checked this session, after the backlog
  merge added real human-neutral rows, it still got worse because AI-silver grew
  faster). Combined with this session's separate finding that its val-measured gains
  collapse on the aleatoric generalization check, **recommend demoting it to
  ensemble-only, not primary/production** — it still adds real value there.
- **list/link-dump filtering never wired into the production two-stage script.**
  `is_list_or_link_dump_window()` (`stance_window_utils.py`) is used in ~10 other
  scoring scripts across the project (confirmed real: caught 2 actual quality-check
  misses where link-dumps got scored confidently-endorsing) but `train_twostage_patched.py`
  never calls it. Cheap, already-validated fix, not yet applied to production training
  — the uncollapsed_v1 experiment above uses it (as a feature) but that architecture
  isn't in production.
- **Entity-span windowing now wired into `train_twostage_patched.py`** (this session,
  see §10) — was previously a proven-but-undeployed fix (+0.045 kappa isolated
  ablation), now fixed. Only 3.8% of training rows have precomputed `entity_spans`, so
  windowing computes spans on the fly via case-insensitive substring search for
  `target_entity`.
- **The "un-collapsed other" redesign** (§8) — tested this session, not validated as an
  improvement in its current form, but the mechanism (content-detectable stage1 gate,
  avoids the scarce-label problem) is structurally sound; may need a wider bare-mention
  threshold or more training to actually pay off.
- **Progressive/distillation cascade loop** (designed 2026-08-03, never launched) —
  still the most concrete unbuilt option specifically targeting stage1: uses escalation
  + Nash's active-learning review as the two feedstocks into periodic stage1-specific
  retraining. Scoped at ~20-30k entity-mention rows, threshold≈0.40.
- **More human labels on stage1 boundary cases** — direct, no-engineering option, costs
  Nash's time not compute.

## 10. Windowing wired into training (`train_twostage_patched.py`, scratchpad)

Was previously naive truncation (`tokenizer(..., truncation=True, max_length=512)`) on
the raw `[ENTITY: X] full_text` string — risked silently dropping the actual entity
mention on long comments (confirmed: ~7.7% of training rows exceed ~512 tokens, ~4.6%
exceed ~768). Fixed: `_texts_with_entity()` now windows ±15 words around each occurrence
of `target_entity` (case-insensitive substring search, quote-line filtering) before
prepending the `[ENTITY: X]` prefix. Verified on real long comments (a 9,779-char comment
correctly windows differently for "Snowden" vs "Assange" mentions in the same text).
**This is in the scratchpad copy of `train_twostage_patched.py`, not yet pushed as the
canonical version anywhere in `src/`** — push to VMs before the next real retrain.

---

## Infrastructure — VM state (checked directly, 2026-08-13)

| VM | Project | Zone | Status | What's on it |
|---|---|---|---|---|
| `vm2image-20260810-093317` | gpuincrease | asia-southeast1-b | **RUNNING, IDLE** | Ran the uncollapsed_v1 stage1 experiment (§8), now finished, GPU 0MiB used. Has `train_uncollapsed_v1.py` + `stance_classifier_training_data_uncollapsed_v1.parquet` in `/home/nash/`, results in `/home/nash/uncollapsed_v1/`. |
| `stance-twostage-retrain` | conspiracycomments-gce | us-east1-c | **RUNNING, IDLE since at least Aug11** | Nothing running, GPU 0MiB used. Been billing for 2+ days doing nothing — check if anything on it is still needed before stopping. |
| `aug5-disk-reader` | conspiracycomments-gce | asia-southeast1-a | TERMINATED | Already stopped, no action needed. |
| `stance-r7v3` / `stance-arch-smoke-test` / `stance-arch-image-20260810-212434` | both projects | various | TERMINATED | No action needed. |

**Recommend stopping both running VMs if not immediately continuing work** — neither is
doing anything right now.

---

## Files created or modified this session (for reference)

- `src/pull_hitl_val_batch.py` — both bugs fixed, `AMBIGUOUS_SURNAMES` expanded, entity
  source switched to verified lists + real combined doc_count threshold
- `src/build_round9_pull.py` — new, coverage-driven round9 pull, both corpora
- `src/merge_round9_hitl_backlog.py` — new, HITL backlog merge with upgrade/correction logic
- `src/maverick_authority_verified.py` — 12 entities added (446→458)
- `data/processed/verified_entity_combined_doc_counts.csv` — new, combined long+short
  doc_count per verified entity (built via `entity_mentions_cache_2stage_pooled.parquet`
  + `entity_mentions_cache_short.parquet`, bridged through `entity_final_review.csv`'s
  `best_identity` — has some coverage gaps for entities whose common alias isn't its own
  row in that file; `entity_frequency_full_corpus.csv` is more reliable if exact numbers
  matter)
- `data/processed/entity_mentions_cache_short.parquet` + `.csv` — new, built via
  `src/build_entity_mentions_cache_short.py` (existing script, just never run before;
  needed `statsmodels`/`spacy` deps — use the `miniforge3` base conda env, has them
  already, not the project `.venv`)
- `data/hitl/queue_expanded_entity_val_r2.csv` — rebuilt 3x this session, final version
  has both fixes, 0/410 labeled
- `data/hitl/queue_expanded_entity_val_r2_hawking_sagan_bug.csv.bak` — an intermediate
  broken version, kept as backup, safe to delete
- `data/processed/round9/round9_unlabeled_pool.parquet` — new
- `data/processed/stance_classifier_training_data_round9_hitl_backlog.parquet` — new,
  current canonical training data (41,647 train / 680 val)
- `/private/tmp/.../scratchpad/train_twostage_patched.py` — windowing added, not yet in `src/`
- `/private/tmp/.../scratchpad/build_uncollapsed_targets.py` + `train_uncollapsed_v1.py`
  — the stage1 experiment scripts, not yet in `src/`

## Corrections to claims made earlier in this same session (don't trust these if seen in transcript)

- "Old 11-entity total: 30,168" — **wrong**, used the stale `entity_final_review.csv`
  doc_count. Real number: 224,494 (see §2).
- "Bill Gates has zero mentions captured anywhere" — **wrong**, was only zero in one
  specific cache's per-entity output. Real: 62,417 combined mentions, 2,005 existing
  training rows.
- "62 zero-match entities in the first round9 pull, probably fine" — **wrong**, was the
  case-sensitivity bug (§1), not corpus scarcity. Fixed.
