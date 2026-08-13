"""pull_hitl_val_batch.py

Pull a new HITL labeling batch for val-set expansion using the full
defensibly-generated entity set rather than the hardcoded 11.

Entity sources:
  1. Person mavericks — maverick_candidate_entities_scored.csv (corpus_mentions >= 300),
     excluding the 11 entities already covered in round 7/8 training data,
     and excluding historical canonical figures (Tesla, Newton, etc.).
  2. Domain epistemic sources — domain_classification_lookup.csv, categories
     alt_media and leak_whistleblower.  Matched by domain key in comment text.

Stance labeling (hostile/endorsement/neutral/ambiguous/wrong_match) applies to
both persons and domains: "hostile to <naturalnews.com>" = dismissal,
"endorsement" = treating as a trusted epistemic source.

Usage:
  python3 src/pull_hitl_val_batch.py --out data/hitl/queue_expanded_entity_val_r1.csv
  python3 src/pull_hitl_val_batch.py --out data/hitl/queue_expanded_entity_val_r2.csv --seed 44
"""

import argparse
import re
import sys
import pandas as pd
import duckdb
from pathlib import Path

EMPATH   = "data/processed/empath_scores_full_mapped.parquet"
DOC_COUNTS_FILE = "data/processed/verified_entity_combined_doc_counts.csv"
DOM_FILE = "data/processed/domain_classification_lookup.csv"

TARGET_ROWS       = 410
MAX_PER_ENTITY    = 10   # cap per individual entity before final balance sample
# Combined long+short comment doc_count (see DOC_COUNTS_FILE) — replaces the
# old MIN_ENTITY_MENTIONS=300 raw-candidate threshold, which turned out to be
# long-comment-only and admitted only ~14% of the verified entity universe
# (2026-08-12 analysis). >=100 captures 130/190 (68%) of already-verified
# maverick+consensus entities with real, non-trivial corpus presence — no
# per-entity judgment calls needed since it's applied uniformly to entities
# already reviewed and confirmed by maverick_authority_verified.py /
# consensus_experts_verified.py.
MIN_COMBINED_DOC_COUNT = 100
RANDOM_STATE      = 42

# The 11 entities already covered in existing training/val data — skip them
SKIP_ENTITIES = {
    "wikileaks", "alex jones", "tucker carlson", "julian assange", "roger stone",
    "edward snowden", "matt gaetz", "glenn greenwald", "aaron swartz",
    "anthony fauci", "bill gates",
}

# Historical canonical / non-maverick figures to skip
SKIP_PERSONS = {
    "Nikola Tesla", "Neil deGrasse Tyson", "Bill Hicks", "Adam Weishaupt",
    "Oliver Stone", "Mark Dice", "Deep Throat",  # anonymous — matching unreliable
    "Jenny McCarthy",  # surname dominated by 1950s Red Scare McCarthyism in this
                        # corpus; not independently established as discussed here,
                        # not worth a disambiguation pass — see AMBIGUOUS_SURNAMES.
    "Stephen Hawking", "Carl Sagan",  # historical/canonical scientists, excluded
                                       # 2026-08-12 alongside Tesla/deGrasse Tyson.
}

# Skip categories that are historical/canonical rather than maverick/consensus
SKIP_CATEGORIES = {"free_energy_theorist", "rogan_guest_scientist"}

# Domain categories to include
DOMAIN_CATS = {"alt_media", "leak_whistleblower"}

# Domains to skip (platforms, not epistemic sources in the stance sense)
SKIP_DOMAINS = {
    "reddit.com", "youtube.com", "twitter.com", "facebook.com",
    "instagram.com", "imgur.com", "archive.is", "archive.org",
    "web.archive.org", "wikileaks.org", "wikileaks.com",  # already in person 11
}


def _bare_surname_key(entity: str) -> str:
    """Last word of a multi-word entity name, stripped of trailing punctuation."""
    parts = entity.strip().split()
    last = parts[-1].lower()
    last = re.sub(r"[.,]+$", "", last)   # "jr." → "jr"
    last = re.sub(r"'s$", "", last)       # possessive only
    return last


