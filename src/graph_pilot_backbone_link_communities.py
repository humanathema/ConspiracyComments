"""graph_pilot_backbone_link_communities.py

Disparity-filter backbone extraction (Serrano, Boguna & Vespignani,
PNAS 2009) applied to the full 3-layer combined graph (reply structure
+ Gemini semantic k-NN + author connectivity), THEN the real link-
communities algorithm (Ahn/Bagrow/Lehmann via cdlib's
hierarchical_link_community, already validated on a 700-node sample)
on the resulting backbone -- at the FULL 90k-node pilot scale, not a
subsample.

Why this instead of a global similarity threshold: the disparity
filter prunes each node's edges based on whether an edge's weight is a
STATISTICALLY SIGNIFICANT outlier relative to that SAME node's other
edges (local, per-node adaptive), not one arbitrary global cutoff --
directly addresses something found earlier tonight: no single global
threshold gave Gemini's embedding space a clean multi-group structure
(percolation sweep showed either one giant blob or confetti at every
threshold tried). A locally-adaptive backbone is a principled reason
that might not hold, not another number to tune.

Disparity filter formula (from the original paper): for node i with
degree k_i and edge weights w_ij, let p_ij = w_ij / sum_j(w_ij) (i's
normalized share of weight on this edge). Under a null model of weight
uniformly distributed among i's k_i edges, the probability of seeing a
share >= p_ij by chance is alpha_ij = (1 - p_ij)^(k_i - 1). An edge
survives if it's significant from EITHER endpoint's perspective
(alpha_ij < ALPHA or alpha_ji < ALPHA) -- the standard "OR" rule,
preserves a low-degree node's one strong tie to a high-degree hub even
if that same edge looks unremarkable from the hub's side.

Output: data/processed/graph_pilot_top200_depth/backbone_link_communities.csv
  (id, community_id) -- overlapping node membership, full pilot scale
"""
import numpy as np
import pandas as pd
import networkx as nx
from sklearn.neighbors import NearestNeighbors
from cdlib import algorithms

PILOT_DIR = "data/processed/graph_pilot_top200_depth"
SEM_SIM_THRESHOLD = 0.60  # loose base floor -- disparity filter does the real
# pruning work below, don't want to have already thrown away locally-significant
# edges before it gets a chance to evaluate them
ALPHA = 0.05  # standard significance level from the original paper


def disparity_filter(G, alpha=ALPHA):
    keep_edges = set()
    for i in G.nodes():
        neighbors = list(G[i])
        k_i = len(neighbors)
        if k_i < 2:
            if k_i == 1:
                keep_edges.add(tuple(sorted([i, neighbors[0]])))  # degree-1 nodes: keep their only edge
            continue
        weights = np.array([G[i][j].get("weight", 1.0) for j in neighbors])
        total = weights.sum()
        if total <= 0:
            continue
        p = weights / total
        significance = (1 - p) ** (k_i - 1)  # alpha_ij: smaller = more significant
        for j, sig in zip(neighbors, significance):
            if sig < alpha:
                keep_edges.add(tuple(sorted([i, j])))
    return keep_edges


def main():
    comments = pd.read_parquet(f"{PILOT_DIR}/comments.parquet")
    emb = np.load(f"{PILOT_DIR}/comment_embeddings_gemini.npy")
    id_set = set(comments["id"])

    print("Building full 3-layer combined graph (reply + Gemini semantic + author connectivity)...", flush=True)
    G = nx.Graph()
    G.add_nodes_from(comments["id"])

    n_reply = 0
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
            G.add_edge(row["id"], cand, weight=max(G[row["id"]][cand].get("weight", 0), 1.0) if G.has_edge(row["id"], cand) else 1.0)
            n_reply += 1

    ids = comments["id"].to_numpy()
    nn = NearestNeighbors(n_neighbors=11, metric="cosine").fit(emb)
    dists, idxs = nn.kneighbors(emb)
    n_sem = 0
    for i in range(len(ids)):
        for j_pos in range(1, 11):
            j = idxs[i, j_pos]
            sim = 1 - dists[i, j_pos]
            if sim >= SEM_SIM_THRESHOLD:
                a, b = ids[i], ids[j]
                w = float(sim)
                if G.has_edge(a, b):
                    G[a][b]["weight"] = max(G[a][b]["weight"], w)
                else:
                    G.add_edge(a, b, weight=w)
                n_sem += 1

    author_df = pd.read_csv(f"{PILOT_DIR}/author_comment_edges.csv")
    n_auth = 0
    for _, row in author_df.iterrows():
        a, b = row["comment_a"], row["comment_b"]
        if G.has_edge(a, b):
            G[a][b]["weight"] = max(G[a][b]["weight"], 1.0)
        else:
            G.add_edge(a, b, weight=1.0)
        n_auth += 1

    print(f"  {n_reply:,} reply edges, {n_sem:,} semantic edges (sim>={SEM_SIM_THRESHOLD}), "
          f"{n_auth:,} author edges", flush=True)
    print(f"  pre-backbone graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges", flush=True)

    print(f"\nApplying disparity filter (alpha={ALPHA})...", flush=True)
    keep_edges = disparity_filter(G, ALPHA)
    print(f"  backbone: {len(keep_edges):,} edges kept of {G.number_of_edges():,} "
          f"({len(keep_edges)/G.number_of_edges()*100:.1f}%)", flush=True)

    B = nx.Graph()
    B.add_nodes_from(G.nodes())
    B.add_edges_from(keep_edges)
    n_isolated_after = sum(1 for n in B.nodes() if B.degree(n) == 0)
    print(f"  backbone graph: {B.number_of_nodes():,} nodes, {B.number_of_edges():,} edges, "
          f"{n_isolated_after:,} isolated after pruning", flush=True)

    print("\nRunning hierarchical link community detection on the backbone (full pilot scale)...", flush=True)
    result = algorithms.hierarchical_link_community(B)
    edge_communities = result.communities
    print(f"  {len(edge_communities)} link communities found (edge-level)", flush=True)

    membership_count = {}
    rows = []
    for i, edges in enumerate(edge_communities):
        nodes_in_community = set()
        for edge in edges:
            nodes_in_community.add(edge[0])
            nodes_in_community.add(edge[1])
        for node in nodes_in_community:
            membership_count[node] = membership_count.get(node, 0) + 1
            rows.append({"id": node, "community_id": i})

    out = pd.DataFrame(rows)
    out.to_csv(f"{PILOT_DIR}/backbone_link_communities.csv", index=False)

    sizes = sorted(out.groupby("community_id").size().tolist(), reverse=True) if len(out) else []
    n_multi = sum(1 for v in membership_count.values() if v > 1)
    n_in_any = len(membership_count)
    print(f"\n  community sizes, top 10: {sizes[:10]}", flush=True)
    print(f"  {n_in_any:,}/{B.number_of_nodes():,} nodes belong to at least 1 community", flush=True)
    if n_in_any:
        print(f"  {n_multi:,}/{n_in_any:,} of those belong to MORE THAN ONE community "
              f"({n_multi/n_in_any*100:.1f}%)", flush=True)
    if n_multi:
        print(f"  max communities any single node belongs to: {max(membership_count.values())}", flush=True)


if __name__ == "__main__":
    main()
