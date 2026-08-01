"""Deterministic entity-dedup pass over the bottom-up NER candidate pool.

Context: an AIITL judge (Qwen2.5-1.5B-Instruct, tobiasnashktc/entity-coverage-
aiitl-judge) found 42.7% of a 5,000-row sample from corpus_entity_frequency.csv
was "duplicate_variant_needs_merging" -- but its free-text `reason` field is
not reliable as a machine-actionable merge target (e.g. it called "MSM" a
misspelling of "media services", "Wikipedia" a misspelling of "encyclopedia",
"NYT" a misspelling of "New York Times" -- backwards, NYT is an abbreviation,
not a misspelling). Using that text to drive automated merges would introduce
wrong merges.

This script instead does the safe, unambiguous part mechanically: group
entities that are identical after case-folding and punctuation stripping
(e.g. "Covid" / "COVID" / "covid" / "Covid.") -- no LLM judgment involved,
no risk of a wrong semantic merge, since these are the same string by
construction. Abbreviation/acronym expansion (MSM -> mainstream media, NYT ->
New York Times) is a genuinely harder problem needing real-world knowledge,
not string similarity -- deliberately out of scope here, left as a separate
task for human/LLM review, not force-fit into this mechanical pass.

Input: data/processed/corpus_entity_frequency.csv (683,635 rows)
Output:
  data/processed/entity_canonical_map.csv -- one row per original entity
    string, with its assigned canonical form and cluster id.
  data/processed/entity_canonical_aggregated.csv -- one row per canonical
    form, doc_count summed across all variants in its cluster.
"""
import re

import pandas as pd

IN_PATH = "data/processed/corpus_entity_frequency.csv"
MAP_OUT_PATH = "data/processed/entity_canonical_map.csv"
AGG_OUT_PATH = "data/processed/entity_canonical_aggregated.csv"

_PUNCT_RE = re.compile(r"[^a-z0-9 ]")


def normalize(entity: str) -> str:
    stripped = _PUNCT_RE.sub("", str(entity).lower().strip())
    # Collapse whatever whitespace is left over from removed characters (e.g.
    # a 3-word all-Unicode-symbol string becomes "  " -- two bare spaces --
    # not "", so a naive emptiness check on the un-collapsed string misses it)
    # and strip again so "   " normalizes to "" like a single symbol does.
    return re.sub(r"\s+", " ", stripped).strip()


def main():
    df = pd.read_csv(IN_PATH, low_memory=False)
    df["norm"] = df["entity"].map(normalize)

    # Guard against false clustering: the normalizer strips everything outside
    # [a-z0-9 ], so emoji, Cyrillic/Arabic script, box-drawing characters, and
    # Unicode "mathematical alphanumeric" stylized text (used to fake bold/
    # italic Latin letters, e.g. stylized "Trump") all collapse to an empty
    # string -- which would otherwise group hundreds of unrelated entities
    # into one fake "cluster" keyed on "". Anything that normalizes to empty
    # keeps its own original string as its norm key instead, so it's never
    # merged with anything else.
    empty_mask = df["norm"].str.len() == 0
    df.loc[empty_mask, "norm"] = "__no_ascii__" + df.loc[empty_mask, "entity"].astype(str)

    # Canonical form = the variant with the highest doc_count in its cluster
    # (the most-used spelling is the most useful label for downstream joins).
    canonical_by_norm = (
        df.sort_values("doc_count", ascending=False)
        .drop_duplicates("norm")
        .set_index("norm")["entity"]
    )
    df["canonical_entity"] = df["norm"].map(canonical_by_norm)
    df["cluster_size"] = df.groupby("norm")["entity"].transform("size")

    df[["entity", "label", "doc_count", "norm", "canonical_entity", "cluster_size"]].to_csv(
        MAP_OUT_PATH, index=False
    )

    agg = (
        df.groupby("canonical_entity")
        .agg(
            doc_count=("doc_count", "sum"),
            n_variants=("entity", "nunique"),
            labels=("label", lambda s: "|".join(sorted(set(s.astype(str))))),
        )
        .reset_index()
        .sort_values("doc_count", ascending=False)
    )
    agg.to_csv(AGG_OUT_PATH, index=False)

    n_merged_groups = (df["cluster_size"] > 1).sum()
    n_clusters_with_dupes = (df.groupby("norm").size() > 1).sum()
    print(f"Input rows: {len(df):,}")
    print(f"Rows belonging to a multi-variant cluster: {n_merged_groups:,}")
    print(f"Distinct clusters with >1 variant: {n_clusters_with_dupes:,}")
    print(f"Output entity count after canonicalization: {len(agg):,}")
    print(f"Reduction: {len(df):,} -> {len(agg):,} ({(1 - len(agg) / len(df)):.1%} fewer distinct strings)")


if __name__ == "__main__":
    main()
