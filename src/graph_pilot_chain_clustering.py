"""graph_pilot_chain_clustering.py

Nash's refinement 2026-08-02, same session as graph_pilot.py: reply
threads mostly retread the same handful of topics across many different
posts -- so instead of clustering individual COMMENTS by semantic
similarity (what graph_pilot.py's Layer 2 does), decompose each tree
into its CHAIN SEGMENTS (maximal straight-line runs between fork
points), pool each segment's embedding, and cluster CHAINS. Chain-
clusters become "trunk topics." At every fork point, check whether the
child chain lands in the SAME cluster as its parent (a same-topic
continuation, different voices) or a DIFFERENT one (a genuine subtopic
branching off) -- this is the concrete mechanism for "see where these
can explore subtopics."

Reuses graph_pilot.py's already-computed outputs (comments.parquet,
comment_embeddings.npy) -- no re-extraction or re-embedding.

Chain decomposition: a chain segment starts at (a) a top-level comment
(child of the post) or (b) immediately after a branch point (a node
with >1 children). It continues through single-child descendants until
hitting a leaf or another branch point.

Output: data/processed/graph_pilot_top200_depth/chains.parquet
  (chain_id, member comment ids, pooled embedding index, chain_cluster)
        data/processed/graph_pilot_top200_depth/fork_analysis.csv
  (parent_chain_id, child_chain_id, same_cluster bool) -- one row per fork
"""
import os
import sys

sys.setrecursionlimit(10000)  # deepest pilot thread hits depth 610; the
# recursive walk() below can approach that depth on a chain of frequent
# forks, past Python's default 1000-frame limit in the worst case.

import numpy as np
import pandas as pd
import networkx as nx
from sklearn.neighbors import NearestNeighbors
from sklearn.metrics.pairwise import cosine_similarity

PILOT_DIR = "data/processed/graph_pilot_top200_depth"
K_NEIGHBORS = 10
SIM_THRESHOLD = 0.5


def build_children_map(comments):
    """id -> list of child ids, and id -> parent id (None for top-level)."""
    children = {}
    parent_of = {}
    id_set = set(comments["id"])
    for _, row in comments.iterrows():
        p = row["parent_id"]
        if p == row["link_id"]:
            parent_of[row["id"]] = row["link_id"]  # parent is the post
            children.setdefault(row["link_id"], []).append(row["id"])
        elif isinstance(p, str) and p.startswith("t1_"):
            parent_comment_id = p[3:]
            if parent_comment_id in id_set:
                parent_of[row["id"]] = parent_comment_id
                children.setdefault(parent_comment_id, []).append(row["id"])
    return children, parent_of


def decompose_chains(comments, children):
    """Walk from each top-level comment, splitting into a new chain at
    every fork point (a node with >1 children). Returns a list of chains
    (each a list of comment ids in order) and, for every fork, the
    (parent_chain_idx, child_chain_idx) pairs."""
    post_ids = set(comments["link_id"].unique())
    chains = []  # list of lists of comment ids
    chain_end_owner = {}  # comment_id (end of a chain) -> chain index, for fork lookup
    forks = []  # (parent_chain_idx, child_chain_idx)

    def walk(start_id, parent_chain_idx):
        chain = [start_id]
        node = start_id
        while True:
            kids = children.get(node, [])
            if len(kids) == 1:
                node = kids[0]
                chain.append(node)
            else:
                break
        chain_idx = len(chains)
        chains.append(chain)
        if parent_chain_idx is not None:
            forks.append((parent_chain_idx, chain_idx))
        kids = children.get(node, [])
        if len(kids) > 1:
            for k in kids:
                walk(k, chain_idx)

    for post_id in post_ids:
        for top_level_id in children.get(post_id, []):
            walk(top_level_id, None)

    return chains, forks


