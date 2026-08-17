"""build_author_entity_stance_ledger.py

Per-author x per-entity stance ledger -- infrastructure for the
author-pattern question Nash raised 2026-08-18: what does an individual
commenter's stance look like across the specific entities they mention
most, and how does that vary/correlate across authors and across entities
(believer/debunker being just one candidate axis, not the only one worth
looking for). Deliberately NOT an analysis script -- it only assembles the
raw (author, entity, stance, source) observations. Pattern-mining on top of
this is explicitly out of scope here per Nash's caution against greedily
grabbing whatever correlation shows up first or presuming the relationship
form in advance.

Three label sources, kept distinguishable (never collapsed into one
"stance" column without provenance) because they carry different trust
levels -- explicit ask: don't lean on raw classifier self-confidence as if
it were as solid as a human or frontier-judge call:
  - "human": HITL-labeled rows from the canonical training parquet
    (is_human=True). Highest trust. No comment `id` is stored in that
    parquet, so these are joined back to the source corpora by exact
    (text, target_entity) match to recover id/author/created_utc.
  - "frontier_judge": round9's frontier-AI escalation pass
    (round9_all_for_frontier_with_context.csv joined to
    round9_frontier_scored_with_context.csv / round9_epistemic_frontier_scored.csv
    by id) -- a real independent second-opinion call on rows the
    ensemble itself flagged as uncertain, not a self-rated score.
  - "ensemble": round9_pool_continuous_scores.csv, the 8-model ensemble's
    own prediction across the full round9 pool. Lowest trust of the
    three -- kept and tagged, not dropped, since Nash wants to "see what
    might correlate," but any downstream analysis should weight/filter
    this tier deliberately rather than pooling it with the other two.

Designed to be appended to, not treated as a finished artifact: as the
full-cascade inference (build_full_entity_mention_pool.py's pool, scored
by the eventual cascade) lands, its output should be unioned in here with
its own label_source tag (e.g. "cascade_confidence_filtered") rather than
rebuilding this from scratch.

Output: data/processed/author_entity_stance_ledger.parquet
Columns: id, author, target_entity, entity_category, stance_label,
         stance_score, label_source, created_utc
stance_label is the discrete hostile/endorsement/other call (human and
ensemble tiers). stance_score is a continuous -1..1 signal (frontier_judge
tier only, from round9's frontier_score -- 0.5=lean endorsement,
-0.5=lean hostile, +-1=confident, per that pipeline's own scale). Kept as
two separate columns rather than one mixed-type "stance" column -- pyarrow
can't serialize a column holding both strings and floats.
"""
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

LONG_CORPUS = "data/processed/empath_scores_full_mapped.parquet"
SHORT_CORPUS = "data/processed/conspiracy_comments_short_lte100chars_mapped.parquet"
TRAINING_PARQUET = "data/processed/stance_classifier_training_data_round10_truncation_fixed.parquet"
FRONTIER_CONTEXT = "data/processed/round9/round9_all_for_frontier_with_context.csv"
FRONTIER_SCORES = [
    "data/processed/round9/round9_frontier_scored_with_context.csv",
    "data/processed/round9/round9_epistemic_frontier_scored.csv",
]
ENSEMBLE_SCORES = "data/processed/round9/round9_pool_continuous_scores.csv"
OUT_PATH = "data/processed/author_entity_stance_ledger.parquet"


def _recover_author_by_text(con, texts_entities: pd.DataFrame) -> pd.DataFrame:
    """Join (text, target_entity) rows back to the source corpora on exact
    text match to recover id/author/created_utc. Training data doesn't
    carry a comment id at all, so this is the only way back to author for
    the human-labeled tier."""
    con.register("te", texts_entities)
    matched = con.execute(f"""
        SELECT te.text, te.target_entity, te.label,
               c.id, c.author, c.created_utc
        FROM te
        JOIN (
            SELECT id, author, created_utc, text FROM read_parquet('{LONG_CORPUS}')
            UNION ALL
            SELECT id, author, created_utc, text FROM read_parquet('{SHORT_CORPUS}')
        ) c ON c.text = te.text
    """).df()
    con.unregister("te")
    # A given text could in principle match multiple rows (rare duplicate
    # comments) -- keep the first, this is a best-effort recovery join,
    # not a guarantee of uniqueness.
    matched = matched.drop_duplicates(subset=["text", "target_entity"])
    return matched


