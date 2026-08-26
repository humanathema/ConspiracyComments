"""build_fullcorpus_chain_contexts.py

Context-walk for the full-corpus escalation population (rows the
ensemble+binconf pipeline is uncertain about, or the FP-detector
flagged) -- reuses the proven round9 chain-walk logic
(walk_round9_aleatoric_chains.py: parent -> grandparent -> ... ->
top-level comment -> submission title+selftext, MAX_DEPTH=15,
uncapped text) but adapted to a BATCHED, level-by-level BFS against
local_context.duckdb (44.1M rows, rebuilt 2026-08-24, full r/Conspiracy
coverage -- better than round9's original scoped-by-link_id pull) instead
of walking row-by-row. Post title/selftext looked up from
data/raw/r_conspiracy_posts2.jsonl.gz (local_context.duckdb has comments
only, no posts table).

Input: escalation_population.parquet (id, parent_id, link_id, ...)
Output: fullcorpus_chain_contexts.parquet (id, depth, cumulative_context,
  terminal, terminal_reason)
"""
import duckdb
import pandas as pd

ESCALATION_PATH = "/private/tmp/claude-502/-Users-nash-Projects-ConspiracyComments/d39b542f-db2c-4e55-8710-cdf7727b690a/scratchpad/escalation_population.parquet"
LOCAL_CONTEXT_DB = "local_context.duckdb"
POSTS_PATH = "data/raw/r_conspiracy_posts2.jsonl.gz"
OUT_PATH = "outputs/reinfer_probs/fullcorpus_chain_contexts.parquet"
MAX_DEPTH = 15


def main():
    df = pd.read_parquet(ESCALATION_PATH)
    print(f"{len(df):,} rows to context-walk", flush=True)

    con = duckdb.connect(LOCAL_CONTEXT_DB, read_only=True)
    con.execute("PRAGMA memory_limit='4GB'")

    # state per row: id -> (current_parent_id, list of ancestor texts newest-first)
    state = {rid: {"parent_id": pid, "ancestors": [], "terminal_reason": None, "done": False}
              for rid, pid in zip(df["id"], df["parent_id"])}

    depth_reached_counts = {}

    for depth in range(1, MAX_DEPTH + 1):
        # collect comment-parent ids needed this level (t1_ prefix)
        need_comment = {}
        need_post = {}
        for rid, s in state.items():
            if s["done"]:
                continue
            pid = s["parent_id"]
            if not isinstance(pid, str):
                s["done"] = True
                s["terminal_reason"] = "no_parent_id"
                continue
            if pid.startswith("t3_"):
                need_post[rid] = pid[3:]
            elif pid.startswith("t1_"):
                need_comment[rid] = pid[3:]
            else:
                s["done"] = True
                s["terminal_reason"] = "unexpected_prefix"

        if not need_comment and not need_post:
            break

        print(f"depth {depth}: {len(need_comment)} comment lookups, {len(need_post)} post lookups", flush=True)

        # batch comment lookup
        if need_comment:
            ids_needed = list(set(need_comment.values()))
            id_df = pd.DataFrame({"cid": ids_needed})
            con.register("ids_needed", id_df)
            found = con.execute("""
                SELECT c.id, c.text, c.parent_id
                FROM comments c JOIN ids_needed n ON c.id = n.cid
            """).fetchdf()
            con.unregister("ids_needed")
            lookup = {row["id"]: (row["text"], row["parent_id"]) for _, row in found.iterrows()}

            for rid, cid in need_comment.items():
                if cid in lookup:
                    body, next_parent = lookup[cid]
                    state[rid]["ancestors"].append(body)
                    state[rid]["parent_id"] = next_parent
                else:
                    state[rid]["done"] = True
                    state[rid]["terminal_reason"] = "parent_not_found"

        # batch post lookup (terminates the chain)
        if need_post:
            post_ids_needed = list(set(need_post.values()))
            pcon = duckdb.connect()
            post_id_df = pd.DataFrame({"pid": post_ids_needed})
            pcon.register("post_ids_needed", post_id_df)
            posts_found = pcon.execute(f"""
                SELECT p.id, p.title, p.selftext
                FROM read_ndjson('{POSTS_PATH}', ignore_errors=true) p
                JOIN post_ids_needed n ON p.id = n.pid
            """).fetchdf()
            pcon.close()
            post_lookup = {row["id"]: f"{row['title'] or ''} {row['selftext'] or ''}".strip()
                           for _, row in posts_found.iterrows()}

            for rid, pid in need_post.items():
                post_text = post_lookup.get(pid, "")
                if post_text:
                    state[rid]["ancestors"].append(post_text)
                state[rid]["done"] = True
                state[rid]["terminal_reason"] = "reached_post"

    for rid, s in state.items():
        if not s["done"]:
            s["terminal_reason"] = "max_depth_hit"
        d = len(s["ancestors"])
        depth_reached_counts[d] = depth_reached_counts.get(d, 0) + 1

    print("\nDepth-reached distribution:", flush=True)
    for d in sorted(depth_reached_counts):
        print(f"  depth {d}: {depth_reached_counts[d]:,} rows", flush=True)

    rows_out = []
    for rid, s in state.items():
        ancestors = s["ancestors"]
        for d in range(1, len(ancestors) + 1):
            levels_oldest_to_newest = list(reversed(ancestors[:d]))
            cumulative = " ".join(str(t) for t in levels_oldest_to_newest)
            rows_out.append({
                "id": rid,
                "depth": d,
                "cumulative_context": cumulative,
                "terminal": (d == len(ancestors)),
                "terminal_reason": s["terminal_reason"] if d == len(ancestors) else None,
            })

    out = pd.DataFrame(rows_out)
    out.to_parquet(OUT_PATH, index=False)
    print(f"\nSaved {len(out):,} (id, depth) context rows to {OUT_PATH}", flush=True)
    n_no_context = depth_reached_counts.get(0, 0)
    print(f"Rows with NO context found at all: {n_no_context:,}", flush=True)


if __name__ == "__main__":
    main()
