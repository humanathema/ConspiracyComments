"""build_entity_description_lookup.py

Stage 2 of the cascade rebuild: a short background description per verified
maverick/consensus entity, meant to be concatenated into the classifier's
input text alongside the target entity (e.g. "[ENTITY: Kary Mullis --
American biochemist, Nobel laureate, HIV/AIDS denialist] <comment text>")
so the model isn't inferring who someone is purely from context windows
that may never explain it.

Two sources, kept distinguishable via a `source` column -- never blended
silently, since one is externally verifiable and the other isn't:
  - "wikipedia": entity_wikidata_tier1.csv's wp_description field (a real
    Wikipedia short-description string, already fetched and stored by
    earlier project work). Matched directly, then by stripping a
    parenthetical disambiguator off either side (e.g. "William Binney
    (intelligence official)" vs plain "William Binney").
  - "claude_general_knowledge": for the entities Wikidata coverage missed
    (mostly the original-11 already-established entities like Assange/
    Snowden that predate this project's Wikidata tooling, plus some
    fringe figures). Hand-written from general knowledge, NOT independently
    verified against a source -- flagged as such so anyone reviewing the
    training data (or the classifier's behavior) knows which entities'
    "background" is Wikipedia-grounded and which is a model's own recall,
    which could be wrong or dated.

Domains use domain_classification_lookup.csv's category/mbfc_reliability_label
fields instead of a free-text description (no natural-language source
exists for these) -- source tag "domain_metadata".

Output: data/processed/entity_description_lookup.csv
Columns: entity, category, description, source
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from pull_hitl_val_batch import build_person_entities, build_domain_entities

WIKIDATA_PATH = "/Volumes/NO NAME/processed/entity_wikidata_tier1.csv"
DOMAIN_LOOKUP_PATH = "data/processed/domain_classification_lookup.csv"
OUT_PATH = "data/processed/entity_description_lookup.csv"

# Hand-written fallback for entities entity_wikidata_tier1.csv doesn't
# cover -- mostly the original-11 (predate the project's Wikidata tooling)
# plus a handful of fringe figures. NOT independently verified against a
# source; see module docstring. Kept short and factual (occupation/claim
# to fame), not evaluative.
CLAUDE_KNOWLEDGE_FALLBACK = {
    "Assange": "Julian Assange, founder of WikiLeaks, published leaked government and diplomatic documents.",
    "Snowden": "Edward Snowden, former NSA contractor who leaked classified US surveillance program documents in 2013.",
    "Mark Sargent": "Prominent Flat Earth movement proponent and YouTube figure.",
    "Jim Caviezel": "Actor known for playing Jesus in The Passion of the Christ; has promoted QAnon-adjacent claims.",
    "Erin Brockovich": "American legal clerk and environmental activist, subject of the film bearing her name.",
    "Brian Cox": "British physicist and science broadcaster (distinct from the Succession actor of the same name).",
    "America's Frontline Doctors": "US physician group formed in 2020 promoting unproven COVID-19 treatments and vaccine skepticism.",
    "Lara Logan": "Former CBS/Fox News correspondent who has promoted conspiracy theories since leaving mainstream journalism.",
    "Charlie Ward": "British former football player turned QAnon-adjacent conspiracy commentator.",
    "Jay Weidner": "American author and filmmaker on alternative history and conspiracy topics (e.g. Kubrick moon-landing claims).",
    "Michael Cremo": "Author of 'Forbidden Archeology', arguing for a much older human presence than mainstream archaeology accepts.",
    "Massimo Mazzucco": "Italian filmmaker and 9/11 truth movement / moon-landing-hoax proponent.",
    "Pilots for 9/11 Truth": "Organization of pilots disputing the official account of the September 11 attacks.",
    "Ron Wyatt": "American amateur archaeologist known for disputed biblical-artifact discovery claims (e.g. Noah's Ark, Ark of the Covenant).",
    "Rhonda Patrick": "American biomedical scientist and health/nutrition podcaster.",
    "Dan Bilzerian": "American social-media personality and poker player known for a lavish lifestyle persona.",
}


def _lookup_wikidata(names):
    wd = pd.read_csv(WIKIDATA_PATH)
    exact = wd.set_index(wd["entity"].str.lower())["wp_description"].to_dict()
    by_title = wd.set_index(wd["wp_title"].astype(str).str.lower())["wp_description"].to_dict()

    rows = []
    for n in names:
        low = n.lower()
        base = n.split(" (")[0].strip().lower()
        desc = exact.get(low) or exact.get(base) or by_title.get(low) or by_title.get(base)
        if desc:
            rows.append((n, desc, "wikipedia"))
    return rows


def build_person_rows():
    persons = build_person_entities()
    names = [n for n, _, _ in persons]
    cats = {n: c for n, _, c in persons}

    wiki_rows = _lookup_wikidata(names)
    covered = {n for n, _, _ in wiki_rows}

    rows = []
    for n, desc, src in wiki_rows:
        rows.append({"entity": n, "category": cats[n], "description": desc, "source": src})

    missing = [n for n in names if n not in covered]
    still_missing = []
    for n in missing:
        fallback = CLAUDE_KNOWLEDGE_FALLBACK.get(n) or CLAUDE_KNOWLEDGE_FALLBACK.get(n.split(" (")[0].strip())
        if fallback:
            rows.append({"entity": n, "category": cats[n], "description": fallback, "source": "claude_general_knowledge"})
        else:
            still_missing.append(n)

    if still_missing:
        print(f"  WARNING: {len(still_missing)} person entities have no description at all: {still_missing}")
    return rows


def build_domain_rows():
    domains = build_domain_entities()
    names = [n for n, _, _ in domains]
    cats = {n: c for n, _, c in domains}
    lookup = pd.read_csv(DOMAIN_LOOKUP_PATH).set_index("domain")

    rows = []
    for n in names:
        if n in lookup.index:
            r = lookup.loc[n]
            cat = r["category"] if pd.notna(r["category"]) else "unknown category"
            rel = r["mbfc_reliability_label"] if pd.notna(r["mbfc_reliability_label"]) else "unrated"
            desc = f"{cat} website, Media Bias/Fact Check reliability rating: {rel}"
        else:
            desc = f"{cats[n]} website (no independent reliability rating on file)"
        rows.append({"entity": n, "category": cats[n], "description": desc, "source": "domain_metadata"})
    return rows


def main():
    print("Building person description rows...")
    person_rows = build_person_rows()
    print(f"  {len(person_rows)} person rows")

    print("Building domain description rows...")
    domain_rows = build_domain_rows()
    print(f"  {len(domain_rows)} domain rows")

    out = pd.DataFrame(person_rows + domain_rows)
    out.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(out)} rows to {OUT_PATH}")
    print("\nBy source:")
    print(out["source"].value_counts().to_string())


if __name__ == "__main__":
    main()
