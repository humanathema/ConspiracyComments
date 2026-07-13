"""Seed a named-entity list of maverick-authority figures from HITL labels.

Runs spaCy NER over data/hitl/queue_maverick_authority.csv, split by human
label. Reports entities that are disproportionately common in positive
(maverick_authority) comments vs negative ones, not just raw frequency in
positives alone — a name that's common in both (e.g. "Trump" in general
political discussion) isn't a maverick-authority marker, it's just a common
entity in this subreddit.

Output: data/processed/maverick_authority_entities.csv
"""
import pandas as pd
import spacy
from collections import Counter

QUEUE_PATH = "data/hitl/queue_maverick_authority.csv"
OUT_PATH = "data/processed/maverick_authority_entities.csv"
KEEP_LABELS = {"PERSON", "ORG", "NORP"}


def extract_entities(nlp, texts):
    counts = Counter()
    doc_counts = Counter()  # how many distinct comments mention the entity
    for doc in nlp.pipe(texts, batch_size=32):
        seen_this_doc = set()
        for ent in doc.ents:
            if ent.label_ not in KEEP_LABELS:
                continue
            key = ent.text.strip()
            if len(key) < 3:
                continue
            counts[key] += 1
            seen_this_doc.add(key)
        for key in seen_this_doc:
            doc_counts[key] += 1
    return counts, doc_counts


def main():
    df = pd.read_csv(QUEUE_PATH)
    df["is_positive"] = df["human_label"].astype(str).str.lower().isin(
        ["positive", "lean_positive"])
    pos = df[df["is_positive"]]
    neg = df[df["human_label"].astype(str).str.lower() == "negative"]
    print(f"Positive comments: {len(pos)}  Negative comments: {len(neg)}")

    nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])

    pos_counts, pos_doc_counts = extract_entities(nlp, pos["full_text"].fillna(""))
    neg_counts, neg_doc_counts = extract_entities(nlp, neg["full_text"].fillna(""))

    n_pos, n_neg = len(pos), len(neg)
    rows = []
    for ent, pcount in pos_doc_counts.items():
        ncount = neg_doc_counts.get(ent, 0)
        pos_rate = pcount / n_pos if n_pos else 0
        neg_rate = ncount / n_neg if n_neg else 0
        # Laplace-smoothed lift: how much more likely in positive vs negative comments
        lift = (pos_rate + 0.01) / (neg_rate + 0.01)
        rows.append({
            "entity": ent,
            "positive_mentions": pcount,
            "negative_mentions": ncount,
            "positive_rate": round(pos_rate, 3),
            "negative_rate": round(neg_rate, 3),
            "lift": round(lift, 2),
        })

    out = pd.DataFrame(rows).sort_values(["lift", "positive_mentions"], ascending=False)
    out.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(out)} candidate entities to {OUT_PATH}")
    print("\nTop 25 by lift (min 2 positive mentions):")
    print(out[out["positive_mentions"] >= 2].head(25).to_string(index=False))


if __name__ == "__main__":
    main()
