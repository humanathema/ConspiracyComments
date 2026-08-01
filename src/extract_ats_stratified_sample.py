"""
extract_ats_stratified_sample.py

Draws three statistically matched samples specifically within the 2008-2016
overlap window to run an apples-to-apples reverse topic transfer diagnostic:
1. ATS Train Overlap Sample (N = 100,000) for training BERTopic.
2. ATS Validation Overlap Sample (N = 20,000) representing held-out ATS in-domain data.
3. Reddit Validation Overlap Sample (N = 20,000) representing the out-of-domain transfer target.

Features:
- Restricted strictly to 2008-2016.
- Stratified by length (Short <= 100 vs Long > 100 chars).
- Stratified by engagement (Reddit: upvote tiers; ATS: binary starred).
- Natively proportional-to-volume across years by drawing from a uniform random pool.
- Uses exact, post-duplicate-fix Parquet tables.
- Completely memory-safe for 8GB Macs.
"""
import os
import gc
import time
import numpy as np
import pandas as pd
import duckdb

def main():
    print("=== Step 1: Extracting Stratified ATS and Reddit Overlap Samples (2008-2016) ===")
    t_start = time.time()
    
    con = duckdb.connect()
    
    # ------------------ ATS SAMPLING (100k Train + 20k Val) ------------------
    print("\n--- Part A: Drawing ATS Stratified Overlap Samples ---")
    ats_parquet = 'data/processed/ats_comments_final.parquet'
    
    # We need a pool of comments from 2008-2016.
    # Drawing a 15% sample using DuckDB provides a large pool (~730k raw comments)
    # which ensures abundant comments in all length/engagement/year strata.
    # Note: Use [0-9][0-9][0-9][0-9] instead of {4} to bypass f-string curly brace evaluation.
    print("Fetching a fast 15% sample of 2008-2016 ATS comments...")
    ats_pool_query = f"""
        SELECT post_id, author, raw_timestamp, body, starred, year
        FROM (
            SELECT post_id, author, raw_timestamp, body, starred,
                   try_cast(regexp_extract(raw_timestamp, '([0-9][0-9][0-9][0-9])', 1) as INT) as year
            FROM '{ats_parquet}'
            WHERE body IS NOT NULL
            USING SAMPLE 15 PERCENT
        )
        WHERE year BETWEEN 2008 AND 2016
    """
    df_ats_pool = con.execute(ats_pool_query).df()
    print(f"Loaded {len(df_ats_pool):,} raw ATS comments from 15% pool.")
    
    # Apply clean text filters
    print("Applying ATS text filters...")
    df_ats_pool = df_ats_pool[
        df_ats_pool['body'].notna() &
        (df_ats_pool['body'].str.len() >= 15) &
        (~df_ats_pool['author'].str.lower().str.contains('moderator', na=False)) &
        (~df_ats_pool['author'].str.lower().str.contains('admin', na=False)) &
        (df_ats_pool['body'] != '[deleted]') &
        (df_ats_pool['body'] != '[removed]')
    ].reset_index(drop=True)
    print(f"Pool size after filtering: {len(df_ats_pool):,} clean comments.")
    
    # Assign Strata
    print("Assigning ATS strata (Length & Starred)...")
    df_ats_pool['length_stratum'] = df_ats_pool['body'].apply(lambda x: 'Short (<=100)' if len(x) <= 100 else 'Long (>100)')
    df_ats_pool['starred_stratum'] = df_ats_pool['starred'].apply(lambda x: 'Starred (1)' if x == 1 else 'Unstarred (0)')
    df_ats_pool['stratum_key'] = list(zip(df_ats_pool['length_stratum'], df_ats_pool['starred_stratum']))
    
    # Calculate native ratios within the filtered pool
    strata_counts = df_ats_pool['stratum_key'].value_counts()
    strata_ratios = strata_counts / len(df_ats_pool)
    print("ATS Strata Ratios in Filtered Pool:")
    for k, v in strata_ratios.items():
        print(f"  {k}: {v*100:.4f}%")
        
    # Draw stratified sample to reach exactly 120,000 comments (100k Train + 20k Val)
    total_ats_needed = 120000
    ats_sampled_dfs = []
    for key, ratio in strata_ratios.items():
        stratum_df = df_ats_pool[df_ats_pool['stratum_key'] == key]
        target = int(total_ats_needed * ratio)
        if len(stratum_df) < target:
            print(f"  Warning: stratum {key} only has {len(stratum_df):,} rows, requested {target:,}. Sampling all.")
            ats_sampled_dfs.append(stratum_df)
        else:
            ats_sampled_dfs.append(stratum_df.sample(n=target, random_state=42))
            
    df_ats_sampled = pd.concat(ats_sampled_dfs, ignore_index=True)
    # Shuffle
    df_ats_sampled = df_ats_sampled.sample(frac=1.0, random_state=42).reset_index(drop=True)
    
    # Split into 100k Train and 20k Val
    df_ats_train = df_ats_sampled.iloc[:100000].reset_index(drop=True)
    df_ats_val = df_ats_sampled.iloc[100000:].reset_index(drop=True)
    
    # Save Parquet files
    ats_train_out = 'data/processed/ats_train_overlap_sample.parquet'
    ats_val_out = 'data/processed/ats_val_overlap_sample.parquet'
    df_ats_train.to_parquet(ats_train_out)
    df_ats_val.to_parquet(ats_val_out)
    print(f"Successfully drawn and saved:")
    print(f"  -> ATS Train ({len(df_ats_train):,} rows) to {ats_train_out}")
    print(f"  -> ATS Validation ({len(df_ats_val):,} rows) to {ats_val_out}")
    
    # Clean memory
    del df_ats_pool, df_ats_sampled, df_ats_train, df_ats_val
    gc.collect()
    
    # ------------------ REDDIT SAMPLING (20k Val) ------------------
    print("\n--- Part B: Drawing Reddit Stratified Overlap Validation Sample ---")
    reddit_long = 'data/processed/empath_scores_full_mapped.parquet'
    reddit_short = 'data/processed/conspiracy_comments_short_lte100chars_mapped.parquet'
    
    # Fetch a fast 10% sample of 2008-2016 comments to ensure a rich pool (~400k comments)
    print("Fetching a fast 10% sample of 2008-2016 Reddit comments...")
    reddit_pool_query = f"""
        SELECT id, text, upvotes, char_length, link_id, author, year
        FROM (
            SELECT id, text, upvotes, char_length, link_id, author,
                   year(to_timestamp(created_utc)) as year
            FROM '{reddit_long}'
            WHERE text IS NOT NULL
            USING SAMPLE 10 PERCENT
        )
        WHERE year BETWEEN 2008 AND 2016
        
        UNION ALL
        
        SELECT id, text, upvotes, char_length, link_id, author, year
        FROM (
            SELECT id, text, upvotes, char_length, link_id, author,
                   year(to_timestamp(created_utc)) as year
            FROM '{reddit_short}'
            WHERE text IS NOT NULL
            USING SAMPLE 10 PERCENT
        )
        WHERE year BETWEEN 2008 AND 2016
    """
    df_reddit_pool = con.execute(reddit_pool_query).df()
    print(f"Loaded {len(df_reddit_pool):,} raw Reddit comments from 10% pool.")
    
    # Apply clean text filters (min 15 chars, drop empty, exclude moderators)
    print("Applying Reddit text filters...")
    df_reddit_pool = df_reddit_pool[
        df_reddit_pool['text'].notna() &
        (df_reddit_pool['char_length'] >= 15) &
        (~df_reddit_pool['author'].str.lower().str.contains('moderator', na=False)) &
        (~df_reddit_pool['text'].str.contains('###\\[Meta\\] Sticky Comment|submission statement|Your post has been removed', case=False, na=False)) &
        (df_reddit_pool['text'] != '[deleted]') &
        (df_reddit_pool['text'] != '[removed]')
    ].reset_index(drop=True)
    print(f"Pool size after filtering: {len(df_reddit_pool):,} clean comments.")
    
    # Assign Strata
    print("Assigning Reddit strata (Length & Upvotes)...")
    df_reddit_pool['length_stratum'] = df_reddit_pool['char_length'].apply(lambda x: 'Short (<=100)' if x <= 100 else 'Long (>100)')
    
    def get_upvote_stratum(upvotes):
        if upvotes <= 1:
            return 'Low (<=1)'
        elif upvotes <= 10:
            return 'Medium (2-10)'
        return 'High (>10)'
        
    df_reddit_pool['upvote_stratum'] = df_reddit_pool['upvotes'].apply(get_upvote_stratum)
    df_reddit_pool['stratum_key'] = list(zip(df_reddit_pool['length_stratum'], df_reddit_pool['upvote_stratum']))
    
    # Calculate native ratios within the filtered pool
    r_strata_counts = df_reddit_pool['stratum_key'].value_counts()
    r_strata_ratios = r_strata_counts / len(df_reddit_pool)
    print("Reddit Strata Ratios in Filtered Pool:")
    for k, v in r_strata_ratios.items():
        print(f"  {k}: {v*100:.4f}%")
        
    # Draw stratified sample to reach exactly 20,000 comments
    r_target_total = 20000
    reddit_sampled_dfs = []
    for key, ratio in r_strata_ratios.items():
        stratum_df = df_reddit_pool[df_reddit_pool['stratum_key'] == key]
        target = int(r_target_total * ratio)
        if len(stratum_df) < target:
            print(f"  Warning: stratum {key} only has {len(stratum_df):,} rows, requested {target:,}. Sampling all.")
            reddit_sampled_dfs.append(stratum_df)
        else:
            reddit_sampled_dfs.append(stratum_df.sample(n=target, random_state=42))
            
    df_reddit_sampled = pd.concat(reddit_sampled_dfs, ignore_index=True)
    # Shuffle
    df_reddit_sampled = df_reddit_sampled.sample(frac=1.0, random_state=42).reset_index(drop=True)
    
    # Save Reddit Sample
    reddit_out = 'data/processed/reddit_val_overlap_sample.parquet'
    df_reddit_sampled.to_parquet(reddit_out)
    print(f"Successfully drawn and saved:")
    print(f"  -> Reddit Validation ({len(df_reddit_sampled):,} rows) to {reddit_out}")
    
    print(f"\n=== Stratified Sampling Complete in {time.time()-t_start:.2f} seconds! ===")

if __name__ == '__main__':
    main()
