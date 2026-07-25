"""build_subreddit_overlaps.py

Aggregates the 7.6M rows in author_subreddit_footprints_async.csv down
into a cross-subreddit association and co-membership lift table.

This computes a robust association profile for r/conspiracy authors relative
to a control group of 125,747 non-conspiracy authors. To eliminate small-subreddit
bias (where tiny niche subreddits float to the top of standard lift calculations due
to small sample noise), this script implements two robust metrics:

1. Chi-Square Statistic (chi2): Measures the statistical significance and magnitude
   of co-occurrence between r/conspiracy and subreddit S. This rewards subreddits
   with substantial user volume and a strong, consistent positive association.
2. Heavy Smoothed Lift (lift_heavy): Applies a Laplace smoothing factor of +200 pseudo-users
   to both the numerator and denominator, which heavily penalizes tiny subreddits and
   ranks the highly popular, adjacent peer subreddits (like r/conspiracy_commons) at the top.

Saves the result to data/processed/conspiracy_author_overlaps.csv.
"""
import os
import pandas as pd
import numpy as np

# Define relative paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOOTPRINTS_PATH = os.path.join(BASE_DIR, "data", "processed", "author_subreddit_footprints_async.csv")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "processed", "conspiracy_author_overlaps.csv")

def main():
    if not os.path.exists(FOOTPRINTS_PATH):
        print(f"Error: Footprints file not found at {FOOTPRINTS_PATH}")
        return

    print("Loading author footprints (7.6M rows)...")
    df = pd.read_csv(FOOTPRINTS_PATH)
    
    # Identify unique authors
    all_authors = set(df["author"].dropna().unique())
    con_authors = set(df[df["subreddit"] == "conspiracy"]["author"].dropna().unique())
    ctrl_authors = all_authors - con_authors
    
    n_con = len(con_authors)
    n_ctrl = len(ctrl_authors)
    
    print(f"Total unique authors: {len(all_authors):,}")
    print(f"  r/conspiracy authors (Active): {n_con:,}")
    print(f"  Control group authors (Non-conspiracy): {n_ctrl:,}")

    # Exclude conspiracy itself to check overlaps
    df_non_con = df[df["subreddit"] != "conspiracy"]
    
    print("Computing unique user overlaps per subreddit...")
    # Count unique authors per subreddit for conspiracy and control
    sub_con = df_non_con[df_non_con["author"].isin(con_authors)].groupby("subreddit")["author"].nunique().reset_index()
    sub_con.rename(columns={"author": "count_con"}, inplace=True)
    
    sub_ctrl = df_non_con[df_non_con["author"].isin(ctrl_authors)].groupby("subreddit")["author"].nunique().reset_index()
    sub_ctrl.rename(columns={"author": "count_ctrl"}, inplace=True)
    
    # Merge and fill missing with 0
    merged = pd.merge(sub_con, sub_ctrl, on="subreddit", how="outer").fillna(0)
    merged["count_con"] = merged["count_con"].astype(int)
    merged["count_ctrl"] = merged["count_ctrl"].astype(int)
    merged["total_authors"] = merged["count_con"] + merged["count_ctrl"]
    
    # Calculate raw probabilities
    merged["p_con"] = merged["count_con"] / n_con
    merged["p_ctrl"] = merged["count_ctrl"] / n_ctrl
    
    # 1. Chi-Square Association Statistic
    def get_chi2(row):
        a = row["count_con"]
        b = n_con - a
        c = row["count_ctrl"]
        d = n_ctrl - c
        
        total = n_con + n_ctrl
        row_sub = a + c
        
        e_a = (n_con * row_sub) / total
        e_c = (n_ctrl * row_sub) / total
        
        if e_a == 0 or e_c == 0:
            return 0.0
            
        chi2 = ((a - e_a)**2 / e_a) + ((c - e_c)**2 / e_c)
        # We only care about positive associations (where conspiracy authors are overrepresented)
        if a / n_con < c / n_ctrl:
            chi2 = -chi2
        return chi2
        
    print("Calculating Chi-Square and Heavy Smoothed Lift metrics...")
    merged["chi2"] = merged.apply(get_chi2, axis=1)
    
    # 2. Heavy Smoothed Lift (Laplace smoothing with alpha=200 users)
    smoothed_p_con = (merged["count_con"] + 200) / (n_con + 400)
    smoothed_p_ctrl = (merged["count_ctrl"] + 200) / (n_ctrl + 400)
    merged["lift_heavy"] = smoothed_p_con / smoothed_p_ctrl
    
    # Sort by Chi-Square to find the most statistically significant and robust overlaps
    top_by_chi2 = merged.sort_values("chi2", ascending=False)
    
    print("\n--- Top 20 Subreddits by Chi-Square (Robust Association) ---")
    cols_to_print = ["count_con", "count_ctrl", "total_authors", "p_con", "p_ctrl", "chi2", "lift_heavy"]
    print(top_by_chi2[cols_to_print].head(20).to_string(index=True))
    
    # Specific defaults of interest for context
    print("\n--- Mainstream Default Reference Subreddits ---")
    defaults = ["AskReddit", "politics", "news", "worldnews"]
    for sub in defaults:
        if sub in merged["subreddit"].values:
            row = merged[merged["subreddit"] == sub].iloc[0]
            print(f"{sub}:")
            print(f"  Conspiracy: {row['count_con']:,} ({row['p_con']:.2%}) | Control: {row['count_ctrl']:,} ({row['p_ctrl']:.2%})")
            print(f"  Chi-Square: {row['chi2']:.2f} | Heavy Smoothed Lift: {row['lift_heavy']:.2f}x")
            
    # Save output CSV
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    merged.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSuccessfully saved detailed overlaps to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
