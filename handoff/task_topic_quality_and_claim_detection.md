# Task: Topic quality audit -> topic "central claim" detection -> topic stance

**Status as of 2026-07-26: audit calibration and claim extraction are
DONE** (a follow-on session finished the corrected rerun and built
`src/extract_topic_claims.py` -- see its own walkthrough in
`~/.gemini/antigravity/brain/` if you want the detail, or just trust the
CSVs on disk, verified directly on 2026-07-26). **What's still open from
this file: step 3 (claim-bearing classification) was deliberately NOT
built as an auto-classifier** -- see
`handoff/task_topic_quality_explorer_integration.md` instead, which
supersedes this file's explorer-facing remaining steps and covers why
(short version: some topics are a genuine mix with no coherent claim,
and that's Nash's call per-topic, not a threshold to guess). **Step 4
(resuming `build_topic_stance_queue.py` labeling) is still open and not
covered by the new doc** -- that one's still just "needs more human
labeling," nothing new to design there.

The section below is kept for the original design rationale (why the
three signals are shaped the way they are) and the calibration history --
useful context, not a live task list anymore for the explorer-integration
half.

## Why (Nash's framing, 2026-07-25)

Two related asks bundled together:
1. Some of the ~97 BERTopic topics are ambiguous / too broad / accidentally
   split into near-duplicates and need auditing before anything is built on
   top of them (splitting, tightening, or merging as appropriate).
