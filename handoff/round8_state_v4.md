# ConspiracyComments — Round8 State v4 (supersedes v3)

**Last updated: 2026-08-11 (this session)**

v3 had two wrong claims corrected here:
1. "VM1 is CONFIRMED RUNNING" — VM1 (`stance-arch-image-20260810-212434`) is TERMINATED.
2. "VM2 running redesign/split arm" — VM2 was running a single-stage old-gen retrain (wrong
   architecture). That was killed this session. v3's "reproduces 0.5283" referred to an
   earlier completed run, not the then-current process.

---

## §0. Current VM state (verified 2026-08-11)

| VM | Project | Zone | Status | Running |
|---|---|---|---|---|
| `vm2image-20260810-093317` | gpuincrease | asia-southeast1-b | RUNNING | r7v2 two-stage retrain (~3h left) |
| `stance-twostage-retrain` | conspiracycomments-gce | us-east1-c | RUNNING | r7v1 two-stage retrain (~3h left) |
| `aug5-disk-reader` | conspiracycomments-gce | asia-southeast1-a | RUNNING | idle (e2-small, cheap) |
| `stance-arch-image-20260810-212434` | conspiracycomments-gce | asia-southeast1-a | TERMINATED | — |

**Stop when done**: aug5-disk-reader (e2-small but still billing).

### Retrain scripts in flight

**stance-twostage-retrain** (`/home/nash/retrain_r7v1_r7v2.log`):
```bash
TAG=r7v1 INPUT_FILE=.../round7_bigval_split.parquet SAVE_ROOT=/home/nash/retrain_twostage \
  python3 /home/nash/train_twostage_patched.py
```
Produces: `/home/nash/retrain_twostage/r7v1_baseline_stage{1,2}/` and
`r7v1_redesign_stage{1,2}/`. Val preds saved to `~/preds_r7v1_baseline.csv` and
`~/preds_r7v1_split.csv`.

**vm2image-20260810-093317** (`/home/nash/retrain_r7v2.log`):
```bash
TAG=r7v2 INPUT_FILE=.../round7_bigval_split_v2.parquet SAVE_ROOT=/home/nash/retrain_twostage \
  python3 /home/nash/train_twostage_patched.py
```
Produces: `/home/nash/retrain_twostage/r7v2_baseline_stage{1,2}/` and `r7v2_redesign_stage{1,2}/`.

`train_twostage_patched.py` is the correct patched script (saves to SAVE_ROOT, not /tmp).
It lives at `/home/nash/train_twostage_patched.py` on both VMs.

---

## §1. Committed best result (verified git show 5bf8f0b)

**5-model majority-vote** (r7v2_split + r7v1_baseline + r5v2_baseline + r5v2_split +
r7v3_baseline) + stage2-only frontier escalation:
- Baseline ensemble: **0.5311** (680-row val)
- With frontier: **0.5773** (commit `5bf8f0b`, 2026-08-05)

Individual two-stage ModernBERT val kappas (Aug 4, all on VM2 at `~/preds_r*.csv`):

| model | val kappa |
|---|---|
| r7v1_baseline | 0.5136 |
| r7v2_split | 0.5111 |
| r7v3_split | 0.5124 |
| r7v3_baseline | 0.5089 |
| r7v1_split | 0.4511 |
| r5v3_baseline | 0.4489 |
| r5v2_split | 0.4429 |
| r5v2_baseline | 0.4367 |
| r5v3_split | 0.3560 |

**0.5311** confirmed = the Aug 4 five-model ensemble baseline. Not a mystery number.

---

## §2. Aleatoric inference results (418 usable rows, 2026-08-11)

All preds in `/home/nash/outputs/aleatoric_preds/` on VM2.

### Valid two-stage ModernBERT results

| file | val kappa | aleat kappa | notes |
|---|---|---|---|
| `aleat_r7v3_baseline.csv` | 0.5089 | **0.4000** | original r7v3 checkpoint |
| `aleat_r7v3_retrain_baseline.csv` | 0.5283 | **0.5594** | fresh retrain, best individual so far |
| `aleat_r7v3_retrain_redesign.csv` | 0.5374 | **0.2116** | ⚠️ big overfitting signal — see §4 |

### Invalid (RoBERTa smoke-test checkpoints — not the committed ensemble models)

| file | aleat kappa | why wrong |
|---|---|---|
| `aleat_r5v2_baseline.csv` | 0.1704 | RoBERTa checkpoint, not ModernBERT |
| `aleat_r5v2_redesign.csv` | 0.0587 | RoBERTa checkpoint, not ModernBERT |
| `aleat_og_*.csv` (4 files) | -0.07 to 0.03 | single-stage inference on wrong checkpoints |

The ModernBERT r5v2 checkpoints (from Aug 4 run) were lost to /tmp. The
`checkpoints_twostage/r5v2/` directory on VM2 contains RoBERTa models from the Aug 3 smoke
test — these are NOT the committed ensemble models.

