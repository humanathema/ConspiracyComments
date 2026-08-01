"""compare_embedding_models_for_topics.py

Tests whether a stronger, paid embedding model (Vertex AI's
gemini-embedding-2, 3072-dim) produces meaningfully better BERTopic
clusters than the current all-MiniLM-L6-v2 (384-dim, chosen for
CPU/8GB-RAM constraints) -- per conversation 2026-08-02, Nash's
complaint that reddit topics are "loose/generic/redundant" (real,
quantified: 24/97 topics flagged low-cohesion, 8 near-duplicate pairs
found by audit_topic_quality.py, though note that flag is a
bottom-25th-percentile-of-this-run threshold, not an absolute badness
score -- ~25% of topics get flagged by construction regardless of
overall quality).

Runs BOTH embedding models on the IDENTICAL 20k-comment sample (not the
old model's full-100k baseline vs a new-model smaller sample -- isolates
the embedding model as the only variable, same clustering hyperparameters
as train_bertopic.py: UMAP(n_neighbors=15, n_components=5, min_dist=0.0,
cosine, seed=42), CountVectorizer(stop_words=english, min_df=5),
min_topic_size=100.

Cost: ~$0.15-0.30 for the Vertex embedding calls on 20k short comments
(gemini-embedding-2 @ $0.20/M tokens) -- confirmed cheap before running.

Output: data/processed/embedding_comparison_{minilm,gemini}.csv
  (per-topic cohesion + near-duplicate pairs for each), printed summary.
"""
import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from umap import UMAP
from bertopic import BERTopic

N_SAMPLE = 100000  # the full population used to fit reddit's current model
# (train_topic_assignments.parquet), not a subsample -- Nash's direction
# 2026-08-02 after confirming cost (~$1.50 at gemini-embedding-2's $0.20/M
# token rate) rather than assuming "whole corpus" meant the full
# multi-million-row unfiltered population.
SEED = 42
PROJECT = "tobiasnash-vertex-frontier"
LOCATION = "global"
GEMINI_CACHE_PATH = "data/processed/_gemini_embedding_comparison_cache.npy"

# Same dual-condition near-duplicate methodology as audit_topic_quality.py
# (CENTROID_SIM_THRESHOLD / KEYWORD_JACCARD_THRESHOLD) -- centroid cosine
# similarity alone isn't comparable across embedding spaces of different
# dimensionality (higher-dim spaces skew the whole similarity distribution
# upward, confirmed 2026-08-02: raw >0.5 threshold flagged 446 MiniLM pairs
# vs 5,565 Gemini pairs on the SAME docs, which is a scale artifact, not a
# real quality difference). Keyword Jaccard is scale-invariant, so requiring
# both to agree keeps the flag meaningful across spaces.
CENTROID_SIM_THRESHOLD = 0.65
KEYWORD_JACCARD_THRESHOLD = 0.10
COHESION_FLAG_PERCENTILE = 0.25
TOP_N_KEYWORDS = 10


def get_umap(n_neighbors=15):
    return UMAP(n_neighbors=n_neighbors, n_components=5, min_dist=0.0, metric="cosine", random_state=SEED)


def get_vectorizer(n_docs):
    # min_df=5 matches train_bertopic.py's real 100k run; smaller smoke-test
    # samples produce too few docs-per-topic for that floor to be satisfiable
    # (sklearn errors instead of silently clamping), so relax it below ~20k docs.
    min_df = 5 if n_docs >= 20000 else 1
    return CountVectorizer(stop_words="english", min_df=min_df)


def embed_minilm(docs):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    return model.encode(docs, batch_size=256, show_progress_bar=True)


def embed_gemini(docs, workers=30):
    from google import genai
    import threading
    tl = threading.local()

    def client():
        if not hasattr(tl, "c"):
            tl.c = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
        return tl.c

    def one(i_doc):
        i, doc = i_doc
        for attempt in range(3):
            try:
                resp = client().models.embed_content(model="gemini-embedding-2", contents=doc[:2000])
                return i, resp.embeddings[0].values
            except Exception as e:
                if "429" in str(e):
                    time.sleep(5 * (attempt + 1))
                    continue
                return i, None
        return i, None

    results = [None] * len(docs)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, (i, d)) for i, d in enumerate(docs)]
        done = 0
        for fut in as_completed(futures):
            i, vec = fut.result()
            results[i] = vec
            done += 1
            if done % 1000 == 0:
                print(f"  embedded {done}/{len(docs)} ({time.time()-t0:.0f}s elapsed)", flush=True)
    # a handful may have failed -- fill with zero vector, will just look like a bad
    # cluster fit for that doc rather than crashing the whole run
    dim = next(len(v) for v in results if v is not None)
    results = [v if v is not None else [0.0] * dim for v in results]
    return np.array(results)


