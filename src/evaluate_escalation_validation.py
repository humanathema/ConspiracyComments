"""evaluate_escalation_validation.py

Compares the human-labeled validation queue against predictions from the local ensemble
and the Vertex AI frontier model, calculating precision, recall, accuracy, and Kappa.
"""
import os
import pandas as pd
from sklearn.metrics import cohen_kappa_score, classification_report, accuracy_score

QUEUE_PATH = "data/hitl/queue_escalation_validation.csv"
KEY_PATH = "data/hitl/key_escalation_validation.csv"

def main():
    if not os.path.exists(QUEUE_PATH):
        print(f"Error: Labeled queue not found at {QUEUE_PATH}")
        return
    if not os.path.exists(KEY_PATH):
        print(f"Error: Secret key not found at {KEY_PATH}")
        return
        
    queue = pd.read_csv(QUEUE_PATH)
    key = pd.read_csv(KEY_PATH)
    
    # Check if human labels are present
    if "human_label" not in queue.columns:
        print("Error: 'human_label' column missing from queue.")
        return
        
    # Clean human labels
    queue["human_label"] = queue["human_label"].astype(str).str.lower().str.strip()
    
    # Filter to rows that have actually been labeled (not empty or nan)
    labeled = queue[~queue["human_label"].isin(["", "nan", "none"])]
    if len(labeled) == 0:
        print("No human labels found. Please fill in the 'human_label' column in data/hitl/queue_escalation_validation.csv with 'hostile', 'endorsement', or 'other'.")
        return
        
    # Merge key
    df = pd.merge(labeled, key, on="id")
    print(f"Loaded {len(df)} human-labeled verification rows.\n")
    
    # Evaluate Frontier
    print("==================================================")
    print("              FRONTIER MODEL PERFORMANCE          ")
    print("==================================================")
    f_acc = accuracy_score(df["human_label"], df["frontier_class"])
    f_kappa = cohen_kappa_score(df["human_label"], df["frontier_class"])
    print(f"Accuracy: {f_acc:.4f}")
    print(f"Cohen's Kappa: {f_kappa:.4f}\n")
    print("Classification Report:")
    print(classification_report(df["human_label"], df["frontier_class"], zero_division=0))
    
    # Evaluate Ensemble
    print("==================================================")
    print("             LOCAL ENSEMBLE PERFORMANCE           ")
    print("==================================================")
    e_acc = accuracy_score(df["human_label"], df["ensemble_class"])
    e_kappa = cohen_kappa_score(df["human_label"], df["ensemble_class"])
    print(f"Accuracy: {e_acc:.4f}")
    print(f"Cohen's Kappa: {e_kappa:.4f}\n")
    print("Classification Report:")
    print(classification_report(df["human_label"], df["ensemble_class"], zero_division=0))
    
    print("==================================================")
    print("             DISAGREEMENT ANALYSIS               ")
    print("==================================================")
    # Check what happens in flips
    flips = df[df["ensemble_class"] != df["frontier_class"]]
    if len(flips) > 0:
        f_flip_corr = (flips["frontier_class"] == flips["human_label"]).sum()
        e_flip_corr = (flips["ensemble_class"] == flips["human_label"]).sum()
        print(f"Total Disagreements (Flips) Labeled: {len(flips)}")
        print(f" - Frontier was correct: {f_flip_corr} times ({f_flip_corr/len(flips)*100:.1f}%)")
        print(f" - Ensemble was correct: {e_flip_corr} times ({e_flip_corr/len(flips)*100:.1f}%)")
        print(f" - Both were wrong: {len(flips) - f_flip_corr - e_flip_corr} times ({(len(flips) - f_flip_corr - e_flip_corr)/len(flips)*100:.1f}%)")
    else:
        print("No disagreements found in labeled set.")

if __name__ == "__main__":
    main()
