"""fill_fullcorpus_no_context_gaps.py

Fixes a real bug in build_fullcorpus_chain_contexts.py: the 30,739 rows
that came back with zero context weren't actually missing a parent_id --
they're all top-level comments (parent_id = t3_<submission>) whose
submission simply wasn't found in data/raw/r_conspiracy_posts2.jsonl.gz
(post record missing/never scraped, even though the comment thread
itself IS present in local_context.duckdb). The original script silently
dropped these instead of falling back to anything else.

Nash's fix: even without the post record, (1) the thread's own comments
are still queryable by link_id in local_context.duckdb, and (2) many
r/Conspiracy submissions have a top-level "Submission Statement" comment
(conventionally starting "SS:") that stands in for what the post
title/selftext would have told us. Both are tried here.

Input: the escalation population + the existing (incomplete)
  fullcorpus_chain_contexts.parquet
Output: fullcorpus_chain_contexts_gapfilled.parquet -- just the NEW rows
  for previously-uncovered ids, to be concatenated with the original file
"""
import duckdb
import pandas as pd

ESCALATION_PATH = "/private/tmp/claude-502/-Users-nash-Projects-ConspiracyComments/d39b542f-db2c-4e55-8710-cdf7727b690a/scratchpad/escalation_population.parquet"
EXISTING_CTX_PATH = "outputs/reinfer_probs/fullcorpus_chain_contexts.parquet"
LOCAL_CONTEXT_DB = "local_context.duckdb"
POSTS_PATH = "data/raw/r_conspiracy_posts2.jsonl.gz"
OUT_PATH = "outputs/reinfer_probs/fullcorpus_chain_contexts_gapfilled.parquet"


def main():
    esc = pd.read_parquet(ESCALATION_PATH)
    ctx = pd.read_parquet(EXISTING_CTX_PATH)
    covered_ids = set(ctx["id"])
    gap = esc[~esc["id"].isin(covered_ids)].copy()
    print(f"{len(gap):,} rows with no context to gap-fill", flush=True)

    gap["link_sub_id"] = gap["link_id"].str.replace("t3_", "", regex=False)
    link_ids = gap["link_sub_id"].dropna().unique().tolist()
    print(f"{len(link_ids):,} unique submissions involved", flush=True)

    # Retry post title/selftext (in case the earlier pull missed some due to a
    # transient issue -- cheap to re-check)
    pcon = duckdb.connect()
    post_id_df = pd.DataFrame({"pid": link_ids})
    pcon.register("post_ids_needed", post_id_df)
    posts_found = pcon.execute(f"""
        SELECT p.id, p.title, p.selftext
        FROM read_ndjson('{POSTS_PATH}', ignore_errors=true) p
        JOIN post_ids_needed n ON p.id = n.pid
    """).fetchdf()
    pcon.close()
    post_lookup = {row["id"]: f"{row['title'] or ''} {row['selftext'] or ''}".strip()
                   for _, row in posts_found.iterrows()}
    print(f"posts found on retry: {len(post_lookup):,}", flush=True)

    # SS: comment fallback via local_context.duckdb, scoped by link_id
    con = duckdb.connect(LOCAL_CONTEXT_DB, read_only=True)
    con.execute("PRAGMA memory_limit='4GB'")
    id_df = pd.DataFrame({"lid": ["t3_" + l for l in link_ids]})
    con.register("ids_needed", id_df)
    ss_matches = con.execute("""
        SELECT c.link_id, c.text
        FROM comments c JOIN ids_needed n ON c.link_id = n.lid
        WHERE regexp_matches(lower(trim(c.text)), '^(ss[:\\-]|submission statement)')
    """).fetchdf()
    con.unregister("ids_needed")
    con.close()
    # one SS comment per submission (first match) -- multiple SS-like comments
    # in one thread are rare and not worth disambiguating here
    ss_lookup = dict(zip(ss_matches["link_id"], ss_matches["text"]))
    print(f"SS comments found: {len(ss_lookup):,} / {len(link_ids):,} submissions", flush=True)

    rows_out = []
    n_recovered = 0
    for _, row in gap.iterrows():
        rid = row["id"]
        sub_id = row["link_sub_id"]
        pieces = []
        post_text = post_lookup.get(sub_id, "")
        if post_text:
            pieces.append(post_text)
        ss_text = ss_lookup.get(row["link_id"])
        if ss_text:
            pieces.append(ss_text)
        if not pieces:
            continue  # genuinely no recoverable context
        n_recovered += 1
        cumulative = " ".join(pieces)
        rows_out.append({
            "id": rid,
            "depth": 1,
            "cumulative_context": cumulative,
            "terminal": True,
            "terminal_reason": "post_and_or_ss_gapfill",
        })

    out = pd.DataFrame(rows_out)
    out.to_parquet(OUT_PATH, index=False)
    print(f"\nRecovered context for {n_recovered:,} / {len(gap):,} previously-uncovered rows", flush=True)
    print(f"Still genuinely no context: {len(gap) - n_recovered:,}", flush=True)
    print(f"Saved {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
