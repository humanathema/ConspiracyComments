"""graph_pilot_build_multilayer_edges.py

Nash's direction 2026-08-02 (late): build out the full multi-layer
signal set as separate, inspectable, TOGGLEABLE edge lists, rather than
committing to one fixed combined graph -- "we can start with what we
have and see how it goes and we can always toggle on certain layers or
off". Each layer is saved as its own tagged block of an (id_a, id_b,
layer, weight) table; downstream scripts (real HLC, disparity-filter
backbone, whatever comes next) just filter by `layer` before building
the actual graph object, instead of re-deriving each layer inline every
time (how reply/semantic/author were built repeatedly across
graph_pilot_link_communities.py / graph_pilot_backbone_link_communities.py
/ graph_pilot_overlapping_communities.py tonight).

Layers, in the order Nash asked for them across tonight's discussion:

  reply           -- direct parent/child (or top-level-to-post) structure.
  semantic        -- Gemini comment-embedding top-10 k-NN, cosine sim >= floor.
  author          -- same-author cross-thread + recurring-exchange edges
                      (already built by graph_pilot_author_comment_edges.py,
                      just re-tagged here).
  temporal        -- within-thread time-proximity, NOT gated on reply
                      structure or content -- two comments in the same
                      thread posted within TIME_WINDOW_SEC of each other.
                      Deliberately within-thread only for this first pass
                      (cross-thread "same real-world moment" edges are a
                      real idea but need their own bounding to not
                      explode combinatorially -- left for a later pass).
  topic_lineage   -- derived from temporal_topic_lineage.py's join-or-spawn
                      output, but built as CHAIN edges (each comment to its
                      immediate chronological predecessor within the same
                      topic_id) plus GENEALOGY edges (each spawned topic's
                      first comment to the parent topic's most recent member
                      at spawn time) -- NOT full same-topic pairwise cliques,
                      which would blow up combinatorially for large topics
                      (a 500-comment topic would be 124,750 pairwise edges
                      for zero extra information over a 499-edge chain).
  entity_comention -- comments sharing an entity_key in
                      entity_mentions_cache_2stage_pooled.csv. Sparse on
                      this pilot (542/89,994 comments have any mention at
                      all) -- real signal where present, thin coverage.
  citation_comention -- comments citing the same source in
                      citations_cache.csv, excluding is_platform rows
                      (reddit.com/youtube.com etc -- categorically not a
                      "shared source" signal). Two specificity tiers, both
                      weighted rather than hard-filtered by a noise list
                      (Nash's direction 2026-08-02: rank by statistical
                      significance like the disparity filter, not manual
                      exclusion) -- weight = IDF-style specificity,
                      log(N_citing_comments / n_citing_this_source), so a
                      source almost everyone cites (t.co, google.com) gets
                      pushed toward ~0 naturally, and a source only 2 people
                      cite gets a high weight, without hand-picking which
                      domains are "noise". Feeds directly into a disparity-
                      filter pass downstream instead of pre-deciding for it.
                      citation_comention_url:    exact same URL (rare, high weight)
                      citation_comention_domain: same domain, subdomain-
                      granular as citations_cache.csv already stores it
                      (pubmed.ncbi.nlm.nih.gov != ncbi.nlm.nih.gov)
                      Sparse either way (5,316/89,994 comments have any citation).
  post_similarity -- thread-to-thread edges on the POST node ids (same
                      "t3_<id>" ids already used as parent nodes in the
                      reply layer for top-level comments) from
                      post_embeddings_gemini.npy's title+selftext
                      embeddings, top-10 k-NN. Only 200 posts, so this is
                      cheap regardless of k -- no blowup risk the way a
                      comment-level post-similarity expansion would have.

Output: data/processed/graph_pilot_top200_depth/multilayer_edges.csv
  (id_a, id_b, layer, weight) -- id_a < id_b within each row (undirected,
  deduped per layer). A node pair can appear once per layer it's real in;
  layers are NOT merged/deduped against each other here -- that's a
  downstream choice (max-weight collapse, union, whatever a given method
  needs), keeping this file a raw per-layer record.
"""
import re

import pandas as pd
import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.metrics.pairwise import cosine_similarity

