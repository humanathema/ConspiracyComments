"""validate_against_human_labels.py

Validates the local, deterministic attribution_confidence_scorer.py against human labels
in data/hitl/queue_maverick_authority.csv.
"""
import os
import re
import sys
import pandas as pd
import spacy
from sklearn.metrics import classification_report, cohen_kappa_score

sys.path.insert(0, os.path.dirname(__file__))
from attribution_confidence_scorer import score_entity_attribution
from combined_maverick_detector import build_entity_regex, load_curated_maverick_entities

QUEUE_PATH = "data/hitl/queue_maverick_authority.csv"


def main():
    print("Loading human-labeled queue...")
    df = pd.read_csv(QUEUE_PATH)
    df = df[df["human_label"].notna()]
    df["is_positive_gold"] = df["human_label"].astype(str).str.lower().isin(["positive", "lean_positive"])

    print("Loading spaCy for sentence splitting...")
    nlp = spacy.load("en_core_web_sm", disable=["ner", "parser", "lemmatizer"])
    if "sentencizer" not in nlp.pipe_names:
        nlp.add_pipe("sentencizer")

    print("Building entity regex...")
    entities = load_curated_maverick_entities()
    entity_rx = build_entity_regex()

    results = []

    print("\nRunning attribution scorer on queue comments...")
    for idx, row in df.iterrows():
        text = str(row["full_text"])
        doc = nlp(text)

        comment_matches = []
        sentences = [sent.text.strip() for sent in doc.sents if len(sent.text.strip()) > 5]

        for sent_text in sentences:
            for m in entity_rx.finditer(sent_text):
                entity_matched = m.group(0)
                other_entities = [e for e in entities if e.lower() != entity_matched.lower()]
                nearby_others = [e for e in other_entities if e.lower() in sent_text.lower()][:10]
                
                result = score_entity_attribution(
                    sent_text, entity_matched, m.start(), m.end(),
                    other_known_entities=nearby_others
                )
                comment_matches.append(result)

        # Aggregate confidence for the comment: highest confidence wins
        if not comment_matches:
            max_conf = "none"
        else:
            confs = [m.confidence for m in comment_matches]
            if "high" in confs:
                max_conf = "high"
            elif "medium" in confs:
                max_conf = "medium"
            elif "low" in confs:
                max_conf = "low"
            else:
                max_conf = "none"

        results.append({
            "id": row["id"],
            "human_label": row["human_label"],
            "is_positive_gold": row["is_positive_gold"],
            "max_confidence": max_conf,
            "matches": comment_matches
        })

    results_df = pd.DataFrame(results)

    # Let's evaluate three thresholds:
    # 1. Prediction is Positive if confidence >= 'high' (i.e. 'high')
    # 2. Prediction is Positive if confidence >= 'medium' (i.e. 'high' or 'medium')
    # 3. Prediction is Positive if confidence >= 'low' (i.e. 'high', 'medium', or 'low')

    y_true = results_df["is_positive_gold"].values

    for threshold, name in [
        ("high", "High Confidence Only"),
        ("medium", "Medium or High Confidence"),
        ("low", "Low, Medium, or High Confidence")
    ]:
        if threshold == "high":
            preds = results_df["max_confidence"] == "high"
        elif threshold == "medium":
            preds = results_df["max_confidence"].isin(["high", "medium"])
        else:
            preds = results_df["max_confidence"].isin(["high", "medium", "low"])

        preds = preds.values
        kappa = cohen_kappa_score(y_true, preds)
        
        print("\n" + "="*60)
        print(f"      THRESHOLD: {name}")
        print("="*60)
        print(f"Cohen's Kappa (κ): {kappa:.4f}")
        print("\nClassification Report:")
        print(classification_report(y_true, preds, target_names=["Negative", "Positive"]))
        print("="*60)


if __name__ == "__main__":
    main()
