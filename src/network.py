import duckdb
import pandas as pd

def calculate_upvote_percentiles(parquet_path: str) -> pd.DataFrame:
    """Calculates upvote percentiles across the full corpus."""
    query = f"""
        SELECT 
            COUNT(*) as total_valid_comments,
            MIN(upvotes) as min_score,
            APPROX_QUANTILE(upvotes, 0.50) as p50_median,
            APPROX_QUANTILE(upvotes, 0.75) as p75,
            APPROX_QUANTILE(upvotes, 0.90) as p90,
            APPROX_QUANTILE(upvotes, 0.95) as p95,
            APPROX_QUANTILE(upvotes, 0.99) as p99,
            MAX(upvotes) as max_score
        FROM '{parquet_path}'
        WHERE text IS NOT NULL 
          AND text != '[deleted]' 
          AND text != '[removed]'
    """
    return duckdb.query(query).df()

def calculate_upvote_counts(parquet_path: str) -> pd.DataFrame:
    """Calculates comment counts remaining at specific upvote cutoffs."""
    query = f"""
        SELECT 
            SUM(CASE WHEN upvotes >= 2 THEN 1 ELSE 0 END) as remaining_gte_2,
            SUM(CASE WHEN upvotes >= 5 THEN 1 ELSE 0 END) as remaining_gte_5,
            SUM(CASE WHEN upvotes >= 10 THEN 1 ELSE 0 END) as remaining_gte_10,
            SUM(CASE WHEN upvotes >= 25 THEN 1 ELSE 0 END) as remaining_gte_25,
            SUM(CASE WHEN upvotes >= 50 THEN 1 ELSE 0 END) as remaining_gte_50,
            SUM(CASE WHEN upvotes >= 100 THEN 1 ELSE 0 END) as remaining_gte_100
        FROM '{parquet_path}'
        WHERE text IS NOT NULL 
          AND text != '[deleted]' 
          AND text != '[removed]'
    """
    return duckdb.query(query).df()

def build_insider_matrix(parquet_path: str) -> pd.DataFrame:
    """Builds the Insider-Only Epistemic Dataset (Author History >= 21)."""
    query = f"""
        WITH author_counts AS (
            SELECT author, COUNT(*) as total_global_comments
            FROM '{parquet_path}'
            WHERE author NOT IN ('[deleted]', '[removed]', 'AutoModerator')
            GROUP BY author
        ),
        verified_insiders AS (
            SELECT m.*
            FROM '{parquet_path}' m
            JOIN author_counts ac ON m.author = ac.author
            WHERE ac.total_global_comments >= 21
              AND m.text IS NOT NULL 
              AND m.text != '[deleted]' 
              AND m.text != '[removed]'
        )
        SELECT 
            CASE 
                WHEN upvotes >= 5 AND upvotes < 50 THEN '1. Insider Trench (5-49 Upvotes)'
                WHEN upvotes BETWEEN 50 AND 100 AND controversiality >= 0.5 THEN '2. Insider Contested High (50-100 Up, Friction >= 0.5)'
                WHEN upvotes < 0 AND controversiality >= 0.5 THEN '3. Insider Organic Negatives (Downvoted, Friction >= 0.5)'
            END AS insider_segment,
            COUNT(*) as total_comments,
            ROUND(AVG(char_length), 1) as avg_length,
            ROUND(AVG(evidence_count), 4) as avg_evidence,
            ROUND(AVG(adversarial_count), 4) as avg_adversarial,
            ROUND(AVG(hedge_count), 4) as avg_hedge,
            ROUND(AVG(certainty_count), 4) as avg_certainty,
            ROUND(AVG(pattern_count), 4) as avg_pattern,
            ROUND(AVG(meta_count), 4) as avg_meta
        FROM verified_insiders
        WHERE 
            (upvotes >= 5 AND upvotes < 50)
            OR (upvotes BETWEEN 50 AND 100 AND controversiality >= 0.5)
            OR (upvotes < 0 AND controversiality >= 0.5)
        GROUP BY insider_segment
        ORDER BY insider_segment ASC
    """
    return duckdb.query(query).df()

def calculate_controversiality_distributions(parquet_path: str) -> pd.DataFrame:
    """Calculates controversiality distributions across structural cohort tiers."""
    query = f"""
        WITH author_counts AS (
            SELECT author, COUNT(*) as total_global_comments
            FROM '{parquet_path}'
            WHERE author NOT IN ('[deleted]', '[removed]', 'AutoModerator')
            GROUP BY author
        ),
        labeled_data AS (
            SELECT 
                m.upvotes,
                m.controversiality,
                CASE 
                    WHEN m.upvotes >= 100 AND ac.total_global_comments = 1 THEN 'Known Upvote Brigade'
                    WHEN m.upvotes <= -6 AND ac.total_global_comments >= 21 THEN 'Known Downvote Suppression'
                    WHEN m.upvotes BETWEEN 5 AND 49 AND ac.total_global_comments >= 21 THEN 'Organic Insider Trench'
                END AS structural_cohort
            FROM '{parquet_path}' m
            JOIN author_counts ac ON m.author = ac.author
        )
        SELECT 
            structural_cohort,
            COUNT(*) as sample_size,
            ROUND(AVG(controversiality), 4) as mean_controversiality,
            ROUND(QUANTILE(controversiality, 0.50), 4) as p50_median,
            ROUND(QUANTILE(controversiality, 0.75), 4) as p75,
            ROUND(QUANTILE(controversiality, 0.90), 4) as p90
        FROM labeled_data
        WHERE structural_cohort IS NOT NULL
        GROUP BY structural_cohort
    """
    return duckdb.query(query).df()

