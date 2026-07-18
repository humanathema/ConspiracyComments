"""
Finds near-duplicate comment clusters via MinHash/LSH — the fuzzy-match
counterpart to detect_spam_bots.py's exact-text reuse detection.

detect_spam_bots.py catches copypasta only when the *same author* reuses
the *exact same* text. It misses two real patterns:
  - the same author reposting the same claim with minor edits (a link
    swapped, a sentence added) — the exact-text ratio doesn't see these
    as duplicates at all;
  - a coordinated campaign where *different* accounts post near-identical
    text — no single author's ratio looks unusual, so per-author stats
    can't catch it.

Method: 4-word shingles -> MinHash(num_perm=64) -> LSH (Jaccard
threshold=0.75), streamed in chunks so the full corpus is never held in
memory at once. Each doc is inserted into the LSH index and immediately
queried against it (query-after-insert), so by the time doc N is
processed, every near-duplicate among docs 1..N-1 is already indexed —
this finds every matching pair in one streaming pass without ever
materializing all MinHash objects simultaneously. Matches are unioned
into clusters with a dict-based union-find keyed by comment id.

Runs only on comments with char_length > MIN_CHAR_LENGTH (copypasta-scale
text — shorter comments produce too many coincidental near-matches and
would blow past this machine's available RAM) and skips authors already
flagged as bots by detect_spam_bots.py, since that reuse is already
accounted for. All comparisons are on token shingles, not semantic
content — deterministic, no LLM/embedding calls.

This machine has ~8GB total RAM with as little as ~1.3GB free during
normal use, so MIN_CHAR_LENGTH defaults conservatively high
(~220K candidate comments at 2000 chars — the longest-form copypasta
only). A 150K-candidate dry run at the 1000-char threshold (~930K
candidates full-scale) held under 600MB RSS, so if more RAM is free
when you run this, lowering MIN_CHAR_LENGTH to 1000 or below is
reasonable — just watch `top`/`vm_stat` while it runs, since this
script does not enforce a memory ceiling itself.

Incremental re-runs: pass --max-char-length to cap the candidate pool
at the *previous* run's --min-char-length, so a lower-threshold rerun
only processes the newly-included band instead of recomputing MinHash
for comments already clustered. Output is merged (not overwritten) with
whatever's already in OUT_PATH, matched on comment_id. Caveat: because
each band is run as its own independent LSH pass, a near-duplicate pair
straddling the band boundary (e.g. one comment at 1990 chars, its
near-twin at 2010) will be missed — a near-identical pair can't differ
in length by much though, so this only misses matches within roughly
one boundary's width of each other.

Usage: python -m src.detect_near_duplicate_spam [--min-char-length N] [--max-char-length N]
Input:  data/processed/lexical_scores_full.parquet
        data/processed/author_spam_bot_flags.parquet (optional; skips if absent)
Output: data/processed/near_duplicate_clusters.parquet (merged across runs)
"""

import argparse
import json
import os
import re
import time

import duckdb
import pandas as pd
from datasketch import MinHash, MinHashLSH

LEXICAL_PATH = "data/processed/lexical_scores_full.parquet"
BOT_FLAGS_PATH = "data/processed/author_spam_bot_flags.parquet"
OUT_PATH = "data/processed/near_duplicate_clusters.parquet"
META_PATH = "data/processed/near_duplicate_clusters_meta.json"

MIN_CHAR_LENGTH = 2000
MAX_CHAR_LENGTH = None  # exclusive upper bound; None = no cap
SHINGLE_K = 4
NUM_PERM = 64
JACCARD_THRESHOLD = 0.75
CHUNK_SIZE = 50_000

_WORD_RE = re.compile(r"\w+")


def shingles(text: str, k: int = SHINGLE_K) -> list:
    words = _WORD_RE.findall(text.lower())
    if len(words) < k:
        return [" ".join(words).encode("utf8")]
    return [" ".join(words[i:i + k]).encode("utf8") for i in range(len(words) - k + 1)]


class UnionFind:
    """Dict-based union-find keyed by arbitrary hashable ids (here: comment id strings)."""

    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def candidate_query() -> str:
    bot_join = ""
    if os.path.exists(BOT_FLAGS_PATH):
        bot_join = f"LEFT JOIN '{BOT_FLAGS_PATH}' f ON l.author = f.author"
        bot_where = "AND (f.is_likely_bot IS NULL OR NOT f.is_likely_bot)"
    else:
        bot_where = ""

    max_clause = f"AND l.char_length <= {MAX_CHAR_LENGTH}" if MAX_CHAR_LENGTH is not None else ""

    return f"""
        SELECT l.id, l.author, l.text, l.char_length
        FROM '{LEXICAL_PATH}' l
        {bot_join}
        WHERE l.char_length > {MIN_CHAR_LENGTH}
          {max_clause}
          AND l.author IS NOT NULL
          AND l.author NOT IN ('[deleted]', 'AutoModerator')
          {bot_where}
        -- the base corpus has a small number of duplicate comment ids
        -- (upstream ingestion overlap); keep one row per id defensively
        QUALIFY ROW_NUMBER() OVER (PARTITION BY l.id) = 1
    """