def build_human_tier(con) -> pd.DataFrame:
    df = pd.read_parquet(TRAINING_PARQUET)
    human = df[df["is_human"] == True][["text", "target_entity", "label"]].copy()
    human = human.dropna(subset=["text", "target_entity"])
    print(f"  {len(human):,} human-labeled rows to recover author for", flush=True)
    matched = _recover_author_by_text(con, human)
    print(f"  {len(matched):,} recovered with author ({len(matched)/max(len(human),1):.1%} match rate)", flush=True)
    matched["entity_category"] = None
    matched["stance_label"] = matched["label"]
    matched["stance_score"] = float("nan")
    matched["label_source"] = "human"
    return matched[["id", "author", "target_entity", "entity_category", "stance_label", "stance_score", "label_source", "created_utc"]]


def build_frontier_tier(con) -> pd.DataFrame:
    ctx = pd.read_csv(FRONTIER_CONTEXT, usecols=["id", "text", "target_entity"])
    scores = []
    for f in FRONTIER_SCORES:
        try:
            scores.append(pd.read_csv(f))
        except FileNotFoundError:
            continue
    if not scores:
        return pd.DataFrame(columns=["id", "author", "target_entity", "entity_category", "stance_label", "stance_score", "label_source", "created_utc"])
    scored = pd.concat(scores, ignore_index=True).drop_duplicates(subset=["id"])
    merged = ctx.merge(scored, on="id", how="inner")
    print(f"  {len(merged):,} frontier-judge-scored rows", flush=True)

    con.register("fj", merged[["id"]])
    ids = con.execute(f"""
        SELECT c.id, c.author, c.created_utc
        FROM (
            SELECT id, author, created_utc FROM read_parquet('{LONG_CORPUS}')
            UNION ALL
            SELECT id, author, created_utc FROM read_parquet('{SHORT_CORPUS}')
        ) c
        JOIN fj ON fj.id = c.id
    """).df()
    con.unregister("fj")
    merged = merged.merge(ids, on="id", how="inner")
    merged["entity_category"] = None
    merged["stance_label"] = None
    merged["stance_score"] = merged["frontier_score"].astype(float)
    merged["label_source"] = "frontier_judge"
    return merged[["id", "author", "target_entity", "entity_category", "stance_label", "stance_score", "label_source", "created_utc"]]


def build_ensemble_tier(con) -> pd.DataFrame:
    df = pd.read_csv(ENSEMBLE_SCORES)
    print(f"  {len(df):,} ensemble-scored rows (full round9 pool)", flush=True)
    con.register("ens", df[["id"]])
    ids = con.execute(f"""
        SELECT c.id, c.author, c.created_utc
        FROM (
            SELECT id, author, created_utc FROM read_parquet('{LONG_CORPUS}')
            UNION ALL
            SELECT id, author, created_utc FROM read_parquet('{SHORT_CORPUS}')
        ) c
        JOIN ens ON ens.id = c.id
    """).df()
    con.unregister("ens")
    df = df.merge(ids, on="id", how="inner")
    df["stance_label"] = df["pred_label"]
    df["stance_score"] = df["signed_score"].astype(float) if "signed_score" in df.columns else float("nan")
    df["label_source"] = "ensemble"
    return df[["id", "author", "target_entity", "entity_category", "stance_label", "stance_score", "label_source", "created_utc"]]


def main():
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='4GB'")

    print("=== human tier (HITL-labeled training data) ===", flush=True)
    human = build_human_tier(con)

    print("\n=== frontier_judge tier (round9 escalation pass) ===", flush=True)
    frontier = build_frontier_tier(con)

    print("\n=== ensemble tier (round9 full-pool ensemble predictions) ===", flush=True)
    ensemble = build_ensemble_tier(con)

    ledger = pd.concat([human, frontier, ensemble], ignore_index=True)
    ledger = ledger.dropna(subset=["author"])
    ledger = ledger[ledger["author"] != "[deleted]"]

    Path(OUT_PATH).parent.mkdir(parents=True, exist_ok=True)
    ledger.to_parquet(OUT_PATH, index=False)
    print(f"\nSaved {len(ledger):,} rows to {OUT_PATH}", flush=True)
    print("\nBy label_source:")
    print(ledger["label_source"].value_counts().to_string())
    print(f"\nDistinct authors: {ledger['author'].nunique():,}")
    print(f"Distinct entities: {ledger['target_entity'].nunique():,}")
    print("\nAuthors with >=5 distinct entities mentioned (real cross-entity signal):")
    per_author_entities = ledger.groupby("author")["target_entity"].nunique()
    print(f"  {(per_author_entities >= 5).sum():,} authors")


if __name__ == "__main__":
    main()
