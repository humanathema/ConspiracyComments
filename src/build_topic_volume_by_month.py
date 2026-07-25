"""build_topic_volume_by_month.py

Monthly comment volume per granular topic (assigned_topic/topic_name), across
the full corpus (long comments + short comments, both topic-assigned by
apply_topic_assignments.py). Granular topics are the primary key, not the
6-group super_topic taxonomy -- collapsing to super-topic risks averaging
away real topic-specific effects, the same failure mode already found in the
pure-population has_maverick null (whistleblower/media-personality mix-ratio
canceling out under a pooled coefficient). super_topic is kept as a
secondary column for presentation use only.

Outputs data/processed/topic_volume_by_month.csv:
  month, assigned_topic, topic_name, super_topic,
  n_comments, n_distinct_authors, share_of_month
"""
import os
import duckdb

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    long_path = os.path.join(REPO_ROOT, 'data/processed/empath_scores_full_mapped.parquet')
    short_path = os.path.join(REPO_ROOT, 'data/processed/conspiracy_comments_short_lte100chars_mapped.parquet')
    output_path = os.path.join(REPO_ROOT, 'data/processed/topic_volume_by_month.csv')

    con = duckdb.connect()
    con.execute("SET memory_limit='3GB'; SET threads=3;")

    print("Aggregating monthly topic volume across long + short populations...")
    con.execute(f"""
        CREATE TEMP TABLE combined AS
        SELECT created_utc, author, assigned_topic, topic_name, super_topic
        FROM '{long_path}'
        UNION ALL
        SELECT created_utc, author, assigned_topic, topic_name, super_topic
        FROM '{short_path}'
    """)

    df = con.execute("""
        WITH monthly AS (
            SELECT
                strftime(to_timestamp(created_utc), '%Y-%m') AS month,
                assigned_topic, topic_name, super_topic,
                count(*) AS n_comments,
                count(DISTINCT author) AS n_distinct_authors
            FROM combined
            GROUP BY 1, 2, 3, 4
        ),
        month_totals AS (
            SELECT month, sum(n_comments) AS month_total
            FROM monthly GROUP BY 1
        )
        SELECT m.month, m.assigned_topic, m.topic_name, m.super_topic,
               m.n_comments, m.n_distinct_authors,
               round(m.n_comments::DOUBLE / t.month_total, 6) AS share_of_month
        FROM monthly m
        JOIN month_totals t USING (month)
        ORDER BY m.month, m.n_comments DESC
    """).df()

    df.to_csv(output_path, index=False)
    print(f"Saved {len(df):,} rows ({df['month'].nunique()} months x up to {df['assigned_topic'].nunique()} topics) to {output_path}")


if __name__ == '__main__':
    main()
