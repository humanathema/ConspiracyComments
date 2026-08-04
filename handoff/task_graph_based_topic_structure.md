# Graph-based topic/discourse structure — pilot built and run 2026-08-02, results below

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

## Expanded signal design (2026-08-02, later same session) — explicit
## anti-black-box requirement

Nash's framing, verbatim in spirit: "these different features we pick
should be tunable, but we want this not to be a black box as we
progress -- we want it to be comprehensible at each stage as much as
possible, a conscious rejection of the black box AI approach." This is
a real design constraint, not a preference -- it argues for a
**multiplex graph**: same node set, multiple SEPARATE named edge
layers, never collapsed into one blended similarity score. Each layer
should be independently computable, independently inspectable (run
community detection on it ALONE before combining anything), and
independently tunable (turn a layer on/off, reweight it) -- so a
finding can always be traced back to which signal(s) produced it.
Layer disagreement is itself informative, not noise to average away
(e.g. two threads linked by author-burst co-occurrence but NOT by
semantic similarity flags "this author was doing something unrelated
in the same session," a real finding a pre-blended score would erase).

Six layers now scoped (two implemented in `src/graph_pilot.py`'s first
pilot, four designed but not built):

1. **Reply structure** (implemented) -- direct `parent_id` -> `id`
   edges within a thread.
2. **Semantic similarity** (implemented) -- k-NN cosine edges from
   comment embeddings (MiniLM in the pilot; the earlier embedding-model
   test showed Gemini doesn't obviously help here, so no reason to pay
   for it in this context either).
3. **Author co-participation** -- author X appears in threads A and B
   -> edge between those threads, weighted by shared-thread count.
4. **Author-pair recurring exchange** -- a DISTINCT, stronger signal
   from #3: A replied to B (or vice versa, real reply edges, not just
   co-presence) in more than one separate thread. Two people who've
   actually argued across three threads is a different fact from two
   people who happened to both comment in three threads without
   interacting -- deliberately not folded into #3.
5. **Post-title topic similarity** -- a thread-to-thread signal (not
   comment-to-comment): embed post titles, connect threads by title
   similarity. Distinct axis from within-thread comment content (#2).
6. **Author burst co-occurrence** -- the newest, most novel signal: for
   each author, find contiguous windows of rapid activity (several
   comments close together in time -- a "burst," roughly a session of
   engagement). If a single burst spans multiple threads, that's a real
   behavioral link between those threads independent of content
   similarity -- those threads were live in the same person's attention
   *simultaneously*. Genuinely different from #3 (no timing
   requirement) and #2 (pure content, no behavior). How hard/soft this
   signal should be (burst-window width, minimum burst size) is
   explicitly unresolved -- Nash flagged this himself ("idk how hard or
   soft that signal should be").

`src/graph_pilot.py`'s first pilot run (top 100 threads by comment
count, ~313k comments, layers 1+2 only) also computes normalized mutual
information between the two layers' independent community-detection
results -- a first concrete instance of the "compare layers before
combining" principle above, not just a design intention.

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

## Update 2026-08-03: recovering what actually got built 2026-08-02

The whole pilot below was built and run in one long session 2026-08-02
into 2026-08-03 but never made it into any handoff doc — the session
that wrote `handoff/task_2026-08-03_session_handoff_stance_cascade_and_topic_escalation.md`
compacted context partway through and only recorded it as one throwaway
line ("Graph-pilot multi-layer HLC work... also included"). Recovered
2026-08-03 by reading the actual committed code (`git log`, commit
`11d4f75`, 17 new `src/graph_pilot_*.py` scripts — this was all real
work, not lost, just undocumented) and the output it produced. **This
section is a reconstruction from artifacts, not a session narrative** —
treat design rationale in code docstrings as more reliable than any
summary here.

### What actually got built (beyond the 6-layer design above)

Scope corrected twice by Nash early on: thread selection moved from
raw comment count to **longest reply chain** (`thread_depth.parquet`,
pure-DuckDB recursive CTE — zero overlap between top-20-by-count and
top-20-by-depth thread lists, so this was a real, not cosmetic, fix),
and each selected thread's **full tree** gets built (every branch, post
itself as an explicit root node), not a single longest chain or a
forest of disconnected top-level comments.

