import pandas as pd
import numpy as np
import re
import joblib
import os
import asyncio
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

# Import classification utilities from src
from src.classification import init_vertex_ai, get_model, classify_comment_async, TARGET_CATEGORIES

# --- STAGE 1 REGEX PATTERNS ---
PRONOUNS = re.compile(r"\b(i|me|my|myself|we|our|us)\b", re.IGNORECASE)
LIFE_ANCHORS = re.compile(
    r"\b(family|career|brother|sister|wife|husband|job|life|school|hospital|mom|dad|mother|father|parents|kid|kids|child|children|grew up|remember|remembered|happened)\b",
    re.IGNORECASE
)

SKEPT_TERMS = re.compile(
    r"\b(evidence|proof|argument|premise|contradict|logical|validity|source|cite|citation|logic|facts|peer|study|studies|data|science|scientific|statistics)\b",
    re.IGNORECASE
)
NEGATIONS = re.compile(
    r"\b(doesn't add up|makes no sense|where is the|flaw|disprove|debunk|falsify|invalid|manipulate|bias|biased|cherry pick|cherry-picked|propaganda)\b",
    re.IGNORECASE
)

def pass_personal_experience_filter(text):
    text_str = str(text)
    return bool(PRONOUNS.search(text_str)) and bool(LIFE_ANCHORS.search(text_str))

def pass_procedural_skepticism_filter(text):
    text_str = str(text)
    return bool(SKEPT_TERMS.search(text_str)) or bool(NEGATIONS.search(text_str))

# --- TRAINING STAGE 2 BASES ---
def train_stage2_models():
    print("🚀 Training local Stage 2 ML models on your HITL ground truth...")
    
    # 1. Personal Experience Model
    df_pe = pd.read_csv("data/hitl/queue_personal_experience.csv")
    df_pe['human_bin'] = df_pe['human_label'].map({'positive': 1, 'lean_positive': 1, 'negative': 0})
    df_pe = df_pe.dropna(subset=['human_bin'])
    
    pe_vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 1), sublinear_tf=True, stop_words='english')
    X_pe = pe_vec.fit_transform(df_pe['full_text'].fillna(''))
    y_pe = df_pe['human_bin'].astype(int)
    
    pe_clf = LogisticRegression(class_weight='balanced', C=1.0, random_state=42)
    pe_clf.fit(X_pe, y_pe)
    print(f"  Trained Personal Experience model (n={len(df_pe)} active rows)")
    
    # 2. Procedural Skepticism Model
    df_ps = pd.read_csv("data/hitl/queue_procedural_skepticism.csv")
    df_ps['human_bin'] = df_ps['human_label'].map({'positive': 1, 'lean_positive': 1, 'negative': 0})
    df_ps = df_ps.dropna(subset=['human_bin'])
    
    ps_vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 1), sublinear_tf=True, stop_words='english')
    X_ps = ps_vec.fit_transform(df_ps['full_text'].fillna(''))
    y_ps = df_ps['human_bin'].astype(int)
    
    ps_clf = LogisticRegression(class_weight='balanced', C=1.0, random_state=42)
    ps_clf.fit(X_ps, y_ps)
    print(f"  Trained Procedural Skepticism model (n={len(df_ps)} active rows)")
    
    # Save the models
    models = {
        'personal_experience': {'vec': pe_vec, 'clf': pe_clf},
        'procedural_skepticism': {'vec': ps_vec, 'clf': ps_clf}
    }
    os.makedirs('data/processed', exist_ok=True)
    joblib.dump(models, 'data/processed/staged_pipeline_models.joblib')
    print("💾 Saved local models to data/processed/staged_pipeline_models.joblib")
    return models

