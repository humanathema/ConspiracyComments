"""
build_topic_stance_queue.py

Builds a HITL tagging queue for TOPIC-level stance (for / against / neither /
wrong_topic) against the full-corpus BERTopic assignments, seeded by the
existing entity-stance classifier's predictions wherever a comment's entity
mention overlaps its assigned topic.

This is a DIFFERENT construct from the existing entity-stance work: entity
stance asks "is this comment hostile or endorsing toward Fauci/Jones/etc.",
this asks "is this comment for or against the topic itself" (e.g. the
comment's stance toward the *claim* a topic like "chemtrails" or "5G/vaccine"
represents). Do not conflate the two when writing up results.

Guardrails followed (per ANTIGRAVITY_HANDOFF.md / CLAUDE.md):
  - No paid LLM/API calls. Seeding reuses the already-trained local
    TF-IDF+LogisticRegression stance classifier's cached per-comment
    predictions -- no fresh model call of any kind.
  - Reads from the FULL UNFILTERED r/conspiracy population (16.7M rows),
    per explicit scope choice. Fetches `text` only for the small sampled
    subset, never for the full 16.7M-row population (see the repeated
    8GB-RAM OOM pattern already documented -- this script follows the same
    fix: fetch/keep text only for what's actually being written out).
  - Checks count(*) vs count(DISTINCT id) before AND after every join
    (this project has hit silent join-fanout bugs three times already).
  - Even-N-per-topic sampling, NOT weighted by topic size -- rare topics
    get the same N as dominant ones. Topics that come up short are
    reported, not silently under-filled.
  - Queue-BUILDING only. No labels are assigned here -- `label` ships
    blank. This is scaffolding, same status as the other
    task_*_quality_check_queue.md files: not wired into any regression
    until reviewed and rated.
  - Never overwrites an existing data/hitl/queue_*.csv with real ratings
    in it without backing it up first.
"""

import os
import sys
import shutil
import re
from datetime import datetime

import duckdb
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from utils.file_paths import Paths
from utils.concurrency_utils import atomic_write_dataframe

N_PER_TOPIC = 15  # even sample size per topic -- adjust as needed
OUTPUT_PATH = "data/hitl/queue_topic_stance.csv"

# Confirmed paths against the actual repo structure:
# - SHORT_COMMENTS_PATH and LONG_COMMENTS_PATH: map full-corpus comments to topic assignments
# - SEED_ENTITY_STANCE_PATH: maps comments to predicted entity stance
SHORT_COMMENTS_PATH = "data/processed/conspiracy_comments_short_lte100chars_mapped.parquet"
LONG_COMMENTS_PATH = "data/processed/empath_scores_full_mapped.parquet"
SEED_ENTITY_STANCE_PATH = "data/processed/entity_mentions_cache_2stage_pooled.parquet"


def backup_if_exists(path):
    if os.path.exists(path):
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        backup = f"{path}.bak.{stamp}"
        shutil.copy2(path, backup)
        print(f"Existing queue found -- backed up to {backup}")


def check_duplicate_keys(con, query, key="id", label=""):
    total, distinct = con.execute(
        f"SELECT count(*), count(DISTINCT {key}) FROM ({query})"
    ).fetchone()
    if total != distinct:
        raise RuntimeError(
            f"[{label}] duplicate {key}s: {total} rows vs {distinct} distinct "
            f"-- fix the join-fanout bug before continuing (guardrail #5)."
        )
    print(f"[{label}] OK -- {total} rows, all distinct {key}s.")


