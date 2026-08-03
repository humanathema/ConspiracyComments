"""select_random_expansion_sample.py

Nash's direction 2026-08-02: the population-level boundary-proportion
estimate (boundary_proportion_estimate.py kernel, 12.55% of the wider
population is genuinely boundary-confidence at margin<0.12) implies a
population-representative sample needs ~5,000/0.1255 ~= 40,000 rows for
the existing boundary batch to sit at its natural proportion. Rather
than supplementing the existing 5k with more targeted rows (risks
double-counting -- some of a fresh random batch would land in the
boundary zone by chance anyway), this draws a FRESH random 40k sample
directly. No classifier inference needed (unlike boundary_confidence_selection.py)
since this isn't targeting uncertainty -- pure random draw, so it can
run entirely locally (entity_mentions_cache_2stage_pooled.csv and the
raw comment archive are both present on this machine) instead of
needing a Kaggle GPU kernel.

Output: data/processed/random_expansion_candidates.csv
  (comment_id, entity_key, text, margin=NaN) -- same column shape
  score_boundary_candidates_vertex.py expects, margin unused for scoring.
"""
import duckdb
import pandas as pd

N_SAMPLE = 40000
CACHE_PATH = "data/processed/entity_mentions_cache_2stage_pooled.csv"
RAW_GLOB = "data/raw/r_conspiracy_comments*.jsonl*"
TRAINING_PATH = "data/processed/stance_classifier_training_data.parquet"
OUT_PATH = "data/processed/random_expansion_candidates.csv"


def main():
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='5GB'")
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA enable_progress_bar=false")

    print(f"Sampling {N_SAMPLE:,} random (comment_id, entity_key) pairs "
          f"(excluding merged_% aggregates)...", flush=True)
    sample = con.execute(f"""
        SELECT DISTINCT comment_id, entity_key
        FROM read_csv_auto('{CACHE_PATH}')
        WHERE entity_key NOT LIKE 'merged_%'
        USING SAMPLE {N_SAMPLE} ROWS
    """).df()
    print(f"  {len(sample):,} candidate pairs sampled", flush=True)

    print("Joining to real text from the raw archive...", flush=True)
    con.register("sample_ids", sample)
    joined = con.execute(f"""
        SELECT s.comment_id, s.entity_key, r.body AS text
        FROM sample_ids s
        JOIN read_json_auto('{RAW_GLOB}', maximum_object_size=50000000, union_by_name=True) r
          ON r.id = s.comment_id
        WHERE r.body IS NOT NULL AND r.body != '' AND r.body != '[deleted]' AND r.body != '[removed]'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY s.comment_id, s.entity_key ORDER BY r.created_utc DESC) = 1
    """).df()
    print(f"  {len(joined):,} rows with real text (post-dedup, deleted/removed excluded)", flush=True)

    print("Excluding rows already in the training set...", flush=True)
    training = pd.read_parquet(TRAINING_PATH, columns=["text"])
    already_labeled = set(training["text"])
    joined = joined[~joined["text"].isin(already_labeled)].reset_index(drop=True)
    print(f"  {len(joined):,} genuinely new rows", flush=True)

    joined["margin"] = float("nan")  # not meaningful for a random sample, kept for schema compatibility
    joined.to_csv(OUT_PATH, index=False)
    print(f"\nSaved to {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
