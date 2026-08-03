"""graph_pilot.py

First pilot for the graph-based topic/discourse structure idea
(handoff/task_graph_based_topic_structure.md) -- nodes = comments (PLUS
each pilot thread's post as an explicit root node), multiple SEPARATE
edge layers (not one blended similarity score, per Nash's explicit
interpretability requirement 2026-08-02).

Scope corrected twice from the first version, both times by Nash:
1. Thread selection is by LONGEST REPLY CHAIN (max_depth, from
   data/processed/thread_depth.parquet -- computed via a pure-DuckDB
   recursive CTE, no pandas, since threads are independent and don't
   need to be loaded into Python memory together), not raw comment
   count -- a high comment count picks the WIDEST posts (many shallow
   replies to the original post), not genuine sustained back-and-forth.
   Confirmed empirically: zero overlap between the top-20-by-count and
   top-20-by-depth thread lists.
2. Build the FULL TREE per selected thread (every branch, every reply
   at every level), not just the single longest chain -- and root it
   explicitly at the post itself (link_id becomes a real graph node,
   with edges to its top-level comments), not a forest of disconnected
   floating top-level comments.

Layers built here (the two with existing working patterns):
  1. reply structure -- post (root) -> top-level comments -> ... full tree
  2. semantic similarity -- k-NN cosine edges from MiniLM embeddings

Output: data/processed/graph_pilot_top200_depth/
  - comments.parquet (id, link_id, parent_id, author, created_utc, text, depth)
  - communities_reply.csv, communities_semantic.csv (id -> community_id per layer)
  - summary printed to stdout
"""
import os

import duckdb
import numpy as np
import pandas as pd
import networkx as nx
from sklearn.neighbors import NearestNeighbors

