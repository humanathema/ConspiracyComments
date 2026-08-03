"""graph_pilot_topic_samples.py

Reusable version of the ad-hoc inspection queries run repeatedly tonight
(check top community texts, dominant layer, top citation domains / entity
mentions) -- Nash's direction 2026-08-02: "can we build a thing that gives
us sample comments for the topics" instead of one-off queries each time.

For every community at or above MIN_SIZE in hlc_multilayer_communities.csv,
reports: size, thread count, per-layer edge breakdown (which layer(s)
actually drove this community, temporal excluded since it's not part of
the graph these communities were built from), top citation domains and
entity mentions when relevant, and a handful of sample comment texts.

Output: data/processed/graph_pilot_top200_depth/topic_samples.md
  -- one section per community, largest first, meant for direct reading/
  skimming, not further programmatic parsing.
"""
import pandas as pd

PILOT_DIR = "data/processed/graph_pilot_top200_depth"
MIN_SIZE = 10
N_SAMPLES = 5
SNIPPET_LEN = 220


def main():
    comm = pd.read_csv(f"{PILOT_DIR}/hlc_multilayer_communities.csv")
    comments = pd.read_parquet(f"{PILOT_DIR}/comments.parquet")
    edges = pd.read_csv(f"{PILOT_DIR}/multilayer_edges.csv")
    edges = edges[edges["layer"] != "temporal"]  # not part of the graph these
    # communities were actually built from -- excluded from the HLC run itself

    cite = pd.read_csv("data/processed/citations_cache.csv", usecols=["comment_id", "domain"])
    em = pd.read_csv("data/processed/entity_mentions_cache_2stage_pooled.csv",
                      usecols=["comment_id", "entity_key"])
    em = em[~em["entity_key"].str.startswith("merged_")]

    sizes = comm.groupby("community_id").size().sort_values(ascending=False)
    selected = sizes[sizes >= MIN_SIZE]
    print(f"{len(selected):,} communities >= size {MIN_SIZE} (of {len(sizes):,} total)", flush=True)

    lines = [f"# Graph pilot topic samples\n\n{len(selected):,} communities >= size {MIN_SIZE}, largest first.\n"]

    for cid, size in selected.items():
        ids = comm[comm["community_id"] == cid]["id"].tolist()
        sub = comments[comments["id"].isin(ids)]
        e_sub = edges[edges["id_a"].isin(ids) & edges["id_b"].isin(ids)]
        layer_counts = e_sub["layer"].value_counts()
        top_layer = layer_counts.idxmax() if len(layer_counts) else "none"

        lines.append(f"\n## Community {cid} -- size={size}, threads={sub['link_id'].nunique()}, "
                      f"top_layer={top_layer} ({layer_counts.max() if len(layer_counts) else 0} edges)")
        lines.append(f"Layer breakdown: {layer_counts.to_dict()}")

        if "citation" in str(top_layer):
            c = cite[cite["comment_id"].isin(ids)]
            if len(c):
                lines.append(f"Top domains: {c['domain'].value_counts().head(5).to_dict()}")
        if "entity" in str(top_layer):
            e = em[em["comment_id"].isin(ids)]
            if len(e):
                lines.append(f"Top entities: {e['entity_key'].value_counts().head(5).to_dict()}")

        lines.append("")
        for t in sub["text"].head(N_SAMPLES):
            snippet = str(t)[:SNIPPET_LEN].replace("\n", " ")
            lines.append(f"- {snippet}")

    out_path = f"{PILOT_DIR}/topic_samples.md"
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved to {out_path}", flush=True)


if __name__ == "__main__":
    main()
