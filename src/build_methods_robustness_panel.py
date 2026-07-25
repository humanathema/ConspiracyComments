"""build_methods_robustness_panel.py

Assembles small, already-computed methods-transparency data for the corpus
explorer's "Methods & robustness" and "Comparison corpora" tabs -- no new
analysis, just structuring existing outputs (HITL_INVENTORY.md, IRR
summary, bot/near-duplicate/brigade diagnostics, insider-presence
threshold sweep, comparison-corpus files) into small CSVs.

Outputs (all small, hand-verified against source):
  data/processed/explorer_hitl_coverage.csv
  data/processed/explorer_data_quality.csv
  data/processed/explorer_comparison_corpora.csv
  data/processed/explorer_core_regression_clustered.csv (reshaped subset of
    refined_regression_results_v2_clustered.csv for the regression browser)
"""
import csv
import duckdb

con = duckdb.connect()
con.execute("PRAGMA memory_limit='4GB'")

# ---------- HITL/IRR coverage (transcribed from handoff/HITL_INVENTORY.md
# and data/hitl/irr_responses/irr_summary.md, both hand-verified source docs
# -- not re-derived here, just structured for display) ----------
hitl_rows = [
    # construct, n_labeled, label_scheme, group, note
    ('stance (hostile/endorsement/other)', 1344, 'hostile / endorsement / neutral / ambiguous / wrong_match', 'A', '3-rater IRR done: Fleiss kappa 0.402 (4-class), 0.484 (3-class collapsed)'),
    ('personal_experience', 100, 'positive / lean_positive / negative / unsure', 'A', 'single-rater only'),
    ('procedural_skepticism', 100, 'positive / lean_positive / negative / unsure', 'A', 'single-rater only'),
    ('maverick_authority', 197, 'positive / lean_positive / negative / unsure', 'A', 'single-rater only'),
    ('hedged_suspicion', 725, 'binary (0/1)', 'A', 'single-rater only'),
    ('appeal_to_authority', 225, 'binary (0/1)', 'A', 'single-rater only; construct itself later failed validation (kappa=-0.018)'),
    ('entity stance quality-checks', 99, 'same as stance', 'A', 'Wikileaks done; Assange/Snowden/Greenwald/Jones-short pending'),
    ('anti_establishment_stance', 0, 'undefined -- no codebook exists', 'B', 'LLM-cascade labels only, zero human ground truth'),
    ('insider_ethos', 0, 'undefined -- no codebook exists', 'B', 'never built as a classifier at all, prompt-only from the Gemini-cascade era'),
    ('reasonableness_performance', 0, 'undefined -- no codebook exists', 'B', 'name/prompt only, never explored'),
    ('source_citation (LLM-cascade version)', 0, 'undefined -- no codebook exists', 'B', 'distinct from the resurrected local TF-IDF classifier, which IS validated (kappa=0.655)'),
]
with open('data/processed/explorer_hitl_coverage.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['construct', 'n_labeled', 'label_scheme', 'group', 'note'])
    w.writerows(hitl_rows)
print(f"Saved {len(hitl_rows)} rows to explorer_hitl_coverage.csv")

# ---------- Data quality diagnostics (aggregate only, no author/comment rows) ----------
bot = con.execute("""
    select count(*) as n_authors, sum(n_comments) as total_comments,
      sum(case when is_likely_bot or is_named_bot then n_comments else 0 end) as bot_comments,
      sum(case when is_likely_bot or is_named_bot then 1 else 0 end) as bot_authors
    from 'data/processed/author_spam_bot_flags.parquet'
""").fetchone()
dup = con.execute("""
    select count(distinct cluster_id) as n_clusters, count(*) as n_comments_in_clusters
    from 'data/processed/near_duplicate_clusters.parquet'
""").fetchone()
brig = con.execute("""
    select count(*) as n_evaluated, sum(brigade_upvote_flag) as n_upvote_flag, sum(brigade_downvote_flag) as n_downvote_flag
    from 'data/processed/comment_brigade_flags.csv'
""").fetchone()

quality_rows = [
    ('bot/spam authors', bot[3], bot[0], round(bot[3]/bot[0]*100, 2), f"{bot[2]:,} of {bot[1]:,} comments ({bot[2]/bot[1]*100:.2f}%) are from flagged authors"),
    ('near-duplicate comments', dup[1], None, None, f"{dup[1]:,} comments across {dup[0]:,} clusters (copypasta / coordinated-text reposts)"),
    ('brigade-flagged comments (evaluated subset)', brig[1] + brig[2], brig[0], None, f"of {brig[0]:,} comments evaluated for brigading, {brig[1]:,} upvote-flagged, {brig[2]:,} downvote-flagged -- this evaluated set's exact sampling scope is undocumented, don't read the flag rate as a full-corpus percentage"),
]
with open('data/processed/explorer_data_quality.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['metric', 'n_flagged', 'n_total', 'pct', 'detail'])
    w.writerows(quality_rows)
print(f"Saved {len(quality_rows)} rows to explorer_data_quality.csv")

# ---------- Comparison corpora ----------
corpora_files = {
    'r/politics': ('data/processed/comparison_politics_scored.parquet', 'used', 'The actual control sample -- temporally-stratified crawl (20 evenly-spaced months), matched scope to the pure r/conspiracy population.'),
    'r/TopMindsOfReddit': ('data/processed/comparison_topmindsofreddit_scored.parquet', 'rejected', 'Rejected 2026-07-15: a mockery/meta-subreddit that quotes and ridicules r/conspiracy, not a neutral control -- comparisons against it are invalid.'),
    'r/AskReddit': ('data/processed/comparison_askreddit_scored.parquet', 'secondary', 'Used for semantic-keyness context comparison; rejected as the primary control (single-day snapshot, not temporally matched) in favor of r/politics.'),
    'r/conspiracy_commons': ('data/processed/comparison_conspiracy_commons_scored.parquet', 'exploratory', 'Secondary/exploratory sister-subreddit sample; not written up as a formal comparison anywhere yet.'),
}
corpora_rows = []
for name, (path, status, reason) in corpora_files.items():
    n = con.execute(f"select count(*) from '{path}'").fetchone()[0]
    dr = con.execute(f"select min(created_utc), max(created_utc) from '{path}'").fetchone()
    corpora_rows.append((name, status, n, dr[0], dr[1], reason))

with open('data/processed/explorer_comparison_corpora.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['corpus', 'status', 'n_comments', 'earliest_utc', 'latest_utc', 'reason'])
    w.writerows(corpora_rows)
print(f"Saved {len(corpora_rows)} rows to explorer_comparison_corpora.csv")

# ---------- Core regression, clustered SEs (reshaped for the regression browser) ----------
con.execute(f"""
COPY (
  SELECT
    'Core regression (clustered SEs)' AS source,
    subreddit AS stratum,
    cov_type AS model_type,
    variable,
    coef,
    pvalue,
    n_obs
  FROM 'data/processed/refined_regression_results_v2_clustered.csv'
) TO 'data/processed/explorer_core_regression_clustered.csv' (FORMAT CSV, HEADER)
""")
n = con.execute("select count(*) from 'data/processed/explorer_core_regression_clustered.csv'").fetchone()[0]
print(f"Saved {n} rows to explorer_core_regression_clustered.csv")

print("=== Done ===")