PILOT_DIR = "data/processed/graph_pilot_top200_depth"
SEM_SIM_THRESHOLD = 0.60  # matches the backbone script's loose floor
TEMPORAL_WINDOW_SEC = 600  # 10 minutes -- same conversational moment,
# within-thread only for this pass
N_NEIGHBORS = 10


def edge(a, b, layer, weight=1.0):
    return (a, b, layer, weight) if a < b else (b, a, layer, weight)


def build_reply_layer(comments):
    id_set = set(comments["id"])
    rows = []
    for _, row in comments.iterrows():
        p = row["parent_id"]
        cand = None
        if p == row["link_id"]:
            cand = row["link_id"]
        elif isinstance(p, str) and p.startswith("t1_"):
            pid = p[3:]
            if pid in id_set:
                cand = pid
        if cand is not None:
            rows.append(edge(row["id"], cand, "reply"))
    return rows


PROJECTED_SIM_THRESHOLD = 0.45  # rescaled for the contrastive-projected space
# 2026-08-02: NOT the same scale as raw Gemini's 0.60 floor -- projection
# trained on citation/entity/reply positive pairs collapsed random-pair
# similarity to ~0.06 (near-orthogonal) while keeping trusted-positive-pair
# similarity at ~0.68 (5x wider separation than raw embeddings' 0.70 vs 0.58).
# 0.45 sits at roughly the general population's ~95th percentile (checked
# empirically on a 3k-comment sample: p90=0.34, p95=0.43, p99=0.61) --
# comfortably above the noise floor, selective without being as tight as the
# trusted-pair mean itself (leaves room to catch real matches beyond the
# specific citation/entity/reply pairs used for training).


def build_semantic_layer(comments):
    # Raw Gemini embeddings dropped tonight after repeated degeneracy under
    # multiple algorithms (clique percolation giant-blob, near-complete
    # chain-similarity graph). This layer now uses the CONTRASTIVE-PROJECTED
    # embeddings instead (comment_embeddings_projected.npy, trained via
    # contrastive_projection.py on citation_comention/entity_comention/reply
    # as trusted positive-pair supervision) -- confirmed to genuinely
    # separate related from unrelated pairs, not just re-patch the same
    # degeneracy downstream.
    emb = np.load(f"{PILOT_DIR}/comment_embeddings_projected.npy")
    ids = comments["id"].to_numpy()
    nn = NearestNeighbors(n_neighbors=N_NEIGHBORS + 1, metric="cosine").fit(emb)
    dists, idxs = nn.kneighbors(emb)
    rows = []
    for i in range(len(ids)):
        for j_pos in range(1, N_NEIGHBORS + 1):
            j = idxs[i, j_pos]
            sim = 1 - dists[i, j_pos]
            if sim >= PROJECTED_SIM_THRESHOLD:
                rows.append(edge(ids[i], ids[j], "semantic_projected", float(sim)))
    return rows


def build_author_layer():
    df = pd.read_csv(f"{PILOT_DIR}/author_comment_edges.csv")
    return [edge(r.comment_a, r.comment_b, "author") for r in df.itertuples()]


def build_temporal_layer(comments):
    rows = []
    for link_id, grp in comments.groupby("link_id"):
        grp = grp.sort_values("created_utc")
        ids = grp["id"].to_numpy()
        times = grp["created_utc"].to_numpy()
        n = len(grp)
        for i in range(n):
            for j in range(i + 1, n):
                dt = times[j] - times[i]
                if dt > TEMPORAL_WINDOW_SEC:
                    break
                rows.append(edge(ids[i], ids[j], "temporal"))
    return rows


def build_topic_lineage_layer():
    topics = pd.read_parquet(f"{PILOT_DIR}/temporal_topics_enriched.parquet")
    lineage = pd.read_parquet(f"{PILOT_DIR}/temporal_topic_lineage_enriched.parquet")
    rows = []

    for topic_id, grp in topics.groupby("topic_id"):
        grp = grp.sort_values("created_utc")
        ids = grp["comment_id"].to_numpy()
        for i in range(len(ids) - 1):
            rows.append(edge(ids[i], ids[i + 1], "topic_lineage"))

    topics_sorted = topics.sort_values("created_utc")
    for row in lineage.itertuples():
        if pd.isna(row.parent_topic_id):
            continue
        parent_members = topics_sorted[
            (topics_sorted["topic_id"] == row.parent_topic_id)
            & (topics_sorted["created_utc"] <= row.born_at)
        ]
        if len(parent_members) == 0:
            continue
        most_recent_parent_comment = parent_members.iloc[-1]["comment_id"]
        rows.append(edge(row.first_comment_id, most_recent_parent_comment, "topic_lineage"))

    return rows


