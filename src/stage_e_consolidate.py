"""True Stage E: final consolidation of the entire entity-curation pipeline
(ANTIGRAVITY_HANDOFF.md §12, steps 1-11) into one file for Nash's HITL pass.

Precedence rules for the final bucket guess:
1. If the entity is one of the known ambiguous bare-name clusters (bill,
   hunter, kennedy, clinton, sanders, rich, tucker) -- don't give it a
   single bucket at all. Bare "Bill" isn't one person. Instead attach a
   disambiguation summary from Stage C's per-instance classifications
   (e.g. "43% Bill Gates, 39% Bill Clinton, 18% Bill Kristol, unresolved
   rest") so a human reviewer understands it's a mixed-referent entity,
   not a single candidate to accept/reject.
2. Otherwise, prefer the Wikipedia-categories bucket guess IF backed by
   2+ independently-matching categories (the "reliable" tier from step 11
   -- single-category matches were confirmed unreliable: Bin Laden, Nixon,
   Giuliani, Michael Flynn all got wrongly bucketed maverick_authority via
   one incidental category each).
3. Fall back to the description-text bucket guess (tier1_bucket_guess) if
   categories didn't produce a reliable match.
4. Otherwise, if categories matched via only 1 category, keep it but mark
   confidence as "weak_hint" rather than "reliable".
5. Otherwise unresolved -- still include the entity with whatever identity
   info exists (wp_title/wp_description/corpus example) for manual review.

Output: data/processed/entity_final_review.csv
"""
import pandas as pd

TIER1_PATH = "data/processed/entity_wikidata_tier1.csv"
STAGE_D_PATH = "data/processed/stage_d_resolved.csv"
DISAMBIG_REFINE_PATH = "data/processed/entity_disambiguation_refined.csv"
STAGE_A_PATH = "data/processed/entity_stage_a_filtered.csv"
STAGE_C_PATH = "data/processed/entity_disambiguation_classified.csv"
STAGE_E_CATEGORIES_PATH = "data/processed/stage_e_category_buckets.csv"
CONTEXT_WINDOWS_PATH = "data/processed/entity_context_windows.csv"
OUT_PATH = "data/processed/entity_final_review.csv"

AMBIGUOUS_CLUSTER_ENTITIES = {"bill", "hunter", "kennedy", "clinton", "sanders", "rich", "tucker"}


def build_disambiguation_summaries():
    """From Stage C's per-instance classifications, build a human-readable
    summary per ambiguous cluster: "43% Bill Gates, 39% Bill Clinton, 18%
    Bill Kristol, N unresolved of M total"."""
    df = pd.read_csv(STAGE_C_PATH)
    summaries = {}
    for cluster, g in df.groupby("cluster"):
        total = len(g)
        counts = g["classified_as"].fillna("unresolved").replace("", "unresolved").value_counts()
        parts = []
        for name, n in counts.items():
            if name == "unresolved":
                continue
            parts.append(f"{n/total*100:.0f}% {name} (n={n})")
        n_unresolved = counts.get("unresolved", 0)
        parts.append(f"{n_unresolved/total*100:.0f}% unresolved (n={n_unresolved})")
        summaries[cluster] = f"AMBIGUOUS NAME, mixed referents: " + ", ".join(parts) + f" [of {total} sampled mentions]"
    return summaries


