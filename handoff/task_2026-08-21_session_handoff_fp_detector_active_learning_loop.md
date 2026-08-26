# Session handoff: FP-detector active-learning loop (v4 → v7), base-rate reality check

**Status: paused for the night, not finished.** Read this before touching
`fp_detector_v*` files, the `vm2image*` VMs/image, or any of the
`fp_detector_v*_*` entries in `data/experiment_log.jsonl` from 2026-08-21.

## 1. Where this thread started

Goal for the session: use the false-positive detector to clean up the 42k
training set (specifically: find rows currently labeled hostile/endorsement
that are actually "other"), since stage1 (has-stance-vs-other gate) kappa
has been the project's persistent weak point (documented best: **0.428**,
the ensemble+binconf blend — the earlier "-0.248" figure Nash asked about
was a typo) versus stage2 polarity kappa's well-established 0.7+ (up to a
theoretical ~0.89 AI-based ceiling per Nash).

**Direct answer, unchanged by anything below: none of this session's work
has moved that 0.428 number at all.** Everything built is candidate-finding
infrastructure — no training label has been corrected, no classifier
retrained on corrected data, no before/after kappa comparison exists. See
§6 for what closing that loop would actually require.

## 2. Round-by-round summary (v4 → v7)

**v4** (session start, found already built) — fine-tuned ModernBERT-large,
but shown `SILVER_LABEL`/`CLASSIFIER_PREDICTED` tags as explicit input.
**Root cause found and fixed this session**: the training-pool construction
made those two tags an almost-perfect predictor of the target on their own
(every `SILVER_LABEL=stanced/CLASSIFIER_PREDICTED=stanced` example was
negative, by construction) — so v4 learned to read the tag, not the text.
Confirmed directly: 0% flag rate when binconf agrees with the label, 97.1%
when it disagrees — indistinguishable from just thresholding binconf's own
confidence. Separately, v4 also had a genuine bug: never trained on a
`SILVER_LABEL=other/CLASSIFIER_PREDICTED=other` (no-conflict) example, so it
flagged 100% of a 632-row held-out set of genuinely-correct "other" rows,
confidently (mean score 0.915). **v4 is not usable and superseded by v5+.**

**v5** (`src/train_fp_detector_v5_no_tags.py`) — fixed both problems: text-only
input (`[ENTITY: X] text`, no tags at all), and correctly-scoped positive/
negative classes (positive = human OR frontier judge says "other", classifier
says stanced; negative = confidently-correct stanced). Held-out val: AUC
0.7118, precision 0.57, recall 0.24 (low — no class-balance correction).
Full-scan on all 32,607 stanced train rows: 1,298 flagged (4.0%), and
crucially **broke the shortcut** — 3.7% flag rate when binconf agrees vs
8.5% when it disagrees (v4 was 0%/97.1%).

**v5b** — same data, added a class-balance weight (positives ×4.174).
Recall improved (0.24→0.46) but AUC stayed flat (0.7118→0.7001) — a pure
threshold/calibration shift, not a real improvement. Confirmed the ceiling
was a **data volume** problem, not calibration.

**v6** (`src/train_fp_detector_v6_expanded.py`) — round 1 of the active-learning
loop: sent v5's 1,298 full-scan flags to frontier (Gemini 3.5 Flash) for
blind verification (no mention of current label). Result: 43.5% overall
precision, **80.5%** precision within the binconf-disagreement subset,
**38.6%** within the binconf-*agreement* subset (n=1,149 — territory no
prior detector could reach at all, since round 1-4 and the raw threshold
rule all require disagreement to fire). Added 564 confirmed positives + 714
confirmed negatives to training (~3x the positive class). Held-out val:
AUC 0.73, precision 0.56, recall 0.53 — **AUC genuinely moved this time**,
confirming more data (not reweighting) was the real lever.

**v7** (`src/train_fp_detector_v7_expanded.py`) — round 2: full-scan v6
(32,607 rows → 2,819 flagged, 8.6%), frontier-verify again. Precision
climbed further: 58.1% overall, 80.9% disagreement / **54.6%** agreement
(up from 38.6%). Added 1,637 confirmed positives + 1,120 confirmed
negatives. Held-out val: **AUC 0.759, precision 0.65, recall 0.64** — first
round where precision AND recall improved together, not traded off.

