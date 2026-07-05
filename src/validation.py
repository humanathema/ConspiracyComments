import pandas as pd
from sklearn.metrics import precision_score, recall_score, f1_score
import os

def main():
    input_file = "data/processed/labeled_2k_with_scores.csv"
    output_file = "data/processed/classifier_performance_summary.csv"
    
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return
        
    df = pd.read_csv(input_file)
    
    dimensions = [
        "anti_establishment_stance", "hedged_suspicion", "personal_experience",
        "source_citation", "appeal_to_authority", "procedural_skepticism", "maverick_authority"
    ]
    
    results = []
    
    for dim in dimensions:
        pred_col = f"{dim}_best"
        if pred_col not in df.columns or dim not in df.columns:
            continue
            
        # Drop rows where either ground truth or prediction is missing
        df_clean = df.dropna(subset=[dim, pred_col])
        
        y_true = df_clean[dim].astype(int)
        y_pred = df_clean[pred_col].astype(int)
        
        precision = precision_score(y_true, y_pred, zero_division=0)
        recall = recall_score(y_true, y_pred, zero_division=0)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        support = len(y_true)
        
        results.append({
            "Dimension": dim,
            "Precision": round(precision, 3),
            "Recall": round(recall, 3),
            "F1_Score": round(f1, 3),
            "Support": support
        })
        
    results_df = pd.DataFrame(results)
    results_df.to_csv(output_file, index=False)
    print("Classifier performance summarized in:", output_file)
    print(results_df)

if __name__ == "__main__":
    main()
