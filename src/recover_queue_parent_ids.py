"""recover_queue_parent_ids.py

Adds id/parent_id/link_id to the two new review queues (built from
stance_classifier_training_data.parquet, which carries no id column --
same "text has no id" situation as everywhere else in this project) by
matching full_text against the local context DB built from the raw
comment shards. Needed for hitl_rater.py's "Load surrounding context"
button, which only renders when row.parent_id is populated.

Matched by exact text, same convention used throughout this project
(training parquet has no id column, text is unique per row in practice).
Rows with no match keep parent_id blank -- the context button simply
won't show for those, same as before, not a regression.

Input: data/hitl/queue_active_learning_requeue_v2.csv,
       data/hitl/queue_escalation_aleatoric_review.csv
Output: same files, rewritten in place with id/parent_id/link_id added
        (id column only overwritten if not already present and useful --
        active_learning_requeue_v2 already has a synthetic al_XXXX id,
        preserved as rater_id; recovered real id goes in a new column).
"""
import duckdb
import pandas as pd

DB_PATH = "data/processed/local_context.duckdb"

FILES = [
    "data/hitl/queue_active_learning_requeue_v2.csv",
    "data/hitl/queue_escalation_aleatoric_review.csv",
]


def main():
    con = duckdb.connect(DB_PATH, read_only=True)

    for path in FILES:
        df = pd.read_csv(path)
        print(f"\n=== {path} ({len(df)} rows) ===", flush=True)

        texts = df["full_text"].fillna("").tolist()
        con.register("queue_texts", pd.DataFrame({"full_text": texts}))
        matches = con.execute("""
            SELECT q.full_text, c.id, c.parent_id, c.link_id
            FROM queue_texts q
            JOIN comments c ON c.text = q.full_text
        """).fetchdf()
        matches = matches.drop_duplicates(subset="full_text", keep="first")
        print(f"  matched {len(matches)} / {len(df)} rows by exact text", flush=True)

        if "id" in df.columns:
            df = df.rename(columns={"id": "rater_id"})
        df = df.merge(matches.rename(columns={"id": "comment_id"}), on="full_text", how="left")
        df["id"] = df["comment_id"]
        df = df.drop(columns=["comment_id"])

        df.to_csv(path, index=False)
        print(f"  saved with id/parent_id/link_id columns added", flush=True)

    con.close()


if __name__ == "__main__":
    main()
