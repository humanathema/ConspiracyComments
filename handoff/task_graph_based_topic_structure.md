# Graph-based topic/discourse structure — design doc, not started

Raised by Nash 2026-08-02, in the same session as the MiniLM-vs-Gemini
embedding comparison (`src/compare_embedding_models_for_topics.py`) and
the earlier thread-structure/census idea
(`handoff/task_thread_structure_census_embedding.md` -- this doc
supersedes/extends that one with a concrete mechanism, not just a
description). Nothing built yet; this exists so the design survives the
session.

## Why this came up

The embedding-model comparison surfaced a real methodological question:
BERTopic's pipeline (SentenceTransformer -> UMAP -> HDBSCAN -> c-TF-IDF)
was tuned for MiniLM's 384-dim space and doesn't obviously transfer to a
higher-dim embedding space (Gemini's 3072-dim) -- swept UMAP's
`n_neighbors` (15/30/50) and `n_components` (5/10/20), neither fixed the
55%+ outlier rate or the ~40x-higher near-duplicate-topic count vs.
MiniLM's production result. Root cause is plausibly UMAP+HDBSCAN's
reliance on density estimation in a reduced continuous space, which
degrades in ways that don't scale cleanly with source dimensionality
(curse of dimensionality affects both distance concentration AND local
density estimation -- see conversation for the full mathematical
walkthrough). Rather than keep tuning someone else's pipeline, Nash
proposed building a different kind of structure directly: a graph, not
a continuous embedding space, with community detection instead of
density-based clustering.

## The design (as scoped in conversation)

**Core idea**: nodes = comments. Multiple edge types, not just one
similarity measure:

1. **Reply-thread structure** (the backbone) -- real `parent_id`/
   `link_id` edges reconstructed from the corpus, same fields
   `src/score_boundary_candidates_vertex.py`'s sibling
   `escalation_context_check.py` already walks (`fetch_context()` in
   that file has the working parent/sibling/post-lookup query pattern
   to reuse, including the FIX for top-level comments needing the
   ORIGINAL POST as parent when `parent_id == link_id`).
2. **Semantic similarity** -- k-NN edges from comment embeddings
   (cosine similarity), same embeddings already being computed/compared
   in the MiniLM-vs-Gemini test. This is what a plain k-NN-graph +
   Leiden/Louvain community-detection approach would use on its own if
   built without the other signals -- worth keeping as an independently
   testable baseline before adding more edge types.
3. **Temporal / real-world-event alignment** -- entities and events
   already have time-series work done (`per_entity_stance_over_time.py`,
   entity mention caches with timestamps) -- comments discussing the
   same entity/event in the same real-world time window could get an
   edge or edge-weight boost.
4. **Author connectedness** -- the existing author-level analysis
   ("insider" analysis mentioned in conversation -- locate the specific
   file/script before building, not yet confirmed which one) gives two
   more possible signals: (a) co-participation (same authors appearing
   across threads/entities), (b) vocabulary similarity between authors
   (if that's already computed somewhere from the insider work).

**Community detection** (Leiden, most likely -- modularity-optimizing,
well-studied, doesn't need the manifold assumption UMAP relies on) runs
on the resulting multi-edge-type graph. Topics/discourse-clusters emerge
from the combined structure rather than from semantic similarity alone.

**Comparison to the top-down approach**: also discussed in the same
conversation -- a theory-driven semantic tree (root -> broad domains ->
sub-branches -> topics), built from embedded category-prototype
descriptions rather than the existing `map_super_topics.py`'s hardcoded
per-topic dict (that script is a flat, 44-of-97-topics-manually-typed
lookup table, not a real reusable classifier -- confirmed by reading it
in this session). Comparing the graph-community assignment against the
nearest-prototype assignment (e.g. via normalized mutual information, or
just cross-tabulating and eyeballing where they diverge) was floated as
a way to validate structure two independent ways -- agreement is
stronger evidence than either method alone, and disagreement is
probably the more interesting finding (surfaces content the top-down
taxonomy didn't anticipate, or graph communities driven by surface
phrasing rather than real semantic domains).

## Real constraints, confirmed this session

- **Full corpus lives on Kaggle, not locally.** `empath_scores_full_mapped.parquet`
  (the file with real `parent_id`/`link_id` for thread reconstruction)
  isn't present under `data/processed/` on this machine -- it's a
  multi-million-row file used by the Kaggle-hosted kernels. Any full-
  corpus thread reconstruction needs to run on Kaggle, not this 8GB RAM
  dev machine ([[machine_constraints]] memory -- this is exactly the
  kind of job that OOMs locally).
- **Random-sample data won't work for this.** `train_topic_assignments.parquet`
  (the 100k sample used for the embedding-model comparison) breaks most
  reply chains, since siblings/parents of a sampled comment usually
  weren't also sampled. Thread reconstruction needs to start from
  complete threads pulled from the full corpus, not this sample --
  matches the original "rank by thread size, take the biggest branches
  first" framing rather than a uniform random draw.
- **Author-analysis file location not yet confirmed.** Referenced
  conversationally ("our partial census of authors," "insider
  analysis") but not pinned down to a specific file/script in this
  session -- locate it before building the author-connectedness edges.

## Suggested first step, when picked up

Scope a **small pilot**: pick the largest N complete threads (by
comment count) from the full corpus on Kaggle, reconstruct them, build
just the two easiest edge types first (reply structure + semantic
similarity -- both have working code/patterns already), run Leiden
community detection, and look at the result before adding temporal or
author signals. Mirrors how every other expansion tonight was scoped
down to something testable first (100k sample before full corpus,
deadzone threshold before a new judge prompt, etc.).

## Status

Not started. No code written for graph construction or community
detection. This doc exists purely to not lose the design.