def main():
    t1 = pd.read_csv(TIER1_PATH, on_bad_lines="skip", engine="python")
    d = pd.read_csv(STAGE_D_PATH, on_bad_lines="skip", engine="python")
    base = pd.concat([t1, d], ignore_index=True)
    base = base.drop_duplicates(subset=["entity"], keep="first")
    print(f"Base entity list: {len(base)}")

    # disambiguation refinement: use refined_title when it's a sane,
    # confident re-resolution of a disambiguation-page match
    refine = pd.read_csv(DISAMBIG_REFINE_PATH, on_bad_lines="skip", engine="python")
    refine_map = refine.set_index("entity")[["refined_title", "refined_confident_sane"]].to_dict("index")

    def better_identity(row):
        r = refine_map.get(row["entity"])
        if r and r.get("refined_confident_sane") and r.get("refined_title"):
            return r["refined_title"]
        return row["wp_title"]

    base["best_identity"] = base.apply(better_identity, axis=1)

    # Stage A junk/dual-purpose flags (only covers the entities that were
    # still unbucketed at that point -- left join, missing = not flagged)
    stage_a = pd.read_csv(STAGE_A_PATH, on_bad_lines="skip", engine="python")
    stage_a_map = stage_a.set_index("entity")[["likely_pure_junk", "dual_purpose_word"]].to_dict("index")
    base["likely_pure_junk"] = base["entity"].map(lambda e: stage_a_map.get(e, {}).get("likely_pure_junk", False))
    base["dual_purpose_word"] = base["entity"].map(lambda e: stage_a_map.get(e, {}).get("dual_purpose_word", False))

    # category-based bucket guess with the 2+ reliability threshold
    cats = pd.read_csv(STAGE_E_CATEGORIES_PATH, on_bad_lines="skip", engine="python")
    cats = cats.drop_duplicates(subset=["entity"], keep="first")
    cats_map = cats.set_index("entity")[["category_bucket_guess", "category_bucket_n_matches"]].to_dict("index")

    def resolve_bucket(row):
        entity_key = str(row["entity"]).lower()
        if entity_key in AMBIGUOUS_CLUSTER_ENTITIES:
            return "AMBIGUOUS_CLUSTER", "n/a"
        c = cats_map.get(row["entity"], {})
        cat_bucket = c.get("category_bucket_guess", "")
        cat_n = c.get("category_bucket_n_matches", 0)
        desc_bucket = row.get("tier1_bucket_guess", "")
        if cat_bucket and cat_n >= 2:
            return cat_bucket, "reliable_categories"
        if isinstance(desc_bucket, str) and desc_bucket:
            return desc_bucket, "reliable_description"
        if cat_bucket and cat_n == 1:
            return cat_bucket, "weak_hint_single_category"
        return "", "unresolved"

    resolved = base.apply(resolve_bucket, axis=1)
    base["final_bucket_guess"] = resolved.map(lambda x: x[0])
    base["bucket_confidence"] = resolved.map(lambda x: x[1])

    # disambiguation summaries for the 7 known ambiguous cluster entities
    summaries = build_disambiguation_summaries()
    base["disambiguation_note"] = base["entity"].map(
        lambda e: summaries.get(str(e).lower(), ""))

    # corpus context (properly-centered windows, not the earlier flawed
    # first-200-chars version)
    ctx = pd.read_csv(CONTEXT_WINDOWS_PATH, on_bad_lines="skip", engine="python")
    ctx = ctx.drop_duplicates(subset=["entity"], keep="first")
    ctx_map = ctx.set_index("entity")["examples"].to_dict()
    base["corpus_example"] = base["entity"].map(lambda e: ctx_map.get(e, ""))

    base["final_decision"] = ""  # blank for Nash's HITL pass

    out_cols = ["entity", "doc_count", "best_identity", "wp_description",
                "final_bucket_guess", "bucket_confidence", "disambiguation_note",
                "likely_pure_junk", "dual_purpose_word", "corpus_example",
                "in_candidate_list", "final_decision"]
    out = base[[c for c in out_cols if c in base.columns]]
    out = out.sort_values("doc_count", ascending=False)
    out.to_csv(OUT_PATH, index=False)

    print(f"\nSaved {len(out)} rows to {OUT_PATH}")
    print(f"\nbucket_confidence breakdown:")
    print(out["bucket_confidence"].value_counts().to_string())
    print(f"\nfinal_bucket_guess breakdown (excluding ambiguous clusters/unresolved):")
    print(out[~out.final_bucket_guess.isin(["", "AMBIGUOUS_CLUSTER"])]["final_bucket_guess"].value_counts().to_string())
    print(f"\nlikely_pure_junk: {out['likely_pure_junk'].sum()}")
    print(f"ambiguous cluster entities (see disambiguation_note): "
          f"{(out.final_bucket_guess=='AMBIGUOUS_CLUSTER').sum()}")


if __name__ == "__main__":
    main()