def run(con: duckdb.DuckDBPyConnection) -> None:
    total = con.execute(f"SELECT COUNT(*) FROM ({candidate_query()})").fetchone()[0]
    bound_desc = f"{MIN_CHAR_LENGTH} < char_length <= {MAX_CHAR_LENGTH}" if MAX_CHAR_LENGTH is not None else f"char_length > {MIN_CHAR_LENGTH}"
    print(f"Candidate comments ({bound_desc}): {total:,}")

    lsh = MinHashLSH(threshold=JACCARD_THRESHOLD, num_perm=NUM_PERM)
    uf = UnionFind()
    meta = {}  # comment_id -> (author, char_length)

    result = con.execute(candidate_query())
    t0 = time.time()
    n_processed = 0
    n_edges = 0

    while True:
        chunk = result.fetch_df_chunk(vectors_per_chunk=CHUNK_SIZE // 2048 or 1)
        if chunk.empty:
            break

        shingle_lists = [shingles(t) for t in chunk["text"]]
        minhashes = MinHash.bulk(shingle_lists, num_perm=NUM_PERM)

        for row, m in zip(chunk.itertuples(index=False), minhashes):
            cid = row.id
            meta[cid] = (row.author, int(row.char_length))
            for match in lsh.query(m):
                if match != cid:
                    uf.union(cid, match)
                    n_edges += 1
            lsh.insert(cid, m)

        n_processed += len(chunk)
        elapsed = time.time() - t0
        rate = n_processed / elapsed if elapsed > 0 else 0
        eta_min = (total - n_processed) / rate / 60 if rate > 0 else float("nan")
        print(f"  {n_processed:,}/{total:,} ({rate:.0f} docs/sec, ETA {eta_min:.1f} min, {n_edges:,} edges so far)")

    write_output(uf, meta)


def write_output(uf: UnionFind, meta: dict) -> None:
    clusters: dict = {}
    for cid in meta:
        root = uf.find(cid)
        clusters.setdefault(root, []).append(cid)
    clusters = {root: members for root, members in clusters.items() if len(members) > 1}

    rows = []
    for root, members in clusters.items():
        author_set = {meta[m][0] for m in members}
        for m in members:
            author, char_length = meta[m]
            rows.append({
                "comment_id": m,
                "author": author,
                "char_length": char_length,
                "cluster_id": root,
                "cluster_size": len(members),
                "n_distinct_authors": len(author_set),
            })

    new_df = pd.DataFrame(rows)

    if os.path.exists(OUT_PATH):
        prior_df = pd.read_parquet(OUT_PATH)
        overlap = set(prior_df["comment_id"]) & set(new_df["comment_id"])
        if overlap:
            print(f"WARNING: {len(overlap):,} comment_ids already present in {OUT_PATH} — "
                  f"this run's candidate range overlaps a prior run. Keeping the prior rows.")
            new_df = new_df[~new_df["comment_id"].isin(overlap)]
        out_df = pd.concat([prior_df, new_df], ignore_index=True)
    else:
        out_df = new_df

    out_df.to_parquet(OUT_PATH, index=False)

    # Track the lowest char_length threshold covered across all merged runs,
    # so downstream consumers (the notebook) know the true candidate-pool
    # boundary without needing to hardcode a run's --min-char-length.
    prior_min = None
    if os.path.exists(META_PATH):
        with open(META_PATH) as f:
            prior_min = json.load(f).get("min_char_length_covered")
    covered_min = MIN_CHAR_LENGTH if prior_min is None else min(prior_min, MIN_CHAR_LENGTH)
    with open(META_PATH, "w") as f:
        json.dump({"min_char_length_covered": covered_min}, f)

    n_clusters = len(clusters)
    n_comments = len(rows)
    cross_author = [m for m in clusters.values() if len({meta[i][0] for i in m}) > 1]
    print(f"\nNew clusters found this run:        {n_clusters:,}")
    print(f"New comments clustered this run:    {n_comments:,}")
    print(f"New cross-author clusters:          {len(cross_author):,}")
    print(f"New comments in cross-author clusters: {sum(len(m) for m in cross_author):,}")
    print(f"Total rows in {OUT_PATH} now:        {len(out_df):,}")
    print(f"\nWrote near-duplicate clusters to {OUT_PATH}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-char-length", type=int, default=MIN_CHAR_LENGTH,
                         help="Exclusive lower bound on char_length (default: %(default)s)")
    parser.add_argument("--max-char-length", type=int, default=MAX_CHAR_LENGTH,
                         help="Inclusive upper bound on char_length, to skip a range already "
                              "processed in a prior run (default: no cap)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    MIN_CHAR_LENGTH = args.min_char_length
    MAX_CHAR_LENGTH = args.max_char_length
    con = duckdb.connect()
    run(con)
