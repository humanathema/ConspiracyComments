# cloudrun_seed_probe/main.py
import os
import json
import logging
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastembed import TextEmbedding
import gcsfs

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_probe")

app = FastAPI(title="ConspiracyComments Seed-Claim Probe API")

# Add CORS middleware to support local testing and external access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables to hold loaded data
MODEL = None
ASSIGNMENTS_DF = None
EMBEDDINGS = None
CENTROIDS = None
CENTROID_TOPIC_IDS = None

# GCS settings
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "sapient-zodiac-502400-k2-conspiracy-data")

def parse_topic_id(val):
    if isinstance(val, int):
        return val
    try:
        return int(str(val).split('_')[0])
    except ValueError:
        return None

@app.on_event("startup")
def initialize_data():
    global MODEL, ASSIGNMENTS_DF, EMBEDDINGS, CENTROIDS, CENTROID_TOPIC_IDS
    logger.info("Initializing fastembed model 'sentence-transformers/all-MiniLM-L6-v2' (ONNX, CPU)...")
    try:
        # Use sentence-transformers/all-MiniLM-L6-v2 which maps to 384-dimensional space
        MODEL = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    except Exception as e:
        logger.error(f"Failed to initialize fastembed model: {e}")
        raise e

    logger.info(f"Connecting to GCS bucket '{BUCKET_NAME}' to load cached embeddings and assignments...")
    try:
        fs = gcsfs.GCSFileSystem()
        
        # 1. Load topic centroids
        centroids_path = f"{BUCKET_NAME}/topic_centroids.npz"
        logger.info(f"Loading centroids from gs://{centroids_path}...")
        with fs.open(centroids_path, "rb") as f:
            c_data = np.load(f)
            CENTROIDS = c_data["embeddings"]
            CENTROID_TOPIC_IDS = c_data["topic_ids"]
        logger.info(f"Successfully loaded centroids for {len(CENTROID_TOPIC_IDS)} topics.")

        # 2. Load comment topic assignments
        df_path = f"{BUCKET_NAME}/train_topic_assignments.parquet"
        logger.info(f"Loading topic assignments from gs://{df_path}...")
        with fs.open(df_path, "rb") as f:
            df = pd.read_parquet(f)
        df_clean = df[df["topic_reduced"] != -1].copy()
        df_clean["embeddings_idx"] = np.arange(len(df_clean))
        ASSIGNMENTS_DF = df_clean
        logger.info(f"Successfully loaded {len(ASSIGNMENTS_DF):,} comment assignments.")

        # 3. Load embeddings cache
        emb_path = f"{BUCKET_NAME}/_audit_topic_quality_embeddings_cache.npy"
        logger.info(f"Loading embeddings cache from gs://{emb_path}...")
        with fs.open(emb_path, "rb") as f:
            EMBEDDINGS = np.load(f)
        
        assert len(EMBEDDINGS) == len(ASSIGNMENTS_DF), f"Embeddings size ({len(EMBEDDINGS)}) does not match assignments size ({len(ASSIGNMENTS_DF)})!"
        logger.info("Successfully loaded embedding cache into memory!")

    except Exception as e:
        logger.error(f"Critical error loading starting datasets from GCS: {e}")
        # Keep running so health-checks don't enter restart loops, but endpoints will error
        pass

@app.get("/api/probe_health")
def health_check():
    loaded = (MODEL is not None and EMBEDDINGS is not None and ASSIGNMENTS_DF is not None)
    return {
        "status": "ok" if loaded else "initializing_or_failed",
        "model_loaded": MODEL is not None,
        "data_loaded": EMBEDDINGS is not None,
        "bucket": BUCKET_NAME
    }

# FastAPI backward-compatibility with GET /api/health
@app.get("/api/health")
def legacy_health_check():
    return health_check()

class ProbeRequest(BaseModel):
    topic_id: str
    seeds: list[str]

