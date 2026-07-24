import os
# Set thread environments for optimal 4-core parallel CPU encoding
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["NUMBA_NUM_THREADS"] = "1"  # Strict Numba safety remains 1
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

def main():
    print("--- Step 2: Training Global BERTopic Model ---")
    
    # Configure PyTorch CPU Threads for safe and fast multi-threaded encoding
    torch.set_num_threads(4)
    device = "cpu"
    print(f"Using PyTorch device: {device} (with {torch.get_num_threads()} CPU threads)")
    
    # Paths
    train_path = 'data/processed/train_topic_comments.parquet'
    model_dir = 'data/processed/bertopic_model_new'
    
    if not os.path.exists(train_path):
        raise FileNotFoundError(f"Training dataset not found at {train_path}. Make sure Step 1 is complete!")
        
    print(f"Loading training dataset from {train_path}...")
    df_train = pd.read_parquet(train_path)
    docs = df_train['text'].fillna("").tolist()
    print(f"Loaded {len(docs):,} comments for training.")
    
    # 1. Generate Sentence Embeddings
    print("\n[1/4] Generating sentence embeddings using SentenceTransformer...")
    t0 = time.time()
    embedding_model = SentenceTransformer("all-MiniLM-L6-v2", device=device)
    embeddings = embedding_model.encode(docs, batch_size=256, show_progress_bar=True)
    print(f"Generated embeddings in {time.time()-t0:.2f} seconds.")
    print("Embedding matrix shape:", embeddings.shape)
    
    # 2. Reduce dimensions with UMAP
    print("\n[2/4] Setting up UMAP dimensionality reduction...")
    umap_model = UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric='cosine', random_state=42)
    
    # 3. Optimize word extraction
    print("[3/4] Setting up CountVectorizer...")
    vectorizer_model = CountVectorizer(stop_words="english", min_df=5)
    
    # 4. Train BERTopic Model
    print("\n[4/4] Training BERTopic model...")
    t1 = time.time()
    topic_model = BERTopic(
        embedding_model=embedding_model,
        umap_model=umap_model,
        vectorizer_model=vectorizer_model,
        min_topic_size=100,
        calculate_probabilities=False,
        verbose=True
    )
    
    topics, _ = topic_model.fit_transform(docs, embeddings)
    print(f"Model fit complete in {time.time()-t1:.2f} seconds.")
    
    # Save raw model
    print(f"\nSaving fitted model to {model_dir}...")
    topic_model.save(model_dir)
    print("Model saved successfully!")
    
    # Report initial outlier rate
    info = topic_model.get_topic_info()
    print(f"\nDiscovered {len(info)-1:,} distinct topics (excluding outliers).")
    
    outliers_initial = sum(1 for t in topics if t == -1)
    print(f"Initial Outliers: {outliers_initial:,} out of {len(topics):,} ({outliers_initial/len(topics)*100:.2f}%)")
    
    # Test outlier reduction on the training set
    print("\nTesting BERTopic built-in outlier reduction on training set...")
    t2 = time.time()
    reduced_topics = topic_model.reduce_outliers(
        docs, 
        topics, 
        strategy="embeddings", 
        embeddings=embeddings,
        threshold=0.0  # Force mapping of all outliers if possible
    )
    print(f"Outlier reduction complete in {time.time()-t2:.2f} seconds.")
    
    outliers_final = sum(1 for t in reduced_topics if t == -1)
    print(f"Final Outliers after reduction: {outliers_final:,} out of {len(topics):,} ({outliers_final/len(topics)*100:.2f}%)")
    
    # Save train assignments for reference
    df_train['topic_initial'] = topics
    df_train['topic_reduced'] = reduced_topics
    df_train.to_parquet('data/processed/train_topic_assignments.parquet')
    
    print("\n--- Training Pipeline Complete ---")

if __name__ == '__main__':
    main()