def _full_name_sql_cond(entity: str) -> str:
    """Require the FULL entity name as a phrase (all words in order, flexible
    whitespace between them), case-insensitive, word-boundary anchored.

    BUG FIXED 2026-08-12: matched against lower(text) but never lowercased
    the pattern itself -- e.g. 'Joe Rogan' built the literal pattern
    '\\bJoe\\s+Rogan\\b', which can never match lowercased corpus text.
    Every entity requiring full-name matching (anything with a short/
    AMBIGUOUS_SURNAMES surname -- Rogan, Icke, Ventura, and more) silently
    returned zero matches from this bug, not real corpus scarcity.
    """
    parts = entity.strip().lower().split()
    escaped_parts = [re.escape(p).replace("'", "''") for p in parts]
    pattern = r"\s+".join(escaped_parts)
    return f"regexp_matches(lower(text), '\\b{pattern}\\b')"


# Surnames confirmed (or already known) to collide with a much more famous
# unrelated person, or to be an ordinary English word/name shared broadly
# enough that bare matching is unsafe. Full name is required for these instead
# of the bare surname. Extended 2026-08-12 after auditing
# queue_expanded_entity_val_r1.csv (34 human-labeled wrong_match rows out of
# 410): weinstein (matches Harvey Weinstein almost exclusively, not Bret),
# manning (the common verb "manning", not just Chelsea Manning), steele
# (Christopher Steele / "Steele dossier", plus a raw substring hit inside
# "Steeler"), ventura (Ace Ventura movie character). Jenny McCarthy dropped
# from the candidate list entirely (see SKIP_PERSONS) rather than
# disambiguated — the corpus attention is dominated by 1950s Red Scare
# McCarthyism, and she isn't independently established as an actively
# discussed figure in this subreddit, so a disambiguation pass isn't worth
# building for her.
AMBIGUOUS_SURNAMES = {
    "jr", "sr", "ii", "iii", "iv", "the", "von", "van", "de",
    "bell", "adams", "allen", "brand", "corsi", "gates", "hersh", "jones",
    "kory", "lake", "duke", "wolf", "wood", "truth",
    "butler", "garrison", "griffin", "peters", "roberts", "watson", "watkins",
    "weinstein", "manning", "steele", "ventura",
}


def _person_sql_cond(entity: str) -> str:
    """Bare surname is the default (this is what actually surfaces real
    mentions — most maverick figures are referred to by surname alone, not
    full name, in casual comments). Falls back to requiring the full name
    phrase only for single/short surnames or ones in AMBIGUOUS_SURNAMES.

    No hand-picked "signature words" shortcut here: recovering bare-surname
    recall for an AMBIGUOUS_SURNAMES entity needs context words *derived from
    the corpus* (co-occurrence with confirmed full-name mentions), not guessed
    from general knowledge — not built yet, full-name-only is the safe
    fallback in the meantime.
    """
    parts = entity.strip().split()
    if len(parts) == 1:
        key = entity.lower()
        escaped = re.escape(key).replace("'", "''")
        return f"regexp_matches(lower(text), '\\b{escaped}\\b')"

    last = _bare_surname_key(entity)
    if len(last) >= 6 and last not in AMBIGUOUS_SURNAMES:
        escaped = re.escape(last).replace("'", "''")
        return f"regexp_matches(lower(text), '\\b{escaped}\\b')"

    return _full_name_sql_cond(entity)


def _domain_key(domain: str) -> str:
    """Strip TLD to get a matchable key, e.g. 'naturalnews.com' → 'naturalnews'."""
    key = re.sub(r"\.(com|org|net|io|co|ca|uk|gov|edu|info|biz)(\.[a-z]{2})?$", "", domain.lower())
    # Remove leading 'www.' if present
    key = re.sub(r"^www\.", "", key)
    return key


