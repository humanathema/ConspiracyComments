"""Reproducibility script for the temporal lexical-convergence trajectory
signal (one of four insider-status dimensions feeding the grand-synthesis
integration -- see ANTIGRAVITY_HANDOFF.md §13).

Extracted and path-corrected from notebooks/archive/ConspiracyConcise.ipynb
(cell 2), which used stale `/Users/nash/Documents/ConspiracyComments/`
paths. NOT re-run as part of this extraction -- the corpus hasn't changed
since the original run, so the existing output
(`data/processed/lifecycle_trajectories_local.csv`, 59.7MB) is still
current. This script exists so the computation is reproducible/auditable.

This is the ONLY one of the four insider-scratchpad notebooks that actually
ran to completion and produced a validated finding: "No Country for Old
Members" -- lexical alignment to the community's dominant monthly
vocabulary DROPS as users age into the community (counter to a naive
"insiders converge more over time" hypothesis). See
data/processed/lifecycle_trajectories_local.csv, column `alignment_score`
per (author, month_str).

**Known open question, not resolved here, needs Nash's call**: this script
builds a FRESH per-month vocabulary from a 10% random sample of that
month's comments each time it runs, independent of the ALREADY-EXISTING
216-month `data/processed/monthly_baselines/baseline_YYYY-MM.csv` series
(the project's established "temporal-analysis backbone", restored earlier
this project and used elsewhere e.g. the master notebook's §9.8 single-
month lexical-insider score). It's not obvious whether these two monthly-
vocabulary constructions are meant to be the same thing, meant to be
independent methodological cross-checks, or whether one has superseded the
other. Don't silently merge/prefer one over the other without checking --
flagged as a real judgment call in §13's reserved items.

Pipeline:
1. Requires data/processed/monthly_partitions/ (raw comments partitioned by
   month as Parquet, already built, ~5.6GB) to exist -- confirmed present.
2. Cohort definition: authors with >=12 distinct active months AND >100
   total comments ("legacy users" -- 40,534 in the original run).
3. Per month: build a CountVectorizer vocabulary (max 5000 features, English
   stopwords removed) from a 10%-sampled community text blob for that
   month; vectorize each cohort author's aggregated comments for that
   month; cosine-similarity each author-month vector against the
   community-month vector -> `alignment_score`.
4. Stream results to CSV per month (memory-safe for a 65GB+ source corpus).
"""
import os

import duckdb
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize

PARTITION_DIR = "data/processed/monthly_partitions"
OUTPUT_CSV = "data/processed/lifecycle_trajectories_local.csv"

MIN_ACTIVE_MONTHS = 12
MIN_TOTAL_COMMENTS = 100
MONTHLY_SAMPLE_FRAC = 0.1
VOCAB_MAX_FEATURES = 5000
RANDOM_STATE = 42


def build_cohort(con):
    return con.execute(f"""
        SELECT
            author,
            MIN(month_str) as first_month,
            MAX(month_str) as last_month,
            COUNT(DISTINCT month_str) as active_months,
            COUNT(*) as total_comments
        FROM read_parquet('{PARTITION_DIR}/*/*.parquet')
        WHERE author != '[deleted]'
        GROUP BY author
        HAVING active_months >= {MIN_ACTIVE_MONTHS} AND total_comments > {MIN_TOTAL_COMMENTS}
    """).df()


def compute_monthly_alignment(con, df_lifespan):
    valid_authors = set(df_lifespan["author"])
    vectorizer = CountVectorizer(stop_words="english", max_features=VOCAB_MAX_FEATURES)
    header_written = False

    month_folders = sorted(f for f in os.listdir(PARTITION_DIR) if f.startswith("month_str="))

    for folder in month_folders:
        month = folder.split("=")[1]
        folder_path = os.path.join(PARTITION_DIR, folder)

        df_month = con.execute(
            f"SELECT author, body FROM read_parquet('{folder_path}/*.parquet') "
            f"WHERE body IS NOT NULL AND body != '[deleted]'"
        ).df()
        if df_month.empty:
            continue

        try:
            community_text = " ".join(
                df_month["body"].sample(frac=MONTHLY_SAMPLE_FRAC, random_state=RANDOM_STATE).astype(str)
            )
            vectorizer.fit([community_text])
            comm_vec = normalize(vectorizer.transform([community_text]), norm="l1")

            df_cohort = df_month[df_month["author"].isin(valid_authors)]
            if df_cohort.empty:
                continue

            user_texts = df_cohort.groupby("author")["body"].apply(
                lambda x: " ".join(x.astype(str))
            ).reset_index()
            user_vecs = normalize(vectorizer.transform(user_texts["body"]), norm="l1")
            user_texts["alignment_score"] = cosine_similarity(user_vecs, comm_vec).flatten()
            user_texts["month_str"] = month

            batch_out = user_texts[["author", "month_str", "alignment_score"]].merge(df_lifespan, on="author")
            batch_out["current_date"] = pd.to_datetime(batch_out["month_str"])
            batch_out["start_date"] = pd.to_datetime(batch_out["first_month"])
            batch_out["months_since_start"] = (
                (batch_out["current_date"].dt.year - batch_out["start_date"].dt.year) * 12
                + (batch_out["current_date"].dt.month - batch_out["start_date"].dt.month)
            )

            cols = ["author", "month_str", "months_since_start", "alignment_score", "total_comments"]
            mode, header = ("w", True) if not header_written else ("a", False)
            batch_out[cols].to_csv(OUTPUT_CSV, mode=mode, index=False, header=header)
            header_written = True
            print(f"  {month}: scored {len(batch_out)} cohort users")
        except Exception as e:
            print(f"  skipped {month}: {e}")


if __name__ == "__main__":
    print("This script documents an already-completed pipeline for "
          "reproducibility. The corpus hasn't changed since the original "
          "run, so re-running isn't necessary -- see "
          "data/processed/lifecycle_trajectories_local.csv for the "
          "existing output. Only run this file directly if the corpus "
          "changes or the cohort definition needs revisiting.")