def build_entity_comention_layer(pilot_ids):
    em = pd.read_csv("data/processed/entity_mentions_cache_2stage_pooled.csv",
                      usecols=["comment_id", "entity_key"])
    # exclude merged_* aggregate/rollup keys (merged_maverick, merged_whistleblower,
    # etc.) -- same convention as select_random_expansion_sample.py. These aren't
    # real specific entities, they're category rollups with hundreds of mentions
    # each on this pilot alone, and produce hub-explosion co-mention edges that
    # swamp every genuinely specific entity (128,935 edges from 542 comments
    # before this filter, almost all from 3 merged_* keys).
    em = em[~em["entity_key"].str.startswith("merged_")]
    em = em[em["comment_id"].isin(pilot_ids)]
    rows = []
    for entity_key, grp in em.groupby("entity_key"):
        ids = sorted(grp["comment_id"].unique())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                rows.append(edge(ids[i], ids[j], "entity_comention"))
    return rows


def _idf_comention_edges(cite, key_col, layer_name):
    n_citing_comments = cite["comment_id"].nunique()
    rows = []
    for key, grp in cite.groupby(key_col):
        ids = sorted(grp["comment_id"].unique())
        n = len(ids)
        if n < 2:
            continue
        # IDF-style specificity: a source almost every citing comment shares
        # (t.co, google.com) -> weight near 0; a source only 2 people share
        # -> high weight. No hand-picked noise list -- let the downstream
        # disparity filter (or any other significance-based pruning) decide
        # what to keep, same logic as that filter, applied here as weight.
        weight = np.log(n_citing_comments / n)
        for i in range(n):
            for j in range(i + 1, n):
                rows.append(edge(ids[i], ids[j], layer_name, float(weight)))
    return rows


AMP_WRAPPER_RE = re.compile(r"^google\.com$")
AMP_PATH_RE = re.compile(r"^/amp/s/(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,4})")  # strip
# optional www. same as build_citations_cache.py's own domain-extraction regex
# (line 228) does for direct links -- otherwise an AMP-resolved "www.nytimes.com"
# wouldn't merge with directly-cited "nytimes.com" rows for the same real source.


def resolve_amp_domain(row):
    """google.com/amp/s/<real-domain>/... bucketed everything under
    domain=google.com regardless of the actual cited source (NYT, NY Post,
    a dictionary site all landed in the same group) -- normalize_url() in
    build_citations_cache.py never unwraps this, confirmed by reading it
    directly 2026-08-02, not something Nash had already solved elsewhere.
    Source-level fix needs the full-corpus input files
    (research_corpus_staged_scores_full21m.parquet, 21M rows) which aren't
    present on this machine right now -- patching locally here instead,
    flagged as a real follow-up once those files are back in reach."""
    if not AMP_WRAPPER_RE.match(str(row["domain"])):
        return row["domain"]
    m = AMP_PATH_RE.search(str(row["url"]).split("google.com", 1)[-1])
    return m.group(1).lower() if m else row["domain"]


def build_citation_comention_layer(pilot_ids):
    cite = pd.read_csv("data/processed/citations_cache.csv",
                        usecols=["comment_id", "url", "domain", "is_platform"])
    cite = cite[cite["comment_id"].isin(pilot_ids) & ~cite["is_platform"]]
    n_amp = cite["domain"].eq("google.com").sum()
    cite["domain"] = cite.apply(resolve_amp_domain, axis=1)
    n_resolved = n_amp - cite["domain"].eq("google.com").sum()
    print(f"  AMP-unwrap patch: resolved {n_resolved}/{n_amp} google.com/amp/s/ "
          f"citations to their real target domain", flush=True)
    rows = _idf_comention_edges(cite, "domain", "citation_comention_domain")
    rows += _idf_comention_edges(cite, "url", "citation_comention_url")
    return rows


