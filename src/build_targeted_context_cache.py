"""build_targeted_context_cache.py

Replaces the local_context.duckdb approach (crashed the disk -- a full
44M-row indexed copy of the corpus's text turned out to be genuinely
~18GB, too large for the ~20GB now free) with something much smaller:
a single streaming pass over the raw comment shards that only extracts
what the CURRENT review queues actually need, and writes directly into
hitl_rater.py's existing CONTEXT_CACHE mechanism
(data/hitl/context_cache.json), which is already checked first, before
any database fallback.

queue_escalation_aleatoric_review.csv already carries real id/parent_id/
link_id (recovered from escalation_candidates.csv's own columns, no
corpus scan needed for THAT part) -- only its sibling texts need a
corpus lookup here.

queue_active_learning_requeue_v2.csv has no id at all (from
stance_classifier_training_data.parquet, which has never carried an id
column all session) -- needs the full text-match scan for id/parent_id/
link_id AND sibling texts.

Single streaming pass, no persisted table -- memory-safe, minimal disk
footprint (just the final small JSON cache).

Output: updates data/hitl/context_cache.json (merged, not overwritten)
        rewrites queue_active_learning_requeue_v2.csv in place with
        recovered id/parent_id/link_id
"""
import glob
import json
import os

import duckdb
import pandas as pd

RAW_DIR = "data/raw"
CACHE_PATH = "data/hitl/context_cache.json"
NEEDS_TEXT_MATCH = "data/hitl/queue_active_learning_requeue_v2.csv"
ALREADY_HAS_IDS = "data/hitl/queue_escalation_aleatoric_review.csv"


def main():
    shards = sorted(glob.glob(os.path.join(RAW_DIR, "r_conspiracy_comments*.jsonl.gz")))
    shards = [s for s in shards if os.path.getsize(s) > 1024]
    glob_pattern = "[" + ",".join(f"'{s}'" for s in shards) + "]"

    df_match = pd.read_csv(NEEDS_TEXT_MATCH)
    df_has_ids = pd.read_csv(ALREADY_HAS_IDS)

    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='3GB'")
    con.execute("PRAGMA threads=4")
    con.execute("SET preserve_insertion_order=false")

    target_texts = set(df_match["full_text"].fillna(""))
    print(f"Text-matching {len(target_texts)} rows from {NEEDS_TEXT_MATCH}...", flush=True)
    targets_df = pd.DataFrame({"body": list(target_texts)})
    con.register("targets", targets_df)
    matched = con.execute(f"""
        SELECT c.id, c.parent_id, c.link_id, c.body
        FROM read_ndjson(
            {glob_pattern},
            columns={{'id':'VARCHAR','parent_id':'VARCHAR','link_id':'VARCHAR','body':'VARCHAR'}},
            ignore_errors=true
        ) c
        JOIN targets t ON c.body = t.body
    """).fetchdf()
    matched = matched.drop_duplicates(subset="body", keep="first")
    print(f"  matched {len(matched)} / {len(target_texts)}", flush=True)

    id_lookup = dict(zip(matched["body"], matched["id"]))
    parent_lookup = dict(zip(matched["body"], matched["parent_id"]))
    link_lookup = dict(zip(matched["body"], matched["link_id"]))
    df_match["rater_id"] = df_match["id"] if "id" in df_match.columns else None
    df_match["id"] = df_match["full_text"].fillna("").map(id_lookup)
    df_match["parent_id"] = df_match["full_text"].fillna("").map(parent_lookup)
    df_match["link_id"] = df_match["full_text"].fillna("").map(link_lookup)
    df_match.to_csv(NEEDS_TEXT_MATCH, index=False)
    print(f"  rewrote {NEEDS_TEXT_MATCH} with recovered ids", flush=True)

    # Combined target set for the context (parent+sibling) fetch pass:
    # matched rows from queue 1, plus already-id'd rows from queue 2.
    all_ids = set(matched["id"].dropna()) | set(df_has_ids["id"].dropna().astype(str))
    all_parent_ids = set(matched["parent_id"].dropna()) | set(df_has_ids["parent_id"].dropna())
    parent_comment_ids = {p[3:] for p in all_parent_ids if isinstance(p, str) and p.startswith("t1_")}

    print(f"\nFetching context (parents + siblings) for {len(all_ids)} rows, "
          f"{len(parent_comment_ids)} distinct parent comment ids...", flush=True)
    lookup_ids = list(parent_comment_ids)
    lookup_df = pd.DataFrame({"lookup_id": lookup_ids})
    con.register("lookup_ids", lookup_df)
    con.register("all_parent_ids_df", pd.DataFrame({"pid": list(all_parent_ids)}))
    context_rows = con.execute(f"""
        SELECT c.id, c.parent_id, c.link_id, c.body
        FROM read_ndjson(
            {glob_pattern},
            columns={{'id':'VARCHAR','parent_id':'VARCHAR','link_id':'VARCHAR','body':'VARCHAR'}},
            ignore_errors=true
        ) c
        WHERE c.id IN (SELECT lookup_id FROM lookup_ids)
           OR c.parent_id IN (SELECT pid FROM all_parent_ids_df)
    """).fetchdf()
    print(f"  fetched {len(context_rows)} context rows", flush=True)
    con.close()

    context_by_id = dict(zip(context_rows["id"], context_rows["body"]))
    context_by_parent = {}
    for _, r in context_rows.iterrows():
        context_by_parent.setdefault(r["parent_id"], []).append((r["id"], r["body"]))

    cache = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            cache = json.load(f)
        print(f"\nLoaded existing cache with {len(cache)} entries.", flush=True)

    n_added = 0
    for cid, pid in list(zip(matched["id"], matched["parent_id"])) + list(zip(df_has_ids["id"], df_has_ids["parent_id"])):
        if not cid or str(cid) in cache:
            continue
        parent_text = None
        if isinstance(pid, str) and pid.startswith("t1_"):
            parent_text = context_by_id.get(pid[3:])
        siblings = [t for sid, t in context_by_parent.get(pid, []) if sid != cid][:5]
        cache[str(cid)] = {"parent_text": parent_text, "sibling_texts": siblings}
        n_added += 1

    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f)
    print(f"\nSaved context cache: {len(cache)} total entries ({n_added} new).", flush=True)


if __name__ == "__main__":
    main()