### Still needed for committed 5-model aleatoric check
- r7v1_baseline aleat preds → need r7v1 retrain to finish first (in flight)
- r7v2_split aleat preds → need r7v2 retrain to finish first (in flight)
- r5v2_baseline + r5v2_split aleat preds → need a NEW r5v2 ModernBERT retrain (not started)

---

## §3. Two-stage checkpoints on VM2

Location: `/home/nash/outputs/round8/checkpoints_twostage/`

| path | stage1 | stage2 | val kappa | notes |
|---|---|---|---|---|
| `r5v2/baseline/` | ✓ | ✓ | ~0.44 | ⚠️ RoBERTa, not ModernBERT |
| `r5v2/redesign/` | ✓ | ✓ | ~0.44 | ⚠️ RoBERTa |
| `r7v3/baseline/` | ✓ | ✓ | 0.5089 | original r7v3 ModernBERT |
| `r7v3_retrain/baseline/` | ✓ | ✓ | 0.5283 | fresh retrain ModernBERT |
| `r7v3_retrain/redesign/` | ✓ | ✓ | 0.5374 | fresh retrain ModernBERT |

After retrains finish, new checkpoints will be at:
- VM2: `/home/nash/retrain_twostage/r7v2_{baseline,redesign}_stage{1,2}/`
- Retrain VM: `/home/nash/retrain_twostage/r7v1_{baseline,redesign}_stage{1,2}/`

---

## §4. Key finding: split-arm overfitting signal

r7v3_retrain_redesign (split arm): val kappa **0.5374** → aleat kappa **0.2116**.
That's a 0.32 kappa gap. The baseline arm of the same retrain generalises well
(val 0.5283 → aleat 0.5594, actually improves on aleatoric). This strongly suggests
the split/redesign arm is overfitting to the val distribution in a way the baseline arm
doesn't. Worth noting in the thesis.

---

## §5. What to do when retrains finish (~3h from 2026-08-11 19:41 NZST)

1. **Run inference on retrain VM** for r7v1 aleatoric preds. Script to use:
   `/home/nash/infer_aleatoric_twostage.py` (already on VM2 — copy it to retrain VM or adapt).
   Checkpoints: `/home/nash/retrain_twostage/r7v1_baseline_stage{1,2}/` and
   `/home/nash/retrain_twostage/r7v1_redesign_stage{1,2}/`.

2. **Run inference on VM2** for r7v2 aleatoric preds using the same script.
   Checkpoints: `/home/nash/retrain_twostage/r7v2_baseline_stage{1,2}/` etc.

3. **Compute ensemble kappa** on aleatoric with however many models are available.
   For the committed 5-model, you'll still be missing r5v2_baseline and r5v2_split
   (need another retrain job, ~1.5h on either VM).

4. **Optionally start r5v2 retrain** on whichever VM finishes first:
   ```bash
   TAG=r5v2 INPUT_FILE=/home/nash/stance_classifier_training_data_round5_bigval_split_v2.parquet \
     SAVE_ROOT=/home/nash/retrain_twostage python3 /home/nash/train_twostage_patched.py
   ```
   Parquet is already on VM2 (`ls /home/nash/stance_classifier_training_data_round5*`).

5. **Infer then ensemble**: once you have aleat preds for all 5 committed models, compute
   majority-vote kappa on 418 rows and compare to val kappa 0.5311.

---

## §6. Entity-prefix / stance-mask bug (resolved)

`infer_with_entity.py` had stance_mask backwards — fixed on VM2. `preds_r7v3_baseline_fresh.csv`
(kappa -0.0285) was from the broken version — ignore it. Round9 inference uses correct convention.

The corrected inference script for old-gen two-stage (no entity prefix) is:
`/home/nash/infer_aleatoric_twostage.py` on VM2.

---

## §7. 8-model weighted ensemble (Aug 11 finding — unvalidated)

Today's session found an 8-model weighted ensemble claiming kappa=0.5621 on the 680-row val
set (no frontier):
```python
weights = {'r7v2_baseline': 2, 'r5v2_split': 1, 'r7v1_split': 1, 'r7v2_split': 2,
           'r7v1_baseline': 1, 'r8_r7v1': 2, 'r8_r5v2': 2, 'r8_r7v3': 1}
```
Source: JSONL search this session. NOT committed. Includes round8 entity-prefix models.
0.5621 < 0.5773 (committed with frontier) so this isn't clearly better. Validate before use.

---

## §8. Round9 status

`src/infer_round9_twostage.py` and `src/build_round9_training_data.py` exist (untracked).
Created by a prior session after considering round8 done — not something Nash requested.
Verify: `git log --diff-filter=A -- src/infer_round9_twostage.py`

---

## §9. Naming convention

- `r7`/`r5` = round7/round5 data versions. `v` suffix = data version within round.
- "baseline arm" = has_stance vs other in stage1; "redesign/split arm" = neutral vs
  non-neutral in stage1, 3-way in stage2. Ambiguous → other at scoring time.
- `retrain_twostage/` = new checkpoints from patched train.py (saves to SAVE_ROOT).
- `checkpoints_twostage/` = older checkpoints (some RoBERTa, some ModernBERT — check first).
