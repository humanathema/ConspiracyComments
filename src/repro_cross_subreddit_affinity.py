"""Reproducibility script for the cross-subreddit insider-affinity signal
(one of four insider-status dimensions feeding the grand-synthesis
integration -- see ANTIGRAVITY_HANDOFF.md §13).

Extracted and path-corrected from two scratchpad notebooks
(notebooks/scratchpads/Untitled1.ipynb cell 8, Untitled3.ipynb cells 10-15)
which used stale `/Users/nash/Documents/ConspiracyComments/` paths from
before a project relocation. NOT re-run as part of this extraction -- the
corpus hasn't changed since the original run, so the existing output
(`data/processed/author_subreddit_footprints_async.csv`, 293,755 authors x
161,459 subreddits, 7.6M rows) is still current. This script exists so the
computation is reproducible/auditable, not because it needs re-running.

Uses the free, public Arctic Shift Reddit archive API (not a paid/LLM API
-- fine under the no-LLM-calls-without-sign-off constraint, but a ~294K-user
crawl at 5 concurrent requests would still take a long time; don't re-run
without discussing scope first if the corpus ever does change).

Pipeline:
1. build_crawl_queue() -- per-author r/conspiracy comment counts, filtered
   to >=5 (MIN_CONSPIRACY_COMMENTS), the crawl target list.
2. crawl_footprints() -- async Arctic Shift sweep: for each author, what
   other subreddits do they comment in and how often. Resumable (skips
   authors already in the output file).
3. compute_insider_metrics() -- from the footprint data:
   - conspiracy_ratio: conspiracy comments / total Reddit comments (a
     "purity" score -- how much of this author's Reddit activity is IN
     r/conspiracy specifically)
   - affinity_score per related subreddit: total_comments / shared_users
     (comments-per-shared-user, a co-occurrence strength measure)
   - bayesian_affinity: affinity_score shrunk toward the global mean using
     a prior weight (m=50) proportional to shared_users, so a subreddit
     visited by 2 people with huge comment counts doesn't rank above one
     genuinely shared by hundreds -- standard empirical-Bayes smoothing for
     small-sample ratios.
"""
import asyncio
import os
import time
from collections import Counter

import aiohttp
import pandas as pd

DATA_DIR = "data/processed/"
COMMENTS_GLOB = "data/raw/r_conspiracy_comments*.jsonl*"
QUEUE_FILE = DATA_DIR + "author_crawl_queue.csv"
FOOTPRINTS_FILE = DATA_DIR + "author_subreddit_footprints_async.csv"
INSIDER_METRICS_FILE = DATA_DIR + "author_insider_metrics.csv"
RELATED_SUBS_FILE = DATA_DIR + "author_related_subreddits_bayesian.csv"

MIN_CONSPIRACY_COMMENTS = 5
CONCURRENT_REQUESTS = 5
MAX_RETRIES = 3
BAYESIAN_PRIOR_WEIGHT = 50  # "m" -- shared_users this large before affinity_score is trusted at face value


def build_crawl_queue(con):
    """Per-author r/conspiracy comment counts -- the crawl target list."""
    query = f"""
        SELECT author, COUNT(*) as r_conspiracy_comments
        FROM read_json_auto('{COMMENTS_GLOB}', maximum_object_size=50000000, union_by_name=True)
        WHERE author NOT IN ('[deleted]', '[removed]', 'AutoModerator')
        GROUP BY author
    """
    df_queue = con.execute(query).df()
    df_queue.to_csv(QUEUE_FILE, index=False)
    return df_queue


