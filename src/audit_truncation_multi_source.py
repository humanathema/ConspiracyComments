"""
Multi-source truncation audit for the 946 human-labeled "other" rows Nash is
reviewing (data/processed/stance_classifier_training_data_round10_neutral_al.parquet).

Fixes two flaws in the earlier single-source (local_context.duckdb only), exact-60-char
prefix audit:
  1. Exact-match blind spot: normalizes whitespace + HTML entities on both sides before
     prefix comparison, using a 45-char *normalized* prefix instead of a raw 60-char one,
     so minor formatting differences (extra space, &amp; vs &, etc.) no longer produce a
     false "no match".
  2. The 14% no-match gap: falls back from local_context.duckdb to
     empath_scores_full_mapped.parquet, then conspiracy_comments_short_lte100chars_mapped.parquet
     (both on the thumb drive, full-corpus coverage, ~21M / ~18.6M rows) for anything not
     found in local_context.

For every training row, classifies as: exact_complete, truncated (source text is longer
and training text is a real prefix of it), mismatch (same normalized prefix but text
diverges further in), or no_match (not found in any of the three sources).
"""
import html
import re
import unicodedata

import duckdb
import pandas as pd

TRAINING_PATH = "data/processed/stance_classifier_training_data_round10_neutral_al.parquet"
LOCAL_CONTEXT_DB = "local_context.duckdb"
EMPATH_PARQUET = "/Volumes/NO NAME/processed/empath_scores_full_mapped.parquet"
SHORT_PARQUET = "/Volumes/NO NAME/processed/conspiracy_comments_short_lte100chars_mapped.parquet"

PREFIX_LEN = 45

WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    if text is None:
        return ""
    t = html.unescape(text)
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


def search_source(con, table_or_query, prefixes_df, source_name):
    """prefixes_df: DataFrame with columns [row_idx, prefix45]. Returns DataFrame of
    [row_idx, cand_id, cand_text] candidate matches by normalized-prefix equality."""
    con.register("train_prefixes", prefixes_df)
    q = f"""
    WITH src_norm AS (
        SELECT id, {SQL_NORMALIZE_EXPR} AS norm_text
        FROM {table_or_query}
    ),
    src_prefix AS (
        SELECT id, norm_text, substr(norm_text, 1, {PREFIX_LEN}) AS prefix45
        FROM src_norm
    )
    SELECT t.row_idx, s.id AS cand_id, s.norm_text AS cand_text
    FROM train_prefixes t
    JOIN src_prefix s ON t.prefix45 = s.prefix45
    """
    result = con.execute(q).fetchdf()
    con.unregister("train_prefixes")
    print(f"  [{source_name}] {len(result)} candidate matches for {prefixes_df['row_idx'].nunique()} query rows")
    return result


def classify(train_norm: str, cand_norm: str) -> str:
    if train_norm == cand_norm:
        return "exact_complete"
    if cand_norm.startswith(train_norm) and len(cand_norm) > len(train_norm):
        return "truncated"
    if train_norm.startswith(cand_norm) and len(train_norm) > len(cand_norm):
        return "training_longer_than_source"  # unexpected, flag for inspection
    return "mismatch"


def main():
    df = pd.read_parquet(TRAINING_PATH)
    human_other = df[(df["label"] == "other") & (df["is_human"] == True)].copy()
    human_other = human_other.reset_index().rename(columns={"index": "row_idx"})
    print(f"Auditing {len(human_other)} human-labeled 'other' rows")

    human_other["norm_text"] = human_other["text"].map(normalize)
    human_other["prefix45"] = human_other["norm_text"].str.slice(0, PREFIX_LEN)

    results = {}  # row_idx -> dict(status, source, cand_id, cand_text)
    remaining = human_other[["row_idx", "prefix45"]].copy()

    sources = [
        (LOCAL_CONTEXT_DB, "comments", "local_context.duckdb"),
        (None, f"read_parquet('{EMPATH_PARQUET}')", "empath_scores_full_mapped"),
        (None, f"read_parquet('{SHORT_PARQUET}')", "short_lte100chars_mapped"),
    ]

    for db_path, table_expr, source_name in sources:
        if remaining.empty:
            break
        print(f"\nSearching {source_name} for {len(remaining)} still-unresolved rows...")
        con = duckdb.connect(db_path, read_only=True) if db_path else duckdb.connect()
        con.execute("PRAGMA memory_limit='3GB'")
        cand = search_source(con, table_expr, remaining, source_name)
        con.close()

        if not cand.empty:
            norm_lookup = dict(zip(human_other["row_idx"], human_other["norm_text"]))
            cand["train_norm"] = cand["row_idx"].map(norm_lookup)
            cand["status"] = cand.apply(
                lambda r: classify(r["train_norm"], r["cand_text"]), axis=1
            )
            # Prefer exact_complete > truncated > mismatch if multiple candidates
            priority = {"exact_complete": 0, "truncated": 1, "mismatch": 2, "training_longer_than_source": 3}
            cand["prio"] = cand["status"].map(priority)
            cand = cand.sort_values("prio").drop_duplicates("row_idx", keep="first")

            for _, r in cand.iterrows():
                results[r["row_idx"]] = {
                    "status": r["status"],
                    "source": source_name,
                    "cand_id": r["cand_id"],
                    "cand_text": r["cand_text"],
                }
            resolved_now = set(cand["row_idx"])
            remaining = remaining[~remaining["row_idx"].isin(resolved_now)]

    print(f"\nStill unresolved after all 3 sources: {len(remaining)}")
    for idx in remaining["row_idx"]:
        results[idx] = {"status": "no_match", "source": None, "cand_id": None, "cand_text": None}

    out_rows = []
    for _, row in human_other.iterrows():
        r = results[row["row_idx"]]
        out_rows.append({
            "row_idx": row["row_idx"],
            "source_file": row["source_file"],
            "target_entity": row["target_entity"],
            "training_text": row["text"],
            "status": r["status"],
            "match_source": r["source"],
            "match_id": r["cand_id"],
            "full_text": r["cand_text"],
        })
    out_df = pd.DataFrame(out_rows)
    out_path = "outputs/reinfer_probs/human_other_946_truncation_audit.csv"
    out_df.to_csv(out_path, index=False)

    print("\n=== Summary ===")
    print(out_df["status"].value_counts())
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
