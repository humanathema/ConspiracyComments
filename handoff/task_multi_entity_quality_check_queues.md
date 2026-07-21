# Task: Generalize the Jones quality-check queue to Wikileaks/Assange/Snowden/Greenwald

**Status: not started. Mechanical generalization of an existing, working
script — bounded, low-risk, safe for Antigravity.**

## Why

`src/build_jones_stance_quality_queue.py` built a 99-row hand-labeled
quality-check queue for Alex Jones and found the stance classifier had a
real, specific weakness (couldn't reliably detect endorsement — see
`handoff/task_stance_endorsement_blindspot.md`). That led to the 3-class
redesign (`stance_classifier_3class.joblib`, hostile/endorsement/other),
now wired into `per_entity_stance_breakdown.py`/`per_entity_stance_over_time.py`.

Under the new 3-class model, Wikileaks/Assange/Snowden/Greenwald all read
as heavily ENDORSED (67-88%, see `data/processed/per_entity_stance_breakdown_unfiltered.csv`).
Nash's specific concern: he's seen "controlled opposition"/"limited
hangout" accusations about these figures in the corpus too (same
rhetorical pattern as the Jones "shill" framing) — and the Jones check
specifically found the model over-predicts endorsement for **sarcastic
or mocking references that lack hostile-coded vocabulary** (e.g. "gay
frogs" mockery scored as confidently endorsing). A "limited hangout"
accusation has exactly that shape — it can read as neutral/factual on
the surface while functioning as an accusation. So there's a specific,
non-generic reason to distrust the 88%/71% endorsement numbers for these
entities until checked the same way Jones was, not just general caution.

## What to build

Generalize `src/build_jones_stance_quality_queue.py` into a script that
takes a `--entity` argument (or loops over a small fixed list) instead of
hardcoding `TARGET_ENTITY = 'alex jones'`. Concretely:

1. **Update to the 3-class model** — the existing Jones script uses the
   OLD binary `stance_classifier.joblib` and buckets by
   `P(endorsement)<0.35/0.35-0.65/>0.65`. That's now stale. Point at
   `stance_classifier_3class.joblib` instead and stratify by the model's
   **predicted_label** (hostile / endorsement / other) directly, same
   pattern as `per_entity_stance_breakdown.py`'s `build_long_table()` —
   don't reinvent the bucketing logic, copy that pattern.
2. **Entities to cover**: `wikileaks`, `assange` (note: `assange` and
   `julian assange` are separate entity_keys in the per-entity breakdown
   — check both, and use whichever surface form has more mentions, or
   combine them if that's simpler — use judgment but note the choice
   explicitly in the script's docstring, don't silently pick one), `snowden`
   (same note re: `edward snowden`), `greenwald`.
3. **Sample size**: ~100 per entity (same as Jones — enough for a rough
   per-class accuracy read, not more than the training data can support
   precision-wise). Stratify by predicted_label so `other` and
   `endorsement` (both rarer than `hostile` for these entities) still
   get real coverage rather than being swamped by hostile-bucket rows.
4. **Output**: `data/hitl/queue_{entity}_stance_quality_check.csv` per
   entity (same schema as the Jones one: `id, full_text, human_stance,
   notes, entity_spans, parent_id, link_id`), predictions saved
   separately per entity (same blind-labeling discipline as Jones — do
   NOT put predicted probabilities in the labeling CSV).
5. **Write a scoring script too** (generalize `score_jones_stance_quality_check.py`
   the same way) so once Nash labels these, computing accuracy/kappa per
   entity is a one-command operation, not manual work each time.

## Guardrails

- This is queue-BUILDING only. Do not attempt to label these queues
  yourself — labeling is Nash's job, same as the Jones one.
- Do not touch `stance_classifier.joblib` (binary) or
  `stance_classifier_3class.joblib` — read-only here.
- Do not rerun or modify `per_entity_stance_breakdown.py` /
  `per_entity_stance_over_time.py` as part of this task.
- If `assange`/`julian assange` (or `snowden`/`edward snowden`) turn out
  to need different handling than described above, say so explicitly in
  the walkthrough rather than silently picking an interpretation.