def main():
    comments = pd.read_parquet(f"{PILOT_DIR}/comments.parquet")
    emb = np.load(f"{PILOT_DIR}/comment_embeddings.npy")
    id_to_idx = {cid: i for i, cid in enumerate(comments["id"])}

    print("Building tree structure...", flush=True)
    children, parent_of = build_children_map(comments)

    print("Decomposing into chain segments...", flush=True)
    chains, forks = decompose_chains(comments, children)
    chain_lengths = [len(c) for c in chains]
    print(f"  {len(chains):,} chain segments (length distribution: min={min(chain_lengths)}, "
          f"max={max(chain_lengths)}, mean={np.mean(chain_lengths):.2f})", flush=True)
    print(f"  {len(forks):,} fork points (parent chain -> child chain edges)", flush=True)

    print("Pooling embeddings per chain...", flush=True)
    chain_emb = np.zeros((len(chains), emb.shape[1]), dtype=np.float32)
    for i, chain in enumerate(chains):
        idxs = [id_to_idx[cid] for cid in chain if cid in id_to_idx]
        if idxs:
            chain_emb[i] = emb[idxs].mean(axis=0)

    print(f"Building chain-level k-NN graph (k={K_NEIGHBORS}, cosine sim >= {SIM_THRESHOLD})...", flush=True)
    nn = NearestNeighbors(n_neighbors=min(K_NEIGHBORS + 1, len(chains)), metric="cosine").fit(chain_emb)
    dists, idxs = nn.kneighbors(chain_emb)

    chain_graph = nx.Graph()
    chain_graph.add_nodes_from(range(len(chains)))
    for i in range(len(chains)):
        for j_pos in range(1, idxs.shape[1]):
            j = idxs[i, j_pos]
            sim = 1 - dists[i, j_pos]
            if sim >= SIM_THRESHOLD:
                chain_graph.add_edge(i, int(j), weight=float(sim))

    print("Running Louvain on chain-level graph (chain-clusters = 'trunk topics')...", flush=True)
    chain_communities = nx.algorithms.community.louvain_communities(chain_graph, seed=42, weight="weight")
    chain_cluster_of = {}
    for cid, comm in enumerate(chain_communities):
        for node in comm:
            chain_cluster_of[node] = cid
    sizes = sorted([len(c) for c in chain_communities], reverse=True)
    print(f"  {len(chain_communities)} chain-clusters, top 10 sizes: {sizes[:10]}", flush=True)

    print("\nAnalyzing fork points: same-cluster continuation vs. subtopic branch...", flush=True)
    fork_rows = []
    for parent_idx, child_idx in forks:
        same = chain_cluster_of.get(parent_idx) == chain_cluster_of.get(child_idx)
        fork_rows.append({
            "parent_chain_idx": parent_idx, "child_chain_idx": child_idx,
            "parent_cluster": chain_cluster_of.get(parent_idx),
            "child_cluster": chain_cluster_of.get(child_idx),
            "same_cluster": same,
        })
    fork_df = pd.DataFrame(fork_rows)
    n_same = fork_df["same_cluster"].sum()
    print(f"  {n_same:,}/{len(fork_df):,} forks ({n_same/len(fork_df)*100:.1f}%) stay in the same chain-cluster "
          f"(continuation, not a topic shift)", flush=True)
    print(f"  {len(fork_df)-n_same:,}/{len(fork_df):,} forks ({(len(fork_df)-n_same)/len(fork_df)*100:.1f}%) "
          f"cross into a different chain-cluster (candidate subtopic branch)", flush=True)

    chains_out = pd.DataFrame({
        "chain_idx": range(len(chains)),
        "chain_cluster": [chain_cluster_of.get(i) for i in range(len(chains))],
        "length": chain_lengths,
        "first_comment_id": [c[0] for c in chains],
        "last_comment_id": [c[-1] for c in chains],
        "member_ids": [",".join(c) for c in chains],
    })
    chains_out.to_parquet(f"{PILOT_DIR}/chains.parquet", index=False)
    fork_df.to_csv(f"{PILOT_DIR}/fork_analysis.csv", index=False)
    print(f"\nDone. Output in {PILOT_DIR}/chains.parquet and fork_analysis.csv", flush=True)


if __name__ == "__main__":
    main()
