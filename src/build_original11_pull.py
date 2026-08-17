"""build_original11_pull.py

Targeted pull for the original 11 entities (SKIP_ENTITIES in
pull_hitl_val_batch.py) -- the entities round9 structurally excludes,
since SKIP_ENTITIES exists to avoid redundant re-pulling of "entities
already covered in existing training/val data."  That exclusion logic
answers a different question than the one this script asks: these 11
entities supply 71.9% of all current training rows (30,440 of 42,327)
and 73.4% of all existing "other"-labeled rows (6,934 of 9,444) -- so
if the goal is specifically to find more likely-neutral candidates for
active learning, skipping them skips the majority of the model's actual
training exposure. Real headroom exists: 224,494 combined corpus mentions
across these 11 vs. only 30,440 rows sampled into training so far.

Reuses the same scan/exclude/cap architecture as build_round9_pull.py and
the same entity-matching machinery from pull_hitl_val_batch.py (including
the 2026-08-14 surname-disambiguation fix, applied here even though none
of these 11 were part of the original 60-entity audit -- two of them
(Tucker Carlson -> "carlson", Glenn Greenwald -> "greenwald") are
currently bare-surname-matched and were never checked for collision risk
since SKIP_ENTITIES excluded them from that audit too).

Per-entity headroom varies a lot and should be checked before trusting
this script's row counts at face value -- Alex Jones/Bill Gates/WikiLeaks
have tens of thousands of mentions available, but Glenn Greenwald's raw
corpus-frequency count (2,272) is already below what's in training (2,331)
-- likely near-zero real headroom, possibly a duplicate/near-duplicate
counting discrepancy between the frequency file and training data, not
investigated further here. Don't be surprised if Greenwald (and to a
lesser extent Swartz/Gaetz/Snowden/Fauci) comes back thin or empty.

Output: data/processed/round9/original11_unlabeled_pool.parquet --
unlabeled, NOT yet ensemble-scored. Scoring + ranking by cross-model
"other" vote agreement is a separate, later step (needs a GPU VM for the
6-model ensemble checkpoints, both currently terminated).
"""
import sys
import duckdb
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pull_hitl_val_batch import _person_sql_cond, _collect_excluded_pairs
from build_round9_pull import scan_corpus

LONG_CORPUS = "data/processed/empath_scores_full_mapped.parquet"
SHORT_CORPUS = "data/processed/conspiracy_comments_short_lte100chars_mapped.parquet"
TARGET_PER_ENTITY = 300
RANDOM_STATE = 42
OUT_PATH = "data/processed/round9/original11_unlabeled_pool.parquet"

# Canonical display names -- matches the most common properly-capitalized
# form seen in existing training data (casing there is inconsistent across
# pipeline generations: e.g. 'Alex Jones' / 'Alex jones' / 'ALEX JONES' all
# appear). SQL matching is case-insensitive regardless, this is just for
# clean output.
ORIGINAL_11 = [
    "WikiLeaks", "Alex Jones", "Tucker Carlson", "Julian Assange",
    "Roger Stone", "Edward Snowden", "Matt Gaetz", "Glenn Greenwald",
    "Aaron Swartz", "Anthony Fauci", "Bill Gates",
]


def build_original11_entities() -> list[tuple[str, str, str]]:
    return [(name, _person_sql_cond(name), "original11") for name in ORIGINAL_11]


def main():
    print("Collecting excluded (id/text, entity) pairs (existing training + all HITL queues) ...")
    excluded_id_pairs, excluded_text_pairs = _collect_excluded_pairs()
    print(f"  {len(excluded_id_pairs):,} id-pairs, {len(excluded_text_pairs):,} text-pairs to exclude\n")

    entities = build_original11_entities()
    print(f"Entities: {len(entities)}\n")

    con = duckdb.connect()
    all_frames = []

    for corpus_path, min_len, tag in [(LONG_CORPUS, 50, "long"), (SHORT_CORPUS, 5, "short")]:
        print(f"=== {tag} corpus ===")
        d = scan_corpus(con, corpus_path, min_len, entities, f"original11_{tag}",
                         excluded_id_pairs, excluded_text_pairs, TARGET_PER_ENTITY,
                         RANDOM_STATE, disambiguate=True)
        if len(d):
            d["population"] = tag
            all_frames.append(d)
        print()

    if not all_frames:
        print("No rows found -- check corpus paths and exclusion logic.")
        return

    pool = pd.concat(all_frames, ignore_index=True).drop_duplicates(subset=["id"])
    print(f"Raw combined pool: {len(pool):,} rows across {pool['target_entity'].nunique()} entities")

    # Cap again post-union: an entity could hit its cap independently in
    # both long and short scans, doubling its representation.
    capped = []
    for name, chunk in pool.groupby("target_entity"):
        n = min(TARGET_PER_ENTITY, len(chunk))
        capped.append(chunk.sample(n=n, random_state=RANDOM_STATE) if len(chunk) > n else chunk)
    pool = pd.concat(capped, ignore_index=True)
    print(f"After re-capping at {TARGET_PER_ENTITY}/entity across both corpora: {len(pool):,} rows")

    Path(OUT_PATH).parent.mkdir(parents=True, exist_ok=True)
    pool.to_parquet(OUT_PATH, index=False)
    print(f"\nSaved to {OUT_PATH}")
    print("\nRows per entity (target {}):".format(TARGET_PER_ENTITY))
    print(pool["target_entity"].value_counts().to_string())
    print("\nPopulation breakdown:")
    print(pool["population"].value_counts().to_string())


if __name__ == "__main__":
    main()
