"""add_round9_escalation_post_fallback.py

Second pass over round9_escalation_candidates_with_context.csv (output of
build_round9_escalation_context.py): for rows where parent_text is still
missing (parent_id is the submission itself, t3_, or a comment not found
in the crawled shards), fall back to the submission's title + selftext.

Scoped DuckDB pass over data/raw/r_conspiracy_posts.jsonl (the main posts
file, 5.4GB uncompressed) -- filtered to only the link_ids actually needed,
same memory-safe pattern as the comment-context pull.
"""
import os

import duckdb
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_PATHS = [
    os.path.join(REPO_ROOT, "data/raw/r_conspiracy_posts.jsonl"),
    os.path.join(REPO_ROOT, "data/raw/r_conspiracy_posts2.jsonl.gz"),
]
IN_PATH = os.path.join(REPO_ROOT, "data/processed/round9/round9_escalation_candidates_with_context.csv")
OUT_PATH = IN_PATH  # overwrite in place, adding post_title/post_selftext/context_source columns


def main():
    df = pd.read_csv(IN_PATH)
    missing = df[df["parent_text"].isna()]
    print(f"Rows missing parent_text: {len(missing):,} / {len(df):,}")

    link_submission_ids = {
        l[3:] for l in missing["link_id"].dropna().unique()
        if isinstance(l, str) and l.startswith("t3_")
    }
    print(f"Distinct submission ids to look up: {len(link_submission_ids):,}")

    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='3GB'")
    con.execute("PRAGMA threads=4")
    con.execute("SET preserve_insertion_order=false")

    lookup_df = pd.DataFrame({"lookup_id": list(link_submission_ids)})
    con.register("lookup_ids", lookup_df)

    paths_literal = "[" + ",".join(f"'{p}'" for p in POSTS_PATHS) + "]"
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
    print(f"Found {len(posts):,} / {len(link_submission_ids):,} submissions")

    title_lookup = dict(zip(posts["id"], posts["title"]))
    selftext_lookup = dict(zip(posts["id"], posts["selftext"]))

    def get_post_id(link_id):
        if isinstance(link_id, str) and link_id.startswith("t3_"):
            return link_id[3:]
        return None

    df["post_title"] = df["link_id"].map(get_post_id).map(title_lookup)
    df["post_selftext"] = df["link_id"].map(get_post_id).map(selftext_lookup)

    def context_source(row):
        if pd.notna(row["parent_text"]):
            return "parent_comment"
        if pd.notna(row["post_title"]):
            return "post_title_selftext"
        return "none"

    df["context_source"] = df.apply(context_source, axis=1)
    print(df["context_source"].value_counts())

    df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    main()
