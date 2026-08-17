"""build_full_entity_mention_pool.py

Full-corpus (uncapped) entity-mention pull -- the real "every mention of a
verified maverick/consensus entity in the whole corpus" pool, as opposed to
round9_unlabeled_pool.parquet which is a 150-per-entity CAPPED SAMPLE drawn
from this same scan (build_round9_pull.py's scan_corpus() already touches
every match, it just throws away everything past the cap before saving).

Reuses build_round9_pull.py's scan_corpus() verbatim (same verified
maverick+consensus entity list via pull_hitl_val_batch.build_person_entities/
build_domain_entities, same canonical-figure exclusion via SKIP_PERSONS, same
excluded-pairs logic so already-labeled/training rows aren't re-included) --
just with TARGET_PER_ENTITY effectively disabled (a cap far above any single
entity's real corpus count) and disambiguation applied to every person
entity (now that _is_bare_surname_mode covers single-token bare-surname
aliases too, fixed 2026-08-18 in pull_hitl_val_batch.py).

Sizing (count-only query, 2026-08-18): 364,934 long + 69,049 short = 433,983
raw person-entity matches before disambiguation/dedup -- comfortably within
memory on this machine (no need for the VM).

Two more fixes folded in after the first build (2026-08-18, found during
QA on that build's output):
  - skip_original_11=False: the default build_person_entities() drops the
    11 entities already covered by early-round training data (correct for
    pull_hitl_val_batch.py's original "don't request redundant new HITL
    labels" purpose) -- but that silently dropped Tucker Carlson, Alex
    Jones, Roger Stone, Matt Gaetz, Aaron Swartz, and WikiLeaks entirely
    from a pool meant for full-corpus inference coverage.
  - drop_duplicates on ["id", "target_entity"], not just ["id"]: a single
    comment mentioning two different tracked entities (e.g. both Alex
    Jones and WikiLeaks) was having one of the two entity-labels silently
    discarded by an id-only dedup. Confirmed via the first build: patching
    in the recovered original-11 entities only added 108,772 of the
    130,085 matched rows, the other ~21K were multi-entity comments
    collapsed onto whichever entity was already in the pool.

Output: data/processed/round9/full_entity_mention_pool.parquet
"""
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from pull_hitl_val_batch import _collect_excluded_pairs
from build_round9_pull import (
    LONG_CORPUS, SHORT_CORPUS, RANDOM_STATE, scan_corpus,
    build_person_entities, build_domain_entities,
)

NO_CAP = 10_000_000  # effectively uncapped -- min(cap, len(chunk)) always picks len(chunk)
OUT_PATH = "data/processed/round9/full_entity_mention_pool.parquet"


def main():
    print("Collecting excluded (id/text, entity) pairs (existing training + all HITL queues) ...", flush=True)
    excluded_id_pairs, excluded_text_pairs = _collect_excluded_pairs()
    print(f"  {len(excluded_id_pairs):,} id-pairs, {len(excluded_text_pairs):,} text-pairs to exclude\n", flush=True)

    persons = build_person_entities(skip_original_11=False)
    domains = build_domain_entities()

    # skip_original_11=False can recover an entity whose SQL condition is
    # byte-identical to one already present under a different display name
    # (e.g. "Julian Assange" -> '\bassange\b', same as the already-present
    # bare alias "Assange") -- scanning both would double-label the exact
    # same matched comments under two different target_entity values.
    # Confirmed 2026-08-18 for Julian Assange/Assange and Edward Snowden/
    # Snowden specifically; this is a general safety net for any other
    # such pair, not just those two.
    seen_conds = set()
    deduped = []
    dropped = []
    for name, cond, cat in persons:
        if cond in seen_conds:
            dropped.append(name)
            continue
        seen_conds.add(cond)
        deduped.append((name, cond, cat))
    if dropped:
        print(f"Dropped {len(dropped)} entities with a duplicate SQL condition (already covered under another display name): {dropped}\n", flush=True)
    persons = deduped

    print(f"Person entities: {len(persons)}  Domain entities: {len(domains)}\n", flush=True)

    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='5GB'")
    all_frames = []

    for corpus_path, min_len, tag in [(LONG_CORPUS, 50, "long"), (SHORT_CORPUS, 5, "short")]:
        print(f"=== {tag} corpus ===", flush=True)
        p_df = scan_corpus(con, corpus_path, min_len, persons, f"person_{tag}",
                            excluded_id_pairs, excluded_text_pairs, NO_CAP, RANDOM_STATE, disambiguate=True)
        d_df = scan_corpus(con, corpus_path, min_len, domains, f"domain_{tag}",
                            excluded_id_pairs, excluded_text_pairs, NO_CAP, RANDOM_STATE)
        if len(p_df):
            p_df["population"] = tag
            all_frames.append(p_df)
        if len(d_df):
            d_df["population"] = tag
            all_frames.append(d_df)
        print(f"  person matches: {len(p_df):,}  domain matches: {len(d_df):,}\n", flush=True)

    pool = pd.concat(all_frames, ignore_index=True).drop_duplicates(subset=["id", "target_entity"])
    print(f"Full combined pool: {len(pool):,} rows across {pool['target_entity'].nunique()} entities", flush=True)

    Path(OUT_PATH).parent.mkdir(parents=True, exist_ok=True)
    pool.to_parquet(OUT_PATH, index=False)
    print(f"\nSaved to {OUT_PATH}", flush=True)
    print("\nEntity category breakdown:")
    print(pool["entity_category"].value_counts().to_string())
    print("\nPopulation breakdown:")
    print(pool["population"].value_counts().to_string())
    print("\nTop 20 entities by row count:")
    print(pool["target_entity"].value_counts().head(20).to_string())
    print("\nBottom 20 entities by row count (thinnest coverage):")
    print(pool["target_entity"].value_counts().tail(20).to_string())


if __name__ == "__main__":
    main()
