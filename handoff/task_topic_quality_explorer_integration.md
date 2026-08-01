# Task: integrate topic-quality audit into the live corpus explorer

**Status: scoped 2026-07-26, ready to build.** The underlying audit
(`src/audit_topic_quality.py` + `src/extract_topic_claims.py`) is
finished and its outputs verified by direct inspection (not just trusted
from a prior session's summary) -- see "Trust assessment" below before
building on any of the three CSVs. This doc supersedes
`task_topic_quality_and_claim_detection.md`'s "remaining steps" section
for the explorer-facing half of that work; that file's step 4 (resuming
`build_topic_stance_queue.py` labeling) is separate and still open on its
own.

## Why this belongs in the explorer, and how it relates to what's already there

The explorer already has topic-fit rating (`topic_fit_ratings`, 5-point
fuzzy scale, per-comment: "does this comment belong to its assigned
topic"). The quality audit operates one level up -- per-topic-pair
("are Topic 2 and Topic 9 actually the same topic") and per-topic
("is Topic 20 secretly two topics", "does Topic 8 have one coherent
claim"). **These are complementary, not redundant** -- but sequencing
matters: resolve topic merges before spending fit-rating effort inside
topics that turn out to get merged away. Surface that ordering hint in
the UI if natural (e.g. a banner on a topic's drill-down: "this topic has
an open merge candidate, see Topic Quality tab").

## Trust assessment (read before building)

Verified directly against the current CSVs on disk, 2026-07-26:

- **`topic_near_duplicate_pairs.csv` (8 pairs): trust as a review queue,
  not as ground truth.** Dual-signal-gated (centroid cosine AND keyword
  Jaccard must both clear threshold), and independently validated --
  correctly catches the previously-known vaccine/covid split (topics 2/9,
  documented in `PROJECT_CAPABILITY_INVENTORY.md` section 4) that a
  miscalibrated first pass had missed. Also flags things not previously
  noticed: `53_media_news_mainstream_journalism` vs
  `64_fox_cnn_news_msnbc` (cosine 0.795, the highest in the set), and a
  three-way overlap among the meta-reddit topics (`23_banned_mods_ban_
  reddit`, `78_karma_upvotes_sub_comment`, `90_sub_politics_trump_
  comments`). **Guardrail: never auto-merge.** Same review-gate pattern
  as entity disambiguation elsewhere in this project -- a human
  merge/keep-separate decision per pair, staged, reviewable.
- **`topic_split_candidates.csv`: empty, currently a non-issue.** Nothing
  cleared the silhouette floor in the finished run. Leave a UI slot for
  it (the mechanism is real and could fire on a future rerun) but don't
  build anything that assumes it's populated.
- **`topic_central_claims.csv` (97 topics): quality is uneven, do not
  render everywhere.** Spot-checked directly: genuinely good for real
  content topics (topic 2/vaccine pulls "mrna vaccine", "vaccine
  injuries" -- exactly right), but garbage for topic 0
  (`0_ha_thanks_thank_lol`, pulls pastebin URL fragments) and noisy for
  topic 5 (`5_kamala_hillary_tulsi_pelosi`, pulls stray first names like
  "candice"/"mia"/"grande" that aren't claims, just names that happen to
  co-occur). **Nash's framing (2026-07-26, worth keeping verbatim):
  some topics are a genuine mix of co-occurring things and just don't
  have one coherent claim -- that's a legitimate end state, not
  automatically evidence the topic needs splitting.** Don't build a
  threshold that auto-decides "has claim" vs "no claim" -- surface the
  extracted phrases as an unreviewed candidate, gated behind
  `NON_SUBSTANTIVE_TOPICS` at minimum, and let a human set a per-topic
  flag: has-claim(s) / no-coherent-claim-mixed-fine / needs-more-thought.
  Store that decision, don't infer it.

## Piece 1: topic merge review queue (ready to build)

Mirror `entity_merges`'s exact shape (already proven, rater-scoped,
self-healing-migration pattern in `serve_drilldown_api.py`):
- New table `topic_merges (source_topic, target_topic, rater, merged_at)`,
  same `PRIMARY KEY (source_topic, rater)` composite-key convention.
- Load `topic_near_duplicate_pairs.csv` (8 rows) into a new
  `topic_near_duplicate_pairs` table, static reference data.
- New endpoints mirroring the entity-merge ones: list pairs needing
  review, submit a merge/keep-separate decision per rater.
- UI: a "Topic Quality" panel or tab -- 8 pairs, side-by-side name +
  count + cosine/jaccard, merge / keep-separate buttons. Small, bounded
  scope (8 rows), low risk.

## Piece 2: claim-or-no-claim as a human flag, not an auto-decision (ready to build)

- New table `topic_claim_review (topic_id, has_claim, rater, reviewed_at)`
  where `has_claim` is an enum: `'has_claim' | 'no_coherent_claim' |
  'unreviewed'` (default `'unreviewed'`, same "don't let unreviewed and
  approved get confused" lesson from the topic-era-split post-mortem
  referenced in the audit task file -- make the default state visually
  distinct, not blank).
- Load `topic_central_claims.csv` (97 rows) as reference data (top-3
  phrases + ratios per topic already computed, nothing to recompute).
- UI: show the top-3 extracted phrases on a topic's drill-down, filtered
  through the existing `NON_SUBSTANTIVE_TOPICS` set (already excludes
  `0_ha_thanks_thank_lol`/`23_banned_mods_ban_reddit`/`Outliers` --
  extend that set if the review pass finds more, e.g. topic 5 above is a
  reasonable candidate once someone actually looks at it), labeled
  clearly as "auto-extracted, unreviewed" until a rater sets the flag.

## Piece 3: seed-claim probing tool (ready to build, architecture decided 2026-07-26)

Type one or more candidate claims against a topic; see whether the claim
vector lines up with the topic's centroid and its characteristic
comments, and whether 2+ seed claims can slice a "mixed" topic where
blind KMeans found nothing (KMeans has no way to know *what* the mixed
things might be -- a human-supplied hypothesis is a different, often
more powerful signal than unsupervised clustering here).

**Decided: stage-2 (embedding) compute runs on Nash's local machine, on
demand -- not live on the GCE VM.** The VM is an e2-micro (1GB RAM),
`drilldown-api.service` is deliberately stdlib-only and currently peaks
at ~14MB RAM; adding `sentence-transformers` there is a real OOM risk
against Caddy/hitl_rater/drilldown-api all sharing that 1GB. Rejected
alternatives: live-on-VM (dependency/RAM risk) and local-batched
(loses the interactive feel Nash wants -- type and immediately see).

Concrete shape:
- **Stage 1 (TF-IDF, on the VM, live)**: cheap keyword-overlap prefilter
  reusing the `tokenize()` infra already built for `/api/outlier_
  suggestions` -- narrows a topic's comments to a shortlist against the
  seed claim's salient terms. No new dependency.
- **Stage 2 (embeddings, local machine)**: a small local endpoint (script
  Nash runs when working, e.g. `python src/serve_seed_claim_probe.py`)
  that embeds the seed claim(s) with the already-vendored
  `all-MiniLM-L6-v2` and compares against:
  - the topic's centroid, from `data/processed/topic_centroids.npz`
    (97, 384) -- macro alignment check.
  - the topic's actual sample-comment embeddings, from
    `data/processed/_audit_topic_quality_embeddings_cache.npy`
    ((100000, 384) float32, **already computed, row-aligned with
    `data/processed/train_topic_assignments.parquet`** -- reuse
    directly, don't recompute) -- micro alignment, does it match real
    comments, not just an aggregate vector.
  - with 2+ seeds: nearest-seed assignment per comment, to test a
    directed slice.
  Because the browser making the request runs on Nash's own machine when
  he's using this feature, a `fetch()` to `http://localhost:<port>` from
  the explorer's JS reaches this local service directly -- no need for
  the VM to reach into Nash's network. Set a permissive CORS header for
  the explorer's origin on the local endpoint.
- Scope note: seed-claim comparison against "characteristic comments" is
  necessarily bounded to the 100k training sample (that's what has
  cached embeddings), same scope limit the audit itself already
  operates under for cohesion measurement -- don't expand to the full
  21M-row corpus without a real reason, that's a different, much bigger
  embedding job.

## Piece 4: noise-topic residual detection + generalized manual reassignment (ready to build, no blockers)

Two sub-pieces, independently useful:

- **Residual/second-best-topic detection (local batch, precompute once)**:
  for every comment in a flagged junk/meta topic (start with the
  low-cohesion 24 and the near-duplicate meta-reddit cluster 23/78/90),
  look up its row in `_audit_topic_quality_embeddings_cache.npy` and
  compute cosine similarity against *all* 97 centroids in
  `topic_centroids.npz`, not just its assigned topic's. Rank by the gap
  between assigned-topic similarity and best-other-topic similarity --
  a small or negative gap is a real signal the comment is substantive
  content that happens to share noise-topic vocabulary (e.g. reddit-meta
  words) rather than actually being noise. Output a CSV, same shape as
  `topic_near_duplicate_pairs.csv`, loaded as a reviewable queue --
  entirely local/offline, no live-inference decision needed for this
  piece regardless of how piece 3 turns out. Start with plain
  second-best-cosine-similarity (simple, well-understood); only reach
  for vector-subtraction/noise-direction-projection if that first pass
  turns out too noisy in practice -- don't build the fancier version
  first.
- **Generalized manual reassignment (near-zero backend cost)**: the
  `outlier_topic_assignments` table and `upsert_outlier_assignment()` /
  `compute_suggestions()` functions in `serve_drilldown_api.py` are
  **already schema-generic** -- `original_topic_name` isn't hardcoded to
  `'Outliers'`, checked directly in the source (`serve_drilldown_api.py`
  around line 137). Extending "reassign this comment to a different
  topic, or a new one" from Outliers-only to any topic is mostly a UI
  change (surface the same reassignment control on every topic's
  drill-down, not just when `topic_name == 'Outliers'`), not new backend
  work. Natural pairing with the residual-detection queue above: click a
  flagged residual comment, see suggested alternate topics (same
  TF-IDF+kNN suggestion mechanism already built), reassign.

## Build order suggestion

1 and 4 first (bounded scope, no open decisions, reuse existing proven
patterns almost verbatim). 2 next (also bounded, mostly a review-flag
table + UI label). 3 last -- it's the most novel piece and the local
on-demand service is a new deployment shape nothing else in this project
does yet, worth having 1/2/4 as working precedent first.
