"""graph_pilot_author_edges.py

Non-semantic thread-to-thread connectivity, per Nash's explicit design
constraint 2026-08-02: he wants a genuinely different structure from
topic modeling, so thread/post connectedness should NOT come from
semantic similarity of their content -- that's just topic modeling
applied at a coarser grain. This builds two purely structural/behavioral
edge layers instead (who, not what):

1. Author co-participation: author X appears in both thread A and B ->
   edge between A and B, weighted by count of shared authors. Weak
   signal on its own (X could just be a prolific commenter everywhere).
2. Author-pair recurring exchange: author A actually REPLIED to author
   B (a real reply edge, not just co-presence) in more than one
   distinct thread. Deliberately separate from (1) and stronger --
   two people who've argued across three threads is a different fact
   from two people who merely both posted in three threads.

Scoped to the 200 pilot threads (data/processed/graph_pilot_top200_depth/comments.parquet),
where these edges directly address "don't leave the trees as a
disjoint forest" -- connects thread N to thread M when real people/
real exchanges link them, independent of what either thread is about.

Output: data/processed/graph_pilot_top200_depth/thread_coparticipation_edges.csv
          (thread_a, thread_b, n_shared_authors)
        data/processed/graph_pilot_top200_depth/author_pair_recurring_exchanges.csv
          (author_a, author_b, n_distinct_threads, thread_ids)
        data/processed/graph_pilot_top200_depth/thread_recurring_exchange_edges.csv
          (thread_a, thread_b, n_recurring_author_pairs)
"""
from itertools import combinations

import pandas as pd

PILOT_DIR = "data/processed/graph_pilot_top200_depth"


def build_coparticipation(comments):
    author_threads = comments.groupby("author")["link_id"].apply(lambda s: set(s) - {"[deleted]"})
    author_threads = author_threads[author_threads.map(len) > 1]  # only authors in >1 thread matter here
    print(f"  {len(author_threads):,} authors appear in more than one pilot thread", flush=True)

    pair_counts = {}
    for author, threads in author_threads.items():
        if author in ("[deleted]", None) or pd.isna(author):
            continue
        for a, b in combinations(sorted(threads), 2):
            pair_counts[(a, b)] = pair_counts.get((a, b), 0) + 1

    rows = [{"thread_a": a, "thread_b": b, "n_shared_authors": n} for (a, b), n in pair_counts.items()]
    df = pd.DataFrame(rows).sort_values("n_shared_authors", ascending=False)
    return df


def build_recurring_exchanges(comments):
    id_to_author = dict(zip(comments["id"], comments["author"]))
    id_to_thread = dict(zip(comments["id"], comments["link_id"]))
    id_set = set(comments["id"])

    # real reply edges (child replied to a specific parent comment, both real authors)
    exchange_threads = {}  # (author_a, author_b) sorted -> set of thread ids where they exchanged
    for _, row in comments.iterrows():
        p = row["parent_id"]
        if not isinstance(p, str) or not p.startswith("t1_"):
            continue
        parent_id = p[3:]
        if parent_id not in id_set:
            continue
        replier = row["author"]
        repliee = id_to_author.get(parent_id)
        if not replier or not repliee or replier == repliee:
            continue
        if replier in ("[deleted]",) or repliee in ("[deleted]",):
            continue
        pair = tuple(sorted([replier, repliee]))
        exchange_threads.setdefault(pair, set()).add(row["link_id"])

    recurring = {pair: threads for pair, threads in exchange_threads.items() if len(threads) > 1}
    print(f"  {len(exchange_threads):,} author pairs exchanged replies at all; "
          f"{len(recurring):,} of them did so across MORE THAN ONE distinct thread", flush=True)

    rows = [{"author_a": a, "author_b": b, "n_distinct_threads": len(threads),
             "thread_ids": ",".join(sorted(threads))} for (a, b), threads in recurring.items()]
    pair_df = pd.DataFrame(rows).sort_values("n_distinct_threads", ascending=False)

    # collapse to thread-thread edges: how many recurring author-pairs link each pair of threads
    thread_pair_counts = {}
    for (a, b), threads in recurring.items():
        for t1, t2 in combinations(sorted(threads), 2):
            thread_pair_counts[(t1, t2)] = thread_pair_counts.get((t1, t2), 0) + 1
    thread_rows = [{"thread_a": t1, "thread_b": t2, "n_recurring_author_pairs": n}
                    for (t1, t2), n in thread_pair_counts.items()]
    thread_df = pd.DataFrame(thread_rows).sort_values("n_recurring_author_pairs", ascending=False) if thread_rows else pd.DataFrame(columns=["thread_a", "thread_b", "n_recurring_author_pairs"])

    return pair_df, thread_df


def main():
    comments = pd.read_parquet(f"{PILOT_DIR}/comments.parquet")
    print(f"{len(comments):,} pilot comments, {comments['author'].nunique():,} distinct authors, "
          f"{comments['link_id'].nunique():,} threads", flush=True)

    print("\n=== Layer: author co-participation ===", flush=True)
    copart = build_coparticipation(comments)
    copart.to_csv(f"{PILOT_DIR}/thread_coparticipation_edges.csv", index=False)
    print(f"  {len(copart):,} thread-pair edges (any shared author)", flush=True)
    print(copart.head(10).to_string(), flush=True)

    print("\n=== Layer: author-pair recurring exchange (stronger signal) ===", flush=True)
    pair_df, thread_df = build_recurring_exchanges(comments)
    pair_df.to_csv(f"{PILOT_DIR}/author_pair_recurring_exchanges.csv", index=False)
    thread_df.to_csv(f"{PILOT_DIR}/thread_recurring_exchange_edges.csv", index=False)
    print(f"  {len(thread_df):,} thread-pair edges via recurring author exchanges", flush=True)
    print(thread_df.head(10).to_string(), flush=True)

    all_threads = set(comments["link_id"].unique())
    connected_via_copart = set(copart["thread_a"]) | set(copart["thread_b"])
    connected_via_exchange = set(thread_df["thread_a"]) | set(thread_df["thread_b"]) if len(thread_df) else set()
    print(f"\n{len(connected_via_copart):,}/{len(all_threads):,} pilot threads have at least one "
          f"co-participation edge to another pilot thread", flush=True)
    print(f"{len(connected_via_exchange):,}/{len(all_threads):,} pilot threads have at least one "
          f"recurring-exchange edge to another pilot thread", flush=True)


if __name__ == "__main__":
    main()
