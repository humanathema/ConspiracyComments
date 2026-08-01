# src/serve_seed_claim_probe.py
"""serve_seed_claim_probe.py

Lightweight local server running on port 8421 on Nash's machine.
Performs semantic claim probing by embedding seed claims with all-MiniLM-L6-v2, 
comparing them against topic centroids (macro alignment) and actual comment embeddings 
(micro alignment) with nearest-seed routing for 2+ seed claims.
"""
import os
import json
import argparse
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# Global state
MODEL = None
ASSIGNMENTS_DF = None
EMBEDDINGS = None
CENTROIDS = None
CENTROID_TOPIC_IDS = None

def parse_topic_id(val):
    if isinstance(val, int):
        return val
    try:
        return int(str(val).split('_')[0])
    except ValueError:
        return None

def initialize_local_data():
    global MODEL, ASSIGNMENTS_DF, EMBEDDINGS, CENTROIDS, CENTROID_TOPIC_IDS
    print("Loading SentenceTransformer model 'all-MiniLM-L6-v2' (CPU)...")
    MODEL = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    
    print("Loading topic centroids...")
    centroids_path = 'data/processed/topic_centroids.npz'
    if os.path.exists(centroids_path):
        c_data = np.load(centroids_path)
        CENTROIDS = c_data['embeddings']
        CENTROID_TOPIC_IDS = c_data['topic_ids']
    else:
        print("⚠️ Warning: topic centroids npz file not found!")
        
    print("Loading comment assignments...")
    df_path = 'data/processed/train_topic_assignments.parquet'
    emb_path = 'data/processed/_audit_topic_quality_embeddings_cache.npy'
    if os.path.exists(df_path) and os.path.exists(emb_path):
        df = pd.read_parquet(df_path)
        df_clean = df[df['topic_reduced'] != -1].copy()
        df_clean['embeddings_idx'] = np.arange(len(df_clean))
        ASSIGNMENTS_DF = df_clean
        
        print("Loading embeddings cache...")
        EMBEDDINGS = np.load(emb_path)
        assert len(EMBEDDINGS) == len(ASSIGNMENTS_DF), "Embeddings shape mismatch!"
        print(f"Loaded {len(EMBEDDINGS):,} comment embeddings!")
    else:
        print("⚠️ Warning: Parquet assignments or embeddings cache not found!")

class ProbeHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"Local Server: {self.address_string()} - {fmt % args}")

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_json({"status": "ok", "local_embeddings": (EMBEDDINGS is not None)})
        else:
            self.send_json({"error": "not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/probe_local":
            self.send_json({"error": "not found"}, status=404)
            return
            
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception as e:
            self.send_json({"error": "invalid JSON body", "detail": str(e)}, status=400)
            return

        topic_id_val = body.get("topic_id")
        seeds = body.get("seeds", [])
        
        target_topic_id = parse_topic_id(topic_id_val)
        if target_topic_id is None or not seeds:
            self.send_json({"error": "topic_id and non-empty seeds list are required"}, status=400)
            return
            
        if CENTROIDS is None or EMBEDDINGS is None or ASSIGNMENTS_DF is None or MODEL is None:
            self.send_json({"error": "server state not fully initialized"}, status=500)
            return

        # 1. Macro alignment (Centroid Sim)
        try:
            centroid_idx = np.where(CENTROID_TOPIC_IDS == target_topic_id)[0]
            if len(centroid_idx) == 0:
                self.send_json({"error": f"Topic ID {target_topic_id} centroid not found"}, status=404)
                return
            centroid = CENTROIDS[centroid_idx[0]]
            
            # Embed seed claims
            seed_embs = MODEL.encode(seeds) # shape (num_seeds, 384)
            if len(seeds) == 1:
                seed_embs = seed_embs.reshape(1, -1)
                
            norm_seeds = seed_embs / (np.linalg.norm(seed_embs, axis=1, keepdims=True) + 1e-9)
            norm_centroid = centroid / (np.linalg.norm(centroid) + 1e-9)
            macro_sims = (norm_seeds @ norm_centroid).tolist() # list of floats
            
            macro_results = [{"seed": seeds[i], "cosine_sim": round(float(macro_sims[i]), 4)} for i in range(len(seeds))]
            
            # 2. Micro alignment (Sample comments)
            topic_df = ASSIGNMENTS_DF[ASSIGNMENTS_DF['topic_reduced'] == target_topic_id].copy()
            if len(topic_df) == 0:
                self.send_json({
                    "macro_alignment": macro_results,
                    "micro_clusters": [],
                    "message": "No sample comments found for this topic."
                })
                return
                
            topic_indices = topic_df['embeddings_idx'].values
            topic_embs = EMBEDDINGS[topic_indices] # shape (N, 384)
            norm_topic_embs = topic_embs / (np.linalg.norm(topic_embs, axis=1, keepdims=True) + 1e-9)
            
            # Cosine sim of comments against all seeds (N, num_seeds)
            sim_matrix = norm_topic_embs @ norm_seeds.T
            
            # Format comments
            comments_list = []
            for idx, (_, row) in enumerate(topic_df.iterrows()):
                comments_list.append({
                    "comment_id": str(row['id']),
                    "text": row['text'].strip(),
                    "upvotes": int(row['upvotes']),
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
                    
            self.send_json({
                "macro_alignment": macro_results,
                "micro_clusters": micro_clusters
            })
            
        except Exception as e:
            self.send_json({"error": "internal execution error", "detail": str(e)}, status=500)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8421)
    args = parser.parse_args()
    
    initialize_local_data()
    
    server = ThreadingHTTPServer((args.host, args.port), ProbeHandler)
    print(f"🚀 Local Seed Claim Probe Server running on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local server...")

if __name__ == '__main__':
    main()
