# Task: Extend the existing name-disambiguation pipeline to maverick entities

**Status: implemented and run (2026-07-20, uncommitted) — steps 1-4 done,
step 5 (rerun regression + validation, report before/after) not yet
confirmed done.** Supersedes an earlier, wrongly-scoped draft of this
task (`candidate_maverick_surname_variants.csv`, kept on disk as raw
input signal only — see below, don't trust its safe/risky framing).

`src/stage_b_consolidated_corpus_pass.py` and
`src/stage_c_classify_ambiguous.py` were generalized (not forked) with
`--maverick`/`--mainstream` flags, per this task's own stated preference.
A `MAVERICK_AMBIGUOUS_CLUSTERS` dict was defined with 9 clusters
(manning, jones, adams, watkins, garrison, cooper, mccarthy, webb,
malone). The pipeline was run: `data/processed/stage_b_maverick_word_bags.json`,
`data/processed/maverick_entity_disambiguation_classified.csv`, and
`data/processed/stage_c_maverick_signature_words.json` all exist
(built 14:40-14:41). `src/combined_maverick_detector.py` now imports the
classified lookup and does regex-plus-override matching for resolved
bare forms, as step 4 specified. **Not yet confirmed**: whether step 5's
before/after report (has_maverick positive-case count, scorer recall,
resolution rate) was actually produced and reviewed — check for it
before assuming this is fully closed out.

**New complication found 2026-07-20, after this work, during HITL rating
of the stance queues** (see `handoff/task_stance_queues_expansion.md`):
at least two *already-existing* bare-form aliases outside this task's new
clusters are themselves colliding — `"Brand"` (Russell Brand) matching
common-noun uses, and `"Hawking"` (Stephen Hawking, consensus-expert
side) matching the verb "hawking". Neither is a maverick-cluster problem
this task introduced; both predate it. Worth a pass checking the rest of
`UNAMBIGUOUS_MAVERICK_ALIASES` (`src/maverick_authority_verified.py`)
and the consensus-expert bare-form list for the same kind of collision
before trusting `has_maverick`/`has_consensus_expert` counts. Nash is
examining this and may fix the lists and rerun the affected queues.

## The actual problem (corrected framing, 2026-07-20)

`VERIFIED_MAVERICK_AUTHORITY` (446 entities, Nash's reviewed list) is
almost entirely full names. Real corpus text uses many other forms —
bare surnames ("Snowden"), bare first names ("Hunter"), nicknames,
initials — and matching only full names undercounts real citations
(confirmed: 86 of 90 human-labeled positive attribution examples in the
validation queue had *zero* entity match at all, because the text only
used a bare form).

**This is not just a bare-surname problem.** A name-string can resolve
to more than one real-world entity (a shared first name like "Hunter" —
Hunter Biden vs. Hunter S. Thompson — or a shared surname across two
different maverick figures, e.g. "Manning" — Chelsea Manning vs. Bradley
Manning, which may actually be the same person under two name changes,
check), or it can collide with something outside the maverick domain
entirely (a consensus/canon figure's surname, a common English word, an
unrelated real person). The unit of decision has to be **the individual
mention**, not the name-string in the abstract — deciding once at the
list level whether a bare form is "safe to add" is exactly the design
this project already explicitly rejected for the mainstream-expert side
(see `src/stage_c_classify_ambiguous.py`'s docstring: "do NOT use a
global majority vote... would mislabel every real minority-referent
mention").

## The existing pipeline to extend (already built and working)

- **`src/stage_b_consolidated_corpus_pass.py`**: one pass over the
  corpus. Hand-curated `AMBIGUOUS_CLUSTERS` dict (bare form -> named
  candidates -> unambiguous alias phrases for each). For every comment,
  if a specific unambiguous alias appears ("Bill Clinton"), extract a
  15-word-each-side context window as a "labeled" sample for that
  candidate. If only the bare form appears ("Bill"), extract the same
  window as an "unlabeled" sample to be classified later. Also runs a
  secondary credential-pattern extraction ("former/ex- CIA/FBI/...
  officer" + nearby capitalized name) that surfaced real candidates too
  rare to clear the frequency floor any other way.
- **`src/stage_c_classify_ambiguous.py`**: for each candidate, builds
  "signature words" (words disproportionately concentrated in that
  candidate's labeled bags vs. the others in the same cluster — ratio
  >=0.7, count >=3, top 40 kept, with a `clean_bag()` filter to drop
  URL/numeric noise that previously corrupted a cluster's profile). For
  each unlabeled bare instance, scores it against every candidate's
  signature set and classifies it — but only if the winner beats the
  runner-up by >=1.5x margin; ties/close calls are left unresolved by
  design, not forced.
- Existing clusters (`bill`, `hunter`, `kennedy`, `clinton`, `sanders`,
  `rich`, `tucker`) are all mainstream-expert-domain. None currently
  cover maverick entities.

## What's already on disk that feeds cluster definition (integrate, don't ignore)

- `data/processed/maverick_authority_entities.csv` and
  `..._localized.csv` — lift-based bottom-up mining output. Shows
  **actual bare/partial name forms that appear in the corpus**, with
  real positive/negative mention counts and lift scores. This is the
  empirical evidence for which bare forms are even worth building a
  cluster for — don't guess at candidate bare forms, check what's
  actually attested here first.
- `data/processed/maverick_non_person_candidates.csv` — 384 entities
  already flagged (with Wikipedia-description and spaCy-NER-based
  reasoning) as likely non-person. Use this to check whether a candidate
  bare form collides with a known topic/organization term before
  building a cluster for it.
- `src/consensus_experts_verified.py` and `CANONICAL_EXPERTS` (in
  `src/refine_thesis_models.py`) — check candidate maverick bare forms
  against these too. A bare surname colliding across the maverick/
  consensus or maverick/canon boundary is a real risk this project has
  hit before in a different form (see `Robert Redfield` /
  `Robert R. Redfield` ambiguous-name collision noted in
  `consensus_experts_verified.py`).
- `data/processed/candidate_maverick_surname_variants.csv` (356 bare
  surnames, generated 2026-07-20 from the earlier wrongly-scoped
  attempt) — keep as a rough seed list of *which* full names lack a
  bare form at all, but don't treat its implicit "these look fine"
  framing as a decision; it wasn't built from corpus evidence or
  collision-checked against anything.

## What to actually do

1. **Definition pass (judgment work, guardrail 3, the real content of
   this task)**: using the lift-based mining files as evidence of what's
   actually attested in the corpus, define a `MAVERICK_AMBIGUOUS_CLUSTERS`
   dict mirroring `AMBIGUOUS_CLUSTERS`'s exact structure (bare form(s) ->
   candidates -> unambiguous alias phrases). For each candidate bare
   form, explicitly check: (a) does it collide with another maverick
   entity, (b) does it collide with a consensus/canon entity, (c) does
   it collide with something in the non-person-candidates file. Forms
   with no real collision risk after checking don't need a cluster at
   all — add them straight to `VERIFIED_MAVERICK_AUTHORITY` as plain
   aliases. Forms with genuine ambiguity go into the cluster dict for
   per-instance classification.
2. Adapt Stage B's word-bag collection for the new cluster dict —
   reuse `extract_word_bag`/`WINDOW_WORDS`/`MAX_SAMPLES_PER_CANDIDATE`/
   `STOPWORDS`/the credential-pattern extraction as-is, just pointed at
   `MAVERICK_AMBIGUOUS_CLUSTERS` instead of `AMBIGUOUS_CLUSTERS`. Prefer
   generalizing the existing script to take a cluster-dict + output-path
   parameter over forking a duplicate copy (this project has accumulated
   enough duplicated `load_entities_split_corrected()`-style copies
   already this session — don't add another one). Output something like
   `data/processed/stage_b_maverick_word_bags.json`.
3. Run Stage C's classification logic against that output (same
   preference: generalize the existing script's I/O paths rather than
   duplicate it). Output
   `data/processed/maverick_entity_disambiguation_classified.csv` +
   a signature-words file for human sanity-check, same as the existing
   pipeline produces.
4. Merge results: unambiguous aliases go straight into
   `VERIFIED_MAVERICK_AUTHORITY`. Per-instance classifications for
   genuinely ambiguous forms become a separate lookup (comment id ->
   resolved candidate or unresolved) — **this changes how `has_maverick`
   needs to be computed for those specific comments**: not a pure regex
   match anymore, but regex-plus-lookup-override for the ambiguous
   subset. Flag this architectural change clearly when reporting back,
   don't silently fold it into the existing regex-only construction.
5. Rerun the core regression and the attribution-scorer validation
   (`src/validate_against_human_labels.py`). Report before/after for
   both — expect `has_maverick` positive-case count and the scorer's
   recall to increase, but also report how many mentions ended up
   genuinely unresolved (left out by design), not just the resolved
   count.

## When done

Report the cluster definitions used and why, the unambiguous-alias
count added directly, the ambiguous-cluster resolution rate (mirror how
the mainstream-expert side reported per-cluster resolution rates —
sanders 47.5%, hunter 41.3%, etc. — leaving a lot unresolved is expected
and correct, not a shortfall), and the before/after regression +
validation comparison. Don't overwrite existing result files directly —
save alongside for comparison, same convention as other reruns this
session.