def main():
    con = duckdb.connect()

    # Define robust sub-queries that deduplicate on ID/comment_id at the database layer.
    # To prevent OOM errors, we optimize the query by performing a simple, ultra-fast UNION ALL 
    # of the disjoint long and short comments datasets, grouping only the short comments that have duplicates.
    topic_assignments_query = f"""
        SELECT id, any_value(assigned_topic) as assigned_topic, any_value(topic_name) as topic_name
        FROM read_parquet('{SHORT_COMMENTS_PATH}')
        GROUP BY id
        UNION ALL
        SELECT id, assigned_topic, topic_name
        FROM read_parquet('{LONG_COMMENTS_PATH}')
    """

    entity_predictions_query = f"""
        SELECT comment_id AS id, entity_key AS entity, predicted_label AS stance_label, greatest(p_hostile, p_endorsement, p_other) AS stance_confidence
        FROM read_parquet('{SEED_ENTITY_STANCE_PATH}')
        WHERE is_list_dump = 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY comment_id ORDER BY greatest(p_hostile, p_endorsement, p_other) DESC) = 1
    """

    # 1. Sanity-check both input files for duplicate keys BEFORE joining.
    check_duplicate_keys(
        con, f"SELECT id FROM ({topic_assignments_query})",
        label="topic_assignments",
    )
    check_duplicate_keys(
        con, f"SELECT id FROM ({entity_predictions_query})",
        label="entity_stance_predictions",
    )

    # 2. LEFT JOIN topic assignments to entity-stance predictions on id.
    #    Most comments won't have an entity-stance prediction at all --
    #    those get an empty seed, not a dropped row (expected, given the
    #    97.8%-no-entity-match finding).
    joined_query = f"""
        SELECT
            t.id,
            t.assigned_topic     AS topic_id,
            t.topic_name         AS topic_label,
            e.entity,
            e.stance_label      AS seed_stance,       -- hostile / endorsement / other
            e.stance_confidence AS seed_confidence
        FROM ({topic_assignments_query}) t
        LEFT JOIN ({entity_predictions_query}) e
          ON t.id = e.id
    """
    check_duplicate_keys(con, joined_query, label="post-join")

    # 3. Even N-per-topic sample. Within each topic, seeded rows are
    #    preferred over unseeded ones (more useful to review/correct a
    #    seed than to blind-label from scratch).
    sample_query = f"""
        WITH joined AS ({joined_query}),
        ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY topic_id
                    ORDER BY (seed_stance IS NOT NULL) DESC, random()
                ) AS rn
            FROM joined
        )
        SELECT * FROM ranked WHERE rn <= {N_PER_TOPIC}
    """
    sample = con.execute(sample_query).df()

    # Flag topics that came up short so they're visible, not silently
    # under-filled.
    counts = sample.groupby("topic_id").size()
    short_topics = counts[counts < N_PER_TOPIC]
    if len(short_topics):
        print(f"NOTE: {len(short_topics)} topics have fewer than "
              f"{N_PER_TOPIC} candidates:")
        print(short_topics)

    # 4. Fetch text ONLY for this small sampled subset -- never for the
    #    full 16.7M-row population.
    ids = tuple(sample["id"].tolist())
    text_query = f"""
        SELECT id, text FROM (
            SELECT id, text FROM read_parquet('{SHORT_COMMENTS_PATH}')
            UNION ALL
            SELECT id, text FROM read_parquet('{LONG_COMMENTS_PATH}')
        )
        WHERE id IN {ids}
    """
    text_df = con.execute(text_query).df()
    check_duplicate_keys(
        con, text_query,
        label="text-fetch",
    )

    out = sample.merge(text_df, on="id", how="left")

    # 5. Apply Stage-1 Quote-stripping + List/Link-dump filter before shipping.
    #    Citation-dump comments with no evaluative content are filtered out.
    QUOTE_LINE_RE = re.compile(r'(?m)^[ \t]*(?:>|&gt;)[ \t]*.*$')
    URL_RE = re.compile(r'https?://\S+')

    initial_len = len(out)

    def strip_quotes(t):
        return QUOTE_LINE_RE.sub('', str(t)).strip()

    out['cleaned_text'] = out['text'].apply(strip_quotes)

    def is_valid_comment(row):
        cleaned = row['cleaned_text']
        if not cleaned:
            return False  # Empty after quote-stripping
        
        # Check if the comment text contains 2+ URLs
        urls = URL_RE.findall(cleaned)
        if len(urls) >= 2:
            return False
            
        return True

    out = out[out.apply(is_valid_comment, axis=1)].copy()
    out['text'] = out['cleaned_text']
    out = out.drop(columns=['cleaned_text'])

    print(f"Filtered out {initial_len - len(out)} citation-dump / quote-only comments.")

    if "rn" in out.columns:
        out = out.drop(columns=["rn"])

    out["label"] = ""  # for / against / neither / wrong_topic -- blank for rating
    out["notes"] = ""

    # Ensure output folder exists
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    backup_if_exists(OUTPUT_PATH)
    atomic_write_dataframe(out, OUTPUT_PATH, index=False)
    print(
        f"Wrote {len(out)} rows across {out['topic_id'].nunique()} topics "
        f"to {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
