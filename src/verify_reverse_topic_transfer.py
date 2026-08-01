"""
verify_reverse_topic_transfer.py

Executes the Reverse Transfer Test (Option B) by:
1. Loading the 2 native ATS topic centroids (data/processed/ats_topic_centroids.npz).
2. Loading and encoding the 20k held-out ATS validation sample and the 20k Reddit validation sample.
3. Projecting both validation sets onto the ATS centroids via cosine similarity.
4. Applying the standard, ungenerous 0.35 cosine similarity threshold to identify outliers.
5. Printing and writing the definitive Control-Gap Table and semantic diagnostics.
"""
import os
# Configure optimal thread parallel environments for CPU
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["NUMBA_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import pandas as pd
import numpy as np
import torch
import time
import gc
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

def project_and_evaluate(embeddings, centroids, threshold=0.35):
    """
    Projects embeddings onto the centroids and calculates the outlier rate
    and median cosine similarity of assigned comments.
    """
    # Calculate cosine similarity matrix of shape (n_comments, n_centroids)
    sim_matrix = cosine_similarity(embeddings, centroids)
    
    # Find the nearest centroid and its similarity score for each comment
    best_centroid_idx = np.argmax(sim_matrix, axis=1)
    best_sim_score = np.max(sim_matrix, axis=1)
    
    # Classify outliers (similarity strictly less than threshold)
    is_outlier = best_sim_score < threshold
    outlier_rate = np.mean(is_outlier) * 100
    
    # Calculate median similarity for non-outliers
    assigned_sims = best_sim_score[~is_outlier]
    median_sim = np.median(assigned_sims) if len(assigned_sims) > 0 else 0.0
    
    return outlier_rate, median_sim, is_outlier, best_centroid_idx, best_sim_score

def main():
    print("=== Step 3: Running Reverse Topic Transfer Diagnostic ===")
    t_start = time.time()
    
    # CPU-only configuration
    device = "cpu"
    torch.set_num_threads(4)
    print(f"Using PyTorch device: {device} (with {torch.get_num_threads()} CPU threads)")
    
    # Paths
    centroids_path = 'data/processed/ats_topic_centroids.npz'
    ats_val_path = 'data/processed/ats_val_overlap_sample.parquet'
    reddit_val_path = 'data/processed/reddit_val_overlap_sample.parquet'
    report_out_path = 'data/processed/reverse_transfer_verification_report.md'
    
    # Load native centroids
    if not os.path.exists(centroids_path):
        raise FileNotFoundError(f"Native ATS centroids not found at {centroids_path}! Please run training first.")
    
    centroids_data = np.load(centroids_path)
    centroids = centroids_data['embeddings']
    topic_ids = centroids_data['topic_ids']
    print(f"Loaded {len(centroids)} native ATS centroids of shape {centroids.shape}.")
    
    # Load datasets
    print(f"Loading held-out ATS validation sample from {ats_val_path}...")
    df_ats_val = pd.read_parquet(ats_val_path)
    ats_docs = df_ats_val['body'].fillna("").tolist()
    
    print(f"Loading Reddit validation sample from {reddit_val_path}...")
    df_reddit_val = pd.read_parquet(reddit_val_path)
    reddit_docs = df_reddit_val['text'].fillna("").tolist()
    
    print(f"Loaded {len(ats_docs):,} ATS and {len(reddit_docs):,} Reddit validation comments.")
    
    # Initialize SentenceTransformer on CPU
    print("\nInitializing SentenceTransformer (all-MiniLM-L6-v2) on CPU...")
    model = SentenceTransformer("all-MiniLM-L6-v2", device=device)
    
    # Encode ATS Validation Sample
    print("\n[1/2] Encoding held-out ATS validation comments...")
    t0 = time.time()
    ats_embeddings_list = []
    chunk_size = 5000
    for i in range(0, len(ats_docs), chunk_size):
        chunk = ats_docs[i:i+chunk_size]
        chunk_embs = model.encode(chunk, batch_size=256, show_progress_bar=False, convert_to_tensor=True, device=device)
        ats_embeddings_list.append(chunk_embs.numpy())
        del chunk_embs
        gc.collect()
    ats_embeddings = np.concatenate(ats_embeddings_list, axis=0)
    print(f"Encoded ATS validation matrix shape {ats_embeddings.shape} in {(time.time()-t0)/60:.2f} minutes.")
    
    # Encode Reddit Validation Sample
    print("\n[2/2] Encoding Reddit validation comments...")
    t0 = time.time()
    reddit_embeddings_list = []
    for i in range(0, len(reddit_docs), chunk_size):
        chunk = reddit_docs[i:i+chunk_size]
        chunk_embs = model.encode(chunk, batch_size=256, show_progress_bar=False, convert_to_tensor=True, device=device)
        reddit_embeddings_list.append(chunk_embs.numpy())
        del chunk_embs
        gc.collect()
    reddit_embeddings = np.concatenate(reddit_embeddings_list, axis=0)
    print(f"Encoded Reddit validation matrix shape {reddit_embeddings.shape} in {(time.time()-t0)/60:.2f} minutes.")
    
    # Evaluate ATS In-Domain Baseline (Floor)
    print("\nProjecting ATS validation comments onto native ATS centroids...")
    ats_outlier_rate, ats_median_sim, ats_outliers, _, _ = project_and_evaluate(ats_embeddings, centroids)
    
    # Evaluate Reddit Transfer
    print("Projecting Reddit validation comments onto native ATS centroids...")
    reddit_outlier_rate, reddit_median_sim, reddit_outliers, _, _ = project_and_evaluate(reddit_embeddings, centroids)
    
    # Calculate Reverse Control-Gap
    transfer_gap = reddit_outlier_rate - ats_outlier_rate
    
    # Build markdown report content
    report_md = f"""# Reverse Topic Transfer Diagnostic Report

This report presents the empirical results of the **Reverse Transfer Test (Option B - Fit-New Reverse Diagnostic)**, replicating the forward validation design to measure how well native ATS centroids capture Reddit discourse relative to its own in-domain baseline.

---

## Reverse Topic Model Architecture
* **Source Corpus**: Stratified AboveTopSecret (ATS) Comments ($N = 100,000$ train)
* **Overlap Era**: 2008–2016 window
* **Discovered Topics**: {len(centroids)} distinct topics
* **Model Class**: BERTopic (UMAP neighbors=15, components=5, min_topic_size=100)

---

## Definitive Reverse Control-Gap Table

| Metric | Held-Out ATS Baseline (In-Domain Floor) | Reddit Overlap Sample (Transferred Target) | Absolute Control Gap (Degradation) |
| :--- | :---: | :---: | :---: |
| **Sample Size ($N$)** | {len(ats_docs):,} | {len(reddit_docs):,} | -- |
| **Outlier Rate ($< 0.35$ Cosine)** | **{ats_outlier_rate:.2f}%** | **{reddit_outlier_rate:.2f}%** | **+{transfer_gap:.2f}%** |
| **Median Cosine Similarity** | **{ats_median_sim:.4f}** | **{reddit_median_sim:.4f}** | **{reddit_median_sim - ats_median_sim:.4f}** |

---

## Semantic Diagnostics & Factual Interpretation

* **In-Domain Noise Floor ({ats_outlier_rate:.2f}%)**: Represents the statistical baseline of comments that do not strongly align to the cluster centroids, even when evaluated against a model fit on their exact same platform and era.
* **Transferred Target Rate ({reddit_outlier_rate:.2f}%)**: Represents the outlier rate when transferring Reddit comments onto the native ATS clusters.
* **The Absolute Transfer Gap (+{transfer_gap:.2f}%)**: Indicates the true semantic degradation.
  - A small gap ($< 10\%$) empirically indicates that both platforms share a symmetric, highly overlapping semantic core, meaning a transferred model holds robust validity.
  - A large gap ($> 10\%$) confirms substantial domain divergence, requiring distinct native models for each forum.
"""
    
    print("\n" + "="*50)
    print("DEFINITIVE REVERSE CONTROL-GAP TABLE")
    print("="*50)
    print(f"ATS In-Domain Floor Outlier Rate : {ats_outlier_rate:.2f}% (Median Cos: {ats_median_sim:.4f})")
    print(f"Reddit Transfer Outlier Rate     : {reddit_outlier_rate:.2f}% (Median Cos: {reddit_median_sim:.4f})")
    print(f"Absolute Reverse Transfer Gap    : +{transfer_gap:.2f}%")
    print("="*50)
    
    # Save markdown report
    with open(report_out_path, 'w') as f:
        f.write(report_md)
    print(f"\nSaved definitive diagnostic report to {report_out_path}")
    print(f"=== Reverse Topic Transfer Complete in {(time.time()-t_start)/60:.2f} minutes! ===")

if __name__ == '__main__':
    main()
