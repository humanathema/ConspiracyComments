"""graph_pilot_link_communities.py

The real Ahn/Bagrow/Lehmann (2010) link-communities algorithm, not
clique percolation's approximation of the same Wittgenstein family-
resemblance idea -- Nash's correction 2026-08-02. Clusters EDGES (the
pairwise resemblances themselves) rather than nodes, so overlapping
node membership falls out naturally from which edge-clusters touch a
node, with no requirement that a node sit inside a dense clique.

Uses cdlib's hierarchical_link_community (the real HLC implementation,
auto-picks the best dendrogram cut via partition density).

Scoped to the SAME 700-node sample (seed=42) already used for the
visualization -- clique percolation OOM'd on the full 90k-node combined
graph, this stays at a scale already proven tractable rather than
risking the same crash again.

Combines the same three layers as the crashed full-scale run: reply
structure, Gemini semantic k-NN, author connectivity -- restricted to
the 700-node subset.

Output: data/processed/graph_pilot_top200_depth/link_communities.csv
  (id, community_id) -- one row per membership, overlapping
"""
import numpy as np
import pandas as pd
import networkx as nx
from sklearn.metrics.pairwise import cosine_similarity
from cdlib import algorithms

PILOT_DIR = "data/processed/graph_pilot_top200_depth"
N_SAMPLE = 700
SEED = 42
SEM_SIM_THRESHOLD = 0.65  # matches the visualization's export floor


def main():
    comments = pd.read_parquet(f"{PILOT_DIR}/comments.parquet")
    emb = np.load(f"{PILOT_DIR}/comment_embeddings_gemini.npy")

    rng = np.random.default_rng(SEED)
    idx = rng.choice(len(comments), size=N_SAMPLE, replace=False)
    sub = comments.iloc[idx].reset_index(drop=True)
    sub_emb = emb[idx]
    sub_ids = set(sub["id"])
    id_set = set(comments["id"])

    print(f"Building combined graph on the same {N_SAMPLE}-node sample as the visualization...", flush=True)

    G = nx.Graph()
    G.add_nodes_from(sub["id"])

    # reply structure, restricted to pairs both in the sample
    n_reply = 0
    for _, row in sub.iterrows():
        p = row["parent_id"]
        cand = None
        if p == row["link_id"]:
            cand = row["link_id"]
        elif isinstance(p, str) and p.startswith("t1_"):
            pid = p[3:]
            if pid in id_set:
                cand = pid
        if cand is not None and cand in sub_ids:
            G.add_edge(row["id"], cand)
            n_reply += 1

    # semantic edges from the pairwise similarity already computed for the sample
    sims = cosine_similarity(sub_emb)
    n_sem = 0
    for i in range(N_SAMPLE):
        for j in range(i + 1, N_SAMPLE):
            if sims[i, j] >= SEM_SIM_THRESHOLD:
                a, b = sub["id"].iloc[i], sub["id"].iloc[j]
                G.add_edge(a, b)
                n_sem += 1

    # author connectivity, restricted to pairs both in the sample
    author_df = pd.read_csv(f"{PILOT_DIR}/author_comment_edges.csv")
    n_auth = 0
    for _, row in author_df.iterrows():
        if row["comment_a"] in sub_ids and row["comment_b"] in sub_ids:
            G.add_edge(row["comment_a"], row["comment_b"])
            n_auth += 1

    print(f"  {n_reply:,} reply edges, {n_sem:,} semantic edges, {n_auth:,} author edges", flush=True)
    print(f"  combined graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges", flush=True)

    print("\nRunning hierarchical link community detection (real HLC, auto-cut by partition density)...", flush=True)
    result = algorithms.hierarchical_link_community(G)
    edge_communities = result.communities  # each community is a list of EDGES, not nodes
    print(f"  {len(edge_communities)} link communities found (edge-level)", flush=True)

    # derive node-level membership: a node belongs to community i if any of its
    # incident edges belongs to community i -- this is exactly how HLC produces
    # overlapping NODE membership from edge clusters (Ahn/Bagrow/Lehmann's own
    # construction, not an approximation of it)
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
    out.to_csv(f"{PILOT_DIR}/link_communities.csv", index=False)

    sizes = sorted(out.groupby("community_id").size().tolist(), reverse=True)  # node count per community
    n_multi = sum(1 for v in membership_count.values() if v > 1)
    n_in_any = len(membership_count)
    print(f"\n  community sizes, top 10: {sizes[:10]}", flush=True)
    print(f"  {n_in_any:,}/{N_SAMPLE:,} nodes belong to at least 1 community", flush=True)
    if n_in_any:
        print(f"  {n_multi:,}/{n_in_any:,} of those belong to MORE THAN ONE community "
              f"({n_multi/n_in_any*100:.1f}%)", flush=True)
    if n_multi:
        print(f"  max communities any single node belongs to: {max(membership_count.values())}", flush=True)


if __name__ == "__main__":
    main()