Two separate pilot scales: a 100-thread/~313k-comment first pass
(reply + semantic layers only, NMI comparison between them), then the
main **200-thread/~90k-comment pilot** (`data/processed/graph_pilot_top200_depth/`)
with the fuller layer set actually implemented: reply, Gemini
comment-embedding k-NN ("semantic"), author co-participation +
recurring-exchange, within-thread temporal proximity, citation
co-mention (by domain AND by exact URL), and entity co-mention —
saved as a single tagged `(id_a, id_b, layer, weight)` edge table per
Nash's explicit toggleable-layers requirement ("we can always toggle on
certain layers or off").

Three community-detection approaches tried, not just Leiden:
1. **Disparity-filter backbone (Serrano/Boguna/Vespignani 2009) + real
   hierarchical link communities (Ahn/Bagrow/Lehmann, via cdlib)** on
   the full combined graph — the actual production run.
2. **Clique-percolation overlapping communities** (networkx
   `k_clique_communities`) on reply+semantic+author — Nash's
   "Wittgenstein family-resemblance" framing (no single shared essence
   required, membership via a network of overlapping pairwise
   resemblances). Real result: nodes CAN and DO belong to multiple
   communities, unlike hard Louvain/HLC partitions.
3. **Post-level HLC**, same methodology one level up on the 200-post
   backbone (post-similarity, thread co-participation, thread recurring-
   exchange layers) — 494 communities over 200 posts.
4. A **crosswalk** between comment-level (142,049 communities/90,194
   comments) and post-level (494/200) results, testing whether comment-
   communities cleanly nest under one dominant post-community
   ("branches off from post topics") or spread thin across many
   (cross-cutting themes not really "under" any single post-topic).

Two more experiments outside the HLC line: **chain-segment clustering**
(decompose each thread's tree into maximal straight-line runs between
fork points, cluster the segments instead of individual comments —
"trunk topics" — then check whether each fork's child chain continues
in the same cluster as its parent or branches into a different one),
and a **temporal topic lineage** model (process comments in real
chronological order 2010-2026, each one either joins an existing topic
via cosine similarity >= 0.72 or spawns a new one linked to its nearest
predecessor, with EWMA centroid drift as new members join — an
embeddings-native structural-topic-model analogue). The lineage run:
4,607 topics spawned, 94.9% of comments joined an existing topic, 99.8%
of spawns have a real parent link.

### Results — genuinely promising, and NOT for the reason originally hoped

**Quantified check, run 2026-08-03**: of the 352 comment-level
communities at or above size 10, **zero have the Gemini semantic k-NN
layer as their dominant edge type**. Breakdown by which layer actually
drove each community:

| Dominant layer | Communities | Share |
|---|---|---|
| `citation_comention_domain` | 156 | 44.3% |
| `author` | 123 | 34.9% |
| `reply` | 54 | 15.3% |
| `entity_comention` | 11 | 3.1% |
| `topic_lineage` | 7 | 2.0% |
| `citation_comention_url` | 1 | 0.3% |
| `semantic` (Gemini) | **0** | **0%** |

Reading the actual sample comments (`topic_samples.md`) confirms this
isn't a fluke of the metric — the citation- and entity-comention-driven
communities are genuinely clean, topical, and readable: a
PubMed/CDC/Mayo-Clinic-cited vaccine-and-mask-skepticism cluster (158
comments, 43 threads), a Wikileaks/Assange/Snowden entity cluster (129
comments, 12 threads), an AE911Truth-controlled-demolition cluster, a
NYT/YouTube/Wikipedia election-fraud-adjacent cluster. These are at
least as coherent as MiniLM's production BERTopic topics, arguably more
so given they're readable directly rather than via keyword lists.

