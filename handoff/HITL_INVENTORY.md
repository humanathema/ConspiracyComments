# HITL Labeling Inventory

Comprehensive catalog of every human-in-the-loop labeled dataset in this
project, built 2026-07-21 while scoping an inter-rater-reliability (IRR)
push. Every count here was verified directly against the actual CSVs
(`.notna() & .str.strip() != ''` on the real label column) — an earlier
pass of this same check had a bug (`str(NaN)` stringifies to `"nan"`,
which isn't empty, so it silently counted several fully-unlabeled files
as "labeled"). Don't trust row counts for these files from anywhere else
without re-checking; this file is now the source of truth going forward,
keep it updated.

## Group A: real, existing ground truth (single-rater — Nash only, IRR-ready)

| construct | canonical file | n labeled | label scheme |
|---|---|---|---|
| stance (hostile/endorsement/other) | `data/hitl/queue_consensus_stance.csv` + `queue_maverick_stance*.csv` + rounds 2-7 | ~1,344 | hostile / endorsement / neutral / ambiguous / wrong_match (neutral+ambiguous fold to `other` at training time) |
| personal_experience | `data/hitl/queue_personal_experience.csv` | 100 | positive / lean_positive / negative / unsure |
| procedural_skepticism | `data/hitl/queue_procedural_skepticism.csv` | 100 | positive / lean_positive / negative / unsure |
| maverick_authority | `data/hitl/queue_maverick_authority.csv` | 197 | positive / lean_positive / negative / unsure |
| hedged_suspicion | `data/processed/hedged_suspicion_hitl_queue_deduped.csv` (NOT in `data/hitl/` — the `data/hitl/HITL_hedged_suspicion.csv` copy is a different, empty artifact, don't confuse them) | 725 | binary `hitl_label` (0/1) |
| appeal_to_authority | `data/processed/appeal_to_authority_candidates.csv` (also NOT in `data/hitl/`) | 225 | binary `hitl_label` (0/1) |
| entity stance quality-checks | `data/hitl/queue_{wikileaks,assange,snowden,greenwald,jones_short}_stance_quality_check.csv` | 99 wikileaks done, 4 pending | same as stance |

`queue_intra_rater_hedged_suspicion.csv` (100 rows, unlabeled as of this
writing) is a **self**-consistency check (Nash re-rating a past sample),
not inter-rater — don't count it toward IRR, it answers a different
question (am I consistent with myself over time, not do two people agree).

## Group B: NO real human ground truth found anywhere in the repo

Checked `data/hitl/*.csv` AND `data/processed/*.csv` for every plausible
file per construct. Every file found for these four has an entirely
empty human-label column (`human_label`/`human_verdict`, 100% NaN,
verified by direct dtype/`.isna()` check, not string-parsing) — the only
populated columns are `label_lite`/`label_flash`/`label_pro`/`label_v2_multi`,
which are LLM cascade outputs (the Gemini multi-pass pipeline flagged
elsewhere in project memory as the source of a real budget blowout), not
human ratings, despite files being named `HITL_*.csv`.

| construct | files checked (all empty on human_label/verdict) |
|---|---|
| anti_establishment_stance | `HITL_anti_establishment_stance.csv`, `anti_establishment_stanceresults.csv`, `ensemble_anti_establishment_stance.csv`, `cascade_anti_establishment_stance.csv` |
| insider_ethos | `HITL_insider_ethos.csv`, `insider_ethosresults.csv`, `ensemble_insider_ethos.csv`, `cascade_insider_ethos.csv` |
| reasonableness_performance | `HITL_reasonableness_performance.csv`, `reasonableness_performanceresults.csv`, `ensemble_reasonableness_performance.csv`, `cascade_reasonableness_performance.csv` |
| source_citation | `HITL_source_citation.csv`, `source_citationresults.csv`, `ensemble_source_citation.csv`, `cascade_source_citation.csv`, `STRATIFIED_SAMPLE_source_citation.csv` |

**`smart_priority_review` — RETIRED, confirmed by Nash (2026-07-21) not a
real construct.** Was likely a defunct review-queue/triage mechanism
rather than an actual epistemic-style category — don't write a codebook
for it, don't include it in any future labeling or IRR round.
`HITL_smart_priority_review.csv` can be left alone or deleted at Nash's
convenience; not tracked as an open construct anymore.

**Also unresolved for these four: no rigorous codebook definition exists
anywhere in the repo either.** `src/classification.py`'s LLM prompt (the
only place these category names are defined at all) just lists the bare
names with zero elaboration — the LLM was expected to infer meaning from
the name alone. That's not a labeling gap you can just staff-fill; before
anyone (Nash or an external rater) can label a first batch consistently,
each of these four needs a real definition written down (2-3 sentences +
1-2 examples, same shape as `queue_consensus_stance_CODEBOOK.md`).
**This is Nash's judgment call, not something to guess/invent — do not
fabricate a codebook for these and start labeling against it.**

## Next steps (see `handoff/task_irr_sample_builder.md` for the mechanical build)

1. Nash writes a short codebook definition for each remaining Group B
   construct (or explicitly retires any others that turn out not to
   matter anymore, same as `smart_priority_review` above).
2. Build first-pass labeling queues for Group B (~25-30 rows each, drawn
   from the existing LLM-cascade-scored candidate pools, presented blind
   with no LLM label shown — a completely fresh single-rater pass).
3. Once Group B has real labels, treat it identically to Group A for
   step 4.
4. For all of Group A (+ Group B once labeled): build IRR blind samples
   (~20-25 rows per construct, stratified by existing label, reusing
   already-labeled rows with the label stripped) for external raters.
5. `hitl_rater.py` needs a rater-identity mechanism so multiple raters'
   submissions don't collide — see the tool's own changelog for what's
   already been added.
