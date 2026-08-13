"""build_round9_escalation_context.py

Scoped context pull for the round9 escalation candidates (stage2 margin < 0.45,
data/processed/round9/round9_escalation_candidates.csv), following the
established safe pattern from build_targeted_context_cache.py: a single
streaming DuckDB pass over the raw r_conspiracy_comments*.jsonl.gz shards,
memory-limited, no full corpus index (local_context.duckdb's 44M-row full
index approach is what crashed the disk previously -- do not repeat that).

Both round9 "long" and "short" populations are length-filtered slices of the
same underlying r/conspiracy raw comments, so a single pass over the raw
shards covers parent lookups for both -- no need to pull the short-corpus
parquet from Kaggle.

Output: data/processed/round9/round9_escalation_candidates_with_context.csv
(adds parent_text column; NaN where the parent wasn't found, e.g. parent is
a submission (t3_) rather than a comment, or outside the crawled shards).
"""
import glob
import os

import duckdb
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(REPO_ROOT, "data/raw")
ESC_PATH = os.path.join(REPO_ROOT, "data/processed/round9/round9_escalation_candidates.csv")
POOL_PATH = os.path.join(REPO_ROOT, "data/processed/round9/round9_unlabeled_pool.parquet")
OUT_PATH = os.path.join(REPO_ROOT, "data/processed/round9/round9_escalation_candidates_with_context.csv")


def main():
    esc = pd.read_csv(ESC_PATH)
    pool = pd.read_parquet(POOL_PATH, columns=["id", "parent_id", "link_id"])
    esc = esc.merge(pool, on="id", how="left")
    print(f"Escalation candidates: {len(esc):,}, with parent_id present: {esc['parent_id'].notna().sum():,}")

    parent_comment_ids = {
        p[3:] for p in esc["parent_id"].dropna().unique()
        if isinstance(p, str) and p.startswith("t1_")
    }
    print(f"Distinct parent COMMENT ids to look up (t1_ prefix; t3_ = parent is the submission itself, no lookup needed): {len(parent_comment_ids):,}")

    shards = sorted(glob.glob(os.path.join(RAW_DIR, "r_conspiracy_comments*.jsonl.gz")))
    shards = [s for s in shards if os.path.getsize(s) > 1024]
    print(f"Scanning {len(shards)} raw shards...")
    glob_pattern = "[" + ",".join(f"'{s}'" for s in shards) + "]"

    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='3GB'")
    con.execute("PRAGMA threads=4")
    con.execute("SET preserve_insertion_order=false")

    lookup_df = pd.DataFrame({"lookup_id": list(parent_comment_ids)})
    con.register("lookup_ids", lookup_df)

    parents = con.execute(f"""
        SELECT c.id, c.body
        FROM read_ndjson(
            {glob_pattern},
            columns={{'id':'VARCHAR','parent_id':'VARCHAR','link_id':'VARCHAR','body':'VARCHAR'}},
            ignore_errors=true
        ) c
        WHERE c.id IN (SELECT lookup_id FROM lookup_ids)
    """).fetchdf()
    con.close()
    print(f"Found {len(parents):,} / {len(parent_comment_ids):,} parent comments in raw shards")

    parent_text = dict(zip(parents["id"], parents["body"]))

    def lookup(pid):
        if isinstance(pid, str) and pid.startswith("t1_"):
            return parent_text.get(pid[3:])
        return None  # t3_ (submission) or missing -> no comment-level parent text

    esc["parent_text"] = esc["parent_id"].map(lookup)
    print(f"parent_text populated: {esc['parent_text'].notna().sum():,} / {len(esc):,}")

    esc.to_csv(OUT_PATH, index=False)
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    main()
