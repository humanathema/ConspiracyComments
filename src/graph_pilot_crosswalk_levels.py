"""graph_pilot_crosswalk_levels.py

Links the comment-level HLC communities (hlc_multilayer_communities.csv,
142,049 communities, 90,194 comments) to the post-level HLC communities
(post_level_hlc_communities.csv, 494 communities, 200 posts) -- Nash's
direction 2026-08-02 (late): "let's make one big graph, where we don't
see the comment clusters necessarily as representing topics but sort of
branching off from them [the post-level topics]".

Not building one merged networkx graph object yet -- a crosswalk table
achieves the actual goal (seeing how comment-communities relate to
post-communities) and is more directly inspectable. Every comment
belongs to exactly one post (link_id), so a comment-community's members
map to a SET of posts, which in turn map to a set of post-communities
(posts can be in multiple, same overlapping-membership convention as
everything else tonight). This gives a natural, real test of the
"branches off from post topics" framing: does a comment-community's post
footprint concentrate on one dominant post-community (a clean branch),
or spread thin across many (a comment-community that's more of a
cross-cutting theme, not really "under" any single post-topic)?

CONCENTRATION for a comment-community = the dominant post-community's
share of that comment-community's total post-community "votes" (each
of the comment-community's posts contributes one vote per post-community
it belongs to, so a post in 3 post-communities casts 3 votes -- this
double-counts a little for posts with heavy overlap, but keeps the
computation simple and the interpretation clear enough for inspection).

Output: data/processed/graph_pilot_top200_depth/crosswalk_levels.csv
  (comment_community_id, comment_community_size, n_distinct_posts,
   dominant_post_community_id, dominant_post_community_share,
   dominant_post_community_titles)
"""
import pandas as pd

PILOT_DIR = "data/processed/graph_pilot_top200_depth"
MIN_COMMENT_COMMUNITY_SIZE = 10


def main():
    comments = pd.read_parquet(f"{PILOT_DIR}/comments.parquet")
    id_to_link = comments.set_index("id")["link_id"].to_dict()

    comment_comm = pd.read_csv(f"{PILOT_DIR}/hlc_multilayer_communities.csv")
    sizes = comment_comm.groupby("community_id").size()
    selected = sizes[sizes >= MIN_COMMENT_COMMUNITY_SIZE].index
    print(f"{len(selected):,} comment-communities >= size {MIN_COMMENT_COMMUNITY_SIZE}", flush=True)

    post_comm = pd.read_csv(f"{PILOT_DIR}/post_level_hlc_communities.csv")
    link_to_post_communities = post_comm.groupby("link_id")["community_id"].apply(set).to_dict()
    post_community_members = post_comm.groupby("community_id")["link_id"].apply(set).to_dict()
    # NOTE 2026-08-02: originally used vote-counting (each touched post casts
    # one vote per post-community it belongs to), but post-communities overlap
    # heavily (avg 7, up to 19, memberships/post) -- that diluted every score
    # regardless of real concentration (confirmed on the size=158 health-
    # citation community: 43 touched posts, votes spread thin purely from
    # ambient overlap, not real dispersion). Fixed to direct coverage instead:
    # for each candidate post-community, what fraction of the comment-
    # community's touched posts fall inside it -- no double-counting.

    posts = pd.read_parquet(f"{PILOT_DIR}/posts.parquet")
    id_to_title = posts.set_index("link_id")["title"].to_dict()

    rows = []
    for cc_id in selected:
        member_ids = comment_comm[comment_comm["community_id"] == cc_id]["id"].tolist()
        touched_posts = set(id_to_link.get(m) for m in member_ids if id_to_link.get(m))

        candidate_pcs = set()
        for link_id in touched_posts:
            candidate_pcs |= link_to_post_communities.get(link_id, set())

        coverage = {
            pc_id: len(touched_posts & post_community_members[pc_id]) / len(touched_posts)
            for pc_id in candidate_pcs
        }

        if not coverage:
            dominant_pc, dominant_share, dominant_titles = None, 0.0, ""
        else:
            dominant_pc = max(coverage, key=coverage.get)
            dominant_share = coverage[dominant_pc]
            dominant_post_ids = post_comm[post_comm["community_id"] == dominant_pc]["link_id"].tolist()
            dominant_titles = " | ".join(str(id_to_title.get(p, "?"))[:50] for p in dominant_post_ids[:3])

        rows.append({
            "comment_community_id": cc_id,
            "comment_community_size": sizes[cc_id],
            "n_distinct_posts": len(touched_posts),
            "dominant_post_community_id": dominant_pc,
            "dominant_post_community_share": round(dominant_share, 3),
            "dominant_post_community_sample_titles": dominant_titles,
        })

    out = pd.DataFrame(rows).sort_values("comment_community_size", ascending=False)
    out.to_csv(f"{PILOT_DIR}/crosswalk_levels.csv", index=False)

    print(f"\nConcentration (dominant_post_community_share) distribution:", flush=True)
    print(out["dominant_post_community_share"].describe(), flush=True)
    print(f"\nclean branches (share >= 0.7): {(out['dominant_post_community_share']>=0.7).sum()}/{len(out)}", flush=True)
    print(f"cross-cutting (share < 0.4): {(out['dominant_post_community_share']<0.4).sum()}/{len(out)}", flush=True)
    print(f"\nSaved to {PILOT_DIR}/crosswalk_levels.csv", flush=True)


if __name__ == "__main__":
    main()
