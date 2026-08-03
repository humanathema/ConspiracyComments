"""graph_pilot_chain_similarity_post_layer.py

New post-to-post layer using the whole-chain Gemini embeddings
(chain_embeddings_gemini.npy, one vector per reply-chain, already
confirmed complete -- 29,913/29,913) instead of the existing
post_similarity layer's title+selftext-only embeddings. Nash's direction
2026-08-02 (late): "I just kind of want top level connections between
posts... a consistent way to connect posts together" -- and specifically
NOT via naive flat-averaging of comment embeddings per thread, which
would wash out into a generic centroid for busy threads (median 79
chains/thread, up to 1,353 -- confirmed a real risk, not hypothetical).

Design: don't collapse each thread into one blended vector at all --
find cross-thread chain-to-chain nearest neighbors (a specific
conversational path in thread A closely resembling a specific path in
thread B), then map those chain-pair hits up to post-pair edges. This
keeps multi-modality: a thread that forked into several distinct
sub-conversations can connect to several DIFFERENT other threads via
different chains, rather than being forced into one average signature.
Same "don't blend, keep it inspectable" principle as every other layer
tonight.

Output: data/processed/graph_pilot_top200_depth/post_chain_similarity_edges.csv
  (id_a, id_b, layer, weight) -- id_a/id_b are t3_<postid> link_ids, same
  node space post_similarity and the reply layer's post-nodes already use.
  weight = max cosine similarity across all chain-pairs found for that
  post-pair (aggregated, since multiple chains can connect the same two
  posts -- this file records the strongest one per pair, not every hit).
"""
import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors

PILOT_DIR = "data/processed/graph_pilot_top200_depth"
N_NEIGHBORS = 15  # a bit higher than the other k-NN layers since we then
# filter down to cross-thread-only, losing same-thread hits
SIM_THRESHOLD = 0.70  # higher floor than the comment-level semantic layer's
# 0.60 -- chain embeddings represent a whole coherent conversational path,
# not a single comment, so a genuine match should be a stronger signal


def edge(a, b, weight):
    return (a, b, "post_chain_similarity", weight) if a < b else (b, a, "post_chain_similarity", weight)


def main():
    chains = pd.read_parquet(f"{PILOT_DIR}/chains.parquet")
    comments = pd.read_parquet(f"{PILOT_DIR}/comments.parquet")
    id_to_link = comments.set_index("id")["link_id"].to_dict()
    chains["link_id"] = chains["first_comment_id"].map(id_to_link)

    emb = np.load(f"{PILOT_DIR}/chain_embeddings_gemini.npy")
    link_ids = chains["link_id"].to_numpy()

    print(f"Building cross-thread chain-to-chain k-NN over {len(chains):,} chains...", flush=True)
    nn = NearestNeighbors(n_neighbors=N_NEIGHBORS + 1, metric="cosine").fit(emb)
    dists, idxs = nn.kneighbors(emb)

    best_pair_sim = {}
    n_hits = 0
    for i in range(len(chains)):
        for j_pos in range(1, N_NEIGHBORS + 1):
            j = idxs[i, j_pos]
            if link_ids[i] == link_ids[j]:
                continue  # same-thread hit, not what this layer is for
            sim = 1 - dists[i, j_pos]
            if sim < SIM_THRESHOLD:
                continue
            a, b = (link_ids[i], link_ids[j]) if link_ids[i] < link_ids[j] else (link_ids[j], link_ids[i])
            key = (a, b)
            if key not in best_pair_sim or sim > best_pair_sim[key]:
                best_pair_sim[key] = sim
            n_hits += 1

    print(f"  {n_hits:,} cross-thread chain-pair hits >= {SIM_THRESHOLD}, "
          f"collapsing to {len(best_pair_sim):,} unique post-pairs (max sim kept)", flush=True)

    rows = [edge(a, b, w) for (a, b), w in best_pair_sim.items()]
    out = pd.DataFrame(rows, columns=["id_a", "id_b", "layer", "weight"])
    out.to_csv(f"{PILOT_DIR}/post_chain_similarity_edges.csv", index=False)

    posts_touched = set(out["id_a"]) | set(out["id_b"])
    print(f"\n{len(out):,} post_chain_similarity edges, {len(posts_touched):,}/200 posts touched", flush=True)
    print(f"Saved to {PILOT_DIR}/post_chain_similarity_edges.csv", flush=True)


if __name__ == "__main__":
    main()