PLACEHOLDER_TITLES = {"[deleted by user]", "[deleted]", "[removed]"}  # found
# 2026-08-02: 3/200 posts share the literal placeholder title text, which
# embeds identically and produces spurious similarity=1.000 matches between
# otherwise-unrelated deleted posts -- same class of bug as [deleted]/
# AutoModerator/merged_* elsewhere tonight, same fix: exclude at the source.


POST_N_NEIGHBORS = 25  # bumped from the shared N_NEIGHBORS=10 2026-08-02:
# confirmed real, non-noise pairs (e.g. a cluster of culture-war/political-
# tribalism posts -- LGBT-movement, Columbus, pedophilia-normalization,
# Qanon, WEF-"tyrant", political-gender-divide) were getting genuinely
# elevated pairwise similarity (0.60-0.71, right at the layer's own median)
# but losing out on EACH OTHER's top-10 list to posts from their own more
# specific sub-topic (health, election-fraud, etc.) -- the signal was real,
# the k=10 cutoff was discarding it. Only 200 posts total, so a bigger
# neighbor list is cheap and post_similarity was never degenerate to begin
# with (7.4% pair coverage at k=10), unlike the layers that actually did
# blow up (chain-similarity, comment-level semantic).


def build_post_similarity_layer():
    posts = pd.read_parquet(f"{PILOT_DIR}/posts.parquet")
    emb = np.load(f"{PILOT_DIR}/post_embeddings_gemini.npy")
    keep_mask = ~posts["title"].isin(PLACEHOLDER_TITLES)
    posts, emb = posts[keep_mask].reset_index(drop=True), emb[keep_mask.to_numpy()]
    link_ids = posts["link_id"].to_numpy()
    k = min(POST_N_NEIGHBORS + 1, len(posts))
    nn = NearestNeighbors(n_neighbors=k, metric="cosine").fit(emb)
    dists, idxs = nn.kneighbors(emb)
    rows = []
    for i in range(len(link_ids)):
        for j_pos in range(1, k):
            j = idxs[i, j_pos]
            sim = 1 - dists[i, j_pos]
            if sim >= SEM_SIM_THRESHOLD:
                rows.append(edge(link_ids[i], link_ids[j], "post_similarity", float(sim)))
    return rows


def main():
    comments = pd.read_parquet(f"{PILOT_DIR}/comments.parquet")
    pilot_ids = set(comments["id"])

    layers = {
        "reply": build_reply_layer(comments),
        "semantic_projected": build_semantic_layer(comments),  # re-enabled
        # 2026-08-02: now uses the contrastive-projected embeddings (256-dim,
        # 92MB, safe to run locally) instead of raw Gemini (3072-dim, the
        # one that kept collapsing under every unsupervised method tried).
        # Confirmed real separation improvement before re-enabling: positive-
        # pair similarity ~0.68 vs random-pair ~0.06 in the projected space,
        # vs ~0.70 vs ~0.58 raw (5x wider gap).
        "author": build_author_layer(),
        "temporal": build_temporal_layer(comments),
        "topic_lineage": build_topic_lineage_layer(),
        "entity_comention": build_entity_comention_layer(pilot_ids),
        "citation_comention (domain+url)": build_citation_comention_layer(pilot_ids),
        "post_similarity": build_post_similarity_layer(),
    }

    all_rows = []
    print("Layer edge counts:", flush=True)
    for name, rows in layers.items():
        deduped = sorted(set(rows))
        print(f"  {name:20s} {len(rows):>8,} raw -> {len(deduped):>8,} deduped", flush=True)
        all_rows.extend(deduped)

    out = pd.DataFrame(all_rows, columns=["id_a", "id_b", "layer", "weight"])
    out.to_csv(f"{PILOT_DIR}/multilayer_edges.csv", index=False)
    print(f"\nTotal: {len(out):,} edge-layer rows, {out[['id_a','id_b']].drop_duplicates().shape[0]:,} unique node pairs across all layers", flush=True)
    print(f"Saved to {PILOT_DIR}/multilayer_edges.csv", flush=True)


if __name__ == "__main__":
    main()
