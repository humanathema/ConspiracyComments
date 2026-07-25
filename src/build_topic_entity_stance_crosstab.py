"""build_topic_entity_stance_crosstab.py

Crosses entity mentions (maverick/consensus construct, hostile/endorsement/
other predicted stance) against granular topic. A first look at whether
stance polarization toward these entities is topic-concentrated, before
committing to any user-level believer/doubter classifier -- this is the raw
signal layer that construct would eventually be weakly-supervised from, not
the classifier itself.

Uses entity_mentions_cache_2stage_pooled.parquet (99.7% id-match confirmed
against the topic-assigned corpus) -- no new stance scoring, just a join +
aggregation. Granular topic throughout, not super_topic.

Outputs data/processed/topic_entity_stance_crosstab.csv:
  assigned_topic, topic_name, super_topic, construct, predicted_label,
  n_mentions, share_within_construct_topic

with a documented minimum-mention floor per (topic, construct) cell so thin
cells aren't over-read.
"""
import os
import duckdb

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_MENTIONS_PER_CELL = 30


def main():
    entity_path = os.path.join(REPO_ROOT, 'data/processed/entity_mentions_cache_2stage_pooled.parquet')
    topic_path = os.path.join(REPO_ROOT, 'data/processed/empath_scores_full_mapped.parquet')
    output_path = os.path.join(REPO_ROOT, 'data/processed/topic_entity_stance_crosstab.csv')

    con = duckdb.connect()
    con.execute("SET memory_limit='3GB'; SET threads=3;")

    print("Joining entity-stance mentions to topic assignments...")
    con.execute(f"""
        CREATE TEMP TABLE joined AS
        SELECT e.comment_id, e.construct, e.predicted_label,
               t.assigned_topic, t.topic_name, t.super_topic
        FROM '{entity_path}' e
        JOIN '{topic_path}' t ON e.comment_id = t.id
    """)
    n_joined = con.execute("SELECT count(*) FROM joined").fetchone()[0]
    print(f"{n_joined:,} entity mentions matched to a topic")

    df = con.execute(f"""
        WITH cell_totals AS (
            SELECT assigned_topic, construct, count(*) AS n_cell
            FROM joined GROUP BY 1, 2
        ),
        eligible AS (
            SELECT assigned_topic, construct FROM cell_totals WHERE n_cell >= {MIN_MENTIONS_PER_CELL}
        )
        SELECT j.assigned_topic, j.topic_name, j.super_topic, j.construct, j.predicted_label,
               count(*) AS n_mentions,
               round(count(*)::DOUBLE / c.n_cell, 4) AS share_within_construct_topic
        FROM joined j
        JOIN cell_totals c USING (assigned_topic, construct)
        WHERE (j.assigned_topic, j.construct) IN (SELECT assigned_topic, construct FROM eligible)
        GROUP BY 1, 2, 3, 4, 5, c.n_cell
        ORDER BY j.assigned_topic, j.construct, n_mentions DESC
    """).df()
    df.to_csv(output_path, index=False)
    n_topics = df['assigned_topic'].nunique()
    print(f"Saved {len(df):,} rows ({n_topics} topics clear the >= {MIN_MENTIONS_PER_CELL}-mentions-per-cell floor) to {output_path}")


if __name__ == '__main__':
    main()
