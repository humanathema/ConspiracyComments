# Thread-structure / "census" embedding — future direction, not started

Raised by Nash 2026-08-02, mid-session, alongside the MiniLM-vs-Gemini
topic-embedding comparison (`src/compare_embedding_models_for_topics.py`).
Distinct from that work — do not fold into it. Nothing has been built for
this yet; this doc exists so the idea doesn't get lost.

## The idea, in Nash's words (lightly condensed)

Right now topic modeling treats every comment as an independent,
identically-distributed sample — we embed comments in isolation, cluster
them, and call that "the topics." Nash wants something closer to a
complete structural map of the subreddit(s) (r/conspiracy + ATS + BTS),
not a statistical approximation from a sample:

- Embed comments **with their position in the reply thread**, not just
  their own text in isolation — something like an attention/transformer-
  style mechanism over parent→child chains, so a reply's representation
  carries the argument context it's actually responding to.
- Be **selective, not exhaustive**: prioritize long/deep threads (real
  back-and-forth) over short dead-end side chains and one-off orphan
  replies. Rank threads by length/depth and spend embedding budget there
  first, expanding outward as resources allow — "biggest branches first,
  drill down where we can."
- Layer in **time**: track named entities and real-world events, and the
  stance/affective response to them, aligned to when those events were
  actually happening — not just aggregated stance over the whole corpus
  lifetime.
- Layer in **authorship**: connect this to the existing author-level
  analysis so the structure captures not just what was argued but who
  the recurring participants are across threads.
- Framing: move from "sampling/approximating the corpus" (what
  `train_topic_assignments.parquet`'s 100k-row sample and BERTopic runs
  currently do) toward **near-complete coverage** — a real map of the
  community's intellectual/argumentative structure, expanding outward
  from the largest threads rather than a random draw.

## Why this is a separate task, not a variant of the current work

Tonight's `compare_embedding_models_for_topics.py` is testing whether a
stronger embedding model improves BERTopic cluster quality on the
*existing* per-comment, no-structure sampling approach. This idea is a
different architecture entirely — thread-aware / hierarchical embedding,
probably not BERTopic at all (BERTopic has no notion of thread
structure). It would likely need:

- A thread-reconstruction step (walk `parent_id`/`link_id` chains per
  post to rebuild full reply trees — the corpus already has the fields
  for this, see `escalation_context_check.py`'s `fetch_context()` for
  the DuckDB query pattern already built for parent/sibling lookups).
- A way to rank/select threads by size before committing embedding
  budget (length/depth-based prioritization, not random sampling).
- Some encoder that consumes a sequence of thread-position-aware
  embeddings rather than one embedding per isolated comment — this is
  the part that needs real design work (a lightweight hierarchical/
  attention pooling over an existing sentence embedding per node is the
  cheapest version; a custom-trained model is the expensive version).
- Integration with the existing entity/timeline work
  (`per_entity_stance_over_time.py`, entity mention caches) and the
  existing author-level analysis, rather than being built standalone.

## Status

CORRECTED 2026-08-02 (was stale/wrong): the whole-chain (thread-level
monolithic) embedding piece of this IS done, just not under a name this
doc anticipated. `data/processed/graph_pilot_top200_depth/chain_embeddings_gemini.npy`
is (29,913, 3072) float32 -- one Gemini embedding per WHOLE reply-chain
(the full concatenated chain text embedded as a single document, not
per-comment, not a step-wise trajectory -- that's the separate
`chain_trajectories_gemini.parquet` artifact). 29,913/29,913 chains
embedded (done mask confirms), only 3 failed/zero-vector.

Still genuinely NOT done: the more elaborate attention/hierarchical,
thread-position-aware encoding scheme described above, and the
selective largest-threads-first prioritization, entity/timeline
integration, and author-level integration. Those remain real open work
-- only the "one embedding per whole chain" piece exists so far.
