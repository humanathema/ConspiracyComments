import pandas as pd
import numpy as np
import os
import sys
from sklearn.linear_model import LogisticRegression

def re_rank_queue(queue_name):
    # Setup paths
    queue_path = f"data/hitl/queue_{queue_name}.csv"
    embedded_path = "data/processed/labeled_2k_with_scores.parquet"
    
    if not os.path.exists(queue_path):
        print(f"❌ Queue file not found: {queue_path}")
        return
        
    print(f"🎯 Re-ranking queue: '{queue_name}' using Active Learning...")
    
    # 1. Load human-labeled queue
    df_queue = pd.read_csv(queue_path)
    print(f"  - Total rows in queue: {len(df_queue)}")
    
    # Check current labeled count
    labeled_mask = df_queue['human_label'].notna() & (df_queue['human_label'] != '')
    df_labeled = df_queue[labeled_mask].copy()
    df_unlabeled = df_queue[~labeled_mask].copy()
    
    print(f"  - Human-labeled: {len(df_labeled)}")
    print(f"  - Unlabeled: {len(df_unlabeled)}")
    
    if len(df_labeled) < 2:
        print("⚠️ Not enough human labels yet to train a custom model (need at least 2 labeled rows).")
        print("👉 Go rate a couple of comments first, then run this script to re-rank the remaining queue!")
        return
        
    # Map label strings to binary (positive/lean_positive = 1, negative/unsure = 0)
    # If there are only negatives or only positives, we can't train a binary classifier
    def to_binary(label):
        lbl = str(label).lower().strip()
        if lbl in ['positive', 'lean_positive', 'yes', 'true', '1', '1.0']:
            return 1
        return 0
        
    df_labeled['binary_target'] = df_labeled['human_label'].apply(to_binary)
    target_counts = df_labeled['binary_target'].value_counts()
    print(f"  - Target distribution in human labels: {dict(target_counts)}")
    
    if len(target_counts) < 2:
        print("⚠️ Custom model training requires at least one positive and one negative label in your history.")
        print("👉 Please make sure you have labeled at least one 'positive' and one 'negative' item, then try again!")
        return
        
    # 2. Load pre-computed embedding reference
    print(f"📖 Loading pre-computed embeddings from {embedded_path}...")
    df_emb = pd.read_parquet(embedded_path)
    
    # Build text prefix lookup map to retrieve 384-dim embeddings
    # We truncate to 400 characters to match the pre-embedded texts perfectly
    emb_lookup = {}
    for _, row in df_emb.iterrows():
        prefix = str(row['text']).strip()[:400]
        emb_lookup[prefix] = row['embeddings']
        
    # 3. Align queue items with embeddings
    print("🧠 Extracting embeddings for labeled and unlabeled sets...")
    
    X_train = []
    y_train = []
    
    unlabeled_embeddings = []
    valid_unlabeled_indices = []
    
    # Extract training embeddings
    for idx, row in df_labeled.iterrows():
        prefix = str(row['full_text']).strip()[:400]
        if prefix in emb_lookup:
            X_train.append(emb_lookup[prefix])
            y_train.append(row['binary_target'])
            
    # Extract unlabeled embeddings
    for idx, row in df_unlabeled.iterrows():
        prefix = str(row['full_text']).strip()[:400]
        if prefix in emb_lookup:
            unlabeled_embeddings.append(emb_lookup[prefix])
            valid_unlabeled_indices.append(idx)
            
    print(f"  - Successfully matched {len(X_train)} / {len(df_labeled)} labeled rows to embeddings.")
    print(f"  - Successfully matched {len(unlabeled_embeddings)} / {len(df_unlabeled)} unlabeled rows to embeddings.")
    
    if len(X_train) < 2:
        print("❌ Could not match enough labeled rows to pre-computed embeddings.")
        return
        
    # 4. Train Logistic Regression model on embeddings
    print("🤖 Training embedding-based Logistic Regression model...")
    X_train = np.array(X_train)
    y_train = np.array(y_train)
    
    # We use strong regularization (C=0.1 or C=1.0) because training set size is small
    clf = LogisticRegression(C=1.0, class_weight='balanced', random_state=42)
    clf.fit(X_train, y_train)
    
    # 5. Predict probabilities for unlabeled pool
    print("🔮 Predicting probabilities on remaining unlabeled comments...")
    X_unlabeled = np.array(unlabeled_embeddings)
    probs = clf.predict_proba(X_unlabeled)[:, 1]
    
    # Assign predicted probability back to unlabeled rows
    df_unlabeled['pred_prob'] = 0.0
    df_unlabeled.loc[valid_unlabeled_indices, 'pred_prob'] = probs
    
    # Sort unlabeled comments with highest predicted probability AT THE TOP
    print("🔥 Re-ranking unlabeled comments (Highest Probability 'Yes' first)...")
    df_unlabeled_sorted = df_unlabeled.sort_values(by='pred_prob', ascending=False)
    
    # Print the top 3 highest probability text snips for verification
    print("\n--- TOP 3 SUGGESTED CANDIDATES ---")
    for rank, (idx, row) in enumerate(df_unlabeled_sorted.head(3).iterrows()):
        snip = str(row['full_text']).replace('\n', ' ')[:100]
        print(f" #{rank+1} (Prob: {row['pred_prob']:.3f}): {snip}...")
    print("---------------------------------\n")
    
    # Remove our temporary prediction column before saving to preserve the blind rating schema
    df_unlabeled_sorted = df_unlabeled_sorted.drop(columns=['pred_prob', 'binary_target'], errors='ignore')
    if 'binary_target' in df_labeled.columns:
        df_labeled = df_labeled.drop(columns=['binary_target'])
        
    # 6. Save back to CSV (labeled rows stay at their original positions or are prepended,
    # let's prepend labeled rows so you don't lose them, and append the sorted unlabeled rows next)
    final_output = pd.concat([df_labeled, df_unlabeled_sorted], ignore_index=True)
    final_output.to_csv(queue_path, index=False)
    
    print(f"🎉 Successfully re-ranked {queue_path}!")
    print("👉 Reload your browser tab now to see the highest density 'Yes' candidates first!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/re_rank_queue.py <queue_name>")
        print("Example: python src/re_rank_queue.py maverick_authority")
        sys.exit(1)
        
    re_rank_queue(sys.argv[1])
