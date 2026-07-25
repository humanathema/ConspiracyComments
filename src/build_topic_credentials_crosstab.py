"""build_topic_credentials_crosstab.py

Crosses the credentials-problem finding (does anti-consensus vs
consensus-aligned sourcing lean on a different mix of source types) against
granular topic, to check whether the pattern found in aggregate
(`data/processed/credentials_problem_integration_report.md`) holds uniformly
across topics or is concentrated in specific ones. Granular topic is used
throughout, not super_topic -- collapsing risks averaging away exactly the
kind of topic-specific variation this is checking for.

Uses the existing per-comment `credentials_integration_results.csv` (already
validated, cascade-model stance, chi-square-tested in aggregate) rather than
re-deriving the citation-category taxonomy or stance-combination logic.

category precedence per comment (matches integrate_credentials_problem.py's
own resolution order): credentialed_institutional(4) > individual_named_source(3)
> movement_internal_anonymous(2) > other(1) -- the comment-level view below
takes the max-precedence category per comment, same as the existing report.

Outputs two files:
  data/processed/topic_credentials_crosstab_citation_level.csv
    (every citation event, topic x category)
  data/processed/topic_credentials_crosstab_comment_level.csv
    (one row per comment via max-precedence resolution, topic x category,
     restricted to Anti-Consensus / Consensus-Aligned comment_stance --
     the actual "which side of the issue" comparison -- with a documented
     minimum-N-per-topic floor so thin topics don't get over-read)
"""
import os
import duckdb

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_STANCE_COMMENTS_PER_TOPIC = 30


def main():
    credentials_path = os.path.join(REPO_ROOT, 'data/processed/credentials_integration_results.csv')
    topic_path = os.path.join(REPO_ROOT, 'data/processed/empath_scores_full_mapped.parquet')
    citation_out = os.path.join(REPO_ROOT, 'data/processed/topic_credentials_crosstab_citation_level.csv')
    comment_out = os.path.join(REPO_ROOT, 'data/processed/topic_credentials_crosstab_comment_level.csv')

    con = duckdb.connect()
    con.execute("SET memory_limit='3GB'; SET threads=3;")

    print("Joining credentials-problem citations to topic assignments...")
    con.execute(f"""
        CREATE TEMP TABLE joined AS
        SELECT c.comment_id, c.category, c.comment_stance, c.precedence,
               t.assigned_topic, t.topic_name, t.super_topic
        FROM '{credentials_path}' c
        JOIN '{topic_path}' t ON c.comment_id = t.id
    """)
    n_joined = con.execute("SELECT count(*) FROM joined").fetchone()[0]
    print(f"{n_joined:,} citation events matched to a topic")

    print("Building citation-level crosstab (every citation, all categories)...")
    citation_level = con.execute("""
        SELECT assigned_topic, topic_name, super_topic, category,
               count(*) AS n_citations
        FROM joined
        GROUP BY 1, 2, 3, 4
        ORDER BY assigned_topic, n_citations DESC
    """).df()
    citation_level.to_csv(citation_out, index=False)
    print(f"Saved {len(citation_level):,} rows to {citation_out}")

    print("Building comment-level crosstab (max-precedence category per comment, Anti-Consensus vs Consensus-Aligned only)...")
    comment_level = con.execute(f"""
        WITH resolved AS (
            SELECT comment_id, assigned_topic, topic_name, super_topic, comment_stance, category,
                   row_number() OVER (PARTITION BY comment_id ORDER BY precedence DESC) AS rn
            FROM joined
            WHERE comment_stance IN ('Anti-Consensus', 'Consensus-Aligned')
        ),
        resolved_top AS (
            SELECT * FROM resolved WHERE rn = 1
        ),
        topic_stance_totals AS (
            SELECT assigned_topic, comment_stance, count(*) AS n_stance_comments
            FROM resolved_top GROUP BY 1, 2
        ),
        eligible_topics AS (
            -- require the floor on BOTH stance sides so a topic can't pass with
            -- e.g. 500 anti-consensus comments and 2 consensus-aligned ones
            SELECT assigned_topic
            FROM topic_stance_totals
            GROUP BY assigned_topic
            HAVING min(n_stance_comments) >= {MIN_STANCE_COMMENTS_PER_TOPIC}
               AND count(DISTINCT comment_stance) = 2
        )
        SELECT r.assigned_topic, r.topic_name, r.super_topic, r.comment_stance, r.category,
               count(*) AS n_comments,
               round(count(*)::DOUBLE / t.n_stance_comments, 4) AS share_within_stance
        FROM resolved_top r
        JOIN topic_stance_totals t USING (assigned_topic, comment_stance)
        WHERE r.assigned_topic IN (SELECT assigned_topic FROM eligible_topics)
        GROUP BY 1, 2, 3, 4, 5, t.n_stance_comments
        ORDER BY r.assigned_topic, r.comment_stance, n_comments DESC
    """).df()
    comment_level.to_csv(comment_out, index=False)
    n_topics = comment_level['assigned_topic'].nunique()
    print(f"Saved {len(comment_level):,} rows ({n_topics} topics clear the >= {MIN_STANCE_COMMENTS_PER_TOPIC}-comments-per-stance floor) to {comment_out}")


if __name__ == '__main__':
    main()
