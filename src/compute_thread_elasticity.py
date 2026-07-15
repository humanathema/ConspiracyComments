"""Compute thread elasticity (upvotes-per-comment ratio) and cross-post/
brigading flags for all posts.

Calculates the post-level ratio `score / num_comments` from raw posts.

**Fix 2026-07-14**: the original version only carried `is_crossposted` from
`cross_post_audit_results.csv`, which is an Arctic-Shift-API-verified audit
covering only ~1,000 sampled threads out of the full 17,057-post universe --
absence of a flag there means "never audited", not "confirmed not viral".
Added `num_crossposts` (Reddit's own post metadata field, fully populated
for all 17,057 posts) as the primary, complete virality signal --
`is_high_crosspost = num_crossposts >= 1`. Kept `is_crossposted` as a
secondary, higher-confidence confirmation where the audit exists, but it
should not be relied on alone as an exclusion filter given its coverage gap.

Also added a comment-level brigading-risk flag, reusing the exact
definition already established and used in
`ConspiracyMaster_Refactored.ipynb` cell 76 ("structural_cohort" query) --
not a new threshold invented here:
  - `brigade_upvote_flag`: comment has >=100 upvotes AND its author has
    exactly 1 total lifetime r/conspiracy comment (i.e. a one-off account
    somehow received viral-tier approval -- statistically unusual for an
    organic community vote, consistent with external/brigaded traffic).
  - `brigade_downvote_flag`: comment has <=-6 upvotes AND its author has
    >=21 total lifetime comments (a known regular getting suppressed --
    could be genuine controversy OR organized downvoting; flagged as
    "known downvote suppression" in the original notebook, kept as a
    symmetric signal here, not asserted as proof of brigading either way).
Requires per-author total comment counts -- computed here from the same
raw comments glob rather than joining author_insider_metrics.csv, since
insider_metrics' `conspiracy_comments` comes from the cross-subreddit
crawl's footprint data (a DIFFERENT count, filtered to the crawl's own
>=5-comment threshold) -- using that would double up on a different
counting method rather than replicate the notebook's original definition.

Output: data/processed/thread_quality_metrics.csv (post-level)
        data/processed/comment_brigade_flags.csv (comment-level)
"""
import os
import pandas as pd
import duckdb

RAW_POSTS = "data/raw/r_conspiracy_posts.jsonl"  # full archive recovered 2026-07-15 (1.83M posts, was r_conspiracy_posts2.jsonl.gz's 17,057-post partial file)
RAW_COMMENTS = "data/raw/r_conspiracy_comments*.jsonl*"
CROSSPOST_AUDIT = "data/processed/cross_post_audit_results.csv"
OUT_PATH = "data/processed/thread_quality_metrics.csv"
BRIGADE_FLAGS_PATH = "data/processed/comment_brigade_flags.csv"


def main():
    print("=== Computing Thread Elasticity and Quality Metrics ===")
    
    if not os.path.exists(RAW_POSTS):
        raise FileNotFoundError(f"Raw posts file not found at {RAW_POSTS}")
        
    con = duckdb.connect()
    
    # 1. Query raw posts to get id, score, num_comments, and num_crossposts
    print(f"Reading raw posts from {RAW_POSTS}...")
    query = f"""
        SELECT
            id as post_id,
            score as post_score,
            num_comments,
            num_crossposts,
            created_utc,
            subreddit
        FROM read_json_auto('{RAW_POSTS}', maximum_object_size=50000000, union_by_name=True)
        WHERE id IS NOT NULL
    """
    df_posts = con.execute(query).df()
    print(f"Loaded {len(df_posts):,} posts.")

    # 1b. Complete virality flag (num_crossposts is populated for ALL posts,
    # unlike the sample-limited audit below)
    df_posts["is_high_crosspost"] = (df_posts["num_crossposts"].fillna(0) >= 1).astype(int)
    print(f"Flagged {df_posts['is_high_crosspost'].sum():,}/{len(df_posts):,} posts "
          f"with num_crossposts>=1 (complete coverage, not sample-limited).")
    
    # 2. Compute elasticity ratio (score / num_comments)
    # Avoid division by zero: if num_comments is 0, elasticity_ratio is post_score
    print("Calculating elasticity ratio...")
    df_posts["elasticity_ratio"] = df_posts.apply(
        lambda r: float(r["post_score"]) / float(r["num_comments"]) if r["num_comments"] > 0 else float(r["post_score"]),
        axis=1
    )
    
    # 3. Load crosspost audit to identify external links
    df_posts["is_crossposted"] = 0
    if os.path.exists(CROSSPOST_AUDIT):
        print(f"Loading crosspost audit results from {CROSSPOST_AUDIT}...")
        df_cp = pd.read_csv(CROSSPOST_AUDIT)
        crossposted_ids = set(df_cp["source_post_id"].dropna().astype(str).unique())
        df_posts["is_crossposted"] = df_posts["post_id"].astype(str).isin(crossposted_ids).astype(int)
        print(f"Flagged {df_posts['is_crossposted'].sum():,} posts as crossposted.")
    else:
        print(f"Warning: {CROSSPOST_AUDIT} not found. Skipping crosspost flags.")
        
    # 4. Save mapping to disk
    print(f"Saving thread quality metrics to {OUT_PATH}...")
    df_posts.to_csv(OUT_PATH, index=False)

    # 5. Print summary statistics
    print("\n=== Elasticity Ratio Summary Stats ===")
    print(df_posts["elasticity_ratio"].describe())

    # 6. Comment-level brigading flags (reusing the exact definition from
    # ConspiracyMaster_Refactored.ipynb cell 76, not a new threshold)
    compute_brigade_flags(con)

    print("\nDone!")


def compute_brigade_flags(con):
    print("\n=== Computing comment-level brigading flags (cell-76 definition) ===")
    query = f"""
        WITH author_counts AS (
            SELECT author, COUNT(*) as total_global_comments
            FROM read_json_auto('{RAW_COMMENTS}', maximum_object_size=50000000, union_by_name=True)
            WHERE author NOT IN ('[deleted]', '[removed]', 'AutoModerator')
            GROUP BY author
        )
        SELECT
            m.id as comment_id,
            m.author,
            m.score,
            ac.total_global_comments,
            CASE WHEN m.score >= 100 AND ac.total_global_comments = 1 THEN 1 ELSE 0 END as brigade_upvote_flag,
            CASE WHEN m.score <= -6 AND ac.total_global_comments >= 21 THEN 1 ELSE 0 END as brigade_downvote_flag
        FROM read_json_auto('{RAW_COMMENTS}', maximum_object_size=50000000, union_by_name=True) m
        JOIN author_counts ac ON m.author = ac.author
        WHERE m.score >= 100 OR m.score <= -6
    """
    df_brigade = con.execute(query).df()
    df_brigade.to_csv(BRIGADE_FLAGS_PATH, index=False)
    print(f"Saved {len(df_brigade):,} flagged rows to {BRIGADE_FLAGS_PATH} "
          f"({df_brigade['brigade_upvote_flag'].sum():,} upvote-brigade, "
          f"{df_brigade['brigade_downvote_flag'].sum():,} downvote-suppression)")


if __name__ == "__main__":
    main()