def _collect_excluded_pairs() -> tuple[set, set]:
    """Returns (excluded_id_entity_pairs, excluded_text_entity_pairs) --
    NOT a bare id set. A comment can genuinely mention multiple entities;
    already having a labeled row for that comment under one entity's
    [ENTITY: X] conditioning does not make it stale for a DIFFERENT
    entity's conditioning -- that's a distinct training example (fixed
    2026-08-12, was excluding by id alone and silently discarding real,
    still-needed rows for any entity that shared an id with an
    already-used comment).

    Two separate sets because the canonical training parquets
    (stance_classifier_training_data*.parquet) have no `id` column at all
    -- only `text` -- while HITL queue CSVs do have `id`. Checked directly,
    not assumed: confirm before "fixing" this again.
    """
    id_pairs = set()
    text_pairs = set()
    for path in Path("data/processed").glob("stance_classifier_training_data*.parquet"):
        try:
            cols = pd.read_parquet(path).columns
            if "target_entity" not in cols:
                continue
            if "id" in cols:
                df = pd.read_parquet(path, columns=["id", "target_entity"])
                df = df.dropna(subset=["id", "target_entity"])
                id_pairs.update(zip(df["id"].astype(str), df["target_entity"].str.lower()))
            elif "text" in cols:
                df = pd.read_parquet(path, columns=["text", "target_entity"])
                df = df.dropna(subset=["text", "target_entity"])
                text_pairs.update(zip(df["text"].astype(str), df["target_entity"].str.lower()))
        except Exception:
            pass
    for path in Path("data/hitl").glob("queue_*.csv"):
        try:
            cols = pd.read_csv(path, nrows=0).columns
            if "target_entity" not in cols or "id" not in cols:
                continue
            df = pd.read_csv(path, usecols=["id", "target_entity"])
            df = df.dropna(subset=["id", "target_entity"])
            id_pairs.update(zip(df["id"].astype(str), df["target_entity"].str.lower()))
        except Exception:
            pass
    return id_pairs, text_pairs


def _collect_excluded_ids() -> set:
    """Deprecated shape -- kept only so anything still importing this name
    doesn't hard-crash. Prefer _collect_excluded_pairs()."""
    id_pairs, _ = _collect_excluded_pairs()
    return {i for i, _ in id_pairs}


def build_person_entities() -> list[tuple[str, str, str]]:
    """Return list of (canonical_name, sql_condition, category).

    Source: the hand-reviewed VERIFIED_MAVERICK_AUTHORITY / _ADDITIONS /
    VERIFIED_CONSENSUS_EXPERTS lists (already decided, not raw candidates),
    filtered by real combined long+short doc_count (see DOC_COUNTS_FILE /
    MIN_COMBINED_DOC_COUNT above) — no new per-entity judgment calls, just a
    uniform frequency floor applied to entities already reviewed.
    """
    sys.path.insert(0, str(Path(__file__).parent))
    from maverick_authority_verified import VERIFIED_MAVERICK_AUTHORITY
    from consensus_experts_verified import VERIFIED_CONSENSUS_EXPERTS
    # VERIFIED_MAVERICK_ADDITIONS deliberately excluded here: it's messy alias
    # patterns (possessives, misspellings, hashtags) for entities already
    # covered by their clean canonical form in VERIFIED_MAVERICK_AUTHORITY —
    # using an alias like "Edward Snowden's" as the primary match name would
    # badly under-match (regex would require the literal possessive).

    maverick_names = set(VERIFIED_MAVERICK_AUTHORITY)
    consensus_names = set(VERIFIED_CONSENSUS_EXPERTS)
    all_names = {n: "maverick" for n in maverick_names}
    for n in consensus_names:
        all_names[n] = "consensus" if n not in all_names else all_names[n] + ";consensus"

    doc_counts = pd.read_csv(DOC_COUNTS_FILE).set_index("best_identity")["combined_doc_count"].to_dict()
    review = pd.read_csv("data/processed/entity_final_review.csv")
    best_identity_lookup = review.set_index(review["entity"].str.lower())["best_identity"].to_dict()
    # SKIP_PERSONS names must be resolved through best_identity too, not just
    # matched literally: consensus_experts_verified.py deliberately includes
    # alias variants of skipped people (e.g. "Steven Hawking" misspelling,
    # "Sagan"/"Carl Sagan's" bare/possessive aliases of Carl Sagan) that don't
    # equal the canonical SKIP_PERSONS string but resolve to the same person.
    skip_identities = {best_identity_lookup.get(n.lower()) for n in SKIP_PERSONS} - {None}

    entities = []
    seen = set()
    for name, cat in all_names.items():
        if name.lower() in SKIP_ENTITIES or name in SKIP_PERSONS:
            continue
        best_id = best_identity_lookup.get(name.lower())
        if best_id in skip_identities:
            continue
        count = doc_counts.get(best_id, 0) if best_id else 0
        if count < MIN_COMBINED_DOC_COUNT:
            continue
        # Dedup by best_identity (aliases in VERIFIED_MAVERICK_ADDITIONS like
        # "Ed Snowden" would otherwise create a second, redundant entry for
        # the same person already covered by the canonical form).
        dedup_key = best_id or name
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        cond = _person_sql_cond(name)
        entities.append((name, cond, cat))
    return entities


