"""build_new_territory_panels.py

Assembles previously-unsurfaced-but-finished analytical work for the corpus
explorer's next round of tabs: semantic keyness, lexical turnover over
time, thread-level (post-predicts-comment-style) analysis, plus reshaping
the Grand Synthesis regression grid and Trump-era/classical split into the
regression browser's existing long format.

No new analysis -- everything here already exists on disk. Just
structuring + (where noted) filtering to a bounded top-N for embedding.

Outputs:
  data/processed/explorer_semantic_keyness_top.csv
  data/processed/explorer_lexical_turnover.csv
  data/processed/explorer_thread_by_domain.csv
  data/processed/explorer_synthesis_regression_long.csv
  data/processed/explorer_trump_vs_classical.csv
"""
import csv
import duckdb

con = duckdb.connect()
con.execute("PRAGMA memory_limit='4GB'")

# ---------- Semantic keyness: top 30 per (comparison, subreddit) group ----------
con.execute("""
COPY (
  WITH ranked AS (
    SELECT word, comparison, subreddit, freq_c1, freq_c2, log_likelihood,
      ROW_NUMBER() OVER (PARTITION BY comparison, subreddit ORDER BY log_likelihood DESC) AS rn
    FROM read_csv_auto('data/processed/refined_semantic_keyness_results_v2.csv')
  )
  SELECT word, comparison, subreddit, freq_c1, freq_c2, log_likelihood
  FROM ranked WHERE rn <= 30
  ORDER BY comparison, subreddit, log_likelihood DESC
) TO 'data/processed/explorer_semantic_keyness_top.csv' (FORMAT CSV, HEADER)
""")
n = con.execute("select count(*) from 'data/processed/explorer_semantic_keyness_top.csv'").fetchone()[0]
print(f"Saved {n} rows to explorer_semantic_keyness_top.csv")

# ---------- Lexical turnover over time ----------
con.execute("""
COPY (
  SELECT month, overlap_with_previous, new_words_count, top_new_words
  FROM read_csv_auto('data/processed/lexical_turnover.csv')
  ORDER BY month
) TO 'data/processed/explorer_lexical_turnover.csv' (FORMAT CSV, HEADER)
""")
n = con.execute("select count(*) from 'data/processed/explorer_lexical_turnover.csv'").fetchone()[0]
print(f"Saved {n} rows to explorer_lexical_turnover.csv")

# ---------- Thread-level: does the post predict comment-section epistemic style? ----------
# Aggregated by domain (top 60 by thread count) -- not raw 888,846 rows.
con.execute("""
COPY (
  WITH ranked AS (
    SELECT
      CASE WHEN domain IS NULL OR domain = '' THEN '(self post)' ELSE domain END AS domain,
      count(*) AS n_threads,
      avg(post_score) AS avg_post_score,
      avg(total_comments) AS avg_total_comments,
      avg(avg_comment_upvotes) AS avg_comment_upvotes,
      avg(avg_controversiality) AS avg_controversiality,
      avg(avg_evidence_score) AS avg_evidence_score,
      avg(avg_rhetoric_score) AS avg_rhetoric_score,
      avg(avg_certainty_score) AS avg_certainty_score,
      avg(avg_authority_score) AS avg_authority_score,
      avg(avg_hedge_score) AS avg_hedge_score
    FROM 'data/processed/master_thread_synthesis.parquet'
    GROUP BY 1
  )
  SELECT * FROM ranked
  WHERE n_threads >= 50
  ORDER BY n_threads DESC
  LIMIT 60
) TO 'data/processed/explorer_thread_by_domain.csv' (FORMAT CSV, HEADER)
""")
n = con.execute("select count(*) from 'data/processed/explorer_thread_by_domain.csv'").fetchone()[0]
print(f"Saved {n} rows to explorer_thread_by_domain.csv")

# ---------- Grand Synthesis grid: melt wide -> long, matching regression browser schema ----------
wide = con.execute("SELECT * FROM read_csv_auto('data/processed/synthesis_regression_results_corrected.csv')").fetchdf()
variables = ['pe_prob', 'ps_prob', 'hs_prob', 'link_mainstream_reliable', 'link_mixed_or_low_reliability',
             'link_aggregator_or_platform', 'link_unmatched_link', 'has_maverick', 'has_canonical_expert', 'has_consensus_expert']
long_rows = []
for _, row in wide.iterrows():
    stratum = f"elasticity={row['elasticity_strata']}, insider_threshold={row['insider_threshold']}"
    for v in variables:
        coef_col, pval_col = f"{v}_coef", f"{v}_pvalue"
        if coef_col in row and pval_col in row and row[coef_col] == row[coef_col]:  # not NaN
            long_rows.append(('Grand Synthesis (elasticity x insider grid)', stratum, row['model_name'], v, row[coef_col], row[pval_col], row['n_obs']))

with open('data/processed/explorer_synthesis_regression_long.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['source', 'stratum', 'model_type', 'variable', 'coef', 'pvalue', 'n_obs'])
    w.writerows(long_rows)
print(f"Saved {len(long_rows)} rows to explorer_synthesis_regression_long.csv")

# ---------- Trump-era vs classical split: relabel to match regression browser schema ----------
con.execute("""
COPY (
  SELECT
    'Trump-era vs classical split' AS source,
    stratum,
    model_type,
    variable,
    coef,
    pvalue,
    n_obs
  FROM read_csv_auto('data/processed/trump_vs_classical_regression_results.csv')
) TO 'data/processed/explorer_trump_vs_classical.csv' (FORMAT CSV, HEADER)
""")
n = con.execute("select count(*) from 'data/processed/explorer_trump_vs_classical.csv'").fetchone()[0]
print(f"Saved {n} rows to explorer_trump_vs_classical.csv")

print("=== Done ===")
