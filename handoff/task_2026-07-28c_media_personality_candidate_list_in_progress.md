# Media-personality candidate list — IN PROGRESS, 2026-07-28

Picking up `handoff/task_media_personality_and_byline_review.md`'s ranked
fix #1: the "whistleblower vs. media-personality" stance contrast rests
on an asymmetric foundation (whistleblower = reviewed 124-entity category
in `maverick_authority_verified.py`; media-personality = 4 hardcoded
names in a notebook cell, no systematic process). This builds a properly
sourced candidate list for the media-personality side, same rigor as the
whistleblower one.

## Read this first if picking up cold

An earlier attempt today tried to do this via an LLM judgment call
(Kaggle kernel `tobiasnashktc/entity-authority-type-judge`, asked
Qwen2.5-1.5B to classify entities into consensus_expert/maverick_credentialed/
media_personality/not_applicable from just a name + 2 examples) — **that
failed**, defaulted to `consensus_expert_candidate` for 61% of everything
including Trump/Hitler/Assange with confabulated reasoning. Full detail
in context-repo `conspiracycomments` compartment, key
`job_entity_authority_type_2026-07-28`. Don't repeat that approach.

**The correct approach, matching how the whistleblower list was actually
built**: `src/build_maverick_candidate_list.py` did NOT use an LLM at
all. It pulled real names from Wikipedia list/category pages (List of
whistleblowers, Category:JFK conspiracy theorists, Category:HIV/AIDS
denialists, etc — see that file's own docstring), then scored each
candidate by real corpus mention frequency using `pyahocorasick` (single
O(n) pass over the full comment text, not just NER-extracted strings —
important, since NER-string matching was separately found this session
to have a real recall problem, see `job_topdown_entity_expansion_2026-07-28`
in context-repo). Output: a CSV with a blank `decision` column for
Nash's manual review, same guardrail as everything else entity-related in
this project (`ANTIGRAVITY_HANDOFF.md`'s guardrail #3 — entity-list
membership is not the AI's call to make unsupervised).

## Plan (deterministic, no LLM)

1. **`src/query_media_personality_candidates.py`** (new, modeled on
   `src/query_petscan_experts.py`'s Wikipedia Category API pattern) —
   pull members of media/commentary-related Wikipedia categories:
   - Category:American television talk show hosts
   - Category:American political commentators
   - Category:American podcasters
   - Category:American talk radio hosts
   - Category:American political pundits
   (exact category names need verifying against live Wikipedia — some of
   these may not exist verbatim, check `list=categorymembers` response
   before trusting the pull silently returns empty).
   Output: `data/processed/media_personality_wikipedia_candidates.csv`

2. **`src/build_media_personality_candidate_list.py`** (new, modeled on
   `src/build_maverick_candidate_list.py`'s scoring stage) — score every
   candidate name from step 1 against the full r/conspiracy corpus
   (`data/processed/empath_scores_full_mapped.parquet`, `text` column,
   `id` column) via `pyahocorasick`, single pass. Also include the 4
   already-hardcoded names (Alex Jones, Tucker Carlson, Roger Stone, Matt
   Gaetz) plus anyone already in `maverick_authority_verified.py`'s
   existing loose media-adjacent entries (Joe Rogan under
   `rogan_guest_scientist`, Alex Jones/Tucker Carlson/Matt Gaetz under
   `conspiracy_general`) as known-positive calibration rows.
   Output: `data/processed/media_personality_candidates_scored.csv` with
   columns matching `maverick_candidate_entities_scored.csv`'s shape
   (name, source_category, corpus_mention_count, `decision` blank column).

3. Do NOT merge into `maverick_authority_verified.py` or anywhere else —
   stop at the scored candidate CSV, same as the original maverick
   candidate list did. That's Nash's review step.

## Status log

- 2026-07-28 [this session]: task doc written, about to start step 1.
- 2026-07-28 [this session]: Step 1 done. `src/query_media_personality_candidates.py`
  written and run locally (deterministic Wikipedia Category API pull, no
  LLM). "Category:American_political_pundits" checked against the live
  API first and doesn't exist -- dropped. 4 categories used (TV talk show
  hosts, political commentators, podcasters, talk radio hosts) ->
  1,503 unique candidates -> `data/processed/media_personality_wikipedia_candidates.csv`.
- 2026-07-28 [this session]: Step 2 hit a real blocker -- a THIRD,
  concurrently-running Claude Code session (not this one, not Antigravity)
  did a verified cloud migration and deleted
  `data/processed/empath_scores_full_mapped.parquet` locally (byte-verified
  against a Kaggle copy first, not an accident -- see context-repo
  `conspiracycomments` compartment, search "cloud migration" /
  `task_cloud_migration_2026-07-28.md`). The file now only exists in the
  `tobiasnashws/conspiracycomments-canonical-corpus` Kaggle dataset.
  Pivoted: ported the scoring script to a Kaggle CPU kernel instead of
  regenerating anything locally -- `surge-compute/kaggle_media_personality_score_kernel/`,
  pushed as `tobiasnashws/media-personality-candidate-score`, reads both
  the candidates CSV (uploaded as `tobiasnashws/media-personality-wikipedia-candidates`)
  and the existing canonical-corpus dataset (read-only, per Antigravity's
  standing instruction not to merge anything new into that dataset).
  Running as of this log entry -- check kernel status before assuming
  done. If it errored, `_find_input_file` (os.walk over /kaggle/input)
  should rule out the mount-path bug found earlier today
  (job_entity_authority_type_2026-07-28) as the cause.
- 2026-07-28 [this session]: v1 of the scoring kernel COMPLETED (no
  crash) but produced a real bug -- ALL 1,504 candidates, including the
  5 known-positive calibration names (Alex Jones, Tucker Carlson, Joe
  Rogan, Roger Stone, Matt Gaetz -- names known to appear thousands of
  times in this corpus), scored exactly 0 corpus_mentions. Not a
  plausible real finding, a bug. Ruled out so far via v2/v3 diagnostic
  kernels (same kernel id, versions 2-3):
  - Corpus file itself is fine: mounted correctly, 21,349,908 rows
    scanned (matches the known Reddit-long-comment corpus size), real
    populated text content confirmed by printing sample rows directly.
  - The pyahocorasick matching algorithm itself is fine in isolation: a
    1-word automaton (just "Alex Jones") correctly matches a synthetic
    test string. Rebuilding the SAME test with the full 1,504-word
    automaton (not just 1 word) ALSO correctly matches -- so it is not a
    scale/library-limit issue with a large word list either.
  - No null/non-string entries in the candidate names list.
  So both halves work in isolation but the real per-row scan loop over
  actual corpus batches still returns zero matches. v4 (pushed, running
  as of this log entry) adds row-level debug prints inside the actual
  scan loop for the first 3 real corpus rows (raw type checks, a plain
  Python `in` sanity check independent of the automaton, and the
  automaton's raw hit list for those specific rows) to localize the
  exact point of failure. Not yet resolved -- check kernel
  tobiasnashws/media-personality-candidate-score version 4+ log before
  assuming this is fixed or trusting media_personality_candidates_scored.csv
  from v1 (that file exists but is worthless -- all-zero, do not use it).
- 2026-07-28 [this session]: ROOT CAUSE FOUND (v5's targeted diagnostic --
  searched for a real corpus row containing "alex jones"/"tucker
  carlson"/"joe rogan" and ran the automaton on that exact row: it
  matched correctly every time). So per-row matching was never broken.
  The bug was one line at the very end: `combined["corpus_mentions"] =
  combined["name"].apply(lambda n: counts.get(n.lower(), 0))` -- the
  `counts` dict is keyed by ORIGINAL-CASE name (from the automaton's
  stored `(idx, name)` value), but this line queried with `n.lower()`,
  a case mismatch that made every single lookup miss and silently
  default to 0. `build_maverick_candidate_list.py` (the script this was
  adapted from) does NOT lowercase at that step -- I introduced the bug
  when adapting it. Fixed in both the Kaggle kernel script and the local
  copy (`src/build_media_personality_candidate_list.py`, currently
  unusable locally anyway since its corpus input is Kaggle-only now, but
  fixed for whenever that data is restaged). v6 pushed with the fix and
  diagnostics stripped out -- check kernel status before trusting
  output; this log entry is the fix, not yet the confirmed result.
- 2026-07-28 [this session]: v6 CONFIRMED FIXED and DONE. Real numbers:
  774/1,504 candidates have nonzero corpus mentions. All 5 calibration
  names scored plausibly (Alex Jones 50,497; Joe Rogan 17,003; Tucker
  Carlson 8,895; Roger Stone 4,357; Matt Gaetz 2,067). Output copied to
  `data/processed/media_personality_candidates_scored.csv`.

  **Known limitation, same as the entity-coverage-aiitl-judge finding
  earlier today**: several of the highest-scoring rows are almost
  certainly false-positive collisions with common words/phrases, not
  real matches on the actual media personality --
  `"Spirit"` (44,273, a talk radio host's stage name, but "spirit" is
  an extremely common word), `"Kennedy"` (25,966, near-certainly
  JFK/RFK mentions, not the talk-show host Lisa "Kennedy" Montgomery),
  `"Michael Jackson"` (4,619, near-certainly the singer, not the British
  radio host of the same name), `"Destiny"` and `"Hot Air"` (both common
  words/phrases as well as real commentator names/outlet names). This is
  the SAME single/common-word collision risk flagged in
  `job_entity_coverage_2026-07-28` -- worth checking against
  `corpus_entity_frequency.csv`'s per-mention example context before
  trusting these specific high-count rows, not just taking the raw
  count at face value. Multi-word, distinctive names (Charlie Kirk,
  Candace Owens, Ben Shapiro, Jimmy Dore, Rachel Maddow, Tim Pool, Sean
  Hannity, Bill Maher, Rush Limbaugh, Jon Stewart, Glenn Beck) are much
  safer to trust directly.

  **This is now ready for Nash's review** -- `decision` column is blank
  per the standing guardrail, same as `maverick_candidate_entities_scored.csv`.
  Not merged into `maverick_authority_verified.py` or anywhere else.