**This directly answers your question about the curse-of-dimensionality
problem**: the graph approach didn't need to compensate for it, because
in practice it never leaned on the Gemini embedding layer at all — the
disparity-filter backbone was built specifically because a global
similarity threshold gave Gemini's embedding space "either one giant
blob or confetti at every threshold tried" (same failure mode as the
UMAP+HDBSCAN test, confirmed independently here), but once the *other*,
non-embedding layers (citation domain, entity mention, author,
reply) are in the mix, they simply out-compete the noisy semantic layer
for every community of meaningful size. The multiplex/non-blended
design is what saved this — a single blended score would have let
Gemini's noise drag everything down; keeping layers separate meant the
noisy layer just... didn't win, anywhere.

**Real caveat, not yet addressed**: roughly half of the communities
(author 35% + reply 15% = ~50%) are dominated by *discourse-structure*
signals, not *content* signals, and reading their samples shows it —
one 85-comment/1-thread "community" is almost entirely "." and one-word
filler replies (a bot-like or copypasta reply chain, not a topic); an
author-dominated community was just two people arguing back and forth
about virus methodology with no coherent shared subject. These aren't
wrong, exactly — they're a genuinely different, real kind of structure
(who talks to whom, in what pattern) — but they are not "topics" in the
BERTopic sense, and mixing them into the same `topic_samples.md` list
undersells how clean the citation/entity-driven half actually is.
**A coherence/topicality filter (e.g. require citation_comention or
entity_comention edges above some share, or a minimum text-content
diversity check) before calling something a "topic" would make this a
fair comparison against BERTopic** — right now the un-filtered 352 mixes
two different phenomena together.

### What's actually promising vs. what isn't

**Promising, worth pursuing**: the citation-comention and entity-
comention layers alone (no embeddings at all) produced the cleanest
topical communities in the whole exercise — cleaner than either MiniLM
or Gemini's BERTopic run in the specific sense that they're directly
human-readable without a keyword-list translation step, and they're
free (no embedding cost, deterministic joins). Worth a targeted
ablation: rerun HLC/backbone with ONLY reply + citation_comention +
entity_comention (drop semantic entirely) and see whether the
citation/entity-driven communities are materially different — if not,
the whole approach could run without touching Gemini (or any
embeddings) at all, which would make it much cheaper to scale to the
full 39.9M-row corpus than either BERTopic variant.

**Not promising as a general BERTopic replacement**: this pilot doesn't
cover comments with no citations, no shared entities, and no
distinctive author pattern — plausibly a large fraction of the corpus,
and exactly the population BERTopic (even imperfectly) does cover via
raw semantic content. The graph approach's strength is specific
(structurally-anchored discourse), not general-purpose text clustering.

**Possible complementary role, given the current production setup**:
you're currently using Gemini embeddings narrowly, to rescue MiniLM/
BERTopic's own outlier population (the use that actually proved
effective) rather than as a drop-in embedding swap. The graph/HLC
machinery could plausibly serve a similar narrow, targeted role instead
of being a full replacement: run it specifically on threads/comments
that MiniLM+BERTopic marks as outliers (or on comments with contested/
weak topic assignment), since citation and entity co-mention don't
degrade with corpus size or dimensionality the way embedding-based
clustering does — this would reuse the graph work's actual strength
(structural signals immune to the curse-of-dimensionality problem)
against exactly the population where BERTopic already needs help,
rather than trying to make it cover the whole corpus.

### What's not done

- The semantic-layer-ablation test above (not run).
- A coherence/topicality filter to separate content-communities from
  discourse-structure-communities.
- Anything at full-corpus scale — everything above is the 200-thread/
  ~90k-comment (or 100-thread/~313k-comment) pilot only. Full-corpus
  thread reconstruction still needs Kaggle (see constraints below,
  unchanged).
- Chain-segment "trunk topic" fork analysis and the temporal-lineage
  model's actual lineage chains were built and ran cleanly but were not
  read/validated in depth — worth doing before citing either.
- No comparison yet against the top-down semantic-tree /
  `map_super_topics.py`-replacement idea floated in the original design
  (NMI or cross-tab against graph communities).

## Status

Pilot built and run (2026-08-02/03, recovered into this doc 2026-08-03).
Real, promising result for citation/entity/author-structural
communities specifically; not a general BERTopic replacement as-is. See
update above for the concrete next step (semantic-layer ablation) before
deciding whether to scale this up or fold it into the outlier-rescue
role Gemini embeddings currently play.
