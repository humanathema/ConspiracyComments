"""build_large_post_sample.py

Scaling up post-level semantic clustering, Nash's direction 2026-08-02
(late): the 200-thread pilot's post_similarity layer worked (7.4% pair
coverage, coherent Moon Landing/COVID/WikiLeaks clusters), and the k=25
bump recovered real signal that k=10 was discarding (a culture-war
theme with only 6 known examples in the pilot -- not enough density for
HLC to consolidate them past a few pairwise edges). A much larger post
pool should give thin themes like that real density to work with.

N_SAMPLE=20,000, matching the scale already established and budgeted in
compare_embedding_models_for_topics.py's actual comparison run, not the
full 1.83M-post population (would need ~22GB just for embeddings at
3072-dim float32, plus real vector-index infrastructure for k-NN at that
scale -- a different, much bigger project). Random sample from
r_conspiracy_posts_for_context.parquet, excluding placeholder/deleted
titles (31,682/1,831,271 junk).

Output: data/processed/large_post_sample.parquet (id, title, selftext, combined_text)
"""
import pandas as pd

N_SAMPLE = 20000
SEED = 42
PLACEHOLDER_TITLES = {"[deleted by user]", "[deleted]", "[removed]"}


def main():
    df = pd.read_parquet("data/processed/r_conspiracy_posts_for_context.parquet")
    junk = df["title"].isin(PLACEHOLDER_TITLES) | df["title"].isna()
    df = df[~junk]
    print(f"{len(df):,} usable posts after excluding {junk.sum():,} placeholder/deleted titles", flush=True)

    sample = df.sample(n=N_SAMPLE, random_state=SEED).reset_index(drop=True)
    sample["combined_text"] = sample["title"].fillna("") + "\n" + sample["selftext"].fillna("")

    sample.to_parquet("data/processed/large_post_sample.parquet", index=False)
    print(f"Sampled {len(sample):,} posts, saved to data/processed/large_post_sample.parquet", flush=True)


if __name__ == "__main__":
    main()
