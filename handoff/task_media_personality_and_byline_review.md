# Media-personality category + byline-extraction review (raised 2026-07-27/28, not started)

Background-agent audit finding, not yet acted on.

## 1. Media-personality category is arbitrary; whistleblower category isn't

The "whistleblower vs. media-personality" stance contrast (a core piece of
the "leak-source figures endorsed, media-personality mavericks attacked"
finding) rests on an asymmetric foundation:

- Whistleblower side: a reviewed 124-entity category inside the
  446-entity hand-audited `maverick_authority_verified.py` list.
- Media-personality side: **4 hardcoded names** in a notebook analysis
  cell (`alex jones, tucker carlson, roger stone, matt gaetz`,
  `ConspiracyMaster_Refactored.ipynb` cell 200) — no equivalent
  systematic selection process, no documented review.

This is a real cherry-picking risk for the contrast as currently framed.
Fix: build a reviewed `media_personality`/`platform_commentator` category
with the same rigor as the whistleblower one (same kind of hand-review
process `maverick_authority_verified.py` itself went through), not more
hardcoded names.

Also worth knowing when citing the underlying stance numbers: the stance
classifier has **kappa 0.243-0.274, macro AUC 0.649** on held-out human
labels (documented in `handoff/task_stance_endorsement_blindspot.md`,
not visible from the notebook cells presenting the headline numbers),
specifically weak at confident-endorsement detection. One number that
looks like a symptom of this: `wikileaks.org` shows `pct_hostile =
0.0182%` (1 of 5,486) — implausibly extreme, more consistent with
link-dump mentions defaulting away from "hostile" than genuine
near-unanimous endorsement.

## 2. Byline extraction's "100% precision" claim doesn't survive contact with its own output

`src/run_byline_extraction.py` ran once (2026-07-22) against 500 URLs:
352 successful (70.4%), method breakdown json-ld 232 / meta-tag 75 /
html-pattern 45 / failed 148.

The reported "100% precision after refinement"
(`handoff/byline_extraction_results.md`) is inflated by construction: 2
of 30 spot-checked rows failed, the code was patched to fix those exact 2
failure modes, then the *same* 30-row sample was re-scored as 30/30 —
fitting to the validation set, not an independent re-check. Confirmed
still-live: the "fixed" Statista date-leakage bug (a date extracted as if
it were a byline) still appears **twice** in the actual 352-row output
(`"May 7, 2026"` and `"Jul 13, 2022"`, both `html-pattern` method, both
statista.com URLs) — the fix wasn't actually sufficient, or wasn't
applied full-run.

Fix: re-run the spot-check on a fresh, non-overlapping sample after any
further fixes, and specifically re-check the statista.com/date-leakage-prone
`html-pattern` rows across the full 352.

No downstream use yet either way — nothing currently consumes
`byline_extraction_results.csv` (per `handoff/task_author_byline_extraction.md`'s
own scoping as a standalone artifact for later joining).

## Ranked fixes

1. Build the reviewed `media_personality` category — biggest risk in the
   current finding as stated.
2. Re-validate byline extraction on a fresh sample.
3. Decide, once and for all, whether `entity_final_review.csv` (stale
   since 2026-07-14, superseded for the two headline constructs but still
   imported by 22 other scripts per an earlier audit) needs regenerating.
