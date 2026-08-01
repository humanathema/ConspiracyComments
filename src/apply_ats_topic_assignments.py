"""apply_ats_topic_assignments.py

ATS-side equivalent of apply_topic_assignments.py (the reddit script).
Projects the trained ATS BERTopic centroids (ats_topic_centroids.npz, 108
topics, leaf-clustering fix from 2026-07-27) onto the FULL 9.24M-row ATS
corpus, not just the 100k training sample -- and backfills outlier
comments (cosine similarity < 0.35 to every centroid) using their parent
THREAD's title instead, same trick as the reddit side: a short, generic
reply ("lol", "this is crazy") often carries no topic signal on its own,
but the thread it's posted in usually does, and ATS already carries
`thread_title` per comment.

No curated super-topic taxonomy exists yet for ATS (that's manual work,
same as the reddit side's topic_super_topic_mapping.csv was) -- this uses
the raw BERTopic topic IDs + auto-generated names directly. No synthetic
seed centroids either (none identified as missing for ATS yet).

Uses MPS (Apple Silicon GPU) if available -- CPU-only would take ~24
hours to embed 9.24M comments (extrapolated from the 15.5 min it took to
embed the 100k training sample on CPU), so GPU is not optional at this
corpus size.

Outputs:
- data/processed/ats_thread_topic_map.parquet (thread_id -> topic from title)
- data/processed/ats_comments_topic_assignments.parquet (post_id -> assigned_topic, topic_name)
"""
import os
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import argparse
import gc
import shutil
import time

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import torch
import torch.nn.functional as F
from sentence_transformers import SentenceTransformer

CORPUS_PATH = "data/processed/ats_comments_final.parquet"
CENTROIDS_PATH = "data/processed/ats_topic_centroids.npz"
MODEL_PATH = "data/processed/bertopic_model_ats_overlap"
THREAD_MAP_PATH = "data/processed/ats_thread_topic_map.parquet"
OUT_PATH = "data/processed/ats_comments_topic_assignments.parquet"
CHECKPOINT_DIR = "data/processed/.ats_topic_assignment_chunks"

TITLE_SIM_THRESHOLD = 0.40
COMMENT_SIM_THRESHOLD = 0.35


def get_topic_names():
    from bertopic import BERTopic
    model = BERTopic.load(MODEL_PATH)
    info = model.get_topic_info()
    return dict(zip(info['Topic'], info['Name']))


