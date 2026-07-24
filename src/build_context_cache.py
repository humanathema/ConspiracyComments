"""Script to pre-compile a context cache for all comments in active rating queues.

Queries the heavy local parquet file `data/processed/empath_scores_full.parquet`
using a highly optimized batched-query approach (performing only two database scans
instead of individual row lookups).
"""
import os
import json
import duckdb
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _abs(rel_path):
    return os.path.join(REPO_ROOT, rel_path)

QUEUES = {
    "irr_stance_shared": _abs("data/hitl/queue_irr_stance_shared.csv"),
    "maverick_stance_round8": _abs("data/hitl/queue_maverick_stance_round8.csv"),
    "consensus_stance_round8": _abs("data/hitl/queue_consensus_stance_round8.csv"),
}

EMPATH_PATH = _abs("data/processed/empath_scores_full.parquet")
OUTPUT_CACHE_PATH = _abs("data/hitl/context_cache.json")

def main():
    print("=== Building Context Cache for Active Queues (Batched Mode) ===")
    if not os.path.exists(EMPATH_PATH):
        print(f"Error: Parquet file not found at {EMPATH_PATH}")
        return

    # 1. Collect all comments and parent/link IDs from active queues
    active_comments = []
    parent_comment_ids = set()  # format: 'abc' (from t1_abc)
    parent_ids_raw = set()      # format: 't1_abc'

    for name, path in QUEUES.items():
        if os.path.exists(path):
            df = pd.read_csv(path)
            print(f"Loaded queue '{name}' ({len(df)} rows)")
            for _, row in df.iterrows():
                cid = str(row["id"])
                pid = str(row.get("parent_id", "") or "")
                lid = str(row.get("link_id", "") or "")
                
                active_comments.append({
                    "id": cid,
                    "parent_id": pid,
                    "link_id": lid
                })

                if pid:
                    parent_ids_raw.add(pid)
                    if pid != lid and pid.startswith("t1_"):
                        parent_comment_ids.add(pid[3:])

    if not active_comments:
        print("No active comments found to cache.")
        return

    print(f"Total active comments: {len(active_comments)}")
    print(f"Unique parent comment IDs to fetch: {len(parent_comment_ids)}")
    print(f"Unique raw parent IDs for sibling lookups: {len(parent_ids_raw)}")

    # 2. Query DuckDB in batches
    print("Connecting to local DuckDB...")
    con = duckdb.connect()

    # Batch Fetch Parent Comment Texts
    parent_texts_map = {}
    if parent_comment_ids:
        print("Scanning parquet file to fetch parent texts...")
        parent_comment_ids_list = list(parent_comment_ids)
        # Use parameterized query or safe chunking if list is extremely large,
        # but for ~300 items, a single IN query is perfectly safe and fast.
        res = con.execute(
            f"SELECT id, text FROM read_parquet('{EMPATH_PATH}') WHERE id IN ?",
            [parent_comment_ids_list]
        ).fetchall()
        parent_texts_map = {r[0]: r[1] for r in res}
        print(f"Successfully fetched {len(parent_texts_map)} parent comment texts.")

    # Batch Fetch Sibling Replies
    sibling_map = {}
    if parent_ids_raw:
        print("Scanning parquet file to fetch sibling replies...")
        parent_ids_list = list(parent_ids_raw)
        res = con.execute(
            f"SELECT parent_id, id, text FROM read_parquet('{EMPATH_PATH}') WHERE parent_id IN ?",
            [parent_ids_list]
        ).fetchall()
        
        # Group siblings by parent_id
        for parent_id, sib_id, text in res:
            if parent_id not in sibling_map:
                sibling_map[parent_id] = []
            sibling_map[parent_id].append((sib_id, text))
        print(f"Successfully loaded sibling lists for {len(sibling_map)} parent threads.")

    # 3. Assemble final cache dictionary
    print("Assembling final cache...")
    cache = {}
    for item in active_comments:
        comment_id = item["id"]
        parent_id_raw = item["parent_id"]
        link_id_raw = item["link_id"]

        parent_text = None
        sibling_texts = []

        # Map parent text from parent_texts_map
        if parent_id_raw and parent_id_raw != link_id_raw and parent_id_raw.startswith("t1_"):
            parent_comment_id = parent_id_raw[3:]
            parent_text = parent_texts_map.get(parent_comment_id)

        # Map sibling replies from sibling_map (excluding current comment)
        if parent_id_raw and parent_id_raw in sibling_map:
            sibs = sibling_map[parent_id_raw]
            # Filter out the current comment and take up to 5 siblings
            sibling_texts = [text for sib_id, text in sibs if sib_id != comment_id][:5]

        cache[comment_id] = {
            "parent_text": parent_text,
            "sibling_texts": sibling_texts
        }

    # 4. Save Cache to JSON
    print(f"Saving compiled context cache to {OUTPUT_CACHE_PATH}...")
    with open(OUTPUT_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f"Successfully cached context for {len(cache)} comments! Cache size: {os.path.getsize(OUTPUT_CACHE_PATH) / 1024:.2f} KB")

if __name__ == "__main__":
    main()
