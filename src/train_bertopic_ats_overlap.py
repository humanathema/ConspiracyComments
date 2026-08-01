"""
train_bertopic_ats_overlap.py

Trains a native, global BERTopic model on the stratified 100k ATS overlap sample
specifically within the 2008-2016 window, replicating the hyperparameter configuration
of the Reddit-side topic model.

Saves:
- The fitted model to data/processed/bertopic_model_ats_overlap
- Pre-extracted topic centroids to data/processed/ats_topic_centroids.npz
- Training topic assignments to data/processed/ats_train_topic_assignments.parquet

Forced to CPU-only execution inside the secure sandbox, utilizing memory-safe
chunking and garbage collection.
"""
import os
# Configure optimal parallel thread environments
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["NUMBA_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import pandas as pd
import numpy as np
import torch
import time
import gc
from sentence_transformers import SentenceTransformer
from umap import UMAP
from sklearn.feature_extraction.text import CountVectorizer
from bertopic import BERTopic
import hdbscan

def main():
    print("=== Step 2: Training Overlap-Era ATS-Native BERTopic Model ===")
    t_start = time.time()
    
    # Force CPU to run securely and predictably inside the sandbox without MPS paging overhead
    device = "cpu"
    torch.set_num_threads(4)
    print(f"Using PyTorch device: {device} (with {torch.get_num_threads()} CPU threads)")
    
    # Paths
    train_path = 'data/processed/ats_train_overlap_sample.parquet'
    embeddings_cache_path = 'data/processed/ats_train_overlap_embeddings.npy'
    model_dir = 'data/processed/bertopic_model_ats_overlap'
    centroids_out = 'data/processed/ats_topic_centroids.npz'
    assignments_out = 'data/processed/ats_train_topic_assignments.parquet'
    
    if not os.path.exists(train_path):
        raise FileNotFoundError(f"Training overlap sample not found at {train_path}!")
        
    print(f"Loading 100k training dataset from {train_path}...")
    df_train = pd.read_parquet(train_path)
    docs = df_train['body'].fillna("").tolist()
    print(f"Loaded {len(docs):,} comments for training.")
    
    # 1. Generate or Load Sentence Embeddings
    embeddings = None
    if os.path.exists(embeddings_cache_path):
        print(f"\n[1/4] Loading cached embeddings from {embeddings_cache_path}...")
        embeddings = np.load(embeddings_cache_path)
        print(f"Loaded embeddings of shape {embeddings.shape} instantly!")
    else:
        print("\n[1/4] Generating sentence embeddings using SentenceTransformer on CPU...")
        t0 = time.time()
        embedding_model = SentenceTransformer("all-MiniLM-L6-v2", device=device)
        
        # Encode in memory-safe 10k chunks with active garbage collection
        embeddings_list = []
        chunk_size = 10000
        for i in range(0, len(docs), chunk_size):
            chunk_docs = docs[i:i+chunk_size]
            chunk_embs = embedding_model.encode(
                chunk_docs,
                batch_size=256,
                show_progress_bar=False,
                convert_to_tensor=True,
                device=device
            )
            embeddings_list.append(chunk_embs.numpy())
            del chunk_embs
            gc.collect()
            processed_count = min(i + chunk_size, len(docs))
            print(f"  Encoded {processed_count:,} / {len(docs):,} comments ...", flush=True)
            
        embeddings = np.concatenate(embeddings_list, axis=0)
        print(f"Generated embeddings matrix shape {embeddings.shape} in {(time.time()-t0)/60:.2f} minutes!", flush=True)
        
        # Save to cache immediately
        print(f"Saving generated embeddings to cache: {embeddings_cache_path}", flush=True)
        np.save(embeddings_cache_path, embeddings)
        
    # 2. UMAP Dimensionality Reduction
    print("\n[2/4] Initializing UMAP (n_neighbors=15, n_components=5, cosine, random_state=42)...", flush=True)
    umap_model = UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric='cosine', random_state=42)
    
    # 3. Vectorizer
    # Note: Use min_df=1 to prevent scikit-learn crashes during c-TF-IDF calculation
    # if the number of topics is small (e.g., fewer than 5 topics).
    print("[3/4] Initializing CountVectorizer (stop_words='english', min_df=1)...", flush=True)
    vectorizer_model = CountVectorizer(stop_words="english", min_df=1)

    # HDBSCAN with cluster_selection_method='leaf' explicitly, not BERTopic's
    # default 'eom' (Excess of Mass). Found 2026-07-27: 'eom' collapsed this
    # 100k-doc ATS training sample into 1-2 giant clusters with ~0% outliers
    # (verified this isn't a data/embedding problem -- embeddings are
    # healthy, real variance, and the same UMAP output clusters into 12
    # topics fine at 10k-doc scale; it's specifically an 'eom'-at-100k-scale
    # behavior). 'leaf' on the identical UMAP output gives 108 clusters,
    # 67% outliers -- real topic structure, not a fix invented to force a
    # particular number.
    print("[3.5/4] Initializing HDBSCAN (min_cluster_size=100, cluster_selection_method='leaf')...", flush=True)
    hdbscan_model = hdbscan.HDBSCAN(min_cluster_size=100, metric='euclidean', cluster_selection_method='leaf', prediction_data=True)

    # 4. Train BERTopic Model
    print("\n[4/4] Fitting BERTopic Model (min_topic_size=100)...", flush=True)
    t1 = time.time()
    embedding_model = SentenceTransformer("all-MiniLM-L6-v2", device=device)
    topic_model = BERTopic(
        embedding_model=embedding_model,
        umap_model=umap_model,
        hdbscan_model=hdbscan_model,
        vectorizer_model=vectorizer_model,
        min_topic_size=100,
        calculate_probabilities=False,
        verbose=True
    )
    
    topics, _ = topic_model.fit_transform(docs, embeddings)
    print(f"BERTopic fit complete in {(time.time()-t1)/60:.2f} minutes!", flush=True)
    
    # Report initial outlier statistics
    info = topic_model.get_topic_info()
    n_topics = len(info) - 1 # exclude topic -1
    print(f"\nDiscovered {n_topics:,} distinct topics (excluding outliers).", flush=True)
    
    outliers_initial = sum(1 for t in topics if t == -1)
    print(f"Initial Outliers (Topic -1): {outliers_initial:,} / {len(topics):,} ({outliers_initial/len(topics)*100:.2f}%)", flush=True)
    
    # Save the fitted raw model
    print(f"\nSaving BERTopic model to {model_dir}...", flush=True)
    topic_model.save(model_dir)
    print("Model saved successfully!", flush=True)
    
    # Extract Topic Centroids (mean embedding per valid topic, excluding -1)
    print(f"\nExtracting and saving topic centroids to {centroids_out}...", flush=True)
    unique_topics = sorted(list(set(topics)))
    valid_topics = [t for t in unique_topics if t != -1]
    
    topic_centroids = []
    for t in valid_topics:
        t_indices = np.where(np.array(topics) == t)[0]
        t_embs = embeddings[t_indices]
        t_centroid = np.mean(t_embs, axis=0)
        topic_centroids.append(t_centroid)
        
    topic_centroids = np.array(topic_centroids)
    np.savez(centroids_out, embeddings=topic_centroids, topic_ids=valid_topics)
    print(f"Saved {len(valid_topics)} centroids of shape {topic_centroids.shape}!", flush=True)
    
    # Save training assignments
    print(f"Saving training assignments to {assignments_out}...", flush=True)
    df_train['topic_initial'] = topics
    df_train.to_parquet(assignments_out)
    
    print(f"\n=== ATS BERTopic Training Complete in {(time.time()-t_start)/60:.2f} minutes! ===", flush=True)

if __name__ == '__main__':
    main()
