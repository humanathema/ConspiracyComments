# Task: Final reconciliation of the credentials-problem finding before thesis write-up

**Status: not started (2026-07-22).** Nash is ready to write up the
credentials-problem finding alongside the maverick whistleblower-split
and link-source-tier findings (both already validated to full
floating-point precision this session) -- this is the one remaining gap
before all three are equally citable. Three items, all bounded.

## Why

`data/processed/credentials_problem_integration_report.md` (via
`src/integrate_credentials_problem.py`) is currently the least-rigorous
of the three headline findings from today's session:

1. It reports raw percentage differences (movement-internal-anonymous
   citation share: 19.41% Anti-Consensus vs. 4.58% Consensus-Aligned)
   with **no significance test attached** -- the report's own text says
   "no significance test run yet -- treat as descriptive." Every other
   finding in this project has a kappa/p-value attached; this one doesn't.
2. Its `comment_stance` labeling (Anti-Consensus / Consensus-Aligned /
   Neutral-Other) is computed with the **old flat 3-class stance
   classifier** (`STANCE_MODEL_PATH = 'data/processed/stance_classifier_3class.joblib'`,
   see `integrate_credentials_problem.py`'s `get_pred()` closure) --
   never migrated to the two-stage cascade model (kappa=0.370) that every
   other stance-dependent finding this session now uses. This is a real
   inconsistency: the classifier upgrade was the entire premise of
   today's work on the maverick-split and per-entity findings, and this
   one script was missed.
3. The credentials numbers changed several times today across multiple
   iterations (original buggy report: 1.51%/0.21% movement-internal share
   -> intermediate over-generalized version: much higher -> final
   corrected version: 19.41%/4.58%). Given how much iteration this
   specific pipeline went through, a clean final rerun with an explicit
   diff against the current file is cheap insurance against a stale
   intermediate number having survived by accident -- the same discipline
   already applied to the `+0.3747` vs `+0.2999` coefficient trace earlier
   today.

## What to build

### 1. Migrate `comment_stance` to the cascade model via the existing cache

Don't re-score from scratch with a fresh cascade pass -- `data/processed/
entity_mentions_cache_2stage_pooled.parquet` already has cascade-scored
`merged_maverick`/`merged_consensus` rows (one per comment, `predicted_label`
in {hostile, endorsement, other}) built exactly for this purpose. Replace
`integrate_credentials_problem.py`'s `get_pred()` closure (which currently
loads the stance model directly and re-scores each entity-mentioning
comment with `vec.transform`/`clf.predict_proba`) with a lookup against
this cache's `merged_maverick`/`merged_consensus` `predicted_label`
column, joined on `comment_id`. Keep the same downstream logic
unchanged (`is_anti_consensus = (mav_stance=='endorsement') or
(con_stance=='hostile')`, etc.) -- only the stance-scoring source changes,
not the combination logic.

### 2. Add a significance test to the crosstab

A chi-square test of independence (`scipy.stats.chi2_contingency`) on the
comment-level precedence crosstab (`comment_stance` x `category`, the
2x4-ish table already in the report) is the natural fit -- same test
family already used elsewhere in this project's HITL work. Report the
statistic, df, and p-value alongside the existing percentage table, not
as a replacement for it.

### 3. Clean final rerun + diff

After (1) and (2) land, rerun `integrate_credentials_problem.py`
end-to-end (or the fast `reclassify_credentials_citations.py` path if
only the stance-source changed, whichever is actually correct given what
changed -- note `reclassify_credentials_citations.py` explicitly reuses
the OLD `comment_stance` column unchanged, which will no longer be valid
once item 1 lands, so this likely needs the full
`integrate_credentials_problem.py` rerun, not the fast-path script).
Diff the new `credentials_integration_results.csv` /
`credentials_problem_integration_report.md` against the current versions
and report exactly what changed and why -- don't just overwrite silently.
If the corrected `comment_stance` labeling shifts the headline
percentages (19.41%/4.58%), report the new numbers plainly, the same way
today's earlier corrections were reported.

## When done

All three headline findings (maverick whistleblower-split, link-source-tier
split, credentials-problem) should be at the same standard: validated
model, significance-tested, single canonical output file with no
unexplained drift from prior iterations. This is the last blocker before
Nash starts write-up on the credentials-problem section specifically --
the other two findings are already there.