def calculate_baseline_active_users(jsonl_path: str) -> pd.DataFrame:
    """Calculates baseline active users and estimated voting pools from JSONL comments."""
    query = f"""
        WITH valid_comments AS (
            SELECT 
                author,
                date_trunc('month', to_timestamp(created_utc)) as comment_month
            FROM read_json_auto('{jsonl_path}', maximum_object_size=50000000, union_by_name=True)
            WHERE author NOT IN ('[deleted]', '[removed]', 'AutoModerator')
        ),
        author_totals AS (
            SELECT author, COUNT(*) as lifetime_comments
            FROM valid_comments
            GROUP BY author
        ),
        monthly_activity AS (
            SELECT 
                v.comment_month,
                COUNT(DISTINCT v.author) as monthly_unique_authors,
                COUNT(DISTINCT CASE WHEN a.lifetime_comments >= 21 THEN v.author END) as monthly_unique_insiders
            FROM valid_comments v
            JOIN author_totals a ON v.author = a.author
            GROUP BY v.comment_month
        )
        SELECT 
            strftime(comment_month, '%Y-%m') as month,
            monthly_unique_authors as total_authors,
            monthly_unique_insiders as insider_authors,
            ROUND(monthly_unique_insiders / 30.0, 0)::INT as avg_daily_insider_commenters,
            ROUND((monthly_unique_insiders / 30.0) * 10, 0)::INT as estimated_daily_insider_votes
        FROM monthly_activity
        ORDER BY comment_month ASC
    """
    return duckdb.query(query).df()

def analyze_user_activity_percentiles(jsonl_path: str) -> pd.DataFrame:
    """Analyzes the percentile distribution of user activity (comments per author)."""
    query = f"""
        WITH author_counts AS (
            SELECT author, COUNT(*) as total_comments
            FROM read_json_auto('{jsonl_path}', maximum_object_size=50000000, union_by_name=True)
            WHERE author NOT IN ('[deleted]', '[removed]', 'AutoModerator')
            GROUP BY author
        )
        SELECT 
            COUNT(*) as total_unique_authors,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY total_comments) as median_comments,
            percentile_cont(0.75) WITHIN GROUP (ORDER BY total_comments) as p75_comments,
            percentile_cont(0.90) WITHIN GROUP (ORDER BY total_comments) as p90_comments,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY total_comments) as p95_comments,
            percentile_cont(0.99) WITHIN GROUP (ORDER BY total_comments) as p99_comments
        FROM author_counts
    """
    return duckdb.query(query).df()

def calculate_distribution_tiers(jsonl_path: str) -> pd.DataFrame:
    """Calculates activity tiers and the proportion of comments generated by each tier."""
    query = f"""
        WITH author_counts AS (
            SELECT author, COUNT(*) as total_comments
            FROM read_json_auto('{jsonl_path}', maximum_object_size=50000000, union_by_name=True)
            WHERE author NOT IN ('[deleted]', '[removed]', 'AutoModerator')
            GROUP BY author
        )
        SELECT 
            CASE 
                WHEN total_comments = 1 THEN '01: 1 comment (Drive-by)'
                WHEN total_comments BETWEEN 2 AND 5 THEN '02: 2-5 comments (Tourist)'
                WHEN total_comments BETWEEN 6 AND 20 THEN '03: 6-20 comments (Casual)'
                WHEN total_comments BETWEEN 21 AND 50 THEN '04: 21-50 comments (Regular)'
                WHEN total_comments BETWEEN 51 AND 200 THEN '05: 51-200 comments (Active)'
                WHEN total_comments BETWEEN 201 AND 1000 THEN '06: 201-1000 comments (Power User)'
                WHEN total_comments > 1000 THEN '07: 1000+ comments (Super User)'
            END as activity_tier,
            COUNT(*) as number_of_authors,
            SUM(total_comments) as total_comments_generated
        FROM author_counts
        GROUP BY 1
        ORDER BY 1
    """
    df = duckdb.query(query).df()
    df['pct_of_authors'] = (df['number_of_authors'] / df['number_of_authors'].sum() * 100).round(2)
    df['pct_of_total_comments'] = (df['total_comments_generated'] / df['total_comments_generated'].sum() * 100).round(2)
    return df
