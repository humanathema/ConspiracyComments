"""recover_train_reddit_ids.py

Recovers real Reddit id/parent_id/link_id for the train stance dataset,
which build_stance_classifier_training_data.py drops at consolidation
even for source queues that still have them. Reuses the proven
normalized-45-char-prefix-match methodology from
audit_truncation_multi_source.py (99.7% match rate on a 745-row sample
against local_context.duckdb, per that script's own results, folded into
this project's handoff history) -- applied here at full scale against
the freshly-rebuilt local_context.duckdb (44.1M rows, 2026-08-24).

For each train row: match by normalized text prefix, classify as
exact_complete / truncated / mismatch, keep the id for exact_complete
and truncated matches (both are genuine matches, truncated just means
the training text was pre-truncated relative to the real comment), then
pull parent_id/link_id for every recovered id directly from the same
table.

Input: outputs/reinfer_probs/full_train_fp_pipeline_flags.csv
Output: outputs/reinfer_probs/full_train_reddit_ids_recovered.csv
  (row-aligned with the input, columns: text, target_entity,
  recovered_id, recovered_parent_id, recovered_link_id, match_status)
"""
import html
import re
import unicodedata

import duckdb
import pandas as pd

INPUT_PATH = "outputs/reinfer_probs/full_train_fp_pipeline_flags.csv"
LOCAL_CONTEXT_DB = "local_context.duckdb"
OUT_PATH = "outputs/reinfer_probs/full_train_reddit_ids_recovered.csv"
PREFIX_LEN = 45

WS_RE = re.compile(r"\s+")


def normalize(text):
    if text is None:
        return ""
    t = html.unescape(str(text))
    t = unicodedata.normalize("NFKC", t)
    t = WS_RE.sub(" ", t).strip()
    return t


SQL_NORMALIZE_EXPR = """
trim(regexp_replace(
    replace(replace(replace(replace(replace(text,
        '&amp;', '&'), '&lt;', '<'), '&gt;', '>'), '&quot;', '"'), '&#39;', ''''),
    '\\s+', ' ', 'g'
))
"""


def classify(train_norm, cand_norm):
    if train_norm == cand_norm:
        return "exact_complete"
    if cand_norm.startswith(train_norm) and len(cand_norm) > len(train_norm):
        return "truncated"
    if train_norm.startswith(cand_norm) and len(train_norm) > len(cand_norm):
        return "training_longer_than_source"
    return "mismatch"


def main():
    df = pd.read_csv(INPUT_PATH)
    df = df.reset_index().rename(columns={"index": "row_idx"})
    print(f"Recovering ids for {len(df)} train rows", flush=True)

    df["norm_text"] = df["text"].map(normalize)
    df["prefix45"] = df["norm_text"].str.slice(0, PREFIX_LEN)

    prefixes = df[["row_idx", "prefix45"]].drop_duplicates(subset="prefix45")
    print(f"{len(prefixes)} distinct prefixes to search", flush=True)

    con = duckdb.connect(LOCAL_CONTEXT_DB, read_only=True)
    con.execute("PRAGMA memory_limit='3GB'")
    con.execute("PRAGMA threads=4")
    con.register("train_prefixes", prefixes)

    q = f"""
    WITH src_norm AS (
        SELECT id, {SQL_NORMALIZE_EXPR} AS norm_text
        FROM comments
    ),
    src_prefix AS (
        SELECT id, norm_text, substr(norm_text, 1, {PREFIX_LEN}) AS prefix45
        FROM src_norm
    )
    SELECT t.row_idx, s.id AS cand_id, s.norm_text AS cand_text
    FROM train_prefixes t
    JOIN src_prefix s ON t.prefix45 = s.prefix45
    """
    print("Running prefix join against local_context.duckdb (44.1M rows)...", flush=True)
    cand = con.execute(q).fetchdf()
    con.unregister("train_prefixes")
    print(f"{len(cand)} candidate matches for {cand['row_idx'].nunique()} query prefixes", flush=True)

    norm_lookup = dict(zip(df["row_idx"], df["norm_text"]))
    cand["train_norm"] = cand["row_idx"].map(norm_lookup)
    cand["status"] = cand.apply(lambda r: classify(r["train_norm"], r["cand_text"]), axis=1)
    priority = {"exact_complete": 0, "truncated": 1, "mismatch": 2, "training_longer_than_source": 3}
    cand["prio"] = cand["status"].map(priority)
    cand = cand.sort_values("prio").drop_duplicates("row_idx", keep="first")

    # propagate matches from the deduped-by-prefix set back to all rows sharing that prefix
    prefix_to_result = dict(zip(cand["row_idx"], zip(cand["cand_id"], cand["status"])))
    prefix_of_row = dict(zip(prefixes["row_idx"], prefixes["prefix45"]))
    row_to_prefix_owner = {}
    for _, r in prefixes.iterrows():
        row_to_prefix_owner[r["prefix45"]] = r["row_idx"]

    df["recovered_id"] = None
    df["match_status"] = "no_match"
    for i, row in df.iterrows():
        owner = row_to_prefix_owner.get(row["prefix45"])
        if owner in prefix_to_result:
            cid, status = prefix_to_result[owner]
            if status in ("exact_complete", "truncated"):
                df.at[i, "recovered_id"] = cid
                df.at[i, "match_status"] = status
            else:
                df.at[i, "match_status"] = status

    n_recovered = df["recovered_id"].notna().sum()
    print(f"\nRecovered real Reddit id for {n_recovered}/{len(df)} rows ({n_recovered/len(df):.1%})", flush=True)
    print(df["match_status"].value_counts(), flush=True)

    # pull parent_id/link_id for every recovered id
    ids = df["recovered_id"].dropna().unique().tolist()
    print(f"\nFetching parent_id/link_id for {len(ids)} recovered ids...", flush=True)
    id_df = pd.DataFrame({"id": ids})
    con2 = duckdb.connect(LOCAL_CONTEXT_DB, read_only=True)
    con2.register("ids_needed", id_df)
    parent_lookup = con2.execute("""
        SELECT c.id, c.parent_id, c.link_id
        FROM comments c JOIN ids_needed n ON c.id = n.id
    """).fetchdf()
    con2.close()
    parent_lookup = parent_lookup.drop_duplicates(subset="id")

    df = df.merge(parent_lookup, left_on="recovered_id", right_on="id", how="left", suffixes=("", "_ctx"))
    df = df.rename(columns={"parent_id": "recovered_parent_id", "link_id": "recovered_link_id"})

    out = df[["row_idx", "text", "target_entity", "source_file", "recovered_id",
              "recovered_parent_id", "recovered_link_id", "match_status"]]
    out.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {OUT_PATH}", flush=True)

    n_with_parent = out["recovered_parent_id"].notna().sum()
    print(f"Rows with recovered parent_id (context-ready): {n_with_parent}/{len(out)} ({n_with_parent/len(out):.1%})", flush=True)

    print("\nRecovery rate by source_file:", flush=True)
    print(out.groupby("source_file")["recovered_id"].apply(lambda s: f"{s.notna().sum()}/{len(s)}"), flush=True)


if __name__ == "__main__":
    main()
