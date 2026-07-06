import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
import joblib
import duckdb
import time

dimensions = ['source_citation', 'hedged_suspicion', 'procedural_skepticism', 'personal_experience', 'appeal_to_authority']

def train_models():
    print("Training ML models on labeled_2k_with_scores.csv...")
    df_train = pd.read_csv('data/processed/labeled_2k_with_scores.csv')
    
    # We will train a vectorizer and a model for each dimension
    models = {}
    
    for dim in dimensions:
        # Drop rows where target is missing
        df_dim = df_train.dropna(subset=['text', dim])
        X = df_dim['text']
        y = df_dim[dim].astype(int)
        
        vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 3), stop_words='english')
        X_vec = vec.fit_transform(X)
        
        clf = LogisticRegression(class_weight='balanced', max_iter=1000, random_state=42)
        clf.fit(X_vec, y)
        
        models[dim] = {'vec': vec, 'clf': clf}
        print(f"  Trained {dim}: n={len(X)}")
        
    joblib.dump(models, 'data/processed/comparison_ml_models.pkl')
    return models

def score_corpus(corpus_name, models):
    print(f"\nScoring {corpus_name} with ML models...")
    start = time.time()
    
    # Load raw text from the old scored parquet just for convenience
    df = pd.read_parquet(f'data/processed/comparison_{corpus_name}_scored.parquet')
    texts = df['text'].fillna('')
    
    for dim in dimensions:
        vec = models[dim]['vec']
        clf = models[dim]['clf']
        
        X_vec = vec.transform(texts)
        probs = clf.predict_proba(X_vec)[:, 1]
        
        df[f'{dim}_prob'] = probs
        # We can also add a binary threshold at 0.5
        df[f'{dim}_ml_flag'] = (probs > 0.5).astype(int)
        
    out_file = f'data/processed/comparison_{corpus_name}_ml_scored.parquet'
    df.to_parquet(out_file, index=False)
    
    print(f"  Done in {(time.time() - start):.1f}s. Saved to {out_file}")

if __name__ == "__main__":
    models = train_models()
    score_corpus('conspiracy_commons', models)
    # score_corpus('askreddit', models) # uncomment later
    # score_corpus('topmindsofreddit', models) # uncomment later
    
