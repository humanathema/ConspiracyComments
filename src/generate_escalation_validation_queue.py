"""generate_escalation_validation_queue.py

Pulls a stratified sample of 100 blind validation rows from the scored escalation candidates.
Saves a blind labeling queue to data/hitl/queue_escalation_validation.csv
and a secret key to data/hitl/key_escalation_validation.csv for evaluation.
"""
import os
import re
import pandas as pd

SEED = 42
QUEUE_PATH = "data/hitl/queue_escalation_validation.csv"
KEY_PATH = "data/hitl/key_escalation_validation.csv"

def classify_frontier(val):
    try:
        f = float(val)
        return "hostile" if f < 0 else "endorsement"
    except:
        return "ambiguous"

def map_ensemble(val):
    if val == 0.0: return "hostile"
    if val == 1.0: return "endorsement"
    return "other"

def get_entity_from_text(text):
    text_lower = str(text).lower()
    mapping = {
        'assange': 'Julian Assange',
        'snowden': 'Edward Snowden',
        'greenwald': 'Glenn Greenwald',
        'swartz': 'Aaron Swartz',
        'wikileaks': 'WikiLeaks',
        'fauci': 'Anthony Fauci',
        'gates': 'Bill Gates',
        'cdc': 'CDC',
        'who': 'WHO',
        'jones': 'Alex Jones',
        'carlson': 'Tucker Carlson',
        'stone': 'Roger Stone',
        'gaetz': 'Matt Gaetz'
    }
    for key, formal in mapping.items():
        if key in text_lower:
            return formal
    return "the subject"

def main():
    cand = pd.read_csv("data/processed/batch_escalation_candidates_round8.csv")
    scored = pd.read_csv("data/processed/escalation_cascade_frontier_scored.csv")
    df = pd.merge(cand, scored, on="id")
    
    df["frontier_class"] = df["frontier_score"].apply(classify_frontier)
    df["ensemble_class"] = df["ensemble_pred"].apply(map_ensemble)
    df["target_entity"] = df["text"].apply(get_entity_from_text)
    
    # 1. Flip: Ensemble Endorsement -> Frontier Hostile (Disagreement)
    flips_to_hostile = df[(df["ensemble_class"] == "endorsement") & (df["frontier_class"] == "hostile")]
    # 2. Flip: Ensemble Hostile -> Frontier Endorsement (Disagreement)
    flips_to_endorsement = df[(df["ensemble_class"] == "hostile") & (df["frontier_class"] == "endorsement")]
    # 3. Agreement: Both hostile
    agree_hostile = df[(df["ensemble_class"] == "hostile") & (df["frontier_class"] == "hostile")]
    # 4. Agreement: Both endorsement
    agree_endorsement = df[(df["ensemble_class"] == "endorsement") & (df["frontier_class"] == "endorsement")]
    # 5. Check Cases (Ambiguous or other)
    ambiguous = df[df["frontier_class"] == "ambiguous"]
    other_ensemble = df[(df["ensemble_class"] == "other") & (df["frontier_class"] != "ambiguous")]

    print(f"Pool sizes:\n - Flips to hostile: {len(flips_to_hostile)}\n - Flips to endorsement: {len(flips_to_endorsement)}")
    print(f" - Agree hostile: {len(agree_hostile)}\n - Agree endorsement: {len(agree_endorsement)}")
    print(f" - Ambiguous: {len(ambiguous)}\n - Ensemble other: {len(other_ensemble)}")

    # Sample stratifications
    s_flips_hostile = flips_to_hostile.sample(min(len(flips_to_hostile), 25), random_state=SEED)
    s_flips_endorsement = flips_to_endorsement.sample(min(len(flips_to_endorsement), 25), random_state=SEED)
    s_agree_hostile = agree_hostile.sample(min(len(agree_hostile), 20), random_state=SEED)
    s_agree_endorsement = agree_endorsement.sample(min(len(agree_endorsement), 20), random_state=SEED)
    
    # Ambiguous + ensemble other to check decision boundaries and edge cases (10 total)
    boundary_parts = []
    if len(ambiguous) > 0:
        boundary_parts.append(ambiguous)
    n_other_needed = 10 - len(ambiguous)
    if n_other_needed > 0 and len(other_ensemble) > 0:
        boundary_parts.append(other_ensemble.sample(min(len(other_ensemble), n_other_needed), random_state=SEED))
    s_boundaries = pd.concat(boundary_parts) if boundary_parts else pd.DataFrame()

    # Combine
    queue_df = pd.concat([s_flips_hostile, s_flips_endorsement, s_agree_hostile, s_agree_endorsement, s_boundaries]).drop_duplicates(subset=["id"])
    
    # Shuffle blind
    queue_df = queue_df.sample(frac=1, random_state=SEED).reset_index(drop=True)
    
    # Write blind queue
    os.makedirs("data/hitl", exist_ok=True)
    
    blind_queue = queue_df[["id", "target_entity", "text"]].copy()
    blind_queue["human_label"] = ""  # blank column for labeling (hostile, endorsement, other)
    blind_queue["notes"] = ""
    blind_queue.to_csv(QUEUE_PATH, index=False)
    print(f"\nSaved blind validation queue ({len(blind_queue)} rows) to: {QUEUE_PATH}")
    
    # Write secret key
    key_df = queue_df[["id", "ensemble_class", "frontier_class", "frontier_score"]].copy()
    key_df.to_csv(KEY_PATH, index=False)
    print(f"Saved secret validation key to: {KEY_PATH}")

if __name__ == "__main__":
    main()