2. Longer-term: detect a "central claim" per topic (not just top-10
   c-TF-IDF keywords), decide which topics are even claim-bearing (a
   catch-all like "government/politics" probably isn't; "5G causes cancer"
   is), and use that as the foundation for topic-level stance detection --
   extending the disambiguation pattern already used for named entities
   (`src/stage_c_classify_ambiguous.py`'s "signature words") to topics
   instead of entity name-variants.

Nash also pasted an old crosstab (`epistemic_moves` x `human_stance`) from
early project work as a data point for what "epistemic move" categories
looked like historically -- confirmed to still exist at
`data/processed/human_labels_active_learning.csv` (13 rows only --
genuinely tiny/preliminary, matches how Nash described it, not something
to treat as validated). Worth reading before designing the topic-stance
codebook, as a starting vocabulary of move-types (quoting parent,
direct/indirect quotes, appeal to logic, demand evidence, etc.), not as
statistically meaningful counts.

## What's already built and confirmed working

`src/audit_topic_quality.py` -- three independent, deterministic signals
(no LLM calls, all local: the same `all-MiniLM-L6-v2` SentenceTransformer
already used to train BERTopic, KMeans, and a ratio-test vocabulary
extraction copied from `stage_c_classify_ambiguous.py`'s signature-word
method):

1. **Near-duplicate / merge candidates**: topic-centroid cosine similarity
   (from `data/processed/topic_centroids.npz`) AND top-10-keyword Jaccard
   overlap (from `topic_super_topic_mapping.csv`'s `Keywords` column) --
   flagged only when BOTH agree, so a coincidental keyword or vector
   overlap alone doesn't trigger a false merge suggestion.
2. **Broad / split candidates**: per-topic cohesion (mean cosine
   similarity of each assigned comment's own embedding to its topic's
   centroid, using the 100k-comment training sample in
   `train_topic_assignments.parquet`). Low-cohesion topics get a 2-way
   KMeans split test on their own embeddings; a split is only reported if
   the two sub-clusters clear a silhouette-score floor AND produce a
   ratio-test vocabulary split (signature words per sub-cluster, same
   `MIN_SIGNATURE_RATIO=0.7` / `MIN_SIGNATURE_COUNT=3` mechanic as entity
   disambiguation) -- so any reported split is human-auditable by eyeballing
   two word lists, not just a distance-metric artifact.
3. Thin-topic flag (n < 150 in the 100k sample) as a caveat, not a verdict.

Sanity-check confirmed the method basically works before I ran out of
tokens: the known pre-existing issue documented in
`handoff/PROJECT_CAPABILITY_INVENTORY.md` section 4 ("BERTopic split
vaccine discourse into 3 near-duplicate topics" -- topics `2_vaccine_
vaccines_vaccinated_covid`, `9_covid_flu_virus_deaths`, `26_masks_mask_
wear_wearing`) shows up as elevated centroid similarity (topics 2 vs 9:
cosine 0.7136) even though it didn't clear my first-pass thresholds -- see
calibration note below.

## Rerun finished (2026-07-25) -- results are final, not stale

The corrected rerun completed. `data/processed/_audit_topic_quality_embeddings_cache.npy`
now exists (subsequent reruns are ~seconds, not ~9 min, as long as
`train_topic_assignments.parquet` doesn't change -- delete the cache if it
does). Current `topic_quality_audit.csv` / `topic_near_duplicate_pairs.csv`
/ `topic_split_candidates.csv` reflect this final run. Results:

- **Near-duplicate pairs** (2, unchanged from the miscalibrated pass --
  this signal wasn't affected by the cohesion-threshold bug): topic 50
  (`trump_president_establishment_people`) vs 84 (`obama_bush_president_
  bushes`), cosine 0.7150/jaccard 0.1765; topic 78 (`karma_upvotes_sub_
  comment`) vs 90 (`sub_politics_trump_comments`), cosine 0.6721/jaccard
  0.3333. The 78/90 pair in particular looks like meta-discussion-about-
  the-subreddit rather than conspiracy content -- worth deciding early
  whether that's in scope for claim detection at all, or should be
  excluded as a distinct "non-claim-bearing / meta" category.
- **24 topics flagged `low_cohesion_broad_candidate`** (bottom quartile of
  this run's cohesion distribution, range 0.36-0.61): topics 20, 61, 0, 89,
  17, 8, 71, 33, 47, 21, 41, 32, 1, 57, 86, 83, 49, 78, 10, 56, 88, 15, 3,
  60 -- see `topic_quality_audit.csv` for names/counts. **None cleared the
  silhouette floor (0.05) for a clean 2-way split** -- best observed was
  0.043 (topic 20, `numbers_number_statistics_math`). This is a real,
  interpretable result, not a null: these topics aren't secretly two
  topics glued together, they're genuinely diffuse. Looking at the names
  (`ha_thanks_thank_lol`, `google_search_results_apps`, `city_cities_car_
  cars`, `movie_film_movies_imdb`, `phone_phones_cameras_camera`), most of
  these look like generic-reaction / off-topic-tangent clusters rather
  than substantive conspiracy content -- good first candidates for a
  "not claim-bearing" bucket (step 3 below), independent of any
  split/merge decision.
- **Validation check passed**: the known pre-existing vaccine/covid/mask
  3-way near-duplicate (topics 2/9/26, documented in
  `PROJECT_CAPABILITY_INVENTORY.md`) did NOT show up in either the
  near-duplicate list or the low-cohesion list. That's expected, not a
  bug -- each of those three topics is individually cohesive; their
  problem is cross-topic redundancy (three topics covering overlapping
  ground), a different axis than within-topic diffuseness, and the
  near-duplicate detector's centroid-similarity signal (topics 2 vs 9:
  cosine 0.7136) already caught that one directly during earlier manual
  inspection, just below this run's dual-signal threshold for auto-
  flagging in the pairs CSV. If cross-topic redundancy beyond the two
  auto-flagged pairs matters, worth lowering `CENTROID_SIM_THRESHOLD`
  further and re-inspecting, since 0.65 was picked from the observed max
  (0.795), not from a principled cutoff.

## Calibration history (context for why there's a "first pass" at all)

First run used fixed absolute thresholds (`CENTROID_SIM_THRESHOLD=0.80`,
`COHESION_FLAG_THRESHOLD=0.35` as a raw cosine value) guessed without
checking the actual distribution first -- crashed on an empty near-duplicate
DataFrame (fixed, now returns an empty frame with correct columns instead
of crashing) and silently flagged zero low-cohesion topics because 0.35
turned out to be *below the minimum* cohesion value across all 97 topics
in this embedding space (actual range 0.36-0.61, mean 0.49). Recalibrated:
`CENTROID_SIM_THRESHOLD` lowered to 0.65 (max observed off-diagonal
similarity was 0.795, so 0.80 could never fire), `KEYWORD_JACCARD_
THRESHOLD` lowered to 0.15, and cohesion switched from a fixed absolute
cutoff to a relative one (`COHESION_FLAG_PERCENTILE=0.25`, bottom quartile
of whatever the actual run's distribution turns out to be) since the raw
cosine-similarity scale is a property of this specific embedding run, not
a portable absolute constant. This is the rerun that was in progress when
the session ended -- **don't reuse the fixed-threshold version's numbers**.

At the miscalibrated-but-crash-fixed first pass (thresholds 0.65/0.15,
before the cohesion fix), two near-duplicate pairs were already found and
are probably still valid (near-duplicate detection wasn't affected by the
cohesion miscalibration, only the split-candidate side was):
- Topic 50 (`50_trump_president_establishment_people`) vs Topic 84
  (`84_obama_bush_president_bushes`) -- cosine 0.7150, keyword jaccard 0.1765
- Topic 78 (`78_karma_upvotes_sub_comment`) vs Topic 90 (`90_sub_politics_
  trump_comments`) -- cosine 0.6721, keyword jaccard 0.3333

Worth a skim once the rerun confirms these persist: topic 78/90 look like
they might be meta-discussion-about-the-subreddit topics rather than
substantive conspiracy content at all (worth deciding if those belong in
"claim-bearing" scope from the start, or should be excluded/flagged
separately -- they're a good early example of "some topics don't/can't
have claims").

## Guardrail note (same pattern as `task_trump_vs_classical_topic_split.md`)

**Don't auto-merge or auto-split any topic based on this audit's output.**
Same review-gate pattern as the entity disambiguation and topic-era-split
work elsewhere in this project: the audit should produce a reviewable
candidate list (which it does -- three CSVs), and merge/split/keep
decisions are Nash/Claude's judgment call, not something to apply
unsupervised. The topic-era-split task file's post-mortem (a blank
`confirmed` column silently passing through as approved) is exactly the
failure mode to avoid here too -- if a review-gate step gets added later
for merge/split decisions, make firmly sure "not yet reviewed" and
"approved" can't be confused.

## Remaining steps (not started)

1. Finish calibrating + get the corrected audit output, human-reviewed
   (per guardrail above) for actual merge/split decisions on flagged pairs.
2. **Central-claim extraction** (the actual new-territory ask): adapt the
   same signature-word ratio-test mechanic to extract, per topic, the
   vocabulary/phrases that most distinguish its confidently-assigned
   comments from a general background -- not a generated sentence (no LLM
   calls), an auditable word/phrase set in the same "print and eyeball"
   spirit as `stage_c_classify_ambiguous.py`. Design question still open:
   background corpus to contrast against (all other topics pooled? a
   random sample of the full corpus? both, as two different signals?) --
   worth a quick judgment call with Nash before building, not a default to
   just pick.
3. Once topic-level claim signatures exist, use them to judge which topics
   are actually claim-bearing (contentful conspiracy claim) vs. not (meta/
   moderation topics like 78/90 above, broad political-commentary topics
   like 50/84, procedural/lifestyle topics). This is a real judgment call,
   likely needs the same reviewable-candidate-list pattern as everywhere
   else in this project, not an automatic classifier decision.
4. Resume `src/build_topic_stance_queue.py` -- already exists, already
   asks "does this comment endorse/doubt the topic's underlying claim,"
   but is only ~13% human-labeled (`data/hitl/queue_topic_stance.csv`,
   1,408 rows, ~187 labeled) and has no trained classifier yet. This is
   the natural target once claim-bearing topics are better defined --
   labeling more of this queue (or regenerating it against corrected topic
   definitions if step 1's merges/splits change topic boundaries) is the
   actual path to topic-level stance detection Nash asked about.

## Guardrails that apply here (see `ANTIGRAVITY_HANDOFF.md` for full list)

- No LLM/API calls anywhere in this task -- everything above is local
  (SentenceTransformer already vendored for BERTopic, KMeans, TF-IDF-style
  ratio counting). Keep it that way; this is exactly the kind of
  exploratory multi-step task that could tempt an LLM-cascade shortcut for
  "claim extraction," and the $100 budget blowout history says don't.
- Don't overwrite `data/hitl/queue_topic_stance.csv` (has real human
  labels in ~187 rows) without backing it up first.
- Report back and stop at this task's boundary -- don't chain into
  building the stance classifier itself without a checkpoint, per the
  general "report back and stop at task boundaries" guardrail.
