"""pca_interpretability_check.py

Checks whether top PCA components of MiniLM and Gemini embeddings
correspond to human-nameable structure -- for each of the top N
components, pulls the documents with the highest and lowest projection
("poles") and extracts characteristic vocabulary for each, same
technique used to eyeball PC1-5 on MiniLM in conversation 2026-08-02
(several came back clearly interpretable: PC2 = vaccines/covid vs.
Trump/political-video content, PC5 = mainstream political conspiracy
vs. esoteric/paranormal conspiracy). This extends that check to Gemini
and writes both to disk instead of only printing.

Both embedding caches are row-aligned with
data/processed/train_topic_assignments.parquet (same 100k sample, same
row order) -- confirmed earlier this session when the caches were built.

Output: data/processed/pca_interpretability_minilm.csv
        data/processed/pca_interpretability_gemini.csv
  columns: pc, variance_pct, pole, top_words, example_text
"""
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import CountVectorizer

N_PCS = 10
N_POLE_DOCS = 300
N_WORDS = 12

MINILM_CACHE = "data/processed/_audit_topic_quality_embeddings_cache.npy"
GEMINI_CACHE = "data/processed/_gemini_embedding_comparison_cache.npy"


def top_words(texts, doc_indices, n=N_WORDS):
    docs = [texts[i] for i in doc_indices]
    try:
        vec = CountVectorizer(stop_words="english", max_features=n)
        X = vec.fit_transform(docs)
        counts = np.asarray(X.sum(axis=0)).flatten()
        order = np.argsort(-counts)
        return [vec.get_feature_names_out()[i] for i in order]
    except ValueError:
        return []


def run(cache_path, texts, label, out_path, n_pcs=N_PCS):
    emb = np.load(cache_path)
    pca = PCA(n_components=n_pcs, random_state=42)
    scores = pca.fit_transform(emb)

    rows = []
    for pc in range(n_pcs):
        proj = scores[:, pc]
        high_idx = np.argsort(-proj)[:N_POLE_DOCS]
        low_idx = np.argsort(proj)[:N_POLE_DOCS]
        var_pct = pca.explained_variance_ratio_[pc] * 100
        rows.append({
            "pc": pc + 1, "variance_pct": round(var_pct, 3), "pole": "high",
            "top_words": ", ".join(top_words(texts, high_idx)),
            "example_text": texts[high_idx[0]][:200],
        })
        rows.append({
            "pc": pc + 1, "variance_pct": round(var_pct, 3), "pole": "low",
            "top_words": ", ".join(top_words(texts, low_idx)),
            "example_text": texts[low_idx[0]][:200],
        })

    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)
    print(f"{label}: saved {len(df)} rows ({n_pcs} PCs x 2 poles) to {out_path}", flush=True)
    return df


def main():
    df = pd.read_parquet("data/processed/train_topic_assignments.parquet")
    texts = df["text"].fillna("").tolist()

    minilm_df = run(MINILM_CACHE, texts, "MiniLM", "data/processed/pca_interpretability_minilm.csv")
    gemini_df = run(GEMINI_CACHE, texts, "Gemini", "data/processed/pca_interpretability_gemini.csv")

    print("\n=== Gemini top 5 PCs (for immediate comparison against MiniLM's, printed earlier) ===", flush=True)
    for pc in range(1, 6):
        sub = gemini_df[gemini_df["pc"] == pc]
        high = sub[sub["pole"] == "high"].iloc[0]
        low = sub[sub["pole"] == "low"].iloc[0]
        print(f"PC{pc} ({high['variance_pct']}% variance)", flush=True)
        print(f"  HIGH: {high['top_words']}", flush=True)
        print(f"  LOW:  {low['top_words']}", flush=True)
        print(f"  HIGH example: {high['example_text'][:120]}", flush=True)
        print(f"  LOW  example: {low['example_text'][:120]}", flush=True)
        print(flush=True)


if __name__ == "__main__":
    main()
