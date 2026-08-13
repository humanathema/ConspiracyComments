"""build_round9_thread_chains.py

For the round9 escalation candidates still classified "aleatoric" after the
single-parent context test (round9_epistemic_aleatoric_classification.csv),
pull EVERY comment belonging to their submission threads (link_id) in one
scoped DuckDB pass over the raw shards -- not a repeated per-depth-level
scan. This gives enough data to walk each row's full ancestor chain
(parent, grandparent, ... up to the top-level comment) locally in memory,
purely via pandas, with no further corpus scans needed.

Also pulls title/selftext for the relevant submissions (both raw post
files -- r_conspiracy_posts.jsonl and r_conspiracy_posts2.jsonl.gz cover
complementary date ranges, confirmed 2026-08-13).

Output:
  data/processed/round9/round9_thread_comments.parquet (id, parent_id, body
    for every comment in the relevant threads)
  data/processed/round9/round9_thread_posts.parquet (id, title, selftext
    for the relevant submissions)
"""
import glob
import os

import duckdb
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(REPO_ROOT, "data/raw")
ALEATORIC_PATH = os.path.join(REPO_ROOT, "data/processed/round9/round9_aleatoric_rows_for_chainwalk.csv")
OUT_COMMENTS = os.path.join(REPO_ROOT, "data/processed/round9/round9_thread_comments.parquet")
OUT_POSTS = os.path.join(REPO_ROOT, "data/processed/round9/round9_thread_posts.parquet")


def main():
    df = pd.read_csv(ALEATORIC_PATH)
    submission_ids = {
        l[3:] for l in df["link_id"].dropna().unique()
        if isinstance(l, str) and l.startswith("t3_")
    }
    print(f"{len(df):,} aleatoric rows, {len(submission_ids):,} distinct submissions")

    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='3GB'")
    con.execute("PRAGMA threads=4")
    con.execute("SET preserve_insertion_order=false")

    link_ids_full = [f"t3_{s}" for s in submission_ids]
    lookup_df = pd.DataFrame({"lid": link_ids_full})
    con.register("lookup_links", lookup_df)

    shards = sorted(glob.glob(os.path.join(RAW_DIR, "r_conspiracy_comments*.jsonl.gz")))
    shards = [s for s in shards if os.path.getsize(s) > 1024]
    glob_pattern = "[" + ",".join(f"'{s}'" for s in shards) + "]"
    print(f"Scanning {len(shards)} comment shards for full threads...")

    comments = con.execute(f"""
        SELECT c.id, c.parent_id, c.link_id, c.body
        FROM read_ndjson(
            {glob_pattern},
            columns={{'id':'VARCHAR','parent_id':'VARCHAR','link_id':'VARCHAR','body':'VARCHAR'}},
            ignore_errors=true
        ) c
        WHERE c.link_id IN (SELECT lid FROM lookup_links)
    """).fetchdf()
    print(f"Fetched {len(comments):,} comments across {comments['link_id'].nunique():,} threads")
    comments.to_parquet(OUT_COMMENTS, index=False)

    lookup_ids_df = pd.DataFrame({"lookup_id": list(submission_ids)})
    con.register("lookup_ids", lookup_ids_df)
    posts_paths = [
        os.path.join(RAW_DIR, "r_conspiracy_posts.jsonl"),
        os.path.join(RAW_DIR, "r_conspiracy_posts2.jsonl.gz"),
    ]
    paths_literal = "[" + ",".join(f"'{p}'" for p in posts_paths) + "]"
    posts = con.execute(f"""
        SELECT p.id, p.title, p.selftext
        FROM read_ndjson(
            {paths_literal},
            columns={{'id':'VARCHAR','title':'VARCHAR','selftext':'VARCHAR'}},
            ignore_errors=true
        ) p
        WHERE p.id IN (SELECT lookup_id FROM lookup_ids)
    """).fetchdf()
    con.close()
    print(f"Fetched {len(posts):,} / {len(submission_ids):,} submissions")
    posts.to_parquet(OUT_POSTS, index=False)

    print(f"\nSaved: {OUT_COMMENTS}")
    print(f"Saved: {OUT_POSTS}")


if __name__ == "__main__":
    main()