OUT_DIR = "data/processed/graph_pilot_top200_depth"
N_THREADS = 200
K_NEIGHBORS = 10
SIM_THRESHOLD = 0.5


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='5GB'")
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA enable_progress_bar=false")

    print(f"Selecting top {N_THREADS} threads by longest reply chain (max_depth)...", flush=True)
    top_threads = con.execute(f"""
        SELECT link_id, max_depth, n_comments
        FROM read_parquet('data/processed/thread_depth.parquet')
        ORDER BY max_depth DESC LIMIT {N_THREADS}
    """).df()
    thread_ids = top_threads["link_id"].tolist()
    print(f"  {len(thread_ids)} threads, {top_threads['n_comments'].sum():,} comments total "
          f"(depth range {top_threads['max_depth'].min()}-{top_threads['max_depth'].max()})", flush=True)

    print("Pulling ALL comments (every branch, not just the longest chain) + real text...", flush=True)
    thread_id_list = ", ".join(f"'{t}'" for t in thread_ids)
    comments = con.execute(f"""
        SELECT id, parent_id, link_id, author, created_utc, body AS text
        FROM read_json_auto('data/raw/r_conspiracy_comments*.jsonl*', maximum_object_size=50000000, union_by_name=True)
        WHERE link_id IN ({thread_id_list})
          AND body IS NOT NULL AND body != '' AND body != '[deleted]' AND body != '[removed]'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY created_utc DESC) = 1
    """).df()
    print(f"  {len(comments):,} comments with real text (post-dedup, deleted/removed excluded)", flush=True)
    comments.to_parquet(f"{OUT_DIR}/comments.parquet", index=False)

    # --- Layer 1: reply structure, rooted at the post ---
    print("\n=== Layer 1: reply structure (full tree, rooted at post id) ===", flush=True)
    id_set = set(comments["id"])
    reply_graph = nx.Graph()
    reply_graph.add_nodes_from(comments["id"])
    reply_graph.add_nodes_from(thread_ids)  # posts are real nodes too

    n_top_level_edges = 0
    n_reply_edges = 0
    for _, row in comments.iterrows():
        p = row["parent_id"]
        if p == row["link_id"]:
            # top-level comment: edge to the post itself, the tree's root
            reply_graph.add_edge(row["id"], row["link_id"])
            n_top_level_edges += 1
        elif isinstance(p, str) and p.startswith("t1_"):
            parent_comment_id = p[3:]
            if parent_comment_id in id_set:
                reply_graph.add_edge(row["id"], parent_comment_id)
                n_reply_edges += 1
    print(f"  {n_top_level_edges:,} post-root edges, {n_reply_edges:,} comment-to-comment reply edges", flush=True)
    print(f"  {reply_graph.number_of_nodes():,} nodes ({len(thread_ids)} of them post roots), "
          f"{reply_graph.number_of_edges():,} edges total", flush=True)
    n_components = nx.number_connected_components(reply_graph)
    print(f"  {n_components} connected components (should be close to {len(thread_ids)} -- one real tree per post, "
          f"plus any comments whose parent chain didn't resolve)", flush=True)

    reply_communities = nx.algorithms.community.louvain_communities(reply_graph, seed=42)
    reply_communities = [c for c in reply_communities if len(c) > 1]
    print(f"  {len(reply_communities)} communities (size>1) via Louvain on reply structure alone", flush=True)
    sizes = sorted([len(c) for c in reply_communities], reverse=True)
    print(f"  top 10 sizes: {sizes[:10]}", flush=True)

    reply_map = {}
    for i, c in enumerate(reply_communities):
        for node in c:
            reply_map[node] = i
    pd.DataFrame({"id": list(reply_map.keys()), "community_id": list(reply_map.values())}).to_csv(
        f"{OUT_DIR}/communities_reply.csv", index=False
    )

    # --- Layer 2: semantic similarity ---
    print("\n=== Layer 2: semantic similarity (MiniLM) ===", flush=True)
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    texts = comments["text"].fillna("").tolist()
    print(f"  embedding {len(texts):,} comments...", flush=True)
    emb = model.encode(texts, batch_size=256, show_progress_bar=True)
    np.save(f"{OUT_DIR}/comment_embeddings.npy", emb)

    print(f"  building k-NN graph (k={K_NEIGHBORS}, cosine sim >= {SIM_THRESHOLD})...", flush=True)
    nn = NearestNeighbors(n_neighbors=K_NEIGHBORS + 1, metric="cosine").fit(emb)
    dists, idxs = nn.kneighbors(emb)
    ids = comments["id"].to_numpy()

    sem_graph = nx.Graph()
    sem_graph.add_nodes_from(ids)
    n_sem_edges = 0
    for i in range(len(ids)):
        for j_pos in range(1, K_NEIGHBORS + 1):
            j = idxs[i, j_pos]
            sim = 1 - dists[i, j_pos]
            if sim >= SIM_THRESHOLD:
                sem_graph.add_edge(ids[i], ids[j], weight=float(sim))
                n_sem_edges += 1
    print(f"  {n_sem_edges:,} semantic edges", flush=True)

    sem_communities = nx.algorithms.community.louvain_communities(sem_graph, seed=42, weight="weight")
    sem_communities = [c for c in sem_communities if len(c) > 1]
    print(f"  {len(sem_communities)} communities (size>1) via Louvain on semantic similarity alone", flush=True)
    sizes = sorted([len(c) for c in sem_communities], reverse=True)
    print(f"  top 10 sizes: {sizes[:10]}", flush=True)

    sem_map = {}
    for i, c in enumerate(sem_communities):
        for node in c:
            sem_map[node] = i
    pd.DataFrame({"id": list(sem_map.keys()), "community_id": list(sem_map.values())}).to_csv(
        f"{OUT_DIR}/communities_semantic.csv", index=False
    )

    # --- Layer agreement check ---
    print("\n=== Layer agreement (reply-structure community vs semantic community) ===", flush=True)
    common_ids = set(reply_map.keys()) & set(sem_map.keys())
    if common_ids:
        from sklearn.metrics import normalized_mutual_info_score
        common_ids = list(common_ids)
        nmi = normalized_mutual_info_score(
            [reply_map[i] for i in common_ids], [sem_map[i] for i in common_ids]
        )
        print(f"  {len(common_ids):,} comments have both a reply-community and a semantic-community", flush=True)
        print(f"  normalized mutual information between the two layers: {nmi:.4f} "
              f"(0 = independent, 1 = identical partitions)", flush=True)

    print(f"\nDone. Output in {OUT_DIR}/", flush=True)


if __name__ == "__main__":
    main()