def main(args):
    device = "mps" if (args.device == "auto" and torch.backends.mps.is_available()) else (
        "cpu" if args.device == "auto" else args.device
    )
    print(f"--- ATS Topic Projection (thread-title outlier backfill) ---")
    print(f"Using device: {device}")
    if device == "cpu":
        torch.set_num_threads(4)

    print("Loading topic centroids...")
    centroids = np.load(CENTROIDS_PATH)
    topic_embs = centroids['embeddings']
    topic_ids = [int(t) for t in centroids['topic_ids']]
    print(f"Loaded {len(topic_ids)} topic centroids.")

    topic_names = get_topic_names()
    topic_names[-1] = "Outliers"

    embedding_model = SentenceTransformer("all-MiniLM-L6-v2", device=device)
    centroid_tensor = torch.tensor(topic_embs, dtype=torch.float32, device=device)
    centroid_tensor = F.normalize(centroid_tensor, p=2, dim=1)

    # --- PHASE A: thread-title inference (cached) ---
    thread_topic_map = {}
    if os.path.exists(THREAD_MAP_PATH):
        print(f"\n[PHASE A] Loading cached thread-title mapping from {THREAD_MAP_PATH}...")
        df_cached = pd.read_parquet(THREAD_MAP_PATH)
        thread_topic_map = dict(zip(df_cached['thread_id'], df_cached['assigned_topic'].astype(int)))
        print(f"Loaded {len(thread_topic_map):,} thread mappings.")
    else:
        print("\n[PHASE A] Embedding distinct thread titles...")
        con = duckdb.connect()
        df_titles = con.execute(f"""
            SELECT DISTINCT thread_id, thread_title
            FROM read_parquet('{CORPUS_PATH}')
            WHERE thread_title IS NOT NULL AND thread_title != 'Unknown Title'
        """).df()
        print(f"Loaded {len(df_titles):,} distinct threads.")

        chunk_size = 10000
        t0 = time.time()
        high_conf = 0
        for start in range(0, len(df_titles), chunk_size):
            chunk = df_titles.iloc[start:start + chunk_size]
            titles = chunk['thread_title'].tolist()
            embs = embedding_model.encode(titles, batch_size=256, show_progress_bar=False, convert_to_tensor=True, device=device)
            embs = F.normalize(embs, p=2, dim=1)
            sims = torch.mm(embs, centroid_tensor.t())
            max_sims, max_idx = torch.max(sims, dim=1)
            max_sims, max_idx = max_sims.cpu().numpy(), max_idx.cpu().numpy()
            for i, tid in enumerate(chunk['thread_id'].tolist()):
                if max_sims[i] >= TITLE_SIM_THRESHOLD:
                    thread_topic_map[tid] = topic_ids[max_idx[i]]
                    high_conf += 1
            del embs, sims, max_sims, max_idx
            gc.collect()
            end = min(start + chunk_size, len(df_titles))
            print(f"  Titles: {end:,} / {len(df_titles):,} | {high_conf:,} confidently mapped so far "
                  f"({(time.time()-t0)/60:.1f} min elapsed)", flush=True)

        print(f"Thread-title mapping built: {len(thread_topic_map):,} / {len(df_titles):,} threads "
              f"({len(thread_topic_map)/len(df_titles)*100:.1f}%).")
        pd.DataFrame(list(thread_topic_map.items()), columns=['thread_id', 'assigned_topic']).to_parquet(THREAD_MAP_PATH)
        print(f"Cached to {THREAD_MAP_PATH}")

    # --- PHASE B: stream all comments, assign + backfill ---
    print("\n[PHASE B] Projecting all comments (checkpointed, resumable)...")
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)

    pf = pq.ParquetFile(CORPUS_PATH)
    total_rows = pf.metadata.num_rows
    chunk_size = 20000
    total_processed = 0
    total_resolved_via_title = 0
    t_start = time.time()

    out_schema = pa.schema([
        ('post_id', pa.string()),
        ('assigned_topic', pa.int32()),
        ('topic_name', pa.string()),
        ('resolved_via_title', pa.bool_()),
    ])

    for batch_idx, batch in enumerate(pf.iter_batches(batch_size=chunk_size, columns=['post_id', 'thread_id', 'body'])):
        chunk_path = os.path.join(CHECKPOINT_DIR, f"chunk_{batch_idx:05d}.parquet")
        if os.path.exists(chunk_path):
            total_processed += batch.num_rows
            continue

        t0 = time.time()
        df = batch.to_pandas()
        texts = df['body'].fillna("").tolist()

        embs = embedding_model.encode(texts, batch_size=256 if device != "cpu" else 128,
                                       show_progress_bar=False, convert_to_tensor=True, device=device)
        embs = F.normalize(embs, p=2, dim=1)
        sims = torch.mm(embs, centroid_tensor.t())
        max_sims, max_idx = torch.max(sims, dim=1)
        max_sims, max_idx = max_sims.cpu().numpy(), max_idx.cpu().numpy()

        thread_ids = df['thread_id'].values
        assigned, names, resolved_flags = [], [], []
        n_resolved = 0
        for i in range(len(df)):
            if max_sims[i] >= COMMENT_SIM_THRESHOLD:
                topic = topic_ids[max_idx[i]]
                resolved = False
            else:
                fallback = thread_topic_map.get(thread_ids[i])
                if fallback is not None:
                    topic = fallback
                    resolved = True
                    n_resolved += 1
                else:
                    topic = -1
                    resolved = False
            assigned.append(topic)
            names.append(topic_names.get(topic, "Outliers"))
            resolved_flags.append(resolved)

        out_table = pa.table({
            'post_id': pa.array(df['post_id'].astype(str)),
            'assigned_topic': pa.array(np.array(assigned, dtype=np.int32)),
            'topic_name': pa.array(names),
            'resolved_via_title': pa.array(resolved_flags),
        }, schema=out_schema)
        pq.write_table(out_table, chunk_path + '.tmp', compression='snappy')
        os.rename(chunk_path + '.tmp', chunk_path)

        total_processed += len(df)
        total_resolved_via_title += n_resolved
        elapsed = time.time() - t_start
        rate = total_processed / elapsed if elapsed > 0 else 0
        eta_min = (total_rows - total_processed) / rate / 60 if rate > 0 else float('inf')
        print(f"  Chunk {batch_idx}: {total_processed:,} / {total_rows:,} rows | "
              f"{n_resolved:,} outliers resolved via title this chunk | "
              f"{rate:.0f} rows/sec | ETA {eta_min:.1f} min", flush=True)

        del df, texts, embs, sims, max_sims, max_idx
        gc.collect()
        if device == "mps":
            torch.mps.empty_cache()

        if args.benchmark_chunks and batch_idx + 1 >= args.benchmark_chunks:
            print(f"\n--- Benchmark mode: stopping after {args.benchmark_chunks} chunk(s) ---")
            print(f"Observed rate: {rate:.0f} rows/sec -> full corpus ETA: {(total_rows/rate)/60:.1f} min")
            return

    print(f"\nMerging {batch_idx+1} checkpoint chunks into {OUT_PATH}...")
    con = duckdb.connect()
    con.execute(f"COPY (SELECT * FROM read_parquet('{CHECKPOINT_DIR}/*.parquet')) TO '{OUT_PATH}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    shutil.rmtree(CHECKPOINT_DIR)
    print(f"Done. Total outliers resolved via thread title: {total_resolved_via_title:,}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', choices=['auto', 'mps', 'cpu'], default='auto')
    parser.add_argument('--benchmark-chunks', type=int, default=0,
                         help="Stop after N chunks and print an ETA, instead of running the full corpus")
    args = parser.parse_args()
    main(args)
