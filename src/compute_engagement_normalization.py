"""
compute_engagement_normalization.py

Computes z-score normalized popularity/engagement metrics independently for Reddit
(using the Pure r/conspiracy population as the reference baseline) and ATS (using the
entire ATS comment corpus with recounted/patched star counts as the baseline).

Outputs/Updates:
- Overwrites data/processed/empath_scores_full_mapped.parquet (adds `engagement_z`)
- Overwrites data/processed/ats_comments_final.parquet (adds `star_count` and `engagement_z`)

Verification:
- Confirms Pure Reddit Population upvote z-scores have mean=0, stddev=1.
- Confirms ATS comment star z-scores have mean=0, stddev=1.
- Ensures no NaNs are introduced.
"""

import os
import sys
import shutil
import duckdb
import numpy as np
import pandas as pd

# Paths
STAGED_PATH = 'data/processed/research_corpus_staged_scores_full21m.parquet'
EMPATH_PATH = 'data/processed/empath_scores_full_mapped.parquet'
THREAD_PATH = 'data/processed/thread_quality_metrics.csv'
PRESENCE_PATH = 'data/processed/thread_insider_presence.csv'
BRIGADE_PATH = 'data/processed/comment_brigade_flags.csv'

ATS_PARQUET_PATH = 'data/processed/ats_comments_final.parquet'
STAR_COUNTS_PATH = 'data/processed/ats_star_counts.csv'