## 3. The base-rate reality check — read this before citing v7's "65% precision"

**This is the most important finding of the session and it undercuts the
headline numbers above.** Every precision/recall figure in §2 (except the
one below) was measured on the held-out val split, which is drawn from a
training composition deliberately *enriched* toward positives via the
active-learning loop (v7's training set is ~41% positive / 59% negative).
The real 32,607-row population is nowhere near that ratio — the true error
rate for this specific axis is probably somewhere in the low single digits
to ~10%, not ~40%.

**Real human-grounded check, done this session** (the first one for ANY of
v4-v7 — everything else in §2 was AI-judging-AI):
`src/score_fp_v7_on_hitl_r1_human_validation.py`, run against 331 rows from
Nash's `data/hitl/queue_expanded_entity_val_r1.csv` HITL batch
(254 endorsement + 91 hostile, confirmed zero text+entity overlap with
anything in v7's training pipeline). All 331 are human-confirmed genuinely
stanced.

**Result: v7 flagged 65/331 = 19.6% as false alarms.** Combined with v7's
held-out recall (0.64), the real-world precision at plausible true base
rates works out to roughly:

| assumed true error rate | expected real precision |
|---|---|
| 3% | ~9% |
| 5% | ~15% |
| 9% (rough estimate from v6's confirmed-positive count) | ~24% |
| 15% | ~37% |

**Best-guess real precision: somewhere around 15-25%, not 65%.** This is
the same base-rate-dilution effect that made the very first number in this
whole thread (13.8%, round 4) look bad — it just resurfaced after three
rounds of real, genuine improvement, because none of the held-out val
numbers were ever measured on a population resembling the true deployment
distribution.

**Not fully resolved, flagged for next session**: a quick skim of the top
20-30 highest-scoring false alarms in this 65-row set suggested several
look like *citation-as-endorsement* schema edge cases (e.g. "It's in the
video from Vinay Prasad, shown at the point referenced on Steve Kirsch's
Substack" — labeled endorsement toward Kirsch via the project's own
citation-counts-as-endorsement convention, but with no emotional/evaluative
language for the classifier to key on). **This is NOT verified as a
systematic pattern** — only a handful of examples were read, not
categorized rigorously. Nash correctly pushed back on an early framing of
this as some kind of architectural limitation requiring explicit prompting
— it isn't; it's a plain data-coverage question (are citation-style
positive examples under-represented in the current training pools relative
to more "obviously evaluative" language). Worth a proper categorization
pass before concluding anything.

## 4. What recalibration can and can't fix (Nash asked directly, worth preserving)

AUC/ROC is base-rate-invariant; precision is not. Threshold/weight tuning
(what v5b did) moves the operating point along the *same* ROC curve — it
cannot recover "65% precision at 64% recall" applied to the real
population, because that combination only existed on the artificially
enriched val set. What threshold tuning CAN do: let us pick a deliberate,
honest operating point on the real tradeoff curve (e.g. "accept lower
recall for higher precision") **once we know the true base rate** — which
we currently only have rough estimates for (3-15%), not a direct
measurement. The only lever that shifts the curve itself (raises precision
at a *fixed* recall) is a genuinely better model — i.e., continuing the
active-learning loop, not recalibration.

**The concrete next step to close this properly, not yet done**: pull a
genuinely *random* sample (not model-flagged, not enriched) from the full
32,607-row population, hand-label ~100-150 rows for real ground truth. This
would give (a) a direct, non-extrapolated true base rate, (b) a real
precision/recall pair at the true rate, and (c) a legitimate basis for
threshold calibration. Not started.

## 5. Real infra story this session — read before touching any VM next time

`vm2image-20260810-093317`'s home zone (`asia-southeast1-b`, `gpuincrease`
project) hit `ZONE_RESOURCE_POOL_EXHAUSTED` for L4 GPUs — confirmed via a
12-attempt/18-minute retry loop AND a 12-zone sweep (only `us-east1-c`
worked). **Workaround, now proven and reusable**: created a disk image
(`vm2image-fpv5-snapshot`, still exists in `gpuincrease` — works even while
the source VM is stopped) from vm2image's disk, booted a fresh instance
(`vm2image-fpv5-temp`) from that image in `us-east1-c`. Full environment —
conda, all scripts, all checkpoints (v5/v5b/v6/v7) — carried over intact,
no reinstall or retraining needed. This became the actual working VM for
the rest of the session. **If `asia-southeast1-b` is still exhausted next
session, don't wait on the original VM — either reuse `vm2image-fpv5-temp`
directly (currently `TERMINATED`, just start it) or repeat the image
pattern.** Full detail logged in `data/infra_map.jsonl`.

Also found in passing: `conspiracycomments-gce` project has a hard
`GPUS_ALL_REGIONS` quota of 1 — a second GPU VM there fails outright unless
the first is stopped. `stance-twostage-retrain-asb` (that project's VM) was
found idle (0 GPU used, no python running, up 21h) and stopped as
housekeeping.

**All VMs across both projects confirmed `TERMINATED` at session end**:
`stance-r7v3`, `vm2image-fpv5-temp`, `vm2image-20260810-093317` (gpuincrease);
`stance-arch-smoke-test`, `stance-twostage-retrain`, `aug5-disk-reader`,
`stance-arch-image-20260810-212434`, `stance-twostage-retrain-asb`
(conspiracycomments-gce).

**Not cleaned up, still exists**: `vm2image-fpv5-snapshot` image in
`gpuincrease` (storage cost only, no compute cost while unused) — left in
place since it's the fast-path if `asia-southeast1-b` is still exhausted
next session. Delete if no longer needed.

## 6. What "closing the loop" would actually require (still not done)

Everything in §2-3 is diagnostic/candidate-generation infrastructure. To
actually move the stage1 kappa number:
1. Decide on a real precision threshold to act on (needs §4's random-sample
   validation first, not the enriched-val numbers).
2. Take v7's high-confidence flags above that threshold, get them corrected
   (human review, or frontier re-classification once frontier's own
   accuracy against real human ground truth is validated — not yet done
   either, see §3).
3. Apply corrections to the actual training parquet.
4. Retrain the real stage1 gate classifier (`binconf_other015` or its
   successor) on the corrected data.
5. Re-measure stage1 kappa on a genuinely held-out set and compare to
   0.428.

None of steps 1-5 have been attempted this session.

## 7. Also found, not yet acted on

Reddit `id`/`parent_id`/`link_id` columns **do exist** in the raw HITL
source files (e.g. `data/hitl/queue_expanded_entity_val_r1.csv` has all
three) — the final training parquet just drops them during
`src/build_stance_classifier_training_data.py`'s build (confirmed by
reading `load_human_queues()` and `load_irr_shared_rows()` directly — both
read source CSVs with IDs, then explicitly select a column list that
excludes them). This directly contradicts an earlier session's note that
"training data lacks Reddit IDs entirely" for context-walk purposes — that
claim conflated "not in the final built artifact" with "doesn't exist
anywhere." **Not yet checked**: whether this also holds for the
machine/silver-labeled majority of the data (other loader functions in the
same script, not yet inspected). If it does, context-walk may be far more
recoverable for the train population than previously believed — worth
checking before assuming it's out of reach.

## 8. Concrete open items for next session, in rough priority order

1. **Random-sample human validation** (§4) — the real next step before
   trusting any precision number from this detector lineage further.
2. **Categorize the 65 false alarms properly** (§3) — is citation-as-
   endorsement a real, systematic, fixable gap or a couple of cherry-picked
   examples?
3. **Decide whether to run v8** — another active-learning round, now that
   the base-rate reality check exists. AUC has climbed every round
   (0.71→0.73→0.76) with no sign of plateau yet, but cost per round is
   scaling with flag-list size (1,298→2,819 rows; v7's better recall would
   likely flag even more).
4. **Check whether IDs are recoverable for the silver-labeled majority**
   (§7) — would materially change what's possible for context-walk.
5. **Actually close the loop once** (§6), even on a small scale, to learn
   whether fixing labels via this pipeline moves kappa at all before
   investing further in the detector itself.
