"""walk_round9_aleatoric_chains.py

For the 1,768 round9 rows still classified "aleatoric" after the single-
parent context test, walk each row's ancestor chain (parent, grandparent,
great-grandparent, ... up to the top-level comment, then the submission
title+selftext) using the full-thread data pulled by
build_round9_thread_chains.py -- no further corpus scans, pure in-memory
traversal.

Builds, per row, a cumulative context string at each depth reached (depth 1
= immediate parent, already scored; depth 2 = grandparent+parent; etc.),
oldest-to-newest order, each level capped at 200 chars, total cumulative
context capped at 800 chars (trimmed from the oldest end if needed, so the
context closest to the target comment is always preserved).

Output: data/processed/round9/round9_aleatoric_chain_contexts.csv
  columns: id, depth, cumulative_context, terminal (this is the deepest
  level reachable for this row -- chain hit the post or a dead end)
"""
import os

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALEATORIC_PATH = os.path.join(REPO_ROOT, "data/processed/round9/round9_epistemic_aleatoric_classification.csv")
COMMENTS_PATH = os.path.join(REPO_ROOT, "data/processed/round9/round9_thread_comments.parquet")
POSTS_PATH = os.path.join(REPO_ROOT, "data/processed/round9/round9_thread_posts.parquet")
OUT_PATH = os.path.join(REPO_ROOT, "data/processed/round9/round9_aleatoric_chain_contexts.csv")

MAX_DEPTH = 15
# No artificial per-level/total char caps -- the earlier 200/800-char caps
# were a shortcut to avoid pushing the target comment out of a 768-token
# window. With MAX_LENGTH bumped to 3072 (see rescore scripts) and the
# tokenizer's own truncation handling the rare extreme-length outlier,
# raw ancestor text is used uncapped.


def main():
    df = pd.read_csv(ALEATORIC_PATH)
    aleatoric = df[df["classification"] == "aleatoric"].copy()
    print(f"{len(aleatoric):,} aleatoric rows")

    comments = pd.read_parquet(COMMENTS_PATH)
    posts = pd.read_parquet(POSTS_PATH)
    parent_lookup = dict(zip(comments["id"], comments["parent_id"]))
    body_lookup = dict(zip(comments["id"], comments["body"]))
    title_lookup = dict(zip(posts["id"], posts["title"]))
    selftext_lookup = dict(zip(posts["id"], posts["selftext"]))
    print(f"Loaded {len(comments):,} comments, {len(posts):,} posts for lookup")

    rows_out = []
    depth_reached_counts = {}

    for _, row in aleatoric.iterrows():
        rid = row["id"]
        cur_parent_id = row["parent_id"]
        ancestors = []  # list of texts, oldest appended last during walk (reverse later)
        depth = 0
        terminal_reason = None

        while depth < MAX_DEPTH:
            if not isinstance(cur_parent_id, str):
                terminal_reason = "no_parent_id"
                break
            if cur_parent_id.startswith("t3_"):
                # reached the submission -- add title+selftext as the final ancestor, then stop
                pid = cur_parent_id[3:]
                title = title_lookup.get(pid)
                selftext = selftext_lookup.get(pid)
                post_text = f"{title or ''} {selftext or ''}".strip()
                if post_text:
                    ancestors.append(post_text)
                    depth += 1
                terminal_reason = "reached_post"
                break
            if cur_parent_id.startswith("t1_"):
                cid = cur_parent_id[3:]
                body = body_lookup.get(cid)
                if body is None:
                    terminal_reason = "parent_not_found"
                    break
                ancestors.append(body)
                depth += 1
                cur_parent_id = parent_lookup.get(cid)
                continue
            terminal_reason = "unexpected_prefix"
            break
        else:
            terminal_reason = "max_depth_hit"

        depth_reached_counts[depth] = depth_reached_counts.get(depth, 0) + 1

        # ancestors[0] = immediate parent (newest), ancestors[-1] = oldest.
        # Build cumulative context at each depth level, oldest-to-newest order.
        for d in range(1, len(ancestors) + 1):
            levels_oldest_to_newest = list(reversed(ancestors[:d]))
            cumulative = " ".join(str(t) for t in levels_oldest_to_newest)
            rows_out.append({
                "id": rid,
                "depth": d,
                "cumulative_context": cumulative,
                "terminal": (d == len(ancestors)),
                "terminal_reason": terminal_reason if d == len(ancestors) else None,
            })

    out = pd.DataFrame(rows_out)
    print(f"\nDepth-reached distribution (max depth achieved per row):")
    for d in sorted(depth_reached_counts):
        print(f"  depth {d}: {depth_reached_counts[d]} rows")

    print(f"\nTotal (id, depth) context rows produced: {len(out):,}")
    print(f"Rows with depth reaching only 1 (already had, no further ancestors): {depth_reached_counts.get(1, 0)}")
    print(f"Rows with depth >= 2 (new context available beyond immediate parent): {sum(v for k,v in depth_reached_counts.items() if k >= 2)}")

    out.to_csv(OUT_PATH, index=False)
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    main()