# --- APPLY PIPELINE (STAGE 1 & STAGE 2) ---
def apply_staged_pipeline(df, text_column, models):
    print("\n⚡ Running Staged Hybrid Pipeline (Stage 1 & Stage 2)...")
    
    df_out = df.copy()
    
    for dim in ['personal_experience', 'procedural_skepticism']:
        vec = models[dim]['vec']
        clf = models[dim]['clf']
        filter_fn = pass_personal_experience_filter if dim == 'personal_experience' else pass_procedural_skepticism_filter
        
        # 1. Apply Stage 1: Regex filter
        df_out[f'{dim}_pass_s1'] = df_out[text_column].apply(filter_fn)
        
        # Initialize outputs
        df_out[f'{dim}_prob'] = 0.0
        df_out[f'{dim}_decision'] = 'Auto-Negative'
        df_out[f'{dim}_label'] = 0
        
        # Identify rows passing Stage 1
        passed_idx = df_out[df_out[f'{dim}_pass_s1'] == True].index
        
        if len(passed_idx) > 0:
            # 2. Apply Stage 2: Local ML scoring on passed rows
            texts = df_out.loc[passed_idx, text_column].fillna('')
            X_vec = vec.transform(texts)
            probs = clf.predict_proba(X_vec)[:, 1]
            df_out.loc[passed_idx, f'{dim}_prob'] = probs
            
            # Decisions and Labels mapping
            # p < 0.30 -> Auto-Negative (0)
            # p >= 0.70 -> Auto-Positive (1)
            # 0.30 <= p < 0.70 -> Borderline (requires Stage 3)
            decisions = []
            labels = []
            for p in probs:
                if p < 0.30:
                    decisions.append('Auto-Negative')
                    labels.append(0)
                elif p >= 0.70:
                    decisions.append('Auto-Positive')
                    labels.append(1)
                else:
                    decisions.append('Borderline')
                    labels.append(-1) # Placeholder representing requires Stage 3
            
            df_out.loc[passed_idx, f'{dim}_decision'] = decisions
            df_out.loc[passed_idx, f'{dim}_label'] = labels
            
        print(f"  Dimension '{dim}':")
        counts = df_out[f'{dim}_decision'].value_counts()
        for k, v in counts.items():
            print(f"    - {k}: {v:,} rows")
            
    return df_out

# --- STAGE 3 RUNNER ---
async def run_stage3_async(df_scored, text_column, concurrent_requests=5):
    print("\n🛸 Executing Stage 3 (High-Fidelity API Classifiers) on Borderline cases...")
    
    # Check for GCP Environment Variables
    project_id = os.environ.get("GCP_PROJECT_ID")
    endpoint = os.environ.get("VERTEX_ENDPOINT_ID")
    
    if not project_id or not endpoint:
        print("⚠️ GCP_PROJECT_ID or VERTEX_ENDPOINT_ID is missing. Skipping LLM Stage 3 call.")
        print("💡 Tip: To run Stage 3, make sure to set these environment variables.")
        return df_scored
        
    try:
        init_vertex_ai(project_id)
        model = get_model(endpoint)
        semaphore = asyncio.Semaphore(concurrent_requests)
    except Exception as e:
        print(f"❌ Failed to initialize Vertex AI client: {e}. Skipping Stage 3.")
        return df_scored

    df_out = df_scored.copy()
    
    for dim in ['personal_experience', 'procedural_skepticism']:
        borderline_idx = df_out[df_out[f'{dim}_decision'] == 'Borderline'].index
        print(f"  Processing {len(borderline_idx):,} borderline rows for '{dim}'...")
        
        if len(borderline_idx) == 0:
            continue
            
        tasks = []
        for idx in borderline_idx:
            text = df_out.loc[idx, text_column]
            # Use classify_comment_async from src/classification.py
            tasks.append((idx, classify_comment_async(text, model, semaphore)))
            
        # Run tasks concurrently
        results = await asyncio.gather(*(t[1] for t in tasks))
        
        # Parse results and update labels
        for (idx, _), res in zip(tasks, results):
            if res is not None:
                # If the specific dimension is flagged positive (1) by Gemini
                label_val = res.get(dim, 0)
                df_out.loc[idx, f'{dim}_label'] = label_val
                df_out.loc[idx, f'{dim}_decision'] = 'LLM-Verified' if label_val == 1 else 'LLM-Negative'
            else:
                df_out.loc[idx, f'{dim}_label'] = 0 # Default to negative on exception
                df_out.loc[idx, f'{dim}_decision'] = 'Exception-Negative'
                
        print(f"  Completed '{dim}' Stage 3. New distributions:")
        print(df_out[f'{dim}_decision'].value_counts())
        
    return df_out

if __name__ == "__main__":
    # 1. Train local models on HITL labels
    models = train_stage2_models()
    
    # 2. Load the conspiracy commons comparative parquet
    raw_parquet = 'data/processed/comparison_conspiracy_commons_scored.parquet'
    if os.path.exists(raw_parquet):
        df = pd.read_parquet(raw_parquet)
        print(f"\nLoaded {len(df):,} rows from {raw_parquet}")
        
        # Keep only necessary text column
        # comparison parquet has text as 'text'
        df_scored = apply_staged_pipeline(df, 'text', models)
        
        # 3. Run Stage 3 Borderline Classifications asynchronously
        loop = asyncio.get_event_loop()
        final_df = loop.run_until_complete(run_stage3_async(df_scored, 'text'))
        
        # Save scored output
        out_parquet = 'data/processed/comparison_conspiracy_commons_staged_scored.parquet'
        final_df.to_parquet(out_parquet, index=False)
        print(f"\n🎉 Finished! Saved scored dataset to {out_parquet}")
    else:
        print(f"❌ Raw dataset {raw_parquet} not found!")
