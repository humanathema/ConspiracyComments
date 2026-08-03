"""graph_pilot_overlapping_communities.py

Nash's direction 2026-08-02: try a Wittgenstein family-resemblance
construction instead of hard partitioning -- no single shared essence
required across a whole group, membership via a network of overlapping
PAIRWISE resemblances, possibly in different respects for different
pairs. Hard Louvain (used everywhere else tonight) forces every node
into exactly one community; this instead uses clique percolation
(k_clique_communities, built into networkx) -- finds communities as
unions of adjacent k-cliques, so a node can genuinely belong to MULTIPLE
communities, with no requirement that any single edge type spans the
whole group.

Combines THREE comment-level layers for the 200-thread pilot into one
graph -- reply structure, Gemini semantic k-NN, and author connectivity
(same-author cross-thread + recurring-exchange edges, brought down from
thread-level to comment-level in graph_pilot_author_comment_edges.py)
-- tagging each edge with which layer(s) contributed it, so overlap can
be inspected against the layers it's actually built from, not treated
as an opaque combined score.

Output: data/processed/graph_pilot_top200_depth/overlapping_communities.csv
  (id, community_id) -- one row PER MEMBERSHIP, a node can appear multiple times
        printed summary: how many nodes are in >1 community, size distribution
"""
import time

import networkx as nx
import pandas as pd

PILOT_DIR = "data/processed/graph_pilot_top200_depth"
K_CLIQUE = 5  # bumped from 4 (2026-08-02): k=4 + threshold 0.5 collapsed into one
# 56,469-node mega-community (63% of the graph) via the classic clique-percolation
# giant-component failure mode -- Gemini's raw cosine similarities sit systematically
# higher than MiniLM's at the same threshold, same effect that broke BERTopic earlier
# tonight, now showing up as percolation collapse instead of outlier rate.
SEM_SIM_THRESHOLD = 0.75  # raised from 0.5 for the same reason -- sparsify the
# semantic layer specifically for Gemini rather than reusing MiniLM's tuned value


def load_combined_graph():
    comments = pd.read_parquet(f"{PILOT_DIR}/comments.parquet")
    reply_edges = set()
    id_set = set(comments["id"])
    for _, row in comments.iterrows():
        p = row["parent_id"]
        if p == row["link_id"]:
            reply_edges.add((row["id"], row["link_id"]))
        elif isinstance(p, str) and p.startswith("t1_"):
            parent_id = p[3:]
            if parent_id in id_set:
                reply_edges.add((row["id"], parent_id))

    # Nash's direction 2026-08-02: use Gemini, not MiniLM -- this job is meant to
    # give Gemini's embeddings a fair shot in the pipeline they were actually built
    # for (graph-native, no UMAP/HDBSCAN), not just default to the free one again.
    import numpy as np
    from sklearn.neighbors import NearestNeighbors

    print("Loading cached Gemini embeddings and rebuilding k-NN edges...", flush=True)
    gemini_emb = np.load(f"{PILOT_DIR}/comment_embeddings_gemini.npy")
    ids = comments["id"].to_numpy()
    nn = NearestNeighbors(n_neighbors=11, metric="cosine").fit(gemini_emb)
    dists, idxs = nn.kneighbors(gemini_emb)
    sem_edges = set()
    for i in range(len(ids)):
        for j_pos in range(1, 11):
            j = idxs[i, j_pos]
            sim = 1 - dists[i, j_pos]
            if sim >= SEM_SIM_THRESHOLD:
                sem_edges.add(tuple(sorted([ids[i], ids[j]])))

    author_df = pd.read_csv(f"{PILOT_DIR}/author_comment_edges.csv")
    author_edges = set(zip(author_df["comment_a"], author_df["comment_b"]))
    print(f"  {len(reply_edges):,} reply edges, {len(sem_edges):,} semantic edges "
          f"(sim>={SEM_SIM_THRESHOLD}), {len(author_edges):,} author-connectivity edges", flush=True)

    G = nx.Graph()
    G.add_nodes_from(comments["id"])
    for a, b in reply_edges:
        G.add_edge(a, b, reply=True, semantic=False, author=False)
    for a, b in sem_edges:
        if G.has_edge(a, b):
            G[a][b]["semantic"] = True
        else:
            G.add_edge(a, b, reply=False, semantic=True, author=False)
    for a, b in author_edges:
        if a not in G or b not in G:
            continue
        if G.has_edge(a, b):
            G[a][b]["author"] = True
        else:
            G.add_edge(a, b, reply=False, semantic=False, author=True)

    n_layers = [sum(1 for _, _, d in G.edges(data=True) if sum([d.get("reply", False), d.get("semantic", False), d.get("author", False)]) == k) for k in (1, 2, 3)]
    print(f"  combined graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges "
          f"(in exactly 1 layer: {n_layers[0]:,}, 2 layers: {n_layers[1]:,}, all 3 layers: {n_layers[2]:,})", flush=True)
    return G


def main():
    G = load_combined_graph()

    print(f"\nRunning clique percolation (k={K_CLIQUE})...", flush=True)
    t0 = time.time()
    communities = list(nx.algorithms.community.k_clique_communities(G, K_CLIQUE))
    print(f"  done in {time.time()-t0:.0f}s: {len(communities)} overlapping communities found", flush=True)

    membership_count = {}
    rows = []
    for i, c in enumerate(communities):
        for node in c:
            membership_count[node] = membership_count.get(node, 0) + 1
            rows.append({"id": node, "community_id": i})

    out = pd.DataFrame(rows)
    out.to_csv(f"{PILOT_DIR}/overlapping_communities.csv", index=False)

    sizes = sorted([len(c) for c in communities], reverse=True)
    n_multi = sum(1 for v in membership_count.values() if v > 1)
    n_in_any = len(membership_count)
    print(f"\n  community sizes, top 10: {sizes[:10]}", flush=True)
    print(f"  {n_in_any:,} nodes belong to at least 1 community", flush=True)
    print(f"  {n_multi:,}/{n_in_any:,} of those belong to MORE THAN ONE community "
          f"({n_multi/n_in_any*100:.1f}% -- the genuinely overlapping ones)", flush=True)
    if n_multi:
        max_membership = max(membership_count.values())
        print(f"  max communities any single node belongs to: {max_membership}", flush=True)


if __name__ == "__main__":
    main()
