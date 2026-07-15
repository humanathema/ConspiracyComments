"""Extract maverick-authority entities localized strictly to the triggering spans.

By running spaCy NER over the `final_spans` column (from cascade_maverick_authority.csv)
rather than the entire comment's `full_text`, we isolate the exact entities that
triggered the maverick-authority construct and compare their frequencies in positive
vs. negative human judgments.

Output: data/processed/maverick_authority_entities_localized.csv
"""
import pandas as pd
import spacy
from collections import Counter

QUEUE_PATH = "data/hitl/queue_maverick_authority.csv"
CASCADE_PATH = "data/processed/cascade_maverick_authority.csv"
OUT_PATH = "data/processed/maverick_authority_entities_localized.csv"
KEEP_LABELS = {"PERSON", "ORG", "NORP"}


def extract_entities(nlp, texts):
    counts = Counter()
    doc_counts = Counter()  # how many distinct comments mention the entity in their spans
    # Run pipeline on non-empty spans
    for doc in nlp.pipe(texts, batch_size=32):
        seen_this_doc = set()
        for ent in doc.ents:
            if ent.label_ not in KEEP_LABELS:
                continue
            key = ent.text.strip()
            # Clean up leading/trailing quotes or punctuation if spaCy missed it
            key = key.strip("\"'.,- ")
            if len(key) < 3:
                continue
            counts[key] += 1
            seen_this_doc.add(key)
        for key in seen_this_doc:
            doc_counts[key] += 1
    return counts, doc_counts


def main():
    q = pd.read_csv(QUEUE_PATH)
    c = pd.read_csv(CASCADE_PATH)
    
    # Merge on the shared row index ID
    df = pd.merge(q, c, on="id", how="inner")
    print(f"Merged HITL queue and Cascade file: {len(df)} rows")

    df["is_positive"] = df["human_label"].astype(str).str.lower().isin(
        ["positive", "lean_positive"])
    pos = df[df["is_positive"]]
    neg = df[df["human_label"].astype(str).str.lower() == "negative"]
    print(f"Positive comments: {len(pos)} (spans present: {pos['final_spans'].notna().sum()})")
    print(f"Negative comments: {len(neg)} (spans present: {neg['final_spans'].notna().sum()})")

    nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])

    # Extract entities strictly from the final_spans column
    pos_counts, pos_doc_counts = extract_entities(nlp, pos["final_spans"].fillna("").astype(str))
    neg_counts, neg_doc_counts = extract_entities(nlp, neg["final_spans"].fillna("").astype(str))

    n_pos, n_pos_spans = len(pos), pos['final_spans'].notna().sum()
    n_neg, n_neg_spans = len(neg), neg['final_spans'].notna().sum()
    
    rows = []
    # Collect all unique entities found across positive and negative spans
    all_ents = set(pos_doc_counts.keys()).union(set(neg_doc_counts.keys()))
    
    for ent in all_ents:
        pcount = pos_doc_counts.get(ent, 0)
        ncount = neg_doc_counts.get(ent, 0)
        
        # Calculate rates relative to comments that actually had spans
        pos_rate = pcount / n_pos if n_pos else 0
        neg_rate = ncount / n_neg if n_neg else 0
        
        # Laplace-smoothed lift: how much more likely in positive vs negative comment spans
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
    print(f"\nSaved {len(out)} localized candidate entities to {OUT_PATH}")
    
    print("\nTop 25 by lift (min 2 positive mentions):")
    print(out[out["positive_mentions"] >= 2].head(25).to_string(index=False))


if __name__ == "__main__":
    main()