def build_domain_entities() -> list[tuple[str, str, str]]:
    """Return list of (domain_name, sql_condition, category)."""
    dom = pd.read_csv(DOM_FILE)
    dom = dom[dom["category"].isin(DOMAIN_CATS)]
    dom = dom[~dom["domain"].isin(SKIP_DOMAINS)]

    entities = []
    for _, row in dom.iterrows():
        domain = row["domain"]
        key = _domain_key(domain)
        if len(key) < 5:  # too short to match safely
            continue
        escaped = re.escape(key).replace("'", "''")
        cond = f"regexp_matches(lower(text), '\\b{escaped}')"
        entities.append((domain, cond, row["category"]))
    return entities


def pull_all_entities(
    con,
    entities: list[tuple[str, str, str]],
    source_kind: str,
    excluded_id_pairs: set,
    excluded_text_pairs: set,
    max_per_entity: int,
    seed: int,
) -> pd.DataFrame:
    """Single-pass scan: build one big CASE/WHEN query so the parquet is read once."""
    if not entities:
        return pd.DataFrame()

    # Build: CASE WHEN <cond1> THEN '<name1>' WHEN ... ELSE NULL END AS target_entity
    # Only grab rows that match at least one entity
    when_clauses = "\n    ".join(
        f"WHEN ({cond}) THEN '{name.replace(chr(39), chr(39)+chr(39))}'"
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
        FROM read_parquet('{EMPATH}')
        WHERE text IS NOT NULL
          AND length(trim(text)) > 50
          AND ({any_match})
    """
    print(f"  Scanning parquet for {len(entities)} {source_kind} entities ...", flush=True)
    df = con.execute(q).df()
    df = df[df["target_entity"].notna()]
    # Exclude by (id, entity) AND (text, entity) pair -- not by bare id/text,
    # since the same comment can be legitimate new data for a different
    # entity's conditioning (fixed 2026-08-12).
    id_key = list(zip(df["id"].astype(str), df["target_entity"].str.lower()))
    text_key = list(zip(df["text"].astype(str), df["target_entity"].str.lower()))
    keep = [
        (idk not in excluded_id_pairs) and (txk not in excluded_text_pairs)
        for idk, txk in zip(id_key, text_key)
    ]
    df = df[keep]
    print(f"  {len(df):,} rows after dedup", flush=True)

    # Cap per entity
    frames = []
    for name, _, cats in entities:
        chunk = df[df["target_entity"] == name]
        if len(chunk) == 0:
            print(f"    {name}: 0 rows")
            continue
        n = min(max_per_entity, len(chunk))
        sampled = chunk.sample(n=n, random_state=seed)
        sampled = sampled.copy()
        sampled["entity_category"] = cats
        sampled["source_kind"] = source_kind
        frames.append(sampled)
        print(f"    {name}: {n} rows")

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/hitl/queue_expanded_entity_val_r1.csv")
    ap.add_argument("--seed", type=int, default=RANDOM_STATE)
    ap.add_argument("--target", type=int, default=TARGET_ROWS,
                    help="Target number of rows in output")
    ap.add_argument("--max_per_entity", type=int, default=MAX_PER_ENTITY)
    args = ap.parse_args()

    seed = args.seed

    # Refuse to overwrite a queue that already has human labels in it
    out_path = Path(args.out)
    if out_path.exists():
        existing = pd.read_csv(out_path)
        n_labeled = existing["human_label"].notna().sum() if "human_label" in existing.columns else 0
        if n_labeled > 0:
            print(f"ERROR: {args.out} already has {n_labeled} human labels — refusing to overwrite.")
            print("Use --out to specify a different output path (e.g. queue_expanded_entity_val_r2.csv).")
            return

    print("Collecting excluded (id/text, entity) pairs ...")
    excluded_id_pairs, excluded_text_pairs = _collect_excluded_pairs()
    print(f"  {len(excluded_id_pairs):,} id-pairs, {len(excluded_text_pairs):,} text-pairs to exclude")

    person_entities = build_person_entities()
    domain_entities = build_domain_entities()
    print(f"Person entities: {len(person_entities)}")
    print(f"Domain entities: {len(domain_entities)}")

    con = duckdb.connect()

    print("\n--- Person entities (single scan) ---")
    person_df = pull_all_entities(con, person_entities, "person_maverick", excluded_id_pairs, excluded_text_pairs, args.max_per_entity, seed)

    print("\n--- Domain entities (single scan) ---")
    domain_df = pull_all_entities(con, domain_entities, "domain_source", excluded_id_pairs, excluded_text_pairs, args.max_per_entity, seed)

    frames = [df for df in [person_df, domain_df] if len(df) > 0]

    if not frames:
        print("No rows found — check EMPATH path and filters.")
        return

    pool = pd.concat(frames, ignore_index=True)
    pool = pool.drop_duplicates(subset=["id"])
    n_entities = pool["target_entity"].nunique()
    print(f"\nRaw pool: {len(pool):,} rows across {n_entities} entities")

    # Subsample to target, balanced by entity_category. Within each category,
    # guarantee at least 1 row per matched entity before filling any
    # remaining budget randomly -- a flat chunk.sample() over the whole
    # category pool (the old approach) has zero guarantee any specific
    # entity survives; found 2026-08-12 via Jesse Ventura/David Duke
    # (thousands of real corpus matches each, both randomly zeroed out of
    # a 410-row batch by category-level sampling variance, not a matching
    # bug -- confirmed by tracing the raw CASE/WHEN scan directly).
    cats_present = pool["entity_category"].unique()
    per_cat = max(1, args.target // len(cats_present))

    sampled = []
    for cat in cats_present:
        chunk = pool[pool["entity_category"] == cat]
        cat_target = min(len(chunk), per_cat)
        entities_in_cat = chunk["target_entity"].unique()

        guaranteed = pd.concat(
            [chunk[chunk["target_entity"] == e].sample(n=1, random_state=seed) for e in entities_in_cat],
            ignore_index=True,
        )
        if len(guaranteed) >= cat_target:
            # More distinct entities than this category's budget -- keep
            # coverage (1/entity) rather than depth, trim down to budget.
            sampled.append(guaranteed.sample(n=cat_target, random_state=seed))
        else:
            remaining_budget = cat_target - len(guaranteed)
            rest = chunk[~chunk["id"].astype(str).isin(guaranteed["id"].astype(str))]
            topup = rest.sample(n=min(remaining_budget, len(rest)), random_state=seed) if len(rest) else rest
            sampled.append(pd.concat([guaranteed, topup], ignore_index=True))

    batch = pd.concat(sampled, ignore_index=True)

    # Top up to target from remaining rows if we're short
    if len(batch) < args.target:
        used_ids = set(batch["id"].astype(str))
        remainder = pool[~pool["id"].astype(str).isin(used_ids)]
        topup = min(args.target - len(batch), len(remainder))
        if topup > 0:
            batch = pd.concat(
                [batch, remainder.sample(n=topup, random_state=seed)],
                ignore_index=True
            )

    # Final shuffle
    batch = batch.sample(frac=1, random_state=seed).reset_index(drop=True)

    # Format for HITL rater
    out = pd.DataFrame({
        "id": batch["id"],
        "full_text": batch["text"],
        "target_entity": batch["target_entity"],
        "entity_category": batch["entity_category"],
        "source_kind": batch["source_kind"],
        "parent_id": batch["parent_id"] if "parent_id" in batch.columns else None,
        "link_id": batch["link_id"] if "link_id" in batch.columns else None,
        "human_label": None,
        "notes": None,
        "rater_id": None,
    })

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"\nSaved {len(out):,} rows → {args.out}")
    print("\nEntity category breakdown:")
    print(out["entity_category"].value_counts().to_string())
    print("\nTop entities by row count:")
    print(out["target_entity"].value_counts().head(30).to_string())


if __name__ == "__main__":
    main()
