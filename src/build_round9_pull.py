"""build_round9_pull.py

Round9 unlabeled-batch pull: coverage-driven (not volume-driven), scanning
BOTH long and short comment corpora. Reuses the entity list and safe
matching logic already built and validated in pull_hitl_val_batch.py
(bare-surname-default with AMBIGUOUS_SURNAMES fallback to full-name phrase,
verified maverick+consensus lists, domain list) rather than rebuilding it.

Why a new script instead of just raising pull_hitl_val_batch.py's
MAX_PER_ENTITY: that script's pull_all_entities() hardcodes
`length(trim(text)) > 50`, which would silently drop roughly half the short
corpus (mean length 48.7 chars) -- needs a corpus-appropriate threshold, so
this reimplements the scan loop with that parameterized rather than
monkey-patching the shared one.

Sizing: TARGET_PER_ENTITY=150 (tunable), capped by real availability per
entity via verified_entity_combined_doc_counts.csv -- see the 2026-08-12
round9-sizing conversation for the derivation (yields ~29,466 realistic
new rows against the 398 currently-under-10-training-rows entities).

Output: data/processed/round9/round9_unlabeled_pool.parquet -- unlabeled,
NOT yet ensemble-scored. Ensemble scoring + confidence threshold +
epistemic/aleatoric context test are separate, later steps.
"""
import sys
import duckdb
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pull_hitl_val_batch import (
    build_person_entities, build_domain_entities, _collect_excluded_pairs,
)

LONG_CORPUS = "data/processed/empath_scores_full_mapped.parquet"
SHORT_CORPUS = "data/processed/conspiracy_comments_short_lte100chars_mapped.parquet"
TARGET_PER_ENTITY = 150
RANDOM_STATE = 42
OUT_PATH = "data/processed/round9/round9_unlabeled_pool.parquet"


def scan_corpus(con, corpus_path, min_len, entities, source_kind, excluded_id_pairs, excluded_text_pairs, cap, seed):
    if not entities:
        return pd.DataFrame()
    when_clauses = "\n    ".join(
        f"WHEN ({cond}) THEN '{name.replace(chr(39), chr(39) + chr(39))}'"
        for name, cond, _ in entities
    )
    any_match = " OR ".join(f"({cond})" for _, cond, _ in entities)
    cat_map = {name: cats for name, cond, cats in entities}

    q = f"""
        SELECT id, text, parent_id, link_id,
               CASE
                   {when_clauses}
               ELSE NULL
               END AS target_entity
        FROM read_parquet('{corpus_path}')
        WHERE text IS NOT NULL
          AND length(trim(text)) > {min_len}
          AND ({any_match})
    """
    print(f"  Scanning {corpus_path} ({len(entities)} {source_kind} entities, min_len={min_len}) ...", flush=True)
    df = con.execute(q).df()
    df = df[df["target_entity"].notna()]
    # (id, entity) / (text, entity) pair exclusion -- not bare id, since the
    # same comment can be legitimate new data for a different entity's
    # conditioning (fixed 2026-08-12).
    id_key = list(zip(df["id"].astype(str), df["target_entity"].str.lower()))
    text_key = list(zip(df["text"].astype(str), df["target_entity"].str.lower()))
    keep = [
        (idk not in excluded_id_pairs) and (txk not in excluded_text_pairs)
        for idk, txk in zip(id_key, text_key)
    ]
    df = df[keep]
    print(f"  {len(df):,} rows after dedup", flush=True)

    frames = []
    for name, _, cats in entities:
        chunk = df[df["target_entity"] == name]
        if len(chunk) == 0:
            continue
        n = min(cap, len(chunk))
        sampled = chunk.sample(n=n, random_state=seed).copy()
        sampled["entity_category"] = cats
        sampled["source_kind"] = source_kind
        frames.append(sampled)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main():
    print("Collecting excluded (id/text, entity) pairs (existing training + all HITL queues) ...")
    excluded_id_pairs, excluded_text_pairs = _collect_excluded_pairs()
    print(f"  {len(excluded_id_pairs):,} id-pairs, {len(excluded_text_pairs):,} text-pairs to exclude\n")

    persons = build_person_entities()
    domains = build_domain_entities()
    print(f"Person entities: {len(persons)}  Domain entities: {len(domains)}\n")

    con = duckdb.connect()
    all_frames = []

    for corpus_path, min_len, tag in [(LONG_CORPUS, 50, "long"), (SHORT_CORPUS, 5, "short")]:
        print(f"=== {tag} corpus ===")
        p = scan_corpus(con, corpus_path, min_len, persons, f"person_{tag}", excluded_id_pairs, excluded_text_pairs, TARGET_PER_ENTITY, RANDOM_STATE)
        d = scan_corpus(con, corpus_path, min_len, domains, f"domain_{tag}", excluded_id_pairs, excluded_text_pairs, TARGET_PER_ENTITY, RANDOM_STATE)
        if len(p):
            p["population"] = tag
            all_frames.append(p)
        if len(d):
            d["population"] = tag
            all_frames.append(d)
        print()

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
    print("\nEntity category breakdown:")
    print(pool["entity_category"].value_counts().to_string())
    print("\nPopulation breakdown:")
    print(pool["population"].value_counts().to_string())
    print("\nTop 20 entities by row count:")
    print(pool["target_entity"].value_counts().head(20).to_string())
    print("\nBottom 20 entities by row count (thinnest coverage even after this pull):")
    print(pool["target_entity"].value_counts().tail(20).to_string())


if __name__ == "__main__":
    main()
