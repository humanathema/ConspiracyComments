import os
# Configure optimal parallel thread environments
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["NUMBA_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import argparse
import pandas as pd
import numpy as np
import torch
import torch.nn.functional as F
import time
import gc
import shutil
import pyarrow as pa
import pyarrow.parquet as pq
import duckdb
from sentence_transformers import SentenceTransformer

def clean_link_id(link_id):
    if pd.isna(link_id):
        return ""
    s = str(link_id)
    if s.startswith("t3_"):
        return s[3:]
    return s

def main(args):
    print("--- Step 3: Fast GPU-Accelerated Checkpointed Topic Projection ---")

    # Enable Apple Silicon GPU (MPS) acceleration safely
    if args.device == "auto":
        device = "mps" if torch.backends.mps.is_available() else "cpu"
    else:
        device = args.device
    if device == "cpu":
        torch.set_num_threads(4)
    print(f"Using device for encoding: {device} | shard: {sorted(args.shard_residues)} mod {args.shard_mod}")
    
    centroids_path = 'data/processed/topic_centroids.npz'
    synthesis_path = 'data/processed/master_thread_synthesis.parquet'
    mapping_path = 'data/processed/topic_super_topic_mapping.csv'
    thread_map_path = 'data/processed/thread_topic_map.parquet'

    # Pre-extracted from bertopic_model_new (97x384 topic_embeddings_, outlier
    # topic excluded). Loading the full BERTopic model costs ~1.5GB RSS just to
    # read this array; the npz costs ~150KB.
    if not os.path.exists(centroids_path):
        raise FileNotFoundError(f"Centroids not found at {centroids_path} — extract topic_embeddings_ from the BERTopic model first")
    if not os.path.exists(mapping_path):
        raise FileNotFoundError(f"Taxonomy mapping not found at {mapping_path}")

    print("Loading SentenceTransformer model on GPU...")
    embedding_model = SentenceTransformer("all-MiniLM-L6-v2", device=device)
    print("SentenceTransformer loaded successfully!")
    
    # Load dynamic curated taxonomy mappings
    print(f"Loading curated taxonomy from {mapping_path}...")
    mapping_df = pd.read_csv(mapping_path)
    super_topic_dict = dict(zip(mapping_df['Topic'].astype(int), mapping_df['Super_Topic']))
    topic_dict = dict(zip(mapping_df['Topic'].astype(int), mapping_df['Topic_Name']))
    
    # Inject the 3 newly tuned and validated Synthetic Centroid labels into taxonomy maps
    synthetic_seeds = {
        -101: "5g emf cellular radiation towers electromagnetic fields radiofrequency health hazards 5g network technology safety cell phones",
        -102: "pesticides glyphosate round up monsanto agricultural chemicals crop toxicity poison chemical industry herbicide",
        -103: "microplastics nanoplastics plastic particles plastic debris polymer fragments plastic contamination in blood tissue human organs synthetic polymers"
    }
    
    synthetic_names = {
        -101: "EMF_5G_Radiation_Hazard",
        -102: "Pesticides_Glyphosate_Toxicity",
        -103: "Microplastics_Pollution"
    }
    
    for s_id, s_name in synthetic_names.items():
        topic_dict[s_id] = s_name
        super_topic_dict[s_id] = "Environment, Science, Health & Tech"
        
    # Add outlier fallback mapping
    super_topic_dict[-1] = "Outliers"
    topic_dict[-1] = "Outliers"
    
    # 1. Load pre-extracted 97 valid topic embeddings
    print(f"Loading topic centroids from {centroids_path}...")
    centroids = np.load(centroids_path)
    valid_topic_embs = centroids['embeddings'] # shape (97, 384)
    valid_topic_ids = [int(t) for t in centroids['topic_ids']]

    # Load original topic embeddings to GPU and normalize them
    orig_embs_tensor = torch.tensor(valid_topic_embs, dtype=torch.float32, device=device)
    orig_embs_tensor = F.normalize(orig_embs_tensor, p=2, dim=1)
    
    # 2. Embed synthetic seeds and normalize them
    print("Embedding synthetic centroids and compiling global 100-centroid matrix...")
    synth_embs_list = []
    synth_ids = list(synthetic_seeds.keys())
    for s_id in synth_ids:
        emb = embedding_model.encode(synthetic_seeds[s_id], convert_to_tensor=True, device=device)
        synth_embs_list.append(emb)
        
    synth_embs_tensor = torch.stack(synth_embs_list)
    synth_embs_tensor = F.normalize(synth_embs_tensor, p=2, dim=1)
    
    # 3. Concatenate to create a globally patched 100-centroid similarity matrix
    patched_embs_tensor = torch.cat([orig_embs_tensor, synth_embs_tensor], dim=0) # shape (100, 384)
    patched_topic_ids = valid_topic_ids + synth_ids
    print(f"Successfully compiled globally patched 100-centroid matrix on {device}!")
    
    # --- PHASE 3A: POST-TITLE INFERENCE (WITH INSTANT DISK CACHING) ---
    thread_topic_map = {}
    
    if os.path.exists(thread_map_path):
        print(f"\n[PHASE 3A] Found cached thread mapping at {thread_map_path}!")
        print("Loading thread mapping from disk cache...", flush=True)
        t_load = time.time()
        df_cached_map = pd.read_parquet(thread_map_path)
        thread_topic_map = dict(zip(df_cached_map['post_id'], df_cached_map['assigned_topic'].astype(int)))
        print(f"Loaded {len(thread_topic_map):,} thread mappings in {time.time()-t_load:.2f} seconds! Skipping title encoding entirely.", flush=True)
    else:
        print("\n[PHASE 3A] Running inference on post titles for thread-level mapping (manually chunked)...", flush=True)
        con = duckdb.connect()
        df_synthesis = con.execute(f"SELECT post_id, title FROM '{synthesis_path}' WHERE title IS NOT NULL").df()
        total_titles = len(df_synthesis)
        print(f"Loaded {total_titles:,} post titles.", flush=True)
        
        # 10k title chunk size is optimal for 8GB Apple Silicon unified RAM safety
        title_chunk_size = 10000
        high_conf_count = 0
        t0 = time.time()
        
        for start_idx in range(0, total_titles, title_chunk_size):
            end_idx = min(start_idx + title_chunk_size, total_titles)
            df_chunk = df_synthesis.iloc[start_idx:end_idx]
            titles = df_chunk['title'].tolist()
            
            # High-speed GPU encoding
            title_embeddings = embedding_model.encode(titles, batch_size=512, show_progress_bar=False, convert_to_tensor=True)
            title_embeddings = F.normalize(title_embeddings, p=2, dim=1)
            
            # Calculate post title semantic assignments on GPU via cosine similarity (against all 100 centroids)
            title_similarities = torch.mm(title_embeddings, patched_embs_tensor.t())
            max_sims, max_indices = torch.max(title_similarities, dim=1)
            
            max_sims_cpu = max_sims.cpu().numpy()
            max_indices_cpu = max_indices.cpu().numpy()
            
            # Build thread mapping dictionary (confidence >= 0.40)
            for i, row in enumerate(df_chunk.itertuples()):
                post_id = row.post_id
                sim = max_sims_cpu[i]
                topic_idx = max_indices_cpu[i]
                
                if sim >= 0.40:
                    thread_topic_map[post_id] = int(patched_topic_ids[topic_idx])
                    high_conf_count += 1
                    
            # Force cache clearing
            del titles, title_embeddings, title_similarities, max_sims, max_indices, max_sims_cpu, max_indices_cpu
            gc.collect()
            if device == "mps":
                torch.mps.empty_cache()
                
            if (end_idx % 50000 == 0) or (end_idx == total_titles):
                print(f"  Processed post titles: {end_idx:,} / {total_titles:,} | Speed: {end_idx/(time.time()-t0):.1f} docs/sec", flush=True)
            
        print(f"Title processing complete in {(time.time()-t0)/60:.2f} minutes.")
        print(f"Built thread mapping for {len(thread_topic_map):,} out of {total_titles:,} threads ({high_conf_count/total_titles*100:.6f}% high-confidence).")
        
        # Save thread mapping to disk cache immediately
        print(f"Saving thread-to-topic map to disk cache: {thread_map_path} ...", flush=True)
        df_save_map = pd.DataFrame(list(thread_topic_map.items()), columns=['post_id', 'assigned_topic'])
        df_save_map.to_parquet(thread_map_path, compression='snappy')
        print("Saved thread mapping disk cache successfully!", flush=True)
        
        # Free memory
        del df_synthesis, df_save_map
        gc.collect()
        
    # --- PHASE 3B: STREAMING COMMENTS INFERENCE (WITH CHECKPOINTING) ---
    print("\n[PHASE 3B] Running high-speed checkpointed GPU loop on comments...", flush=True)
    
    files_to_process = [
        ('data/processed/empath_scores_full.parquet', 'data/processed/empath_scores_full_mapped.parquet', 'empath_scores_full'),
        ('data/processed/conspiracy_comments_short_lte100chars.parquet', 'data/processed/conspiracy_comments_short_lte100chars_mapped.parquet', 'short_comments')
    ]
    
    for src_file, out_file, folder_name in files_to_process:
        if not os.path.exists(src_file):
            print(f"Skipping missing source file: {src_file}")
            continue
            
        print(f"\nProcessing {src_file} -> {out_file}...", flush=True)
        
        # Create temporary checkpoints directory
        checkpoint_dir = f"data/processed/checkpoints_{folder_name}"
        os.makedirs(checkpoint_dir, exist_ok=True)
        
        pf = pq.ParquetFile(src_file)
        src_schema = pf.schema.to_arrow_schema()
        
        # Output schema definitions
        new_fields = [
            pa.field('assigned_topic', pa.int32()),
            pa.field('topic_name', pa.string()),
            pa.field('super_topic', pa.string())
        ]
        out_schema = pa.schema(list(src_schema) + new_fields)
        
        # 10k comments per chunk is highly efficient and safe
        chunk_size = 10000
        total_rows_processed = 0
        t_start = time.time()
        
        # Iterate and write to checkpoints
        for batch_idx, batch in enumerate(pf.iter_batches(batch_size=chunk_size)):
            chunk_file_path = f"{checkpoint_dir}/chunk_{batch_idx:05d}.parquet"
            
            # Checkpoint skipping check (Resume Logic)
            if os.path.exists(chunk_file_path):
                total_rows_processed += batch.num_rows
                continue

            # Shard split: lets a second worker process (e.g. a CPU worker
            # alongside the GPU one) share the checkpoint dir, each taking
            # disjoint chunk residues mod --shard-mod
            if (batch_idx % args.shard_mod) not in args.shard_residues:
                total_rows_processed += batch.num_rows
                continue
                
            t_batch_start = time.time()
            df_chunk = batch.to_pandas()
            texts = df_chunk['text'].fillna("").tolist()
            
            # 1. GPU embedding with length-partitioned batch sizes. Peak Metal
            # memory scales with batch_size x seq_len^2 and encode() sorts by
            # length internally, so batches of long comments (27.6% of this
            # file is >400 chars, p99 ~2k chars = full 256-token window) blow
            # the GPU at a fixed 512. Long texts get small batches, short
            # texts keep large ones; embedding values are unaffected.
            idx_short = [i for i, t in enumerate(texts) if len(t) <= 400]
            idx_long = [i for i, t in enumerate(texts) if len(t) > 400]
            chunk_embeddings = torch.empty((len(texts), patched_embs_tensor.shape[1]), dtype=torch.float32, device=device)
            for part_idxs, part_bsz in ((idx_short, 256), (idx_long, 64)):
                if part_idxs:
                    part_embs = embedding_model.encode([texts[i] for i in part_idxs], batch_size=part_bsz, show_progress_bar=False, convert_to_tensor=True)
                    chunk_embeddings[part_idxs] = part_embs
                    del part_embs
            chunk_embeddings = F.normalize(chunk_embeddings, p=2, dim=1)
            
            # 2. Fast GPU Cosine Similarity Cosine Mapping (Against the patched 100-centroid matrix)
            similarities = torch.mm(chunk_embeddings, patched_embs_tensor.t())
            max_sims, max_indices = torch.max(similarities, dim=1)
            
            max_sims_cpu = max_sims.cpu().numpy()
            max_indices_cpu = max_indices.cpu().numpy()
            
            # 3. Apply Fallback Logic and Similarity Threshold (0.35)
            # HIGH SPEED OPTIMIZED LOOP (Removes df.iterrows() completely!)
            final_topics = []
            comments_resolved = 0
            link_ids = df_chunk['link_id'].values
            
            for comment_idx in range(len(df_chunk)):
                sim = max_sims_cpu[comment_idx]
                topic_idx = max_indices_cpu[comment_idx]
                
                # Base similarity classification (against patched_topic_ids)
                topic = int(patched_topic_ids[topic_idx]) if sim >= 0.35 else -1
                
                # Fallback to post-title mapping if comment is an outlier
                if topic == -1:
                    raw_lid = link_ids[comment_idx]
                    link_id_clean = clean_link_id(raw_lid)
                    if link_id_clean in thread_topic_map:
                        topic = thread_topic_map[link_id_clean]
                        comments_resolved += 1
                        
                final_topics.append(topic)
                
            # Enrich chunk dataframe
            df_chunk['assigned_topic'] = final_topics
            df_chunk['topic_name'] = df_chunk['assigned_topic'].map(topic_dict).fillna("Outliers")
            df_chunk['super_topic'] = df_chunk['assigned_topic'].map(super_topic_dict).fillna("Outliers")
            
            # Convert to PyArrow arrays
            arrow_assigned = pa.array(df_chunk['assigned_topic'].astype(np.int32))
            arrow_topic_name = pa.array(df_chunk['topic_name'].astype(str))
            arrow_super_topic = pa.array(df_chunk['super_topic'].astype(str))
            
            # Reconstruct batch columns
            out_columns = [batch.column(name) for name in batch.schema.names]
            out_columns.extend([arrow_assigned, arrow_topic_name, arrow_super_topic])
            
            out_batch = pa.RecordBatch.from_arrays(out_columns, schema=out_schema)
            
            # Write chunk parquet atomically: a crash mid-write must not leave a
            # truncated file at chunk_file_path, or the resume check would skip it
            chunk_writer = pq.ParquetWriter(chunk_file_path + '.tmp', out_schema, compression='snappy')
            chunk_writer.write_batch(out_batch)
            chunk_writer.close()
            os.rename(chunk_file_path + '.tmp', chunk_file_path)
            
            total_rows_processed += len(df_chunk)
            t_batch_elapsed = time.time() - t_batch_start
            
            # Console stats logging after every chunk (updated live!)
            if (batch_idx % 5 == 0) or (total_rows_processed >= pf.metadata.num_rows):
                print(f"  Chunk {batch_idx:04d}: Processed {total_rows_processed:,} / {pf.metadata.num_rows:,} rows | Resolved {comments_resolved:,} outliers via thread titles ({comments_resolved/len(df_chunk)*100:.2f}%) | Speed: {len(df_chunk)/t_batch_elapsed:.1f} rows/sec", flush=True)
            
            # Aggressive device cache purging
            del df_chunk, texts, chunk_embeddings, similarities, max_sims, max_indices, out_batch, out_columns
            gc.collect()
            if device == "mps":
                torch.mps.empty_cache()
                
        # --- END OF CHUNK LOOP: MERGE ALL CHECKPOINT FILES ---
        # With sharded workers, only the worker that completes the final
        # missing chunk performs the merge; earlier finishers move on
        expected_chunks = (pf.metadata.num_rows + chunk_size - 1) // chunk_size
        done_chunks = len([f for f in os.listdir(checkpoint_dir) if f.endswith('.parquet')])
        if done_chunks < expected_chunks:
            print(f"\nThis worker's share of {src_file} is done ({done_chunks}/{expected_chunks} chunks on disk); leaving the merge to the last-finishing worker.", flush=True)
            continue
        print(f"\nMerging checkpoint files into final output parquet: {out_file} ...", flush=True)
        con_merge = duckdb.connect()
        con_merge.execute(f"COPY (SELECT * FROM '{checkpoint_dir}/*.parquet') TO '{out_file}' (FORMAT PARQUET, COMPRESSION SNAPPY)")
        print(f"Merged successfully! Saved output to {out_file}", flush=True)
        
        # Clean up temporary folder
        print(f"Cleaning up checkpoint directory: {checkpoint_dir} ...", flush=True)
        shutil.rmtree(checkpoint_dir)
        
        print(f"Completed {src_file} projection in {(time.time()-t_start)/60:.2f} minutes.", flush=True)
        
    print("\n--- ALL TOPIC PROJECTIONS COMPLETED SUCCESSFULLY ---", flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Checkpointed topic projection; supports sharded multi-worker runs")
    parser.add_argument('--device', choices=['auto', 'mps', 'cpu'], default='auto')
    parser.add_argument('--shard-mod', type=int, default=1,
                        help="Number of shard buckets (chunks assigned by chunk_idx %% shard-mod)")
    parser.add_argument('--shard-take', type=str, default='',
                        help="Comma-separated residues this worker processes, e.g. '0,1,2'. Empty = all")
    args = parser.parse_args()
    if args.shard_take:
        args.shard_residues = {int(r) for r in args.shard_take.split(',')}
    else:
        args.shard_residues = set(range(args.shard_mod))
    main(args)
