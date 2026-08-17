"""build_entity_relationships.py

Person<->org/domain relationship pairs among the verified entity list --
Nash's 2026-08-18 point that Assange/WikiLeaks, Alex Jones/infowars.com,
Mercola/mercola.com etc. are currently tracked as fully independent
entities with zero relationship modeling, even though some pairs are much
more tightly bound than others. NOT a merge -- each entity keeps its own
row/label everywhere else (a comment about mercola.com is not silently
relabeled as being about the person Joseph Mercola, and vice versa).
This is a separate lookup describing the relationship between them, for
whatever downstream use needs it (e.g. checking whether stance toward the
person correlates with stance toward the org, on the author-entity-stance
ledger, once there's enough data to look).

Two relationship tiers, kept distinct because they're different kinds of
claim:
  - "name_embedded": mechanically detected -- the domain's core name
    (stripped of its TLD) literally contains the person's surname. Doesn't
    require outside knowledge, just string matching against the two
    entity lists already in this project (verified 2026-08-18: only two
    pairs in the current 194-person/31-domain list clear this bar --
    Mercola/mercola.com, Greenwald/greenwald.substack.com).
  - "associated_org": no name overlap, relies on a real-world
    founder/host/chair fact (e.g. Alex Jones hosting infowars.com) --
    NOT independently verified against a source the way the Wikipedia
    descriptions are, so treat this the same as the
    claude_general_knowledge tier in build_entity_description_lookup.py:
    plausible and specific, not guaranteed correct. Only included where
    BOTH sides of the pair are already in the verified entity list (no
    new entities added here) and the fact is common-knowledge-level
    confident, not a guess.

Output: data/processed/entity_relationships.csv
Columns: person, org, relationship_type, note
"""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from pull_hitl_val_batch import build_person_entities, build_domain_entities

OUT_PATH = "data/processed/entity_relationships.csv"

# Real-world founder/host/chair facts, common-knowledge-level confidence,
# NOT independently verified against a source. Only pairs where both
# sides are already in the verified entity list.
ASSOCIATED_ORG_PAIRS = [
    ("Assange", "WikiLeaks", "Julian Assange founded WikiLeaks."),
    ("Alex Jones", "infowars.com", "Alex Jones hosts/runs Infowars."),
    ("Alex Jones", "prisonplanet.com", "Alex Jones also runs Prison Planet, a second outlet."),
    ("Mike Adams", "naturalnews.com", "Mike Adams (\"the Health Ranger\") runs Natural News."),
    ("Robert F. Kennedy Jr.", "childrenshealthdefense.org", "RFK Jr. founded/chaired Children's Health Defense."),
    ("Glenn Greenwald", "theintercept.com", "Glenn Greenwald co-founded The Intercept (later left it)."),
]


def find_name_embedded_pairs(persons, domains):
    pairs = []
    for dname, _, _ in domains:
        core = re.sub(r"\.(com|org|net|ca|info)$", "", dname.lower())
        for pname, _, _ in persons:
            surname = pname.strip().split()[-1].lower().rstrip(".,")
            surname = re.sub(r"'s$", "", surname)
            if len(surname) >= 5 and surname in core:
                pairs.append((pname, dname, "name_embedded",
                              f"Domain name contains the surname '{surname}'."))
    return pairs


def main():
    persons = build_person_entities(skip_original_11=False)
    domains = build_domain_entities()
    person_names = {n for n, _, _ in persons}
    domain_names = {n for n, _, _ in domains}

    name_embedded = find_name_embedded_pairs(persons, domains)
    print(f"name_embedded pairs (mechanically detected): {len(name_embedded)}")
    for p_, d_, _, note in name_embedded:
        print(f"  {p_} <-> {d_}  ({note})")

    associated = []
    for person, org, note in ASSOCIATED_ORG_PAIRS:
        if person not in person_names:
            print(f"  SKIPPED (person not in verified list): {person} <-> {org}")
            continue
        # org can be tracked as a domain (infowars.com) or, like WikiLeaks,
        # as its own person-category entity (bare-word match, no .com/.org
        # in the domain list since that was already excluded as "covered
        # in person 11" -- see SKIP_DOMAINS in pull_hitl_val_batch.py).
        if org not in domain_names and org not in person_names:
            print(f"  SKIPPED (org not in verified list): {person} <-> {org}")
            continue
        associated.append((person, org, "associated_org", note))
    print(f"\nassociated_org pairs (hand-curated, both sides verified present): {len(associated)}")

    rows = [{"person": p_, "org": o_, "relationship_type": rt, "note": note}
            for p_, o_, rt, note in name_embedded + associated]
    out = pd.DataFrame(rows)
    out.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(out)} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()
