import duckdb
import os
import pandas as pd
import time

def main():
    print("--- Step 1: Optimized Stratified Comment Sampling ---")
    t_start = time.time()
    
    # Connect to DuckDB
    con = duckdb.connect()
    
    # Define our source tables
    empath_path = 'data/processed/empath_scores_full.parquet'
    short_path = 'data/processed/conspiracy_comments_short_lte100chars.parquet'
    
    # Total sample sizes needed
    train_size = 100000
    val_size = 20000
    total_size = train_size + val_size
    
    # Stratified ratios in the filtered population:
    # Long, High: 5.59%
    # Long, Low: 26.10%
    # Long, Medium: 23.24%
    # Short, High: 4.14%
    # Short, Low: 22.27%
    # Short, Medium: 18.66%
    strata_ratios = {
        ('Long (>100)', 'High (>10)'): 0.0559,
        ('Long (>100)', 'Low (<=1)'): 0.2610,
        ('Long (>100)', 'Medium (2-10)'): 0.2324,
        ('Short (<=100)', 'High (>10)'): 0.0414,
        ('Short (<=100)', 'Low (<=1)'): 0.2227,
        ('Short (<=100)', 'Medium (2-10)'): 0.1866
    }
    
    # Step 1a: Fast 3% sample using DuckDB's USING SAMPLE clause
    # 3% ensures we have an abundant pool in every single stratum (over 1M rows total)
    print("Fetching a fast 3% random sample of the full corpus...")
    t0 = time.time()
    query = f"""
        SELECT id, text, upvotes, char_length, link_id, author
        FROM '{empath_path}' USING SAMPLE 3 PERCENT
        UNION ALL
        SELECT id, text, upvotes, char_length, link_id, author
        FROM '{short_path}' USING SAMPLE 3 PERCENT
    """
    df_pool = con.execute(query).df()
    print(f"Loaded {len(df_pool):,} sample pool rows in {time.time()-t0:.2f} seconds.")
    
    # Step 1b: Apply text cleaning filters in Pandas (extremely fast)
    print("Applying text cleaning filters...")
    df_pool = df_pool[
        df_pool['text'].notna() &
        (df_pool['char_length'] >= 15) &
        (~df_pool['author'].str.lower().str.contains('moderator', na=False)) &
        (~df_pool['text'].str.contains('###\\[Meta\\] Sticky Comment|submission statement|Your post has been removed', case=False, na=False)) &
        (df_pool['text'] != '[deleted]') &
        (df_pool['text'] != '[removed]')
    ].reset_index(drop=True)
    print(f"Pool size after filtering: {len(df_pool):,} clean comments.")
    
    # Step 1c: Assign Strata
    print("Assigning strata labels...")
    df_pool['length_stratum'] = df_pool['char_length'].apply(lambda x: 'Short (<=100)' if x <= 100 else 'Long (>100)')
    
    def get_upvote_stratum(upvotes):
        if upvotes <= 1:
            return 'Low (<=1)'
        elif upvotes <= 10:
            return 'Medium (2-10)'
        return 'High (>10)'
        
    df_pool['upvote_stratum'] = df_pool['upvotes'].apply(get_upvote_stratum)
    df_pool['stratum_key'] = list(zip(df_pool['length_stratum'], df_pool['upvote_stratum']))
    
    # Step 1d: Draw stratified random samples
    print("Drawing stratified samples...")
    sampled_dfs = []
    
    for (len_s, up_s), ratio in strata_ratios.items():
        key = (len_s, up_s)
        stratum_df = df_pool[df_pool['stratum_key'] == key]
        target = int(total_size * ratio)
        
        if len(stratum_df) < target:
            print(f"Warning: stratum {key} only has {len(stratum_df):,} rows, requested {target:,}. Sampling all available.")
            sampled_dfs.append(stratum_df)
        else:
            sampled_dfs.append(stratum_df.sample(n=target, random_state=42))
            
    df_sampled = pd.concat(sampled_dfs, ignore_index=True)
    print(f"Successfully drawn {len(df_sampled):,} total stratified comments.")
    
    # Shuffle and split into train (100k) and validation (20k)
    df_sampled = df_sampled.sample(frac=1.0, random_state=42).reset_index(drop=True)
    
    df_train = df_sampled.iloc[:train_size].reset_index(drop=True)
    df_val = df_sampled.iloc[train_size:].reset_index(drop=True)
    
    # Clean up columns not needed for training
    cols_to_keep = ['id', 'text', 'upvotes', 'char_length', 'link_id', 'length_stratum', 'upvote_stratum']
    df_train = df_train[cols_to_keep]
    df_val = df_val[cols_to_keep]
    
    # Save Parquet files
    train_out = 'data/processed/train_topic_comments.parquet'
    val_out = 'data/processed/val_topic_comments.parquet'
    
    print(f"\nSaving training set ({len(df_train):,} rows) to {train_out}...")
    df_train.to_parquet(train_out)
    
    print(f"Saving validation set ({len(df_val):,} rows) to {val_out}...")
    df_val.to_parquet(val_out)
    
    print(f"\n--- Stratified Sampling Step Complete in {time.time()-t_start:.2f} seconds! ---")

if __name__ == '__main__':
    main()
