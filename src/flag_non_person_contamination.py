"""flag_non_person_contamination.py

Identifies non-person contamination in the maverick_authority entities from entity_final_review.csv.
Outputs a reviewable CSV to data/processed/maverick_non_person_candidates.csv.
"""
import os
import sys
import pandas as pd
import spacy

sys.path.insert(0, os.path.dirname(__file__))
from combined_maverick_detector import load_curated_maverick_entities

ENTITY_PATH = "data/processed/entity_final_review.csv"
OUT_PATH = "data/processed/maverick_non_person_candidates.csv"


def main():
    print("Loading entity final review data...")
    df = pd.read_csv(ENTITY_PATH)

    # Filter to maverick_authority entities (both final_bucket_guess and weak_hint_bucket_guess)
    mask = (df["final_bucket_guess"] == "maverick_authority") | (df["weak_hint_bucket_guess"] == "maverick_authority")
    df_mav = df[mask].copy()
    print(f"Found {len(df_mav)} total maverick candidate entities")

    print("Loading spaCy for NER validation...")
    nlp = spacy.load("en_core_web_sm")

    non_person_keywords = [
        "organisation", "organization", "agency", "group", "movement", "theory", 
        "document", "website", "family", "event", "concept", "system", "program", 
        "corporation", "committee", "foundation", "council", "secret society", 
        "newspaper", "magazine", "series", "book", "film", "album", "platform", 
        "school", "university", "institute", "coalition", "alliance", "union", 
        "party", "regime", "state", "country", "city", "place", "location", 
        "phenomenon", "scandal", "incident", "vaccine", "virus", "disease", "drug", 
        "weapon", "technology", "software", "network", "channel", "acronym", 
        "abbreviation", "meaning", "term", "classification", "category", "subculture",
        "ideology", "religion", "sect", "cult", "uprising", "protest", "riot",
        "agreement", "treaty", "law", "bill", "act", "department", "commission"
    ]

    # Explicitly protect organizations functioning as collective alternative/maverick sources
    protected_collective_sources = [
        "wikileaks", "project veritas", "the intercept", "cryptome", "infowars", 
        "zero hedge", "natural news", "judicial watch", "the washington times",
        "the guardian", "reuters", "associated press", "bbc", "cnn", "fox news",
        "the new york times", "the washington post", "nbc", "msnbc", "qanon", "q-anon"
    ]

    candidates = []

    for idx, row in df_mav.iterrows():
        entity = str(row["entity"])
        
        # Explicitly protect collective maverick/alternative sources from removal
        if entity.lower() in protected_collective_sources:
            continue
            
        desc = str(row["wp_description"]).lower() if pd.notna(row["wp_description"]) else ""
        best_id = str(row["best_identity"]).lower() if pd.notna(row["best_identity"]) else ""

        reasons = []

        # 1. Lowercase check (people names are rarely fully lowercase in standard text)
        if entity.islower() and len(entity) > 3:
            reasons.append("lowercase_name")

        # 2. Check keyword matches in description or best identity
        matched_keywords = [kw for kw in non_person_keywords if kw in desc or kw in best_id]
        if matched_keywords:
            reasons.append(f"description_keywords_match: {', '.join(matched_keywords)}")

        # 3. Check for specific plural or general terms
        if entity.lower() in [
            "debunked", "demons", "ufos", "conspiracy theories", "conspiracy theory", 
            "whistleblowers", "whistleblower", "insiders", "insider", "sources", "source", 
            "leaks", "leak", "scientific consensus", "mainstream media", "the media",
            "the deep state", "new world order", "the new world order", "illuminati"
        ]:
            reasons.append("known_non_person_term")

        # 4. Use spaCy NER on the capitalized entity name to see if it's labeled as ORG, GPE, etc.
        # (Only if it's not a known exception)
        doc = nlp(entity)
        for ent_span in doc.ents:
            if ent_span.label_ in ["ORG", "GPE", "LOC", "FAC", "PRODUCT", "EVENT", "LAW", "NORP"]:
                # NORP can be nationalities/religions, which are non-person
                reasons.append(f"spacy_ner_tag: {ent_span.label_}")

        if reasons:
            candidates.append({
                "entity": row["entity"],
                "wp_description": row["wp_description"],
                "doc_count": row["doc_count"],
                "reason_flagged": " | ".join(dict.fromkeys(reasons)),
                "decision": ""  # blank for Nash to fill in
            })

    out_df = pd.DataFrame(candidates)
    
    # Sort by doc_count descending so high-impact entries are reviewed first
    if not out_df.empty:
        out_df = out_df.sort_values(by="doc_count", ascending=False)
        
    out_df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(out_df)} candidate non-person entities to {OUT_PATH}")


if __name__ == "__main__":
    main()
