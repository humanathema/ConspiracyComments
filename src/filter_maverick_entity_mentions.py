"""Stage-1 cheap filter: does a comment mention any candidate maverick-authority
entity? Meant to run before the heavier FactAppeal/semantic pass (see
ANTIGRAVITY_HANDOFF.md §8b) — narrows a large corpus down to a mention-positive
candidate pool fast, using plain substring matching (no NER at scoring time,
NER already happened once to build the entity list).

Entity list defaults to data/processed/maverick_authority_entities.csv,
thresholded by min_mentions/min_lift. That file is machine-ranked, not
manually curated (see handoff §10) — swap in a curated list by pointing
--entities at a different CSV with an `entity` column once one exists.

Usage:
    python src/filter_maverick_entity_mentions.py \\
        --input data/processed/empath_scores_full.parquet \\
        --output data/processed/maverick_entity_mention_candidates.parquet \\
        --min-mentions 2 --min-lift 1.0
"""
import argparse
import re
import time
import pandas as pd
import pyarrow.parquet as pq


def build_pattern(entities_path, min_mentions, min_lift):
    ents = pd.read_csv(entities_path)
    ents = ents[(ents["positive_mentions"] >= min_mentions) & (ents["lift"] >= min_lift)]
    names = sorted(ents["entity"].astype(str).unique(), key=len, reverse=True)
    if not names:
        raise ValueError("No entities survived the threshold — loosen --min-mentions/--min-lift")
    escaped = [re.escape(n) for n in names]
    pattern = re.compile(r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE)
    return pattern, names


def evaluate_against_hitl(pattern, queue_path="data/hitl/queue_maverick_authority.csv"):
    """Sanity check: how well does 'any entity mention' predict the human label?"""
    from sklearn.metrics import precision_score, recall_score, cohen_kappa_score
    df = pd.read_csv(queue_path)
    y_true = df["human_label"].astype(str).str.lower().isin(["positive", "lean_positive"]).astype(int)
    y_pred = df["full_text"].fillna("").apply(lambda t: bool(pattern.search(t))).astype(int)
    print(f"HITL sanity check (n={len(df)}): "
          f"precision={precision_score(y_true, y_pred, zero_division=0):.3f} "
          f"recall={recall_score(y_true, y_pred, zero_division=0):.3f} "
          f"kappa={cohen_kappa_score(y_true, y_pred):.3f} "
          f"flagged={y_pred.sum()}/{len(df)}")


def run(input_path, output_path, pattern, chunk_size=500_000):
    pf = pq.ParquetFile(input_path)
    total = 0
    matched_frames = []
    start = time.time()
    for i, batch in enumerate(pf.iter_batches(batch_size=chunk_size, columns=["id", "text"])):
        chunk = batch.to_pandas()
        total += len(chunk)
        hit = chunk["text"].fillna("").apply(lambda t: bool(pattern.search(t)))
        matched_frames.append(chunk.loc[hit, ["id"]])
        print(f"  chunk {i+1}: {len(chunk):,} rows, {hit.sum():,} matched "
              f"(cumulative {total:,})")
    out = pd.concat(matched_frames, ignore_index=True) if matched_frames else pd.DataFrame(columns=["id"])
    out.to_parquet(output_path, index=False)
    elapsed = time.time() - start
    print(f"\nDone: {len(out):,}/{total:,} rows matched ({len(out)/total*100:.2f}%) "
          f"in {elapsed/60:.1f} min. Saved to {output_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--entities", default="data/processed/maverick_authority_entities.csv")
    ap.add_argument("--min-mentions", type=int, default=2)
    ap.add_argument("--min-lift", type=float, default=1.0)
    ap.add_argument("--input", default="data/processed/empath_scores_full.parquet")
    ap.add_argument("--output", default="data/processed/maverick_entity_mention_candidates.parquet")
    ap.add_argument("--check-only", action="store_true",
                     help="Just run the HITL sanity check, don't scan the full corpus")
    args = ap.parse_args()

    pattern, names = build_pattern(args.entities, args.min_mentions, args.min_lift)
    print(f"{len(names)} entities in filter pattern: {names[:15]}{'...' if len(names) > 15 else ''}")
    evaluate_against_hitl(pattern)

    if not args.check_only:
        run(args.input, args.output, pattern)