@app.post("/api/probe_local")
def probe_local(req: ProbeRequest):
    topic_id_val = req.topic_id
    seeds = req.seeds

    target_topic_id = parse_topic_id(topic_id_val)
    if target_topic_id is None or not seeds:
        raise HTTPException(status_code=400, detail="topic_id and non-empty seeds list are required")

    if CENTROIDS is None or EMBEDDINGS is None or ASSIGNMENTS_DF is None or MODEL is None:
        raise HTTPException(status_code=500, detail="Server state not fully initialized or GCS files failed to load")

    try:
        # 1. Macro alignment (Centroid Sim)
        centroid_idx = np.where(CENTROID_TOPIC_IDS == target_topic_id)[0]
        if len(centroid_idx) == 0:
            raise HTTPException(status_code=404, detail=f"Topic ID {target_topic_id} centroid not found")
        centroid = CENTROIDS[centroid_idx[0]]

        # Embed seed claims with fastembed.
        # fastembed.embed returns a generator of numpy arrays, we convert to a numpy matrix
        seed_embs = np.array(list(MODEL.embed(seeds))) # shape (num_seeds, 384)
        if len(seeds) == 1:
            seed_embs = seed_embs.reshape(1, -1)

        norm_seeds = seed_embs / (np.linalg.norm(seed_embs, axis=1, keepdims=True) + 1e-9)
        norm_centroid = centroid / (np.linalg.norm(centroid) + 1e-9)
        macro_sims = (norm_seeds @ norm_centroid).tolist() # list of floats

        macro_results = [{"seed": seeds[i], "cosine_sim": round(float(macro_sims[i]), 4)} for i in range(len(seeds))]

        # 2. Micro alignment (Sample comments)
        topic_df = ASSIGNMENTS_DF[ASSIGNMENTS_DF["topic_reduced"] == target_topic_id].copy()
        if len(topic_df) == 0:
            return {
                "macro_alignment": macro_results,
                "micro_clusters": [],
                "message": "No sample comments found for this topic."
            }

        topic_indices = topic_df["embeddings_idx"].values
        topic_embs = EMBEDDINGS[topic_indices] # shape (N, 384)
        norm_topic_embs = topic_embs / (np.linalg.norm(topic_embs, axis=1, keepdims=True) + 1e-9)

        # Cosine similarity of comments against all seeds (N, num_seeds)
        sim_matrix = norm_topic_embs @ norm_seeds.T

        # Format comments
        comments_list = []
        for idx, (_, row) in enumerate(topic_df.iterrows()):
            comments_list.append({
                "comment_id": str(row["id"]),
                "text": row["text"].strip() if isinstance(row["text"], str) else "",
                "upvotes": int(row["upvotes"]) if not pd.isna(row["upvotes"]) else 0,
                "sims": sim_matrix[idx].tolist()
            })

        # If 1 seed, sort and return top comments
        if len(seeds) == 1:
            sorted_comments = sorted(comments_list, key=lambda c: (-c["sims"][0], -c["upvotes"]))
            top_comments = []
            for c in sorted_comments[:20]:
                top_comments.append({
                    "comment_id": c["comment_id"],
                    "text": c["text"],
                    "upvotes": c["upvotes"],
                    "similarity": round(float(c["sims"][0]), 4)
                })
            micro_clusters = [{
                "seed": seeds[0],
                "size": len(comments_list),
                "mean_sim": round(float(np.mean(sim_matrix[:, 0])), 4),
                "comments": top_comments
            }]
        else:
            # 2+ seeds: Assign each comment to its nearest seed
            nearest_seed_idx = np.argmax(sim_matrix, axis=1) # shape (N,)

            micro_clusters = []
            for s_idx, seed in enumerate(seeds):
                assigned_mask = (nearest_seed_idx == s_idx)
                assigned_count = int(np.sum(assigned_mask))

                assigned_comments = [comments_list[i] for i in range(len(comments_list)) if assigned_mask[i]]

                # Sort assigned comments by similarity to this seed
                sorted_assigned = sorted(assigned_comments, key=lambda c: (-c["sims"][s_idx], -c["upvotes"]))
                top_comments = []
                for c in sorted_assigned[:20]:
                    top_comments.append({
                        "comment_id": c["comment_id"],
                        "text": c["text"],
                        "upvotes": c["upvotes"],
                        "similarity": round(float(c["sims"][s_idx]), 4)
                    })

                mean_sim = 0.0
                if assigned_count > 0:
                    mean_sim = float(np.mean(sim_matrix[assigned_mask, s_idx]))

                micro_clusters.append({
                    "seed": seed,
                    "size": assigned_count,
                    "mean_sim": round(mean_sim, 4),
                    "comments": top_comments
                })

        return {
            "macro_alignment": macro_results,
            "micro_clusters": micro_clusters
        }

    except Exception as e:
        logger.error(f"Error executing probe matching: {e}")
        raise HTTPException(status_code=500, detail=str(e))
