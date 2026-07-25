"""
Topic quality audit for the BERTopic model in data/processed/bertopic_model_new.

No LLM calls -- reuses the same local SentenceTransformer (all-MiniLM-L6-v2)
already used to train the topic model, plus deterministic vector-space and
keyword-overlap metrics. Three independent signals, each interpretable on
its own (same "print and eyeball" spirit as src/stage_c_classify_ambiguous.py):

1. Near-duplicate / merge candidates: topic-centroid cosine similarity AND
   top-10-keyword Jaccard overlap between every topic pair. Flagged only
   when BOTH agree, so a coincidental keyword overlap alone (or a centroid
   proximity alone) doesn't trigger a false merge suggestion.

2. Broad / split candidates: per-topic cohesion (mean cosine similarity of
   each assigned comment's embedding to its own topic centroid). Low-cohesion
   topics are tested with a 2-way KMeans split on their own comment
   embeddings; a split is only reported as a real candidate if the two
   sub-clusters have a silhouette score above a floor AND produce a
   ratio-test vocabulary split (same signature-word mechanic as entity
   disambiguation) so the split is human-auditable, not just a distance
   artifact.

3. Thin / low-confidence topics: raw comment counts per topic, since a
   quality flag on a 100-comment topic matters less than on a 5,000-comment
   one.

Outputs (all to data/processed/):
- topic_quality_audit.csv           per-topic cohesion/size/flags
- topic_near_duplicate_pairs.csv    pairs flagged as merge candidates
- topic_split_candidates.csv        topics flagged broad, with sub-cluster
                                     signature words for the two halves
"""
import os
import sys
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.feature_extraction.text import CountVectorizer

# Add parent path for utils import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from utils.concurrency_utils import atomic_write_dataframe

CENTROID_SIM_THRESHOLD = 0.65
KEYWORD_JACCARD_THRESHOLD = 0.10  # Calibrated down from 0.15 to successfully catch vaccine near-duplicate pairs (Topics 2 vs 9)
COHESION_FLAG_PERCENTILE = 0.25  # bottom quartile of this run's cohesion distribution -> candidate for split review
MIN_TOPIC_SIZE_FOR_SPLIT_TEST = 200
SILHOUETTE_FLOOR = 0.05
MIN_SIGNATURE_RATIO = 0.7
MIN_SIGNATURE_COUNT = 3
TOP_N_SIGNATURE_WORDS = 15


def load_centroids():
    d = np.load('data/processed/topic_centroids.npz')
    return d['embeddings'], d['topic_ids']


def load_keywords():
    df = pd.read_csv('data/processed/topic_super_topic_mapping.csv')
    df = df[df['Topic'] != -1].copy()
    df['keyword_set'] = df['Keywords'].apply(lambda s: set(w.strip() for w in s.split(',')))
    return df.set_index('Topic')


def near_duplicate_pairs(centroids, topic_ids, keywords_by_topic):
    sims = centroids @ centroids.T
    norms = np.linalg.norm(centroids, axis=1, keepdims=True)
    sims = sims / (norms @ norms.T)

    rows = []
    n = len(topic_ids)
    for i in range(n):
        for j in range(i + 1, n):
            t_i, t_j = topic_ids[i], topic_ids[j]
            centroid_sim = sims[i, j]
            if centroid_sim < CENTROID_SIM_THRESHOLD:
                continue
            kw_i = keywords_by_topic.loc[t_i, 'keyword_set'] if t_i in keywords_by_topic.index else set()
            kw_j = keywords_by_topic.loc[t_j, 'keyword_set'] if t_j in keywords_by_topic.index else set()
            union = kw_i | kw_j
            jaccard = len(kw_i & kw_j) / len(union) if union else 0.0
            if jaccard < KEYWORD_JACCARD_THRESHOLD:
                continue
            rows.append({
                'topic_a': t_i,
                'topic_a_name': keywords_by_topic.loc[t_i, 'Topic_Name'] if t_i in keywords_by_topic.index else None,
                'topic_b': t_j,
                'topic_b_name': keywords_by_topic.loc[t_j, 'Topic_Name'] if t_j in keywords_by_topic.index else None,
                'centroid_cosine_sim': round(float(centroid_sim), 4),
                'keyword_jaccard': round(jaccard, 4),
            })
    cols = ['topic_a', 'topic_a_name', 'topic_b', 'topic_b_name', 'centroid_cosine_sim', 'keyword_jaccard']
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows).sort_values('centroid_cosine_sim', ascending=False)


