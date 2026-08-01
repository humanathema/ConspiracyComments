# src/detect_topic_residuals.py
"""detect_topic_residuals.py

Precomputes a queue of "substantive residual comments" from diffuse/broad topics 
(24 low-cohesion candidates + 3 meta-reddit topics) that actually align closer to 
another substantive topic centroid.

Output: data/processed/topic_residual_comments.csv
"""
import os
import numpy as np
import pandas as pd

def main():
    print("=== Substantive Residual Comments Detection ===")
    
    # 1. Load topic names & flags from audit_topic_quality.csv
    audit_path = 'data/processed/topic_quality_audit.csv'
    if not os.path.exists(audit_path):
        print(f"❌ Error: {audit_path} not found! Run src/audit_topic_quality.py first.")
        return
        
    audit_df = pd.read_csv(audit_path)
    
    # Identify target diffuse/broad topics (low cohesion)
    low_cohesion_topics = set(audit_df[audit_df['flags'].fillna('').str.contains('low_cohesion_broad_candidate')]['topic'])
    
    # Add meta-reddit topics
    target_topics = low_cohesion_topics.union({23, 78, 90})
    print(f"Targeting {len(target_topics)} diffuse/meta topics for residual detection...")
    
    # Map topic ID to name
    topic_name_map = dict(zip(audit_df['topic'], audit_df['topic_name']))
    # Include Outliers just in case
    topic_name_map[-1] = 'Outliers'
    
    # 2. Load centroids
    centroids_path = 'data/processed/topic_centroids.npz'
    if not os.path.exists(centroids_path):
        print(f"❌ Error: {centroids_path} not found!")
        return
    
    c_data = np.load(centroids_path)
    centroids = c_data['embeddings']      # (97, 384)
    centroid_topic_ids = c_data['topic_ids']  # (97,)
    
    # Map centroid index to topic ID
    idx_to_topic_id = {i: int(tid) for i, tid in enumerate(centroid_topic_ids)}
    
    # 3. Load comment assignments & embeddings
    assignments_path = 'data/processed/train_topic_assignments.parquet'
    embeddings_path = 'data/processed/_audit_topic_quality_embeddings_cache.npy'
    
    if not (os.path.exists(assignments_path) and os.path.exists(embeddings_path)):
        print("❌ Error: Parquet files or embeddings cache are missing!")
        return
        
    print("Loading datasets...")
    df = pd.read_parquet(assignments_path)
    # The cache aligns exactly 1-to-1 with df[df['topic_reduced'] != -1]
    df_clean = df[df['topic_reduced'] != -1].copy()
    
    embeddings = np.load(embeddings_path)
    assert len(embeddings) == len(df_clean), f"Embeddings size ({len(embeddings)}) mismatch with df_clean ({len(df_clean)})"
    
    # Add index to map back to embeddings array
    df_clean['embeddings_idx'] = np.arange(len(df_clean))
    
    # Select target comments
    target_df = df_clean[df_clean['topic_reduced'].isin(target_topics)].copy()
    print(f"Analyzing {len(target_df):,} comments in target topics...")
    
    # Compute normalized centroids & embeddings for cosine similarity
    centroid_norms = np.linalg.norm(centroids, axis=1, keepdims=True) + 1e-9
    norm_centroids = centroids / centroid_norms
    
    target_indices = target_df['embeddings_idx'].values
    target_embs = embeddings[target_indices]
    target_norms = np.linalg.norm(target_embs, axis=1, keepdims=True) + 1e-9
    norm_target_embs = target_embs / target_norms
    
    # Compute similarity matrix: (n_targets, 97)
    print("Computing cosine similarities against all centroids...")
    sim_matrix = norm_target_embs @ norm_centroids.T
    
    results = []
    
    # Let's iterate through each target comment
    for local_idx, row_idx in enumerate(target_indices):
        comment_row = target_df.iloc[local_idx]
        assigned_topic_id = int(comment_row['topic_reduced'])
        
        # Similarities for this comment
        sims = sim_matrix[local_idx]
        
        # Find index of assigned topic in centroid_topic_ids
        assigned_centroid_idx = np.where(centroid_topic_ids == assigned_topic_id)[0]
        if len(assigned_centroid_idx) == 0:
            continue
        assigned_sim = float(sims[assigned_centroid_idx[0]])
        
        # Find best OTHER topic
        other_sims = sims.copy()
        other_sims[assigned_centroid_idx[0]] = -1.0 # Mask assigned topic
        
        best_other_idx = int(np.argmax(other_sims))
        best_other_sim = float(other_sims[best_other_idx])
        best_other_topic_id = idx_to_topic_id[best_other_idx]
        
        gap = assigned_sim - best_other_sim
        
        # We target small or negative gaps
        if gap <= 0.15:
            text = comment_row['text'].strip()
            # Clean up newlines/tabs for TSV/CSV safety
            text = text.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
            results.append({
                'comment_id': str(comment_row['id']),
                'text': text,
                'assigned_topic': topic_name_map.get(assigned_topic_id, str(assigned_topic_id)),
                'assigned_sim': round(assigned_sim, 4),
                'best_other_topic': topic_name_map.get(best_other_topic_id, str(best_other_topic_id)),
                'best_other_sim': round(best_other_sim, 4),
                'gap': round(gap, 4)
            })
            
    if len(results) == 0:
        print("No comments found with similarity gap <= 0.15.")
        return
        
    res_df = pd.DataFrame(results)
    print(f"Found {len(res_df):,} comments with a similarity gap <= 0.15.")
    
    # Sort by gap ascending (most negative / closest first)
    res_df = res_df.sort_values('gap', ascending=True)
    
    # Keep up to 1000 top comments for the UI queue
    queue_df = res_df.head(1000)
    
    output_file = 'data/processed/topic_residual_comments.csv'
    queue_df.to_csv(output_file, index=False)
    print(f"🎉 Successfully wrote {len(queue_df):,} comments to {output_file}!")

if __name__ == '__main__':
    main()
