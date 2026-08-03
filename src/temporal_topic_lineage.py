"""temporal_topic_lineage.py

Embeddings-native analogue of Structural Topic Modeling (STM, Roberts/
Stewart/Tingley) -- Nash's direction 2026-08-02. STM is a real,
established technique from political science/computational social
science, but it's fundamentally a bag-of-words generative model (an
LDA extension); this ports its two core mechanisms into embedding
space instead of word-distribution space:

1. PREVALENCE (how much of each topic is "in play" over time) --
   processed chronologically, no separate mechanism needed: it falls
   directly out of the incremental join-or-spawn assignment log below.
2. CONTENT SHIFT (a topic's character can drift over its lifetime,
   same identity, evolving substance) -- each topic's centroid is an
   exponentially-weighted moving average, nudged by every new member
   that joins, rather than a fixed point computed once.

Mechanism: process comments in chronological order (real created_utc,
not a random sample). For each comment, compare its embedding to all
currently-active topic centroids. If the best match clears
JOIN_THRESHOLD, it joins that topic (nudging the centroid via EWMA).
Otherwise it spawns a NEW topic, explicitly linked as a child of
whichever existing topic it was nearest to at birth (even though not
close enough to join it) -- this is the genealogy piece, a DAG of
topic lineage over time, not just a static partition.

Topics that receive no new members for DORMANCY_WINDOW get marked
dormant (excluded from future matching, but not deleted -- their
history stays in the output).

Scoped to a small pilot first, per the established pattern tonight:
the 200-thread pilot's ~90k comments, using the already-computed
Gemini embeddings and real timestamps, NOT the full 44M-comment corpus.

Output: data/processed/graph_pilot_top200_depth/temporal_topics.csv
  (comment_id, topic_id, created_utc, action) -- action in {joined, spawned}
        data/processed/graph_pilot_top200_depth/temporal_topic_lineage.csv
  (topic_id, parent_topic_id, born_at, first_comment_id) -- the genealogy DAG
"""
import numpy as np
import pandas as pd

PILOT_DIR = "data/processed/graph_pilot_top200_depth"
JOIN_THRESHOLD = 0.72  # cosine similarity to join an existing topic -- a
# judgment call, not derived; sits inside the percolation transition zone
# found earlier (0.70-0.75), deliberately on the stricter side since a topic
# here persists indefinitely rather than being a one-shot graph edge
EWMA_ALPHA = 0.15  # how much each new member nudges its topic's centroid --
# low value: topics drift slowly, retain long memory of earlier members
DORMANCY_SECONDS = 60 * 60 * 24 * 90  # 90 days with no new member -> dormant


def main():
    comments = pd.read_parquet(f"{PILOT_DIR}/comments.parquet")
    emb = np.load(f"{PILOT_DIR}/comment_embeddings_gemini.npy")
    comments = comments.reset_index(drop=True)
    order = comments["created_utc"].argsort().to_numpy()

    print(f"Processing {len(comments):,} comments in chronological order "
          f"({pd.to_datetime(comments['created_utc'].min(), unit='s').date()} "
          f"to {pd.to_datetime(comments['created_utc'].max(), unit='s').date()})...", flush=True)

    topic_centroid = {}  # topic_id -> embedding vector (EWMA)
    topic_last_seen = {}  # topic_id -> created_utc of most recent member
    topic_size = {}
    lineage_rows = []
    assignment_rows = []
    next_topic_id = 0

    for step, idx in enumerate(order):
        row = comments.iloc[idx]
        t = row["created_utc"]
        vec = emb[idx]

        # drop dormant topics from active matching (kept in history, not matched against)
        active = [tid for tid, last in topic_last_seen.items() if t - last <= DORMANCY_SECONDS]

        best_tid, best_sim = None, -1.0
        if active:
            centroids = np.array([topic_centroid[tid] for tid in active])
            sims = centroids @ vec / (np.linalg.norm(centroids, axis=1) * np.linalg.norm(vec) + 1e-9)
            best_i = np.argmax(sims)
            best_tid, best_sim = active[best_i], float(sims[best_i])

        if best_tid is not None and best_sim >= JOIN_THRESHOLD:
            # join: EWMA-update the centroid, this topic's content drifts toward this member
            topic_centroid[best_tid] = (1 - EWMA_ALPHA) * topic_centroid[best_tid] + EWMA_ALPHA * vec
            topic_last_seen[best_tid] = t
            topic_size[best_tid] += 1
            action = "joined"
            tid = best_tid
        else:
            # spawn: new topic, linked as a child of the nearest existing one (even if not close enough to join)
            tid = next_topic_id
            next_topic_id += 1
            topic_centroid[tid] = vec.copy()
            topic_last_seen[tid] = t
            topic_size[tid] = 1
            lineage_rows.append({
                "topic_id": tid, "parent_topic_id": best_tid, "parent_sim_at_birth": best_sim,
                "born_at": t, "first_comment_id": row["id"],
            })
            action = "spawned"

        assignment_rows.append({"comment_id": row["id"], "topic_id": tid, "created_utc": t, "action": action})

        if (step + 1) % 20000 == 0:
            n_active = sum(1 for last in topic_last_seen.values() if t - last <= DORMANCY_SECONDS)
            print(f"  {step+1:,}/{len(order):,} processed, {next_topic_id:,} topics ever spawned, "
                  f"{n_active:,} currently active", flush=True)

    assign_df = pd.DataFrame(assignment_rows)
    lineage_df = pd.DataFrame(lineage_rows)
    assign_df.to_csv(f"{PILOT_DIR}/temporal_topics.csv", index=False)
    lineage_df.to_csv(f"{PILOT_DIR}/temporal_topic_lineage.csv", index=False)

    n_joined = (assign_df["action"] == "joined").sum()
    n_spawned = (assign_df["action"] == "spawned").sum()
    n_rooted = lineage_df["parent_topic_id"].isna().sum()
    n_with_parent = len(lineage_df) - n_rooted
    print(f"\n{next_topic_id:,} topics spawned total, {n_joined:,} comments joined an existing topic, "
          f"{n_spawned:,} spawned a new one", flush=True)
    print(f"{n_with_parent:,}/{len(lineage_df):,} spawned topics have a real parent link "
          f"(genuine lineage, not a root); {n_rooted:,} are roots (no prior topic was close enough to link to)", flush=True)

    sizes = pd.Series(topic_size).sort_values(ascending=False)
    print(f"\nLargest topics by final size:\n{sizes.head(15)}", flush=True)


if __name__ == "__main__":
    main()
