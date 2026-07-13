import pandas as pd
import numpy as np
import re
import joblib
import os
import time

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

def score_main_corpus():
    start_time = time.time()
    
    # 1. Load models
    models_path = 'data/processed/staged_pipeline_models.joblib'
    if not os.path.exists(models_path):
        raise FileNotFoundError(f"Run staged_pipeline.py first to train and save models to {models_path}")
        
    print(f"🚀 Loading Stage 2 models from {models_path}...")
    models = joblib.load(models_path)
    pe_vec = models['personal_experience']['vec']
    pe_clf = models['personal_experience']['clf']
    ps_vec = models['procedural_skepticism']['vec']
    ps_clf = models['procedural_skepticism']['clf']
    
    # 2. Setup paths
    # NOTE: using the full 21M-comment length-filtered corpus, not the 4.78M
    # "enriched" subset — that subset is filtered to evidence_count>0 OR has_link=1
    # OR alt_authority_count>0 OR quantitative_count>0 (built for the FactAppeal/
    # source_citation evidential-grounding analysis), which verified against real
    # HITL labels excludes 77% of true personal_experience positives and 73% of
    # true procedural_skepticism positives. Wrong corpus for these two dimensions.
    input_parquet = 'data/processed/empath_scores_full.parquet'
    output_parquet = 'data/processed/research_corpus_staged_scores_full21m.parquet'
    
    print(f"📖 Processing {input_parquet} in memory-efficient chunks...")
    
    # Since we can't load the entire 1.7GB parquet and do heavy string filtering without high RAM overhead,
    # we read it using pyarrow in chunks.
    import pyarrow.parquet as pq
    parquet_file = pq.ParquetFile(input_parquet)
    
    processed_chunks = []
    total_rows = 0
    
    # Metrics aggregators
    metrics = {
        'personal_experience': {'passed_s1': 0, 'auto_neg': 0, 'auto_pos': 0, 'borderline': 0},
        'procedural_skepticism': {'passed_s1': 0, 'auto_neg': 0, 'auto_pos': 0, 'borderline': 0}
    }
    
    # Process batch by batch
    for i, batch in enumerate(parquet_file.iter_batches(batch_size=500000, columns=['id', 'text'])):
        chunk_start = time.time()
        df_chunk = batch.to_pandas()
        n_rows = len(df_chunk)
        total_rows += n_rows
        
        print(f"\n📦 Processing Chunk #{i+1} ({n_rows:,} rows, Cumulative: {total_rows:,} rows)...")
        
        # We will keep only id and scores to keep output file extremely lean and fast to join later
        df_scored = pd.DataFrame({'id': df_chunk['id']})
        
        # --- PERSONAL EXPERIENCE ---
        # Stage 1: Regex
        pe_pass_s1 = df_chunk['text'].apply(pass_personal_experience_filter)
        metrics['personal_experience']['passed_s1'] += pe_pass_s1.sum()
        
        # Initialize
        df_scored['pe_prob'] = 0.0
        df_scored['pe_decision'] = 'Auto-Negative'
        df_scored['pe_label'] = 0
        
        passed_pe_idx = df_chunk[pe_pass_s1].index
        if len(passed_pe_idx) > 0:
            pe_texts = df_chunk.loc[passed_pe_idx, 'text'].fillna('')
            X_pe = pe_vec.transform(pe_texts)
            pe_probs = pe_clf.predict_proba(X_pe)[:, 1]
            df_scored.loc[passed_pe_idx, 'pe_prob'] = pe_probs
            
            # Map decisions
            decisions = []
            labels = []
            for p in pe_probs:
                if p < 0.30:
                    decisions.append('Auto-Negative')
                    labels.append(0)
                elif p >= 0.70:
                    decisions.append('Auto-Positive')
                    labels.append(1)
                else:
                    decisions.append('Borderline')
                    labels.append(-1)
            df_scored.loc[passed_pe_idx, 'pe_decision'] = decisions
            df_scored.loc[passed_pe_idx, 'pe_label'] = labels
            
        # Update metrics for chunk
        pe_counts = df_scored['pe_decision'].value_counts()
        metrics['personal_experience']['auto_neg'] += pe_counts.get('Auto-Negative', 0)
        metrics['personal_experience']['auto_pos'] += pe_counts.get('Auto-Positive', 0)
        metrics['personal_experience']['borderline'] += pe_counts.get('Borderline', 0)
        
        # --- PROCEDURAL SKEPTICISM ---
        # Stage 1: Regex
        ps_pass_s1 = df_chunk['text'].apply(pass_procedural_skepticism_filter)
        metrics['procedural_skepticism']['passed_s1'] += ps_pass_s1.sum()
        
        # Initialize
        df_scored['ps_prob'] = 0.0
        df_scored['ps_decision'] = 'Auto-Negative'
        df_scored['ps_label'] = 0
        
        passed_ps_idx = df_chunk[ps_pass_s1].index
        if len(passed_ps_idx) > 0:
            ps_texts = df_chunk.loc[passed_ps_idx, 'text'].fillna('')
            X_ps = ps_vec.transform(ps_texts)
            ps_probs = ps_clf.predict_proba(X_ps)[:, 1]
            df_scored.loc[passed_ps_idx, 'ps_prob'] = ps_probs
            
            # Map decisions
            decisions = []
            labels = []
            for p in ps_probs:
                if p < 0.30:
                    decisions.append('Auto-Negative')
                    labels.append(0)
                elif p >= 0.70:
                    decisions.append('Auto-Positive')
                    labels.append(1)
                else:
                    decisions.append('Borderline')
                    labels.append(-1)
            df_scored.loc[passed_ps_idx, 'ps_decision'] = decisions
            df_scored.loc[passed_ps_idx, 'ps_label'] = labels
            
        # Update metrics for chunk
        ps_counts = df_scored['ps_decision'].value_counts()
        metrics['procedural_skepticism']['auto_neg'] += ps_counts.get('Auto-Negative', 0)
        metrics['procedural_skepticism']['auto_pos'] += ps_counts.get('Auto-Positive', 0)
        metrics['procedural_skepticism']['borderline'] += ps_counts.get('Borderline', 0)
        
        processed_chunks.append(df_scored)
        print(f"  Chunk #{i+1} completed in {time.time() - chunk_start:.1f}s.")
        
    # Combine chunks and save
    print("\n💾 Concatenating and saving scored results...")
    final_df = pd.concat(processed_chunks, ignore_index=True)
    final_df.to_parquet(output_parquet, index=False)
    
    elapsed = time.time() - start_time
    print(f"\n🎉 Finished processing {total_rows:,} rows in {elapsed/60:.2f} minutes!")
    print(f"💾 Results saved to {output_parquet}")
    
    # Print out summary report
    print("\n=================== SYSTEM-WIDE SCORING SUMMARY ===================")
    print(f"Total Comments Processed: {total_rows:,}")
    print("-" * 65)
    for dim in ['personal_experience', 'procedural_skepticism']:
        dim_name = dim.replace('_', ' ').title()
        print(f"Dimension: {dim_name}")
        passed_s1 = metrics[dim]['passed_s1']
        auto_neg = metrics[dim]['auto_neg']
        auto_pos = metrics[dim]['auto_pos']
        borderline = metrics[dim]['borderline']
        
        print(f"  - Passed Stage 1 Filter: {passed_s1:,} ({passed_s1/total_rows*100:.2f}%)")
        print(f"  - Auto-Negative (Stage 2): {auto_neg:,} ({auto_neg/total_rows*100:.2f}%)")
        print(f"  - Auto-Positive (Stage 2): {auto_pos:,} ({auto_pos/total_rows*100:.2f}%)")
        print(f"  - Borderline Zone (Stage 3): {borderline:,} ({borderline/total_rows*100:.2f}%)")
        
        # Estimate Stage 3 Costs
        est_tokens = borderline * 150 # approx 150 tokens per row prompt + response
        est_cost = (est_tokens / 1_000_000) * 0.075 # $0.075 per 1M tokens
        print(f"  - Projected Stage 3 LLM Cost: ${est_cost:.2f} (Gemini 1.5 Flash)")
        print("-" * 65)

if __name__ == "__main__":
    score_main_corpus()