def top_keywords_by_topic(docs, topics, top_n=TOP_N_KEYWORDS):
    """Top-N most frequent words per topic (stopwords removed) -- same
    keyword-overlap input audit_topic_quality.py uses for its dual-condition
    near-duplicate check. Computed directly from each topic's doc group
    rather than pulled from a fitted BERTopic model, so it works identically
    whether the topic assignment came from a fresh fit or (MiniLM's case)
    precomputed production labels."""
    topics = np.asarray(topics)
    keywords = {}
    for t in sorted(set(topics.tolist())):
        if t == -1:
            continue
        group_docs = [d for d, tt in zip(docs, topics) if tt == t]
        if len(group_docs) < 2:
            keywords[t] = set()
            continue
        try:
            vec = CountVectorizer(stop_words="english", max_features=top_n)
            X = vec.fit_transform(group_docs)
            counts = np.asarray(X.sum(axis=0)).flatten()
            order = np.argsort(-counts)[:top_n]
            keywords[t] = set(np.array(vec.get_feature_names_out())[order])
        except ValueError:
            keywords[t] = set()
    return keywords


def fit_and_score(docs, embeddings, label, precomputed_topics=None, umap_model=None):
    if precomputed_topics is not None:
        # MiniLM arm: reuse the actual production topic_reduced assignments
        # (train_bertopic.py's real fit on this exact 100k set, already cached
        # by audit_topic_quality.py) instead of re-embedding and re-fitting from
        # scratch -- Nash's question 2026-08-02, correct catch, this was pure
        # waste and also a fairer comparison (real production quality vs. a
        # freshly-refit-for-the-test MiniLM model that may not match production).
        print(f"\n=== Using precomputed production topics for {label} ({embeddings.shape}) ===", flush=True)
        topics = np.array(precomputed_topics)
        n_topics = len(set(topics[topics != -1]))
        n_outliers = (topics == -1).sum()
        print(f"{label}: {n_topics} topics, {n_outliers}/{len(docs)} outliers ({n_outliers/len(docs)*100:.1f}%)", flush=True)
    else:
        print(f"\n=== Fitting BERTopic on {label} embeddings ({embeddings.shape}) ===", flush=True)
        model = BERTopic(
            umap_model=umap_model or get_umap(),
            vectorizer_model=get_vectorizer(len(docs)),
            min_topic_size=100,
            calculate_probabilities=False,
            verbose=True,
        )
        topics, _ = model.fit_transform(docs, embeddings)
        topics = np.array(topics)

        info = model.get_topic_info()
        n_topics = len(info[info.Topic != -1])
        n_outliers = (topics == -1).sum()
        print(f"{label}: {n_topics} topics, {n_outliers}/{len(docs)} outliers ({n_outliers/len(docs)*100:.1f}%)", flush=True)

    # per-topic cohesion (mean cosine sim of each doc's embedding to its topic centroid)
    rows = []
    centroids = {}
    for t in sorted(set(topics.tolist())):
        if t == -1:
            continue
        mask = topics == t
        if mask.sum() < 2:
            continue
        topic_emb = embeddings[mask]
        centroid = topic_emb.mean(axis=0, keepdims=True)
        centroids[t] = centroid[0]
        cos_sim = cosine_similarity(topic_emb, centroid).flatten()
        rows.append({
            "topic": t, "n": int(mask.sum()),
            "mean_cohesion": float(cos_sim.mean()), "std_cohesion": float(cos_sim.std()),
        })
    cohesion_df = pd.DataFrame(rows)

    # near-duplicate topic pairs: dual condition (centroid cosine sim AND
    # keyword Jaccard both above threshold), same as audit_topic_quality.py --
    # a raw centroid-similarity-only threshold isn't comparable across
    # embedding spaces of different dimensionality (see module docstring).
    keywords_by_topic = top_keywords_by_topic(docs, topics)
    dup_rows = []
    topic_ids = list(centroids.keys())
    centroid_matrix = np.array([centroids[t] for t in topic_ids])
    sim_matrix = cosine_similarity(centroid_matrix)
    for i in range(len(topic_ids)):
        for j in range(i + 1, len(topic_ids)):
            sim = sim_matrix[i, j]
            if sim < CENTROID_SIM_THRESHOLD:
                continue
            kw_i, kw_j = keywords_by_topic.get(topic_ids[i], set()), keywords_by_topic.get(topic_ids[j], set())
            union = kw_i | kw_j
            jaccard = len(kw_i & kw_j) / len(union) if union else 0.0
            if jaccard < KEYWORD_JACCARD_THRESHOLD:
                continue
            dup_rows.append({
                "topic_a": topic_ids[i], "topic_b": topic_ids[j],
                "centroid_cosine_sim": float(sim), "keyword_jaccard": round(jaccard, 4),
            })
    dup_cols = ["topic_a", "topic_b", "centroid_cosine_sim", "keyword_jaccard"]
    dup_df = pd.DataFrame(dup_rows).sort_values("centroid_cosine_sim", ascending=False) if dup_rows else pd.DataFrame(columns=dup_cols)

    # percentile-relative cohesion (comparable across differently-scaled
    # embedding spaces, unlike a raw mean) -- same bottom-quartile convention
    # as audit_topic_quality.py's COHESION_FLAG_PERCENTILE.
    flag_threshold = float(np.quantile(cohesion_df.mean_cohesion, COHESION_FLAG_PERCENTILE))
    n_flagged = int((cohesion_df.mean_cohesion <= flag_threshold).sum())

    print(f"{label}: mean cohesion across topics = {cohesion_df.mean_cohesion.mean():.4f}, "
          f"median = {cohesion_df.mean_cohesion.median():.4f} (raw values, NOT comparable across embedding spaces)", flush=True)
    print(f"{label}: bottom-{int(COHESION_FLAG_PERCENTILE*100)}th-percentile cohesion threshold (within-run) "
          f"= {flag_threshold:.4f}, {n_flagged}/{len(cohesion_df)} topics flagged", flush=True)
    print(f"{label}: near-duplicate pairs (centroid sim >= {CENTROID_SIM_THRESHOLD} AND keyword jaccard >= {KEYWORD_JACCARD_THRESHOLD}) = {len(dup_df)}", flush=True)
    if len(dup_df):
        print(dup_df.head(10).to_string(), flush=True)

    return cohesion_df, dup_df, n_topics, n_outliers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=N_SAMPLE)
    args = parser.parse_args()

    # Fixed row order (train_topic_assignments.parquet's own order), not a
    # random resample -- this is the exact set audit_topic_quality.py's cached
    # embeddings and the real production topic_reduced assignments line up
    # against. Nash's correction 2026-08-02: don't re-embed/re-fit MiniLM at
    # all, just use production's real numbers as the baseline and spend the
    # Vertex budget on Gemini for the SAME docs.
    df = pd.read_parquet("data/processed/train_topic_assignments.parquet")
    use_full_set = args.sample >= len(df)
    if not use_full_set:
        df = df.sample(n=args.sample, random_state=SEED).reset_index(drop=True)
    docs = df["text"].fillna("").tolist()
    print(f"Comparing embedding models on {len(docs):,} identical comments", flush=True)

    print("\n--- MiniLM (current production, free, 384-dim) ---", flush=True)
    cache_path = "data/processed/_audit_topic_quality_embeddings_cache.npy"
    if use_full_set:
        minilm_emb = np.load(cache_path)
        assert len(minilm_emb) == len(docs), "cache row count doesn't match current sample -- delete cache or don't use --sample"
        minilm_cohesion, minilm_dup, minilm_ntopics, minilm_outliers = fit_and_score(
            docs, minilm_emb, "MiniLM", precomputed_topics=df["topic_reduced"].to_numpy()
        )
    else:
        minilm_emb = embed_minilm(docs)
        minilm_cohesion, minilm_dup, minilm_ntopics, minilm_outliers = fit_and_score(docs, minilm_emb, "MiniLM")
    minilm_cohesion.to_csv("data/processed/embedding_comparison_minilm_cohesion.csv", index=False)
    minilm_dup.to_csv("data/processed/embedding_comparison_minilm_duplicates.csv", index=False)

    print("\n--- Gemini (Vertex AI, paid, 3072-dim) ---", flush=True)
    if use_full_set and os.path.exists(GEMINI_CACHE_PATH):
        print(f"  Loading cached Gemini embeddings from {GEMINI_CACHE_PATH}...", flush=True)
        gemini_emb = np.load(GEMINI_CACHE_PATH)
        assert len(gemini_emb) == len(docs), "gemini cache row count doesn't match current doc count -- delete cache to regenerate"
    else:
        gemini_emb = embed_gemini(docs)
        if use_full_set:
            np.save(GEMINI_CACHE_PATH, gemini_emb)
            print(f"  Cached embeddings to {GEMINI_CACHE_PATH} (so any re-tuning of clustering doesn't re-pay for embedding calls)", flush=True)

    # UMAP's n_neighbors=15 was tuned for MiniLM's 384-dim space; the first
    # run reused it unchanged for Gemini's 3072-dim space and got a 55.2%
    # outlier rate -- not evidence Gemini is worse, just evidence the
    # hyperparameters weren't retuned for it. Sweep a couple of candidates
    # here (cheap: reuses the cached embeddings, no re-embedding) and report
    # results for all, using whichever gets closest to MiniLM's ~0% outlier
    # rate as the headline comparison.
    print("\n  Sweeping UMAP n_neighbors for the Gemini embedding space...", flush=True)
    sweep_results = {}
    for n_neighbors in (15, 30, 50):
        cohesion, dup, ntopics, outliers = fit_and_score(
            docs, gemini_emb, f"Gemini(n_neighbors={n_neighbors})", umap_model=get_umap(n_neighbors=n_neighbors)
        )
        sweep_results[n_neighbors] = (cohesion, dup, ntopics, outliers)
        print(f"  n_neighbors={n_neighbors}: {ntopics} topics, {outliers/len(docs)*100:.1f}% outliers", flush=True)

    best_n_neighbors = min(sweep_results, key=lambda k: sweep_results[k][3])
    gemini_cohesion, gemini_dup, gemini_ntopics, gemini_outliers = sweep_results[best_n_neighbors]
    print(f"\n  Best config: n_neighbors={best_n_neighbors} (lowest outlier rate) -- using this as the headline Gemini result", flush=True)
    gemini_cohesion.to_csv("data/processed/embedding_comparison_gemini_cohesion.csv", index=False)
    gemini_dup.to_csv("data/processed/embedding_comparison_gemini_duplicates.csv", index=False)

    minilm_flag_threshold = float(np.quantile(minilm_cohesion.mean_cohesion, COHESION_FLAG_PERCENTILE))
    gemini_flag_threshold = float(np.quantile(gemini_cohesion.mean_cohesion, COHESION_FLAG_PERCENTILE))
    minilm_flagged = int((minilm_cohesion.mean_cohesion <= minilm_flag_threshold).sum())
    gemini_flagged = int((gemini_cohesion.mean_cohesion <= gemini_flag_threshold).sum())

    print("\n\n========== SUMMARY ==========", flush=True)
    print(f"{'Metric':<45}{'MiniLM (free)':<20}{'Gemini (paid, best config)':<20}", flush=True)
    print(f"{'Topics found':<45}{minilm_ntopics:<20}{gemini_ntopics:<20}", flush=True)
    print(f"{'Outlier rate':<45}{f'{minilm_outliers/len(docs)*100:.1f}%':<20}{f'{gemini_outliers/len(docs)*100:.1f}%':<20}", flush=True)
    print(f"{'Bottom-25th-pct topics flagged (of total)':<45}{f'{minilm_flagged}/{len(minilm_cohesion)}':<20}{f'{gemini_flagged}/{len(gemini_cohesion)}':<20}", flush=True)
    print(f"{'Near-dup pairs (dual condition)':<45}{len(minilm_dup):<20}{len(gemini_dup):<20}", flush=True)
    print(f"\n(Raw cohesion means are NOT included above -- confirmed not comparable across", flush=True)
    print(f" embedding spaces of different dimensionality; see per-run printouts above for context.)", flush=True)


if __name__ == "__main__":
    main()
