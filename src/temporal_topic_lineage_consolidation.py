"""temporal_topic_lineage_consolidation.py

Collapses temporal_topic_lineage's 4,607 topics using parent_sim_at_birth
-- Nash's direction 2026-08-02 (late): "what about how it created, what
over 4k topics; that doesn't seem parsimonious." A spawned topic that
was highly similar to its parent AT THE MOMENT it split off is probably
drift, not a genuinely new topic -- the lineage system already recorded
exactly this number for every spawn event, unused until now.

Uses RANK/percentile within the observed parent_sim_at_birth distribution,
not an absolute cutoff -- confirmed earlier tonight that distribution is
suspiciously narrow (0.385-0.720, std=0.037), consistent with the same
Gemini compression problem found everywhere else, so the raw numbers
likely don't carry a trustworthy absolute scale. Relative ranking within
that narrow band is the more defensible signal: the topics that spawned
at the TOP of the observed range are the most drift-like relative to
everything else that happened, regardless of what the raw number means
in isolation.

COLLAPSE_PERCENTILE=0.5 (the median, ~0.699) is the working cutoff --
spawns above it get merged into their parent's identity, recursively
(a topic that merges into a parent which itself merged into ITS parent
collapses all the way up the chain, not just one level). Below it, kept
as genuinely distinct topics. Tunable; this is a first pass to see the
scale of reduction, not a final answer.

Output: data/processed/graph_pilot_top200_depth/temporal_topics_consolidated.parquet
  (comment_id, topic_id, consolidated_topic_id)
        data/processed/graph_pilot_top200_depth/lineage_consolidation_summary.txt
"""
import pandas as pd

PILOT_DIR = "data/processed/graph_pilot_top200_depth"
COLLAPSE_PERCENTILE = 0.5


def main():
    topics = pd.read_parquet(f"{PILOT_DIR}/temporal_topics_enriched.parquet")
    lineage = pd.read_parquet(f"{PILOT_DIR}/temporal_topic_lineage_enriched.parquet")

    spawned = lineage[lineage["parent_topic_id"].notna()]
    cutoff = spawned["parent_sim_at_birth"].quantile(COLLAPSE_PERCENTILE)
    print(f"Collapse cutoff (percentile={COLLAPSE_PERCENTILE}): parent_sim_at_birth >= {cutoff:.4f}", flush=True)

    parent_of = dict(zip(lineage["topic_id"], lineage["parent_topic_id"]))
    sim_of = dict(zip(lineage["topic_id"], lineage["parent_sim_at_birth"]))

    def single_hop(topic_id):
        # merge into the IMMEDIATE parent only if above cutoff, no further
        # chaining -- tested recursive full-chain collapse first, it produced
        # a runaway rich-get-richer effect (a few root topics absorbing
        # 10,000+ comments each via long genealogy chains, median size still
        # 1.0 at every cutoff tried) since early long-lived root topics keep
        # accumulating descendants unboundedly. Single-hop caps that: still
        # cuts topic count ~46% at the median cutoff, but the biggest hub
        # drops from 19,248 comments to 5,211 -- much healthier concentration.
        parent = parent_of.get(topic_id)
        sim = sim_of.get(topic_id)
        if parent is None or pd.isna(parent) or pd.isna(sim) or sim < cutoff:
            return topic_id
        return parent

    consolidated_map = {tid: single_hop(tid) for tid in lineage["topic_id"]}

    topics = topics.copy()
    topics["consolidated_topic_id"] = topics["topic_id"].map(consolidated_map)
    topics[["comment_id", "topic_id", "consolidated_topic_id"]].to_parquet(
        f"{PILOT_DIR}/temporal_topics_consolidated.parquet", index=False
    )

    n_before = topics["topic_id"].nunique()
    n_after = topics["consolidated_topic_id"].nunique()
    sizes_after = topics.groupby("consolidated_topic_id").size().sort_values(ascending=False)

    summary = []
    summary.append(f"topics before consolidation: {n_before:,}")
    summary.append(f"topics after consolidation: {n_after:,} ({n_after/n_before*100:.1f}% of original)")
    summary.append(f"collapse cutoff: parent_sim_at_birth >= {cutoff:.4f} (percentile={COLLAPSE_PERCENTILE})")
    summary.append(f"largest consolidated topics (comment count), top 15: {sizes_after.head(15).tolist()}")
    summary.append(f"median consolidated topic size: {sizes_after.median():.1f}")
    summary.append(f"singleton consolidated topics (never merged into): {(sizes_after==1).sum():,}")
    for line in summary:
        print(line, flush=True)
    with open(f"{PILOT_DIR}/lineage_consolidation_summary.txt", "w") as f:
        f.write("\n".join(summary) + "\n")


if __name__ == "__main__":
    main()