async def fetch_user(session, author, semaphore):
    url = "https://arctic-shift.photon-reddit.com/api/comments/search"
    params = {"author": author, "limit": 100, "fields": "subreddit"}
    headers = {"User-Agent": "AcademicDissertationContextAudit/2.0 (Massey University Async)"}
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(url, params=params, headers=headers, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        subreddits = [item["subreddit"] for item in data.get("data", [])]
                        return author, dict(Counter(subreddits))
                    elif response.status == 429:
                        await asyncio.sleep(5 + (attempt * 5))
                        continue
                    else:
                        return author, None
            except Exception:
                await asyncio.sleep(2)
        return author, None


async def crawl_footprints(authors, chunk_size=50):
    """Resumable async crawl -- skips authors already in FOOTPRINTS_FILE."""
    processed_authors = set()
    if os.path.exists(FOOTPRINTS_FILE):
        processed_authors = set(pd.read_csv(FOOTPRINTS_FILE)["author"].unique())
    else:
        pd.DataFrame(columns=["author", "subreddit", "comment_count"]).to_csv(FOOTPRINTS_FILE, index=False)

    remaining = [a for a in authors if a not in processed_authors]
    print(f"{len(remaining):,} authors remaining (of {len(authors):,} total)")

    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(remaining), chunk_size):
            chunk = remaining[i:i + chunk_size]
            results = await asyncio.gather(*[fetch_user(session, a, semaphore) for a in chunk])
            rows = []
            for author, footprint in results:
                if footprint:
                    for sub, count in footprint.items():
                        rows.append({"author": author, "subreddit": sub, "comment_count": count})
                elif footprint is not None:
                    rows.append({"author": author, "subreddit": "_NO_DATA_", "comment_count": 0})
            if rows:
                pd.DataFrame(rows).to_csv(FOOTPRINTS_FILE, mode="a", header=False, index=False)
            print(f"  processed {i + len(chunk):,}/{len(remaining):,}")


def compute_insider_metrics():
    """From FOOTPRINTS_FILE: per-author purity ratio + Bayesian-weighted
    related-subreddit affinity scores."""
    df = pd.read_csv(FOOTPRINTS_FILE)

    total_comments = df.groupby("author")["comment_count"].sum().reset_index()
    total_comments.rename(columns={"comment_count": "total_reddit_comments"}, inplace=True)
    conspiracy_comments = df[df["subreddit"] == "conspiracy"][["author", "comment_count"]]
    conspiracy_comments.rename(columns={"comment_count": "conspiracy_comments"}, inplace=True)
    insider_df = pd.merge(total_comments, conspiracy_comments, on="author", how="left").fillna(0)
    insider_df["conspiracy_ratio"] = insider_df["conspiracy_comments"] / insider_df["total_reddit_comments"]
    insider_df.to_csv(INSIDER_METRICS_FILE, index=False)

    conspiracy_users = df[df["subreddit"] == "conspiracy"]["author"].unique()
    network_df = df[(df["author"].isin(conspiracy_users)) & (df["subreddit"] != "conspiracy")]
    related_subs = network_df.groupby("subreddit").agg(
        shared_users=("author", "nunique"),
        total_comments=("comment_count", "sum"),
    ).reset_index()
    related_subs["affinity_score"] = related_subs["total_comments"] / related_subs["shared_users"]

    global_mean_affinity = related_subs["affinity_score"].mean()
    m = BAYESIAN_PRIOR_WEIGHT
    related_subs["bayesian_affinity"] = (
        (related_subs["shared_users"] / (related_subs["shared_users"] + m)) * related_subs["affinity_score"]
        + (m / (related_subs["shared_users"] + m)) * global_mean_affinity
    )
    related_subs = related_subs.sort_values("bayesian_affinity", ascending=False)
    related_subs.to_csv(RELATED_SUBS_FILE, index=False)

    return insider_df, related_subs


if __name__ == "__main__":
    print("This script documents an already-completed pipeline for "
          "reproducibility. The corpus hasn't changed since the original "
          "run, so re-running isn't necessary -- see "
          "data/processed/author_subreddit_footprints_async.csv for the "
          "existing output. Only run this file directly if you specifically "
          "need to redo the crawl (e.g. corpus changed, or extending to a "
          "different min-comment threshold).")
