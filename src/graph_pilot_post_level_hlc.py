"""graph_pilot_post_level_hlc.py

Post-level version of tonight's comment-level HLC pipeline, applied to
the 200-post backbone instead of the 90k-comment graph. Nash's direction
2026-08-02 (late): "instead of kNN, the overlapping/family resemblance/
HLC thing, with the disparity based pruner/backbone extraction" -- same
real methodology (Ahn/Bagrow/Lehmann HLC + Serrano/Boguna/Vespignani
disparity filter + MST connectivity guarantee) that worked at comment
level, applied one level up.

Only 200 nodes, so this runs entirely locally -- no Kaggle round-trip
needed at this scale.

Layers:
  post_similarity        -- title+selftext Gemini k-NN (already built,
                             AMP/placeholder-title bugs already fixed).
  thread_coparticipation  -- shared-author count between two threads
                             (14,265/19,900 possible pairs -- dense, but
                             genuinely weighted by n_shared_authors, not
                             uniform like temporal was, so disparity
                             filtering has real gradation to work with).
  thread_recurring_exchange -- stronger, sparser signal: pairs of authors
                             who exchanged replies across BOTH threads,
                             not just co-commented (176 pairs).
  post_chain_similarity  -- NOT included yet, pending the destance test
                             (currently degenerate: 65.5% of all possible
                             pairs connected, same failure mode disparity
                             filtering is meant to fix -- add back once
                             the stance-projected version is validated).

Combining rule: same "fire together, wire together" sum-across-layers
weight as the comment-level pruned/MST runs, MST for guaranteed
connectivity (no isolated posts), disparity filter for additional edges
on top.

Output: data/processed/graph_pilot_top200_depth/post_level_hlc_communities.csv
  (link_id, community_id) -- overlapping post membership
"""
import numpy as np
import pandas as pd
import networkx as nx
from sklearn.neighbors import NearestNeighbors
from cdlib import algorithms

PILOT_DIR = "data/processed/graph_pilot_top200_depth"
ALPHA = 0.05


def disparity_filter(G, alpha=ALPHA):
    keep_edges = set()
    for i in G.nodes():
        neighbors = list(G[i])
        k_i = len(neighbors)
        if k_i < 2:
            if k_i == 1:
                keep_edges.add(tuple(sorted([i, neighbors[0]])))
            continue
        weights = np.array([G[i][j].get("weight", 1.0) for j in neighbors])
        total = weights.sum()
        if total <= 0:
            continue
        p = weights / total
        significance = (1 - p) ** (k_i - 1)
        for j, sig in zip(neighbors, significance):
            if sig < alpha:
                keep_edges.add(tuple(sorted([i, j])))
    return keep_edges


def main():
    posts = pd.read_parquet(f"{PILOT_DIR}/posts.parquet")
    all_link_ids = set(posts["link_id"])

    G = nx.Graph()
    G.add_nodes_from(all_link_ids)

    edges = pd.read_csv(f"{PILOT_DIR}/multilayer_edges.csv")
    ps = edges[edges["layer"] == "post_similarity"]
    for row in ps.itertuples():
        if G.has_edge(row.id_a, row.id_b):
            G[row.id_a][row.id_b]["weight"] += row.weight
        else:
            G.add_edge(row.id_a, row.id_b, weight=row.weight)
    print(f"post_similarity: {len(ps):,} edges added", flush=True)

    coparticipation = pd.read_csv(f"{PILOT_DIR}/thread_coparticipation_edges.csv")
    for row in coparticipation.itertuples():
        w = float(row.n_shared_authors) / 10.0  # scale down so it doesn't
        # swamp post_similarity's ~0.6-1.0-range weights by raw author count
        if G.has_edge(row.thread_a, row.thread_b):
            G[row.thread_a][row.thread_b]["weight"] += w
        else:
            G.add_edge(row.thread_a, row.thread_b, weight=w)
    print(f"thread_coparticipation: {len(coparticipation):,} edges added", flush=True)

    recurring = pd.read_csv(f"{PILOT_DIR}/thread_recurring_exchange_edges.csv")
    for row in recurring.itertuples():
        w = float(row.n_recurring_author_pairs) * 2.0  # stronger, more
        # specific signal than mere coparticipation -- weight it up
        if G.has_edge(row.thread_a, row.thread_b):
            G[row.thread_a][row.thread_b]["weight"] += w
        else:
            G.add_edge(row.thread_a, row.thread_b, weight=w)
    print(f"thread_recurring_exchange: {len(recurring):,} edges added", flush=True)

    n_isolated = sum(1 for n in G.nodes() if G.degree(n) == 0)
    print(f"\ncombined graph: {G.number_of_nodes()} nodes, {G.number_of_edges():,} edges, "
          f"{n_isolated} isolated", flush=True)

    print("\nBuilding maximum spanning tree (connectivity guarantee)...", flush=True)
    mst = nx.maximum_spanning_tree(G, weight="weight")
    mst_edges = set(tuple(sorted(e)) for e in mst.edges())
    print(f"  MST: {len(mst_edges)} edges", flush=True)

    print(f"\nApplying disparity filter (alpha={ALPHA}) for additional edges...", flush=True)
    disparity_edges = disparity_filter(G, ALPHA)
    backbone_edges = mst_edges | disparity_edges
    print(f"  disparity-significant: {len(disparity_edges)}, "
          f"combined backbone: {len(backbone_edges)}", flush=True)

    B = nx.Graph()
    B.add_nodes_from(G.nodes())
    for a, b in backbone_edges:
        B.add_edge(a, b, weight=G[a][b]["weight"])
    print(f"  backbone graph: {B.number_of_nodes()} nodes, {B.number_of_edges()} edges", flush=True)

    print("\nRunning hierarchical link community detection...", flush=True)
    result = algorithms.hierarchical_link_community(B)
    edge_communities = result.communities
    print(f"  {len(edge_communities)} link communities found (edge-level)", flush=True)

    membership_count = {}
    rows = []
    for i, comm_edges in enumerate(edge_communities):
        nodes_in_community = set()
        for e in comm_edges:
            nodes_in_community.add(e[0])
            nodes_in_community.add(e[1])
        for node in nodes_in_community:
            membership_count[node] = membership_count.get(node, 0) + 1
            rows.append({"link_id": node, "community_id": i})

    out = pd.DataFrame(rows)
    out.to_csv(f"{PILOT_DIR}/post_level_hlc_communities.csv", index=False)

    sizes = sorted(out.groupby("community_id").size().tolist(), reverse=True) if len(out) else []
    n_multi = sum(1 for v in membership_count.values() if v > 1)
    n_in_any = len(membership_count)
    print(f"\n  community sizes, top 10: {sizes[:10]}", flush=True)
    print(f"  {n_in_any}/{B.number_of_nodes()} posts belong to at least 1 community", flush=True)
    if n_in_any:
        print(f"  {n_multi}/{n_in_any} of those belong to MORE THAN ONE community "
              f"({n_multi/n_in_any*100:.1f}%)", flush=True)
    if n_multi:
        print(f"  max communities any single post belongs to: {max(membership_count.values())}", flush=True)
    print(f"\nSaved to {PILOT_DIR}/post_level_hlc_communities.csv", flush=True)


if __name__ == "__main__":
    main()
