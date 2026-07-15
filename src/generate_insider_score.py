"""Generate the composite continuous insider_score for all authors in the corpus.

Combines four available dimensions:
1. Lifetime r/conspiracy comments (volume, log-transformed)
2. Recent activity purity (conspiracy_ratio)
3. Snapshot lexical convergence similarity (lexical_insider_score)
4. Temporal lexical convergence trajectory (mean_alignment_score)

Computes standardized Z-scores for each feature across the population where it is
observed, then averages the available Z-scores per user to produce a robust,
continuous `insider_score` covering all 293k crawled authors.

Output: data/processed/author_insider_metrics.csv
"""
import os
import numpy as np
import pandas as pd

FOOTPRINTS_PATH = "data/processed/author_subreddit_footprints_async.csv"
USERS_LIVE_PATH = "data/processed/df_users_live.csv"
LIFECYCLE_PATH = "data/processed/lifecycle_trajectories_local.csv"
OUT_PATH = "data/processed/author_insider_metrics.csv"


def main():
    print("=== Generating Composite Insider Score ===")

    # 1. Load footprint data
    if not os.path.exists(FOOTPRINTS_PATH):
        raise FileNotFoundError(f"Missing footprints database at {FOOTPRINTS_PATH}")

    print(f"Loading footprints from {FOOTPRINTS_PATH}...")
    df_foot = pd.read_csv(FOOTPRINTS_PATH)
    
    print("Computing purity and volume from footprints...")
    total_comments = df_foot.groupby("author")["comment_count"].sum().reset_index()
    total_comments.rename(columns={"comment_count": "total_reddit_comments"}, inplace=True)
    
    conspiracy_comments = df_foot[df_foot["subreddit"] == "conspiracy"][["author", "comment_count"]]
    conspiracy_comments.rename(columns={"comment_count": "conspiracy_comments"}, inplace=True)
    
    insider_df = pd.merge(total_comments, conspiracy_comments, on="author", how="left").fillna(0)
    insider_df["conspiracy_ratio"] = insider_df["conspiracy_comments"] / insider_df["total_reddit_comments"]
    insider_df["log_conspiracy_comments"] = np.log1p(insider_df["conspiracy_comments"])
    print(f"Footprints processed for {len(insider_df):,} authors.")

    # 2. Load User Live snapshot lexical scores
    df_user_live = None
    if os.path.exists(USERS_LIVE_PATH):
        print(f"Loading user live snapshot lexical scores from {USERS_LIVE_PATH}...")
        df_user_live = pd.read_csv(USERS_LIVE_PATH)
        df_user_live = df_user_live[["author", "lexical_insider_score"]].dropna()
        print(f"Loaded snapshot scores for {len(df_user_live):,} authors.")
    else:
        print(f"Warning: {USERS_LIVE_PATH} not found. Snapshot lexical scores will be omitted.")

    # 3. Load Trajectory lifecycle lexical scores
    df_traj_summary = None
    if os.path.exists(LIFECYCLE_PATH):
        print(f"Loading trajectory lexical scores from {LIFECYCLE_PATH}...")
        df_traj = pd.read_csv(LIFECYCLE_PATH)
        df_traj_summary = df_traj.groupby("author").agg(
            mean_alignment_score=("alignment_score", "mean")
        ).reset_index().dropna()
        print(f"Loaded trajectory scores for {len(df_traj_summary):,} authors.")
    else:
        print(f"Warning: {LIFECYCLE_PATH} not found. Trajectory lexical scores will be omitted.")

    # 4. Standardize individual features where they are observed
    # This prevents the missingness of lexical scores from biasing the Z-scores
    print("\nStandardizing features...")
    
    insider_df["z_log_conspiracy_comments"] = (
        insider_df["log_conspiracy_comments"] - insider_df["log_conspiracy_comments"].mean()
    ) / insider_df["log_conspiracy_comments"].std()
    
    insider_df["z_conspiracy_ratio"] = (
        insider_df["conspiracy_ratio"] - insider_df["conspiracy_ratio"].mean()
    ) / insider_df["conspiracy_ratio"].std()

    merged = insider_df

    if df_user_live is not None:
        mean_snap = df_user_live["lexical_insider_score"].mean()
        std_snap = df_user_live["lexical_insider_score"].std()
        df_user_live["z_lexical_insider_score"] = (df_user_live["lexical_insider_score"] - mean_snap) / std_snap
        merged = pd.merge(merged, df_user_live, on="author", how="left")

    if df_traj_summary is not None:
        mean_traj = df_traj_summary["mean_alignment_score"].mean()
        std_traj = df_traj_summary["mean_alignment_score"].std()
        df_traj_summary["z_mean_alignment_score"] = (df_traj_summary["mean_alignment_score"] - mean_traj) / std_traj
        merged = pd.merge(merged, df_traj_summary, on="author", how="left")

    # 5. Compute the composite insider score
    # We take the mean of the Z-scores that are present for each row
    z_cols = ["z_log_conspiracy_comments", "z_conspiracy_ratio"]
    if df_user_live is not None:
        z_cols.append("z_lexical_insider_score")
    if df_traj_summary is not None:
        z_cols.append("z_mean_alignment_score")

    print(f"Computing composite insider score using fields: {z_cols}")
    merged["insider_score"] = merged[z_cols].mean(axis=1)

    # 6. Save final file
    out_cols = [
        "author", 
        "conspiracy_comments", 
        "conspiracy_ratio",
        "z_log_conspiracy_comments",
        "z_conspiracy_ratio"
    ]
    if df_user_live is not None:
        out_cols.extend(["lexical_insider_score", "z_lexical_insider_score"])
    if df_traj_summary is not None:
        out_cols.extend(["mean_alignment_score", "z_mean_alignment_score"])
        
    out_cols.append("insider_score")

    print(f"Saving final dataset with {len(merged):,} rows to {OUT_PATH}...")
    merged[out_cols].to_csv(OUT_PATH, index=False)
    
    # 7. Print summary statistics
    print("\n=== Composite Score Summary Stats ===")
    print(merged["insider_score"].describe())
    print("\nCorrelation matrix of scores for users who have all metrics:")
    full_mask = merged[z_cols].notna().all(axis=1)
    if full_mask.sum() > 0:
        print(merged[full_mask][z_cols + ["insider_score"]].corr())
    else:
        print("No users have all metrics populated.")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