def main():
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='4GB'")

    print("Checking prerequisites...")
    for path in [STAGED_PATH, EMPATH_PATH, THREAD_PATH, PRESENCE_PATH, BRIGADE_PATH, ATS_PARQUET_PATH, STAR_COUNTS_PATH]:
        if not os.path.exists(path):
            print(f"❌ Error: Required file {path} not found!")
            sys.exit(1)

    # ==========================================
    # 1. REDDIT ENGAGEMENT NORMALIZATION
    # ==========================================
    print("\n--- Processing Reddit Upvote Normalization ---")
    
    # Calculate pure population statistics dynamically
    print("Dynamically computing mean and stddev for Reddit Pure Population...")
    pure_stats_query = f"""
        WITH pure_comments AS (
            SELECT e.upvotes
            FROM '{STAGED_PATH}' s
            JOIN '{EMPATH_PATH}' e ON s.id = e.id
            JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
            LEFT JOIN '{PRESENCE_PATH}' p ON SUBSTR(e.link_id, 4) = p.post_id
            LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
            WHERE t.elasticity_ratio <= (SELECT quantile(elasticity_ratio, 0.33) FROM '{THREAD_PATH}')
              AND t.is_high_crosspost = 0
              AND p.insider_presence_ratio >= 0.75
              AND COALESCE(b.brigade_upvote_flag, 0) = 0
              AND COALESCE(b.brigade_downvote_flag, 0) = 0
            QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
        )
        SELECT avg(upvotes) as mean_upvotes, stddev_samp(upvotes) as std_upvotes
        FROM pure_comments
    """
    stats = con.execute(pure_stats_query).fetchone()
    reddit_mean, reddit_std = stats[0], stats[1]
    print(f"Reddit Pure Population upvotes: mean = {reddit_mean:.6f}, stddev = {reddit_std:.6f}")

    # Inspect current columns of empath parquet to exclude engagement_z if it already exists
    print("Inspected columns in empath parquet...")
    cols_query = f"DESCRIBE SELECT * FROM '{EMPATH_PATH}' LIMIT 1"
    empath_cols = con.execute(cols_query).df()['column_name'].tolist()
    
    select_cols_sql = "*"
    if 'engagement_z' in empath_cols:
        print("  `engagement_z` column already exists in empath parquet. It will be replaced.")
        select_cols_sql = "* EXCLUDE (engagement_z)"

    temp_empath_path = EMPATH_PATH + '.tmp'
    print(f"Writing updated empath parquet to {temp_empath_path}...")
    
    update_reddit_query = f"""
        COPY (
            SELECT {select_cols_sql}, (upvotes - {reddit_mean}) / {reddit_std} AS engagement_z
            FROM '{EMPATH_PATH}'
        ) TO '{temp_empath_path}' (FORMAT PARQUET)
    """
    con.execute(update_reddit_query)

    print("Replacing old empath parquet with the updated one...")
    shutil.move(temp_empath_path, EMPATH_PATH)
    print("Successfully updated Reddit empath parquet!")

    # ==========================================
    # 2. ATS ENGAGEMENT NORMALIZATION
    # ==========================================
    print("\n--- Processing ATS Star Normalization ---")
    
    # Dynamically compute the mean and stddev over all ATS comments
    print("Dynamically computing mean and stddev for ATS comment star counts...")
    ats_stats_query = f"""
        WITH star_counts AS (
            SELECT 
                COALESCE(s.star_count, 0) as star_count
            FROM '{ATS_PARQUET_PATH}' c
            LEFT JOIN (
                SELECT CAST(post_id AS VARCHAR) as post_id, star_count 
                FROM '{STAR_COUNTS_PATH}'
            ) s ON CAST(c.post_id AS VARCHAR) = s.post_id
        )
        SELECT avg(star_count) as mean_stars, stddev_samp(star_count) as std_stars
        FROM star_counts
    """
    ats_stats = con.execute(ats_stats_query).fetchone()
    ats_mean, ats_std = ats_stats[0], ats_stats[1]
    print(f"ATS Comments star counts: mean = {ats_mean:.6f}, stddev = {ats_std:.6f}")

    # Inspect current columns of ATS parquet to exclude star_count and engagement_z if they exist
    cols_query = f"DESCRIBE SELECT * FROM '{ATS_PARQUET_PATH}' LIMIT 1"
    ats_cols = con.execute(cols_query).df()['column_name'].tolist()
    
    ats_exclude_cols = []
    if 'star_count' in ats_cols:
        print("  `star_count` column already exists in ATS parquet. It will be replaced.")
        ats_exclude_cols.append('star_count')
    if 'engagement_z' in ats_cols:
        print("  `engagement_z` column already exists in ATS parquet. It will be replaced.")
        ats_exclude_cols.append('engagement_z')
    
    ats_select_sql = "c.*"
    if ats_exclude_cols:
        exclude_str = ", ".join(ats_exclude_cols)
        ats_select_sql = f"c.* EXCLUDE ({exclude_str})"

    temp_ats_path = ATS_PARQUET_PATH + '.tmp'
    print(f"Writing updated ATS parquet to {temp_ats_path}...")
    
    update_ats_query = f"""
        COPY (
            SELECT 
                {ats_select_sql},
                COALESCE(s.star_count, 0) as star_count,
                (COALESCE(s.star_count, 0) - {ats_mean}) / {ats_std} AS engagement_z
            FROM '{ATS_PARQUET_PATH}' c
            LEFT JOIN (
                SELECT CAST(post_id AS VARCHAR) as post_id, star_count 
                FROM '{STAR_COUNTS_PATH}'
            ) s ON CAST(c.post_id AS VARCHAR) = s.post_id
        ) TO '{temp_ats_path}' (FORMAT PARQUET)
    """
    con.execute(update_ats_query)

    print("Replacing old ATS parquet with the updated one...")
    shutil.move(temp_ats_path, ATS_PARQUET_PATH)
    print("Successfully updated ATS comments parquet!")

    # ==========================================
    # 3. AUTOMATED VERIFICATION
    # ==========================================
    print("\n--- Running Automated Verifications ---")
    
    # A. Reddit Verifications
    print("Verifying Reddit upvotes z-scores...")
    reddit_verify_query = f"""
        WITH pure_comments AS (
            SELECT e.engagement_z
            FROM '{STAGED_PATH}' s
            JOIN '{EMPATH_PATH}' e ON s.id = e.id
            JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
            LEFT JOIN '{PRESENCE_PATH}' p ON SUBSTR(e.link_id, 4) = p.post_id
            LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
            WHERE t.elasticity_ratio <= (SELECT quantile(elasticity_ratio, 0.33) FROM '{THREAD_PATH}')
              AND t.is_high_crosspost = 0
              AND p.insider_presence_ratio >= 0.75
              AND COALESCE(b.brigade_upvote_flag, 0) = 0
              AND COALESCE(b.brigade_downvote_flag, 0) = 0
            QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
        )
        SELECT 
            avg(engagement_z) as mean_z, 
            stddev_samp(engagement_z) as std_z,
            count(CASE WHEN engagement_z IS NULL THEN 1 END) as null_count
        FROM pure_comments
    """
    rv = con.execute(reddit_verify_query).fetchone()
    print(f"Reddit Pure verification: mean_z = {rv[0]:.8f}, stddev_z = {rv[1]:.8f}, nulls = {rv[2]}")
    
    assert abs(rv[0]) < 1e-5, f"Reddit z-score mean deviation too high: {rv[0]}"
    assert abs(rv[1] - 1.0) < 1e-5, f"Reddit z-score stddev deviation too high: {rv[1]}"
    assert rv[2] == 0, f"Reddit z-score contains nulls in pure population!"

    # Assert no nulls across the whole empath table
    full_null_check = con.execute(f"SELECT count(*) FROM '{EMPATH_PATH}' WHERE engagement_z IS NULL").fetchone()[0]
    print(f"Full empath table null count for engagement_z: {full_null_check}")
    assert full_null_check == 0, f"Full empath table has {full_null_check} null engagement_z scores!"

    # B. ATS Verifications
    print("\nVerifying ATS star counts z-scores...")
    ats_verify_query = f"""
        SELECT 
            avg(engagement_z) as mean_z, 
            stddev_samp(engagement_z) as std_z,
            count(CASE WHEN engagement_z IS NULL THEN 1 END) as null_count,
            count(CASE WHEN star_count IS NULL THEN 1 END) as star_nulls
        FROM '{ATS_PARQUET_PATH}'
    """
    av = con.execute(ats_verify_query).fetchone()
    print(f"ATS verification: mean_z = {av[0]:.8f}, stddev_z = {av[1]:.8f}, nulls = {av[2]}, star_nulls = {av[3]}")
    
    assert abs(av[0]) < 1e-5, f"ATS z-score mean deviation too high: {av[0]}"
    assert abs(av[1] - 1.0) < 1e-5, f"ATS z-score stddev deviation too high: {av[1]}"
    assert av[2] == 0, f"ATS z-score contains nulls!"
    assert av[3] == 0, f"ATS star count contains nulls!"

    # Print summary z-scores for descriptive check
    print("\nDescriptive Check:")
    print("Reddit Pure engagement_z stats:")
    print(con.execute(f"""
        WITH pure_comments AS (
            SELECT e.upvotes, e.engagement_z
            FROM '{STAGED_PATH}' s
            JOIN '{EMPATH_PATH}' e ON s.id = e.id
            JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
            LEFT JOIN '{PRESENCE_PATH}' p ON SUBSTR(e.link_id, 4) = p.post_id
            LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
            WHERE t.elasticity_ratio <= (SELECT quantile(elasticity_ratio, 0.33) FROM '{THREAD_PATH}')
              AND t.is_high_crosspost = 0
              AND p.insider_presence_ratio >= 0.75
              AND COALESCE(b.brigade_upvote_flag, 0) = 0
              AND COALESCE(b.brigade_downvote_flag, 0) = 0
            QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
        )
        SELECT upvotes, engagement_z, count(*) as count
        FROM pure_comments
        GROUP BY upvotes, engagement_z
        ORDER BY upvotes
        LIMIT 5
    """).df())

    print("\nATS engagement_z stats:")
    print(con.execute(f"""
        SELECT star_count, engagement_z, count(*) as count
        FROM '{ATS_PARQUET_PATH}'
        GROUP BY star_count, engagement_z
        ORDER BY star_count
        LIMIT 5
    """).df())

    print("\n✅ All automated verification checks passed successfully!")

if __name__ == '__main__':
    main()
