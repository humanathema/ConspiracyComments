"""Combined Maverick-Expert Detector (Stage 4).

Combines the pre-trained FactAppeal classifier (which predicts source attributions
and factual appeals) with a curated list of maverick entities (whistleblowers,
investigative journalists, and alternative authority figures) to build a robust,
sentence-level hybrid classifier for Maverick Authority.

Evaluates performance against human labels in data/hitl/queue_maverick_authority.csv.
"""
import os
import re
import joblib
import numpy as np
import pandas as pd
import spacy
from sklearn.metrics import classification_report, cohen_kappa_score

QUEUE_PATH = "data/hitl/queue_maverick_authority.csv"
FACTAPPEAL_DIR = "data/processed/factappeal"
ENTITY_PATH = "data/processed/entity_final_review.csv"

from verified_maverick_additions import VERIFIED_MAVERICK_ADDITIONS

# FIXED 2026-07-15: this used to be a hardcoded 24-name placeholder list
# (Assange, Snowden, Manning... plus raw agency acronyms CIA/FBI/NSA/DEA/DIA/
# CSPAN) written before proper entity curation existed, and never updated
# once it did. Now pulled from the real, curated maverick_authority bucket
# (418 entities as of this fix) -- see entity_final_review.csv / §12.
# NOTE: this fixes the entity list, NOT the attribution-vs-co-occurrence
# logic gap documented in ANTIGRAVITY_HANDOFF.md §8b -- the classifier
# below still only checks that an entity and *some* FactAppeal-detected
# appeal co-occur in the same sentence, not that the appeal is actually
# attributed to that entity. That's a separate, bigger fix, not done here.
def load_curated_maverick_entities():
    df_entity = pd.read_csv(ENTITY_PATH)
    ents = df_entity[df_entity["final_bucket_guess"] == "maverick_authority"]["entity"].dropna().astype(str).unique().tolist()
    ents = [e for e in ents if len(e) >= 3]
    # See verified_maverick_additions.py: WikiLeaks/Assange/Manning/Snowden/
    # Ellsberg/Kiriakou never got promoted to final_bucket_guess despite a
    # correct weak-hint -- same blind spot found and fixed for
    # consensus_expert. Added directly rather than fixing the pipeline.
    ents += VERIFIED_MAVERICK_ADDITIONS
    return list(dict.fromkeys(ents))  # dedupe, preserve order


def build_entity_regex():
    ents = load_curated_maverick_entities()
    # Sort by length descending to match longer multi-word phrases first
    sorted_ents = sorted(ents, key=len, reverse=True)
    pattern = r"\b(" + "|".join(re.escape(e) for e in sorted_ents) + r")\b"
    return re.compile(pattern, re.IGNORECASE)


def main():
    # 1. Load data and models
    print("Loading human-labeled queue...")
    df = pd.read_csv(QUEUE_PATH)
    # Exclude rows with missing labels
    df = df[df["human_label"].notna()]
    df["is_positive_gold"] = df["human_label"].astype(str).str.lower().isin(["positive", "lean_positive"])
    
    print("Loading pre-trained FactAppeal model...")
    model_path = os.path.join(FACTAPPEAL_DIR, "factappeal_classifier.pkl")
    vec_path = os.path.join(FACTAPPEAL_DIR, "factappeal_vectorizer.pkl")
    
    clf = joblib.load(model_path)
    vec = joblib.load(vec_path)
    
    print("Initializing spaCy for sentence splitting...")
    nlp = spacy.load("en_core_web_sm", disable=["ner", "parser", "lemmatizer"])
    # Enable sentencizer only for fast sentence splitting
    if "sentencizer" not in nlp.pipe_names:
        nlp.add_pipe("sentencizer")
        
    entity_rx = build_entity_regex()
    
    predictions = []
    trigger_sentences_log = []
    
    print("\nRunning combined hybrid classification on queue comments...")
    for idx, row in df.iterrows():
        text = str(row["full_text"])
        doc = nlp(text)
        
        has_trigger = False
        matching_sentences = []
        
        # Segment comment into sentences
        sentences = [sent.text.strip() for sent in doc.sents if len(sent.text.strip()) > 5]
        
        if sentences:
            # 1. Check entity match in each sentence
            entity_matches = [bool(entity_rx.search(s)) for s in sentences]
            
            # 2. Vectorize and predict FactAppeal for sentences with entity matches
            # This is a major optimization: only run the classifier on sentences that mention our entities!
            candidate_sentences = [s for s, matched in zip(sentences, entity_matches) if matched]
            
            if candidate_sentences:
                X = vec.transform(candidate_sentences)
                preds = clf.predict(X)
                
                # If any candidate sentence triggers a FactAppeal prediction, then the comment is positive
                for sent, pred in zip(candidate_sentences, preds):
                    if pred == 1:
                        has_trigger = True
                        matching_sentences.append(sent)
        
        predictions.append(has_trigger)
        if has_trigger:
            trigger_sentences_log.append({
                "id": row["id"],
                "gold_label": row["human_label"],
                "trigger_sentence": matching_sentences[0]  # log the first trigger
            })
            
    df["pred_combined"] = predictions
    
    # 2. Evaluate performance
    y_true = df["is_positive_gold"].values
    y_pred = df["pred_combined"].values
    
    kappa = cohen_kappa_score(y_true, y_pred)
    
    print("\n" + "="*50)
    print("      COMBINED HYBRID CLASSIFIER PERFORMANCE")
    print("="*50)
    print(f"Cohen's Kappa (κ): {kappa:.4f}")
    print("\nClassification Report:")
    print(classification_report(y_true, y_pred, target_names=["Negative", "Positive"]))
    print("="*50)
    
    # 3. Print some exemplar trigger sentences
    print("\nTrigger Exemplars (Sentence-Level Detections):")
    log_df = pd.DataFrame(trigger_sentences_log)
    if not log_df.empty:
        # Show a mix of positive and negative human-labeled examples to check precision
        sample_size = min(10, len(log_df))
        sample_log = log_df.sample(sample_size, random_state=42)
        for _, r in sample_log.iterrows():
            print(f"\n[ID {r['id']} | Human Label: {r['gold_label'].upper()}]")
            # Highlight matching entity
            match = entity_rx.search(r['trigger_sentence'])
            sent_text = r['trigger_sentence']
            if match:
                ent_text = match.group(0)
                sent_text = sent_text.replace(ent_text, f"**{ent_text.upper()}**")
            print(f"  Sentence: \"{sent_text}\"")
    else:
        print("No triggers found.")


if __name__ == "__main__":
    main()
