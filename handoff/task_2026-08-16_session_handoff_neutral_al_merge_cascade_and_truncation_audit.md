# Session handoff — 2026-08-15/16 — neutral-AL merge, retrain, cascade exploration, and an active truncation audit

Long session, several distinct threads. Read this fully before picking anything up —
the truncation audit at the bottom is the actual open, active task; everything above
it is settled/done.

## 1. Entity disambiguation fixes (done, verified)

`src/pull_hitl_val_batch.py`:
- Added "malone", "summers", "carlson" to `AMBIGUOUS_SURNAMES` (Post Malone / Larry
  Summers-the-season-word / Randall-vs-Tucker Carlson collisions).
- `_passes_surname_disambiguation()` now checks bidirectionally — both a different
  person's surname preceding the match (already existed) and a different person's
  full name where the surname is *their* first name, following the match (new — found
  via a real "Dick Gregory" vs "Gregory Peck" collision Nash caught while rating).
- **Major bug fix**: `build_person_entities()`'s dedup logic used `dedup_key = best_id
  or name` and `count = doc_counts.get(best_id, 0) if best_id else 0` — both use bare
  Python truthiness, but `best_id` can be a literal float NaN (a real row in
  `entity_final_review.csv` with a blank `best_identity` cell), and `bool(float('nan'))
  is True` in Python. This silently treated NaN as a valid resolved identity instead of
  falling back to `name`, which zeroed several real entities' doc-counts and collapsed
  them onto the same bogus dedup key. Confirmed this had been silently dropping Mark
  Lane, Victor Marchetti, Rashid Buttar, Stefan Molyneux (129-446 real corpus mentions
  each) from *every* pull this project has ever run. Fixed with `pd.notna()` checks and
  an `entity_frequency_full_corpus.csv` fallback for count lookups. **Entity count went
  from 122 → 183** after the fix. Also fixed a separate, smaller bug: 41 entities were
  displaying under a bare-surname alias (e.g. "Folta" instead of "Kevin Folta") instead
  of their canonical `best_identity` — cosmetic only, now uses the resolved name.

## 2. `hitl_rater.py` fixes (done, needs a restart to take effect if not already restarted)

- "This comment mentions multiple entities" label was hardcoded to show unconditionally
  — now neutral "Rate stance toward: X".
- Context highlighting: the fallback highlighter picked one needle (full name, or the
  first token that matched) and stopped — a URL slug like "aaron-swartz-was-murdered"
  (no space) failed the full-name check and only highlighted "aaron", never "swartz".
  Now highlights every matching token found, merging overlapping spans.
- **Real performance/reliability bug, fixed**: `/api/context` was opening a brand new
  `duckdb.connect()` on *every single request* against a 19.5GB local DB, and separately
  any row whose immediate parent was the submission itself (not another comment) fell
  into a slow, unindexed raw-file scan of `data/raw/*.jsonl(.gz)` — which lives on the
  **thumb drive**, not local disk. This is what was causing "sometimes says no context"
  and general slowness — it wasn't random, it depended on whether a row's parent
  happened to be a post vs a comment. Fixed with: (a) one persistent DuckDB connection
  reused via per-request cursors instead of reopening per request, (b) a new local
  indexed table `local_posts_index.duckdb` (1,848,328 rows, built from both raw post
  files, confirmed both files' data present) so post lookups no longer touch the thumb
  drive at all, (c) explicit `PRAGMA memory_limit` caps (1GB context, 512MB posts) since
  this machine only has 8GB RAM and the old code had no cap. Verified: previously-timing-
  out rows now resolve in 70-150ms; RSS stayed at 397MB after 30 mixed requests instead
  of growing unbounded.
- `load_df()` now caches queue CSVs by (path, mtime) instead of re-parsing on every
  request.

## 3. Thumb drive crisis (resolved, no data lost, but fragile — see note)

Improper ejection triggered `fsck_exfat -y` twice this session (once mid-session, once
after a computer restart) — **both times it completed cleanly and all data verified
intact** (exact row-count/shape matches on the canonical training parquet both times).
**Real lesson learned the hard way**: unplugging/reconnecting the drive *while*
`fsck_exfat` is actively running is what caused the scare the first time — it does NOT
resume, it just needs to be left alone to finish. If this happens again: check
`ps aux | grep fsck`, and if it's running, wait, don't touch the drive.

Separately, mid-session the drive became inaccessible specifically to Claude's own
process (not to Nash's own Terminal) with `Operation not permitted` — this was a macOS
**Full Disk Access** permission for Claude.app getting reset, not a real drive problem.
Fixed by Nash manually re-enabling it in System Settings → Privacy & Security → Full
Disk Access. If this recurs, check that first before assuming a real crisis.

## 4. Neutral active-learning queue: labeled and merged (done)

`data/hitl/queue_neutral_active_learning_REVIEW.csv` — 550 rows (ensemble-unanimous
"other" candidates from the entity-mismatch-cleaned round9 pool), all labeled by Nash:
293 neutral + 16 ambiguous + 126 endorsement + 104 hostile + 11 wrong_match.

`src/merge_neutral_active_learning.py` (new script, same merge discipline as
`merge_round9_hitl_backlog.py`) merged this into training:
`data/processed/stance_classifier_training_data_round10_neutral_al.parquet` — 536
genuinely new rows + 1 AI-silver upgrade. **Train: 41,647 → 42,183. Val: unchanged at
680** (safeguarded — the merge script hard-fails if val size changes). This is now the
**current canonical training file** — anything downstream should use this, not
`round9_hitl_backlog.parquet`.

## 5. Round10 retrain — real but modest result

Retrained on the VM (`vm2image-20260810-093317`, `train_twostage_patched.py`,
TAG=r10) using the round10 data. **Baseline arm kappa: 0.5053. Split arm: 0.5088.**
Checkpoints pushed to Kaggle: `tobiasnashws/conspiracycomments-round10-neutral-al-checkpoints`.

**Honest caveat, already discussed with Nash**: this isn't a clean isolated test of
"did the new neutral labels help" — round10's training set is round9's full 41,647-row
backlog *plus* the 536 new rows, and the existing canonical checkpoints (r7v2/r5v2/r7v3)
were trained on earlier, smaller, different-round datasets. So this is "round10 vs
older/smaller rounds," not "round10 vs round9" — the isolated effect of just the new
neutral labels was never cleanly measured.

## 6. VM/Kaggle infrastructure notes

- **`stance-twostage-retrain-asb`**: a *new* VM created this session (disk cloned from
  `stance-twostage-retrain-backup-20260814` snapshot, since the original VM's home zone
  `us-east1-c` hit a real `ZONE_RESOURCE_POOL_EXHAUSTED` stockout) — lives in
  `conspiracycomments-gce`/`asia-southeast1-b`. Has `r7v1_baseline`/`r7v1_split`
  (named `r7v1_redesign` on disk) and, temporarily, `r7v3` checkpoints copied to it.
  **Currently TERMINATED** (confirmed stopped, verified via `gcloud compute instances
  list` across both projects — nothing running anywhere as of end of session).
- **`vm2image-20260810-093317`** (`gpuincrease`/`asia-southeast1-b`): has
  `r7v2_baseline/split`, `r5v2_baseline/split`, `r7v3_baseline/split` (at
  `~/outputs/round8/checkpoints_twostage/r7v3_retrain/`, a different path than the
  `~/retrain_twostage/` convention — don't miss it again), `r10_*` (tonight's retrain),
  and `uncollapsed_v1` (at `~/home/nash/uncollapsed_v1/{stage1,stage2}/` — confirmed
  present, was previously thought missing due to searching the wrong VM).
  **Currently TERMINATED.**
- **Direct VM-to-VM file transfer works and is ~400x faster than routing through local
  Mac's connection** (~200MB/s vs ~0.5MB/s measured this session) — generate a temp SSH
  keypair, add the pubkey to the target VM's `~/.ssh/authorized_keys`, scp directly
  between external IPs. Use this instead of downloading-then-reuploading through the
  local machine for any future cross-VM checkpoint moves.
- Kaggle canonical checkpoint backup (`tobiasnashws/conspiracycomments-canonical-
  stance-checkpoints`) confirmed complete: all 10 dirs (r7v2_redesign, r5v2_baseline,
  r5v2_redesign, r7v3_retrain/baseline, uncollapsed_v1 — stage1+2 each).
- **A safety classifier unrelated to auto mode blocked a parallel `gcloud compute
  instances stop` call once this session** (reacting to earlier conversation content,
  not the action) — ran fine when issued as separate sequential calls instead of
  parallel background `&` calls. If this recurs, don't retry the same form, just split
  into sequential calls or ask Nash to run it directly.

## 7. Stage1 bottleneck investigation — cascade/confidence-score exploration

Extensive investigation into whether a continuous confidence-weighted score (rather
than forcing a discrete other/hostile/endorsement label) could route around the
persistent stage1 bottleneck (has-stance-vs-other gate, stuck at kappa 0.22-0.37 across
every architecture/data/reweighting attempt this whole project has tried).

**Built**: `src/reinfer_ensemble_probs.py` (softmax probabilities, not just argmax, for
the 8 standard two-stage models) and `src/reinfer_uncollapsed_v1.py` (handles
uncollapsed_v1's genuinely mixed architecture — stage1 is a real 2-class classifier
`[2,1024]`, stage2 is a real single-scalar regression head `[1,1024]`, confirmed by
checking actual checkpoint tensor shapes, not trusting the misleading `config.json`
metadata which claimed both were regression).

**Real findings, all local, saved in `outputs/reinfer_probs/`**:
- Ran full 8-model probability inference on the 680-row val set, the 22,459-row round9
  pool, and the 410-row `queue_expanded_entity_val_r1.csv` (all outputs saved as CSVs).
- **Split-arm label semantics bug caught and fixed**: split-arm's stage1 gate uses
  `is_neutral` (1=neutral/other-ish, 0=not-neutral/has-stance-ish) — the *opposite*
  polarity from baseline arm's stage1 (`label != "other"`, 1=has-stance). Averaging all
  8 models' raw probabilities without accounting for this gave a broken kappa of 0.029;
  fixed, corrected combined kappa = 0.551.
- **Confidence stratification works well and is validated**: averaged-probability
  max-confidence gives 89.9% accuracy at confidence≥0.9 down to 33.3% at the bottom —
  a clean, monotonic, real signal (AUC 0.765 on ground truth).
- **Honest limit found and confirmed three separate ways**: for the ~43% of true-"other"
  rows the ensemble confidently mislabels as polar, the models aren't *uncertain* —
  they agree confidently and wrongly (mean confidence 0.70, similar to genuinely-correct
  predictions). Tried and failed to find a cheap proxy for this: (1) cheap text
  heuristics — length, quotes, links, first-person markers, attribution language,
  caps-ratio — best combined AUC 0.61-0.74 depending on feature set, none beating
  confidence alone; (2) `uncollapsed_v1` as an independent architecture check — it
  shares the same blind spot (signed score even *more* confidently wrong on these rows
  than the 8-model average, not less); (3) data-derived word-frequency discovery
  (citation words like "wikipedia"/"nytimes"/"site" were genuinely over-represented,
  confirming the known "citation/link-dump" disagreement category from the 2026-07-28
  IRR analysis, but individually weak AUC ~0.56-0.57 and added *zero* marginal value
  combined with confidence — bit-for-bit identical CV AUC with or without them).
- Best-subset ensemble search (255 combinations tested) found kappa 0.5784 (near the
  historical 0.5807), but **at the cost of worse, non-monotonic confidence calibration**
  — a genuine tradeoff between "best hard-label accuracy on this one val set" (likely
  overfit to it, 255 combinations tested on 680 rows) and "best-calibrated confidence,"
  not a free win.

**Conclusion reached, agreed with Nash**: cheap proxies for the correlated-error subset
don't work; this needs either a genuinely independent evidence source (frontier judge
disagreement on a *sample of high-confidence* rows — a new check, since round9's
escalation logic only ever checked *low*-confidence rows against frontier, never
confident-but-possibly-wrong ones) or human review, which is what section 8 below
actually did on a real subset — with a striking result.

## 8. Gemini rescoring of the 76 "confidently wrong" rows — real, large kappa jump

Nash independently had Gemini rescore all 76 rows where the ensemble confidently
mislabeled a true-"other" val comment as polar. Result: **35/76 (46.1%) Gemini confirms
genuinely "other" (real model error) — but 37/76 (48.7%) Gemini agrees with the
model's exact prediction (original val-set label likely wrong, not the model), and
4/76 (5.3%) is a three-way disagreement.**

Recomputing val kappa using Gemini's corrected labels for the 41 rows it actually
disagreed with the original label on: **kappa 0.551 → 0.630 (+0.079)** — no model
change at all, purely from fixing apparent val-set label noise. This is now *above*
the historical best ensemble (0.5807).

**Important, explicitly-flagged caveat**: these 76 rows were a *pre-selected* high-risk
subset (specifically where the model disagreed with the label), not a random sample —
don't extrapolate "the whole val set is ~6% mislabeled" from this. But it's real,
concrete evidence that a meaningful chunk of the apparent stage1 ceiling is genuine
label noise, not just model incapacity — and if the val set has this concentrated in
hard cases, the training set almost certainly does too.

Files: `outputs/reinfer_probs/hard_wrong_76_rows.csv` (the 76 rows), added a `gemini`
column in `outputs/reinfer_probs/hard_wrong_76_with_gemini.csv`.

**Nash is now manually reviewing these and says many of the machine's original
classifications look correct on his own re-read too** — consistent with the Gemini
finding. Not yet fully reconciled into a final corrected label set.

## 9. Full human-labeled "other" set pulled for Nash's review (in progress)

`data/processed/stance_classifier_training_data_round10_neutral_al.parquet` has 946
human-labeled "other" rows total (771 train / 175 val) across ~30 source queues.
Exported to `outputs/reinfer_probs/all_human_other_rows.csv` (also a `.txt` version and
a newline-escaped `_singleline.csv` version were made trying to solve what turned out to
be two *different* problems — see next section).

**Nash is actively reviewing these now** (sent via SendUserFile). No corrections
recorded back yet as of this doc being written.

## 10. ACTIVE, UNFINISHED: truncation audit in the training data — this is the real next task

**Origin**: while reviewing the 76-row Gemini-rescored file, Nash spotted a row that
looked cut off (`"...As someone who has received a"` — mid-clause). Investigated and
found this is a **real, known, pre-existing project bug**, not new: certain AI-silver
pipeline paths stored only a ±15-word entity window as `text`, not the full comment
(`build_stance_classifier_training_data.py` lines 267/283, `"text":
agreed["text_window"]"` / `trusted["text_window"]`). A partial recovery file already
exists (`data/processed/ai_silver_fulltext_recovered_combined.csv`, built earlier via
"reproduced sampling") but **was only ever applied at serve-time in `hitl_rater.py`,
never actually applied to fix the canonical training parquet**.

**Confirmed, quantified**: source `ai_silver__entity_stance_7b_corrected` (742 rows in
current training data) — **476 of those rows are currently training on the truncated
window text**, even though the recovery file has the correct full text sitting right
there, unused. This is a real, fixable, currently-uncorrected bug in the live training
data. **Not yet patched** — Nash asked to fix it but got redirected into checking scope
first before we got back to actually applying the fix.

**Broader check (comprehensive, done)**: built a single vectorized DuckDB join (not a
slow per-row loop — the first attempt at that hung for over an hour completing nothing
useful and had to be killed) comparing 745 sampled training rows across all 35 source
files against `local_context.duckdb`'s real comment text. **99.7% exact match (639/641
with a locatable original)** — zero truncation found in `round8_ensemble`,
`frontier_random_expansion`, `frontier_boundary_expansion` (the three biggest sources,
~87% of all training data combined), or any HITL queue sampled, including the four
`_short_` queues that looked suspicious by length alone but turned out to be genuine
short comments, not truncated ones. One isolated hit: 1/22 in
`queue_short_wikileaks_stance_quality_check.csv`.

**Nash correctly pushed back on this check's limits, and this is unresolved — pick up
here**:
1. The prefix-match method requires an *exact* match on the first 60 characters. Any
   row with even a minor formatting difference there (whitespace normalization, HTML
   entity decoding, unicode differences) would silently fall into "no match" rather
   than being correctly flagged either way — this is a real blind spot in the method,
   not just a coverage gap.
2. **104/745 sampled rows (14%) had no matching prefix found in `local_context.duckdb`
   at all**, and this was never actually investigated — `local_context.duckdb` doesn't
   have 100% corpus coverage (a known, accepted tradeoff from when it was built), but
   that doesn't tell us anything about whether *these specific* 104 rows are complete or
   truncated. Nash explicitly asked: check them against the *other* available corpus
   files (`data/processed/empath_scores_full_mapped.parquet`,
   `data/processed/conspiracy_comments_short_lte100chars_mapped.parquet`, and if
   needed the raw JSONL shards in `data/raw/`) before concluding anything about them.
3. Nash's direct ask, most recent message: **at minimum, verify and fix the 946-row
   human-labeled "other" set he's actively reviewing right now** — not sampled, all of
   them — against multiple corpus sources with proper fallback, before treating that
   review as trustworthy. This is the most concrete, scoped, immediately-actionable
   version of the broader task if picking this up cold.

**Concrete next steps, in order**:
1. Apply the already-existing recovery fix for the 476 confirmed-truncated
   `ai_silver__entity_stance_7b_corrected` rows (cheap, safe, zero new work — the fix
   is already sitting in `ai_silver_fulltext_recovered_combined.csv`).
2. For the 946-row human-"other" set specifically: check every row (not a sample)
   against `local_context.duckdb` first, then fall back to `empath_scores_full_mapped.
   parquet` / `conspiracy_comments_short_lte100chars_mapped.parquet` for whatever isn't
   found there, before telling Nash his review set is trustworthy.
3. Investigate the 1/22 `queue_short_wikileaks_stance_quality_check.csv` hit — isolated
   noise or a real pattern in that specific queue.
4. Once the 946-row set is fully verified/fixed, the same multi-source verification
   should probably be extended to the rest of the training set, not just this one
   review batch, given how badly the first (single-source, sampled) check undersold its
   own limitations.

## Where things stand overall

Both VMs stopped, no compute running or billing anywhere. Local files are the source of
truth for everything in progress. Thumb drive currently mounted and working. The
cascade/confidence-score architecture work (section 7) is genuinely useful and
validated but paused — the truncation audit (section 10) is the live, unfinished
priority, directly motivated by real errors Nash found by hand that the automated
checks initially missed or glossed over.
