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
from maverick_authority_verified import VERIFIED_MAVERICK_AUTHORITY

VALID_MAVERICK_CANDIDATES = {
    "Chelsea Manning", "Bradley Manning",
    "Alex Jones", "Steven E. Jones",
    "Mike Adams", "Stanley Adams", "Jad Adams",
    "Jim Watkins", "Ron Watkins", "Sherron Watkins",
    "Ben Garrison", "Jim Garrison",
    "Milton William Cooper", "Cynthia Cooper",
    "Jenny McCarthy",
    "Whitney Webb", "Gary Webb",
    "Robert W. Malone",
    # Added 2026-07-20: "Ventura"/"Hancock"/"Kory" moved here from the
    # blind UNAMBIGUOUS_MAVERICK_ALIASES list -- see
    # maverick_authority_verified.py's note on why. "Ventura (place name,
    # not a person)"/"Matt Hancock"/"Kory (other person, surname
    # collision)" are the other candidates in their stage_b clusters and
    # are deliberately NOT in this set, so they resolve to has_maverick=0.
    "Jesse Ventura", "Graham Hancock", "Pierre Kory",
}

CANDIDATE_TO_BARES = {
    "Chelsea Manning": ["manning"],
    "Bradley Manning": ["manning"],
    "Alex Jones": ["jones"],
    "Steven E. Jones": ["jones"],
    "Mike Adams": ["adams"],
    "Stanley Adams": ["adams"],
    "Jad Adams": ["adams"],
    "Jim Watkins": ["watkins"],
    "Ron Watkins": ["watkins"],
    "Sherron Watkins": ["watkins"],
    "Ben Garrison": ["garrison"],
    "Jim Garrison": ["garrison"],
    "Milton William Cooper": ["cooper"],
    "Cynthia Cooper": ["cooper"],
    "Jenny McCarthy": ["mccarthy"],
    "Whitney Webb": ["webb"],
    "Gary Webb": ["webb"],
    "Robert W. Malone": ["malone"],
    "Jesse Ventura": ["ventura"],
    "Graham Hancock": ["hancock"],
    "Pierre Kory": ["kory"],
}

def load_maverick_disambiguation_lookup():
    path = "data/processed/maverick_entity_disambiguation_classified.csv"
    lookup = {}
    if os.path.exists(path):
        df = pd.read_csv(path)
        for _, r in df.iterrows():
            cid = str(r["id"])
            resolved = r["classified_as"]
            if pd.notna(resolved) and str(resolved).strip() != "":
                lookup[cid] = str(resolved).strip()
    return lookup

# FIXED 2026-07-15: this used to be a hardcoded 24-name placeholder list
# (Assange, Snowden, Manning... plus raw agency acronyms CIA/FBI/NSA/DEA/DIA/
# CSPAN) written before proper entity curation existed, and never updated
# once it did. At the time, pulled from the raw `final_bucket_guess ==
# 'maverick_authority'` bucket, believing it to be "curated" -- it wasn't.
#
# FIXED AGAIN 2026-07-20: that bucket (418 entities) was never actually
# hand-reviewed and turned out to mix real people/organizations with
# generic conspiracy-topic vocabulary ("New World Order", "Deep State",
# "Conspiracy Theory", etc, ~25% of corpus matches were topic-noise, no
# entity present at all -- see handoff/task_maverick_authority_list_cleanup.md).
# This directly affected THIS scorer's validation: scoring "is this comment
# attributing a claim TO <entity>" against a match on "UFO" or "conspiracy
# theory" is nonsensical, since those aren't attributable sources -- likely
# a real contributor to the near-zero kappa this scorer's validation showed.
# Now pulled from Nash's hand-reviewed VERIFIED_MAVERICK_AUTHORITY (446
# entities) instead.
# NOTE: this fixes the entity list, NOT the attribution-vs-co-occurrence
# logic gap documented in ANTIGRAVITY_HANDOFF.md §8b -- the classifier
# below still only checks that an entity and *some* FactAppeal-detected
# appeal co-occur in the same sentence, not that the appeal is actually
# attributed to that entity. That's a separate, bigger fix, not done here.
def load_curated_maverick_entities():
    ents = list(VERIFIED_MAVERICK_AUTHORITY)
    ents = [e for e in ents if len(e) >= 3]
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
    
    lookup = load_maverick_disambiguation_lookup()
    print(f"Loaded {len(lookup)} resolved bare-form entries from disambiguation lookup.")

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
            # 1. Check entity match in each sentence (including lookup-override for bare forms)
            entity_matches = []
            cid = str(row["id"])
            resolved_cand = lookup.get(cid)
            is_resolved_mav = resolved_cand in VALID_MAVERICK_CANDIDATES
            
            for s in sentences:
                matched = bool(entity_rx.search(s))
                if not matched and is_resolved_mav:
                    bares = CANDIDATE_TO_BARES[resolved_cand]
                    if any(re.search(r'\b' + re.escape(b) + r'\b', s, re.IGNORECASE) for b in bares):
                        matched = True
                entity_matches.append(matched)
            
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
            else:
                # check if it matched via bare-form lookup
                cid = str(r["id"])
                resolved_cand = lookup.get(cid)
                if resolved_cand in VALID_MAVERICK_CANDIDATES:
                    bares = CANDIDATE_TO_BARES[resolved_cand]
                    for b in bares:
                        bare_match = re.search(r'\b' + re.escape(b) + r'\b', sent_text, re.IGNORECASE)
                        if bare_match:
                            ent_text = bare_match.group(0)
                            sent_text = sent_text.replace(ent_text, f"**{ent_text.upper()} (RESOLVED: {resolved_cand})**")
                            break
            print(f"  Sentence: \"{sent_text}\"")
    else:
        print("No triggers found.")


if __name__ == "__main__":
    main()