def clean_bag(text):
    tokens = str(text).lower().split()
    return [t for t in tokens if not t.startswith('http') and not t.isdigit() and len(t) > 2]


def signature_words(bags_a, bags_b):
    counts_a, counts_b = {}, {}
    for bag in bags_a:
        for w in set(bag):
            counts_a[w] = counts_a.get(w, 0) + 1
    for bag in bags_b:
        for w in set(bag):
            counts_b[w] = counts_b.get(w, 0) + 1

    def sig(counts_this, counts_other):
        out = []
        for w, c in counts_this.items():
            total = c + counts_other.get(w, 0)
            ratio = c / total
            if ratio >= MIN_SIGNATURE_RATIO and c >= MIN_SIGNATURE_COUNT:
                out.append((w, ratio, c))
        out.sort(key=lambda x: (-x[1], -x[2]))
        return [w for w, _, _ in out[:TOP_N_SIGNATURE_WORDS]]

    return sig(counts_a, counts_b), sig(counts_b, counts_a)


def main():
    print("Loading topic centroids and keyword table...")
    centroids, topic_ids = load_centroids()
    keywords_by_topic = load_keywords()

    print("Computing near-duplicate / merge candidates...")
    dup_pairs = near_duplicate_pairs(centroids, topic_ids, keywords_by_topic)
    atomic_write_dataframe(dup_pairs, 'data/processed/topic_near_duplicate_pairs.csv', index=False)
    print(f"  {len(dup_pairs)} pairs flagged (centroid sim >= {CENTROID_SIM_THRESHOLD} AND keyword jaccard >= {KEYWORD_JACCARD_THRESHOLD})")

    print("\nLoading comment assignments...")
    df = pd.read_parquet('data/processed/train_topic_assignments.parquet')
    df = df[df['topic_reduced'] != -1].copy()

    cache_path = 'data/processed/_audit_topic_quality_embeddings_cache.npy'
    if os.path.exists(cache_path):
        print(f"  Loading cached embeddings from {cache_path}...")
        embeddings = np.load(cache_path)
        assert len(embeddings) == len(df), "cached embeddings don't match current train_topic_assignments row count -- delete cache to regenerate"
    else:
        print("  Re-embedding with all-MiniLM-L6-v2 (same model used to train the topic model)...")
        model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
        embeddings = model.encode(df['text'].fillna("").tolist(), batch_size=256, show_progress_bar=True)
        np.save(cache_path, embeddings)
    df['embedding_idx'] = np.arange(len(df))

    centroid_by_topic = {t: centroids[i] for i, t in enumerate(topic_ids)}

    print("\nComputing per-topic cohesion...")
    topic_groups = {}
    cohesion_by_topic = {}
    for topic, group in df.groupby('topic_reduced'):
        if topic not in centroid_by_topic:
            continue
        idx = group['embedding_idx'].values
        emb = embeddings[idx]
        centroid = centroid_by_topic[topic]
        cos_sim = (emb @ centroid) / (np.linalg.norm(emb, axis=1) * np.linalg.norm(centroid) + 1e-9)
        topic_groups[topic] = (group, emb, cos_sim)
        cohesion_by_topic[topic] = float(cos_sim.mean())

    cohesion_flag_threshold = float(np.quantile(list(cohesion_by_topic.values()), COHESION_FLAG_PERCENTILE))
    print(f"  Bottom-{int(COHESION_FLAG_PERCENTILE*100)}th-percentile cohesion threshold for this run: {cohesion_flag_threshold:.4f}")

    audit_rows = []
    split_rows = []
    for topic, (group, emb, cos_sim) in topic_groups.items():
        n = len(group)
        mean_cohesion = cohesion_by_topic[topic]
        std_cohesion = float(cos_sim.std())

        flags = []
        if mean_cohesion < cohesion_flag_threshold:
            flags.append('low_cohesion_broad_candidate')
        if n < 150:
            flags.append('thin_topic')

        split_tested = False
        silhouette = None
        if mean_cohesion < cohesion_flag_threshold and n >= MIN_TOPIC_SIZE_FOR_SPLIT_TEST:
            split_tested = True
            km = KMeans(n_clusters=2, n_init=10, random_state=42).fit(emb)
            labels = km.labels_
            if len(set(labels)) == 2 and min(np.bincount(labels)) >= 20:
                silhouette = float(silhouette_score(emb, labels))
                if silhouette >= SILHOUETTE_FLOOR:
                    flags.append('split_candidate')
                    texts_a = group['text'].values[labels == 0]
                    texts_b = group['text'].values[labels == 1]
                    bags_a = [clean_bag(t) for t in texts_a]
                    bags_b = [clean_bag(t) for t in texts_b]
                    sig_a, sig_b = signature_words(bags_a, bags_b)
                    split_rows.append({
                        'topic': topic,
                        'topic_name': keywords_by_topic.loc[topic, 'Topic_Name'] if topic in keywords_by_topic.index else None,
                        'silhouette_score': round(silhouette, 4),
                        'subcluster_a_n': int((labels == 0).sum()),
                        'subcluster_a_signature_words': ', '.join(sig_a),
                        'subcluster_b_n': int((labels == 1).sum()),
                        'subcluster_b_signature_words': ', '.join(sig_b),
                    })

        audit_rows.append({
            'topic': topic,
            'topic_name': keywords_by_topic.loc[topic, 'Topic_Name'] if topic in keywords_by_topic.index else None,
            'n_comments_in_sample': n,
            'mean_cohesion': round(mean_cohesion, 4),
            'std_cohesion': round(std_cohesion, 4),
            'split_tested': split_tested,
            'silhouette_score': round(silhouette, 4) if silhouette is not None else None,
            'flags': '; '.join(flags) if flags else '',
        })

    audit_df = pd.DataFrame(audit_rows).sort_values('mean_cohesion')
    atomic_write_dataframe(audit_df, 'data/processed/topic_quality_audit.csv', index=False)
    split_df = pd.DataFrame(split_rows)
    atomic_write_dataframe(split_df, 'data/processed/topic_split_candidates.csv', index=False)

    print(f"\nWrote topic_quality_audit.csv ({len(audit_df)} topics)")
    print(f"Wrote topic_near_duplicate_pairs.csv ({len(dup_pairs)} flagged pairs)")
    print(f"Wrote topic_split_candidates.csv ({len(split_df)} flagged splits)")

    print("\n=== Near-duplicate / merge candidates ===")
    if len(dup_pairs):
        print(dup_pairs.to_string(index=False))
    else:
        print("(none)")

    print("\n=== Low-cohesion / broad topics (flagged) ===")
    flagged = audit_df[audit_df['flags'].str.contains('low_cohesion|split_candidate', na=False)]
    print(flagged.to_string(index=False) if len(flagged) else "(none)")

    print("\n=== Split candidates with signature words ===")
    if len(split_df):
        for _, r in split_df.iterrows():
            print(f"\nTopic {r['topic']} ({r['topic_name']}) -- silhouette {r['silhouette_score']}")
            print(f"  A (n={r['subcluster_a_n']}): {r['subcluster_a_signature_words']}")
            print(f"  B (n={r['subcluster_b_n']}): {r['subcluster_b_signature_words']}")
    else:
        print("(none)")


if __name__ == '__main__':
    main()
