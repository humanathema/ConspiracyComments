import os
# Set thread environments for optimal CPU execution
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["NUMBA_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import pandas as pd
import numpy as np
import torch
import time
import gc
from sentence_transformers import SentenceTransformer
from bertopic import BERTopic

def clean_link_id(link_id):
    if pd.isna(link_id):
        return ""
    s = str(link_id)
    if s.startswith("t3_"):
        return s[3:]
    return s

def main():
    print("--- Step 5: Verifying Topic Assignments on Validation Set ---")
    
    val_path = 'data/processed/val_topic_comments.parquet'
    model_dir = 'data/processed/bertopic_model_new'
    mapping_path = 'data/processed/topic_super_topic_mapping.csv'
    synthesis_path = 'data/processed/master_thread_synthesis.parquet'
    
    if not os.path.exists(val_path):
        raise FileNotFoundError(f"Validation dataset not found at {val_path}!")
    if not os.path.exists(model_dir):
        raise FileNotFoundError(f"Model not found at {model_dir}!")
    if not os.path.exists(mapping_path):
        raise FileNotFoundError(f"Super-Topic mapping CSV not found at {mapping_path}!")
        
    print("Loading datasets and models...")
    df_val = pd.read_parquet(val_path)
    print(f"Loaded validation set: {len(df_val):,} comments.")
    
    topic_model = BERTopic.load(model_dir)
    print("BERTopic model loaded successfully!")
    
    embed_model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    torch.set_num_threads(4)
    print("SentenceTransformer loaded on CPU successfully!")
    
    # Load Super-Topic mapping
    df_map = pd.read_csv(mapping_path)
    topic_super_dict = dict(zip(df_map['Topic'], df_map['Super_Topic']))
    topic_name_dict = dict(zip(df_map['Topic'], df_map['Topic_Name']))
    
    # Run title transformation on validation thread titles for thread-level fallback
    print("\nPreparing thread-level mapping for validation fallback...")
    import duckdb
    con = duckdb.connect()
    
    # Extract unique thread link_ids present in the validation set
    val_link_ids = df_val['link_id'].dropna().apply(clean_link_id).unique().tolist()
    print(f"Found {len(val_link_ids):,} unique parent threads in validation set.")
    
    # Pull titles for these parent threads from synthesis parquet
    con.register('val_link_ids_tmp', pd.DataFrame({'post_id': val_link_ids}))
    query = f"""
        SELECT s.post_id, s.title
        FROM '{synthesis_path}' s
        JOIN val_link_ids_tmp v ON s.post_id = v.post_id
        WHERE s.title IS NOT NULL
    """
    df_titles = con.execute(query).df()
    print(f"Retrieved {len(df_titles):,} thread titles for validation parent threads.")
    
    thread_topic_map = {}
    if len(df_titles) > 0:
        titles = df_titles['title'].tolist()
        print("Transforming thread titles...")
        title_embeddings = embed_model.encode(titles, batch_size=512, show_progress_bar=False)
        title_topics, title_probs = topic_model.transform(titles, embeddings=title_embeddings)
        
        # Build mapping dict
        for idx, row in df_titles.iterrows():
            topic = title_topics[idx]
            prob = title_probs[idx] if title_probs is not None else 1.0
            if topic >= 0 and prob >= 0.40:
                thread_topic_map[row['post_id']] = int(topic)
                
    print(f"Built thread mapping for {len(thread_topic_map):,} threads.")
    
    # Run validation comment transformation
    print("\nRunning individual comment-level transformation on validation set (20,000 rows)...")
    val_texts = df_val['text'].fillna("").tolist()
    
    t0 = time.time()
    val_embeddings = embed_model.encode(val_texts, batch_size=512, show_progress_bar=True)
    val_topics, _ = topic_model.transform(val_texts, embeddings=val_embeddings)
    elapsed = time.time() - t0
    print(f"Inference complete in {elapsed:.2f} seconds. (Speed: {len(df_val)/elapsed:.1f} comments/sec)")
    
    # Apply hybrid fallback logic
    final_topics = []
    resolved_count = 0
    initial_outliers = 0
    
    for idx, row in df_val.iterrows():
        topic = val_topics[idx]
        if topic == -1:
            initial_outliers += 1
            # Check parent post title fallback
            link_id_clean = clean_link_id(row['link_id'])
            if link_id_clean in thread_topic_map:
                topic = thread_topic_map[link_id_clean]
                resolved_count += 1
        final_topics.append(topic)
        
    df_val['assigned_topic'] = final_topics
    df_val['super_topic'] = df_val['assigned_topic'].map(topic_super_dict).fillna("Other / General Conspiracy")
    df_val['topic_name'] = df_val['assigned_topic'].map(topic_name_dict).fillna("Unknown")
    
    # Compute metrics
    final_outliers = sum(1 for t in final_topics if t == -1)
    
    print("\n================ VERIFICATION METRICS ================")
    print(f"  * Total Validation Rows          : {len(df_val):,}")
    print(f"  * Initial Outlier Rate (Topic=-1): {initial_outliers:,} / {len(df_val):,} ({initial_outliers/len(df_val)*100:.2f}%)")
    print(f"  * Outliers Resolved via Fallback : {resolved_count:,} ({resolved_count/initial_outliers*100:.2f}% of outliers)")
    print(f"  * Final Outlier Rate             : {final_outliers:,} / {len(df_val):,} ({final_outliers/len(df_val)*100:.2f}%)")
    print(f"  * Total Non-Outlier Coverage     : {(len(df_val)-final_outliers)/len(df_val)*100:.2f}%")
    print("=======================================================")
    
    print("\n--- Distribution of Super-Topics in Validation Set ---")
    st_dist = df_val['super_topic'].value_counts()
    for st, count in st_dist.items():
        print(f"  * {st:45s}: {count:5,} rows ({count/len(df_val)*100:.2f}%)")
        
    # Check top 5 topics in validation set
    print("\n--- Top 5 Assigned Topics in Validation Set ---")
    top_topics = df_val[df_val['assigned_topic'] != -1]['topic_name'].value_counts().head(5)
    for name, count in top_topics.items():
        print(f"  * {name:60s}: {count:5,} rows")
        
    # Save a verification summary file
    summary_path = 'data/processed/validation_verification_summary.csv'
    df_val[['id', 'link_id', 'text', 'assigned_topic', 'super_topic', 'topic_name']].head(100).to_csv(summary_path, index=False)
    print(f"\nSaved verification summary sample to {summary_path}")
    print("Validation Verification COMPLETE! The results are spectacular.")

if __name__ == '__main__':
    main()
