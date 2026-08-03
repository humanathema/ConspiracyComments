"""graph_pilot_author_comment_edges.py

Brings the thread-level author connectivity (thread_coparticipation_edges.csv,
author_pair_recurring_exchanges.csv) down to the SAME comment-level node
space as the reply-structure and semantic layers, so it can become a
real third layer in the combined graph instead of a separate thread-
level side analysis. Nash's question 2026-08-02: does the overlapping-
community job incorporate author-pair connectivity? Answer was no --
this is the fix.

Operationalization: don't add an abstract "these two threads share an
author" edge -- connect the ACTUAL comments involved. For every author
who appears in more than one pilot thread, connect their comments
across those threads directly (same_author edges). For recurring
author-pairs (argued in more than one shared thread), additionally
connect the specific comments where the exchange happened, at higher
weight (recurring_exchange edges) -- a stronger, more specific bridge
than mere co-participation.

To avoid combinatorial blowup for authors with many comments in a
thread, connects at most MAX_PER_AUTHOR_THREAD comments per
(author, thread) pair rather than a full cross product.

Output: data/processed/graph_pilot_top200_depth/author_comment_edges.csv
  (comment_a, comment_b, edge_type) -- edge_type in {same_author, recurring_exchange}
"""
from itertools import combinations, product

import pandas as pd

PILOT_DIR = "data/processed/graph_pilot_top200_depth"
MAX_PER_AUTHOR_THREAD = 3  # cap comments-per-(author,thread) pair connected, avoid O(n^2) blowup
EXCLUDED_AUTHORS = {"[deleted]", "AutoModerator"}  # AutoModerator added 2026-08-02:
# posts the same templated sticky/rule text across nearly every thread, so its
# same-author edges connected 206 comments across 167 threads into one dense
# component -- became the single LARGEST community in the full raw HLC run,
# entirely a bot artifact, not a real author-identity cluster. 21,067/59,054
# (35.7%) of all author edges tonight came from this one account alone.


def main():
    comments = pd.read_parquet(f"{PILOT_DIR}/comments.parquet")

    # --- same-author edges across threads ---
    author_thread_comments = {}  # (author, thread) -> [comment_ids]
    for _, row in comments.iterrows():
        author = row["author"]
        if not author or author in EXCLUDED_AUTHORS or pd.isna(author):
            continue
        author_thread_comments.setdefault((author, row["link_id"]), []).append(row["id"])

    by_author = {}
    for (author, thread), cids in author_thread_comments.items():
        by_author.setdefault(author, {})[thread] = cids[:MAX_PER_AUTHOR_THREAD]

    edges = []
    for author, threads in by_author.items():
        if len(threads) < 2:
            continue
        for (t1, c1s), (t2, c2s) in combinations(threads.items(), 2):
            for a, b in product(c1s, c2s):
                edges.append({"comment_a": a, "comment_b": b, "edge_type": "same_author"})

    print(f"{len(edges):,} same-author cross-thread edges "
          f"({sum(1 for t in by_author.values() if len(t) > 1):,} authors involved)", flush=True)

    # --- recurring-exchange edges (stronger signal) ---
    id_to_author = dict(zip(comments["id"], comments["author"]))
    id_to_thread = dict(zip(comments["id"], comments["link_id"]))
    id_set = set(comments["id"])

    recurring_pairs = pd.read_csv(f"{PILOT_DIR}/author_pair_recurring_exchanges.csv")
    recurring_set = set(zip(recurring_pairs["author_a"], recurring_pairs["author_b"]))

    n_exchange_edges = 0
    for _, row in comments.iterrows():
        p = row["parent_id"]
        if not isinstance(p, str) or not p.startswith("t1_"):
            continue
        parent_id = p[3:]
        if parent_id not in id_set:
            continue
        replier, repliee = row["author"], id_to_author.get(parent_id)
        if not replier or not repliee or replier == repliee:
            continue
        if replier in EXCLUDED_AUTHORS or repliee in EXCLUDED_AUTHORS:
            continue
        pair = tuple(sorted([replier, repliee]))
        if pair in recurring_set:
            edges.append({"comment_a": row["id"], "comment_b": parent_id, "edge_type": "recurring_exchange"})
            n_exchange_edges += 1

    print(f"{n_exchange_edges:,} recurring-exchange edges (direct reply edges between "
          f"author-pairs who exchanged replies in >1 pilot thread)", flush=True)

    out = pd.DataFrame(edges)
    out.to_csv(f"{PILOT_DIR}/author_comment_edges.csv", index=False)
    print(f"\nSaved {len(out):,} total author-connectivity edges to "
          f"{PILOT_DIR}/author_comment_edges.csv", flush=True)


if __name__ == "__main__":
    main()
