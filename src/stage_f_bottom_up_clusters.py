"""Bottom-up categorical clustering, complementing the top-down keyword-rule
bucketing (stage_e_wikipedia_categories.py's CATEGORY_BUCKET_RULES, which
reflects assumptions about which categories matter, hand-written in
advance). This instead asks: what groupings emerge from the category data
itself, for the residual that top-down rules didn't confidently bucket?

Method (deliberately simple/interpretable over black-box clustering, same
philosophy as Stage C's signature-words approach -- a human should be able
to audit *why* an entity landed in a cluster):
1. Compute each substantive category's document frequency (how many
   distinct entities carry it) across the whole resolved population.
2. Keep only "informative" categories: frequent enough to represent a real
   recurring type (>=5 entities), not so frequent they're uninformative
   (<=500 entities -- "Living people"-style near-universal tags already
   got stripped as maintenance categories, but plenty of substantive ones
   like "American writers" are still too generic to be a useful cluster).
3. For each entity, assign it to the cluster of its RAREST informative
   category (rarest = most specific/discriminating). This produces
   human-readable cluster labels for free (the category name itself) and
   avoids needing to pick a K or interpret a black-box cluster ID.
4. Report the largest emergent clusters for human inspection -- some will
   obviously map onto the existing 8-bucket taxonomy (fold in
   automatically), others may reveal categories worth adding real rules
   for, or fine-grained subtypes worth keeping separate (e.g. "COVID-19
   conspiracy theorists" vs "9/11 conspiracy theorists" as distinct
   sub-populations of maverick_authority).

Scope: the still-unresolved residual from entity_final_review.csv, since
that's what needs narrowing -- already-bucketed entities don't need this.

Output: data/processed/stage_f_bottom_up_clusters.csv
"""
import re
from collections import Counter, defaultdict

import pandas as pd

FINAL_REVIEW_PATH = "data/processed/entity_final_review.csv"
CATEGORIES_PATH = "data/processed/stage_e_category_buckets.csv"
OUT_PATH = "data/processed/stage_f_bottom_up_clusters.csv"

MIN_CLUSTER_DF = 5      # category must cover at least this many entities
MAX_CLUSTER_DF = 500    # above this, too generic to be a useful cluster

# Stage E's MAINTENANCE_PATTERNS filter turned out incomplete -- running
# the clustering surfaced a much bigger universe of Wikipedia internal
# editorial/tracking categories than anticipated (dated "Use American
# English from <month>" tags, "Commons link from Wikidata", "Official
# website (not) in Wikidata", "Coordinates not on Wikidata", "accuracy
# disputes", "Harv and Sfn no-target errors", "Monitored short pages",
# "Pages including recorded pronunciations", "Pages containing links to
# subscription-only content"). Applied as a SECOND, stronger local filter
# on top of Stage E's already-saved (but under-filtered) output -- no
# re-fetch from Wikipedia needed, this is pure text filtering.
EXTRA_MAINTENANCE_PATTERNS = re.compile(
    r"use \w+ english|commons link|official website|coordinates not|"
    r"accuracy disputes|harv and sfn|monitored short pages|"
    r"recorded pronunciations|subscription-only|no-target errors|"
    r"source attribution",
    re.IGNORECASE,
)

# Categories signaling "this is a generic name-etymology or disambiguation
# page, not a specific person/org" -- confirmed as the single largest
# pattern in the unresolved residual (Human name disambiguation pages,
# Surnames, Masculine/feminine given names, Ship/Educational institution/
# Broadcast call sign/Language and nationality disambiguation pages, etc.)
# Treated as its own signal (same underlying problem as the Bill/Hunter/
# Clinton clusters built in Stage B/C) rather than noise or real content.
AMBIGUOUS_NAME_PATTERNS = re.compile(
    r"disambiguation pages?|^surnames$|given names?$|hypocorisms|"
    r"nicknames|patronymic|matronymic",
    re.IGNORECASE,
)


def main():
    review = pd.read_csv(FINAL_REVIEW_PATH, on_bad_lines="skip", engine="python")
    unresolved = review[review["bucket_confidence"] == "unresolved"].copy()
    print(f"{len(unresolved)} unresolved entities to cluster")

    cats = pd.read_csv(CATEGORIES_PATH, on_bad_lines="skip", engine="python")
    cats = cats.drop_duplicates(subset=["entity"], keep="first")
    cats_map = cats.set_index("entity")["substantive_categories_str"].to_dict()

    def clean_and_split(raw):
        cats = str(raw).split("; ") if raw else []
        return [c for c in cats if not EXTRA_MAINTENANCE_PATTERNS.search(c)]

    unresolved = unresolved.copy()
    unresolved["categories"] = unresolved["entity"].map(lambda e: clean_and_split(cats_map.get(e, "")))
    has_cats = unresolved[unresolved["categories"].map(len) > 0].copy()
    print(f"{len(has_cats)} of those have at least one substantive category "
          f"after the strengthened maintenance filter")

    # split off the ambiguous-name-signal population first -- these aren't
    # a "real" content cluster, they're "this bare name has no single
    # dominant referent findable via Wikipedia search", same underlying
    # issue as Bill/Hunter/Clinton (built as explicit clusters in Stage
    # B/C) just without a hand-built cluster for this specific name yet.
    def is_ambiguous_name(cat_list):
        return any(AMBIGUOUS_NAME_PATTERNS.search(c) for c in cat_list)

    has_cats["ambiguous_name_signal"] = has_cats["categories"].map(is_ambiguous_name)
    ambiguous_pool = has_cats[has_cats["ambiguous_name_signal"]]
    content_pool = has_cats[~has_cats["ambiguous_name_signal"]].copy()
    print(f"{len(ambiguous_pool)} flagged as likely-ambiguous bare names "
          f"(same pattern as Bill/Hunter/Clinton, no hand-built cluster yet)")
    print(f"{len(content_pool)} remain for genuine content clustering")

    # document frequency across the content-only population
    df_counts = Counter()
    for cat_list in content_pool["categories"]:
        for c in set(cat_list):
            if not AMBIGUOUS_NAME_PATTERNS.search(c):
                df_counts[c] += 1

    informative = {c for c, n in df_counts.items() if MIN_CLUSTER_DF <= n <= MAX_CLUSTER_DF}
    print(f"{len(informative)} categories qualify as 'informative' clusters "
          f"(cover {MIN_CLUSTER_DF}-{MAX_CLUSTER_DF} entities each)")

    def assign_cluster(cat_list):
        candidates = [c for c in cat_list if c in informative]
        if not candidates:
            return ""
        return min(candidates, key=lambda c: df_counts[c])

    content_pool["natural_cluster"] = content_pool["categories"].map(assign_cluster)
    clustered = content_pool[content_pool["natural_cluster"] != ""]
    print(f"\n{len(clustered)} entities assigned to a natural content cluster "
          f"({len(content_pool)-len(clustered)} had categories but none qualified as informative)")

    ambiguous_pool = ambiguous_pool.copy()
    ambiguous_pool["natural_cluster"] = "AMBIGUOUS_NAME_LIKE_BILL_HUNTER"
    clustered = pd.concat([clustered, ambiguous_pool], ignore_index=True)

    cluster_sizes = clustered["natural_cluster"].value_counts()
    print(f"\n{len(cluster_sizes)} distinct natural clusters, top 40 by size:")
    print(cluster_sizes.head(40).to_string())

    out_cols = ["entity", "doc_count", "best_identity", "natural_cluster"]
    out = clustered[out_cols].sort_values(["natural_cluster", "doc_count"], ascending=[True, False])
    out.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(out)} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()
