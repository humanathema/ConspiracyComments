# src/spot_check_ambiguous_names.py
import re
import pandas as pd
import duckdb

def spot_check_ambiguous_names():
    print("=== Loading entity_final_review.csv ===")
    df = pd.read_csv('data/processed/entity_final_review.csv')
    
    # Filter for short, non-junk, high-count entities
    is_short = df['entity'].astype(str).str.len() <= 4
    is_not_junk = df['likely_pure_junk'] == False
    is_high_count = df['doc_count'] >= 100
    
    candidates = df[is_short & is_not_junk & is_high_count].copy()
    candidates = candidates.sort_values(by='doc_count', ascending=False)
    
    print(f"Found {len(candidates)} short high-count entities.")
    
    # Take the top 12 short/acronym entities for sampling
    excluded_noise = {'the', 'that', 'not', 'don', 'think', 'know', 'agree', 'who'}
    filtered_candidates = candidates[~candidates['entity'].str.lower().isin(excluded_noise)]
    
    top_targets = filtered_candidates['entity'].head(12).tolist()
    print("Top 12 targets selected for ambiguity spot-check:", top_targets)
    
    con = duckdb.connect()
    
    samples = []
    
    print("\n=== Pulling random samples of 30 comments per target ===")
    for ent in top_targets:
        pattern = rf'\b{re.escape(ent)}\b'
        print(f"  Sampling for entity '{ent}' using pattern '{pattern}'...")
        
        # Query 30 random matching comments by filtering first and ordering randomly
        try:
            query_df = con.execute("""
                SELECT text 
                FROM 'data/processed/empath_scores_full_mapped.parquet'
                WHERE regexp_matches(text, ?, 'i')
                ORDER BY random()
                LIMIT 30
            """, [pattern]).df()
            
            for i, row in query_df.iterrows():
                samples.append({
                    'entity': ent,
                    'sample_index': i + 1,
                    'comment_text': row['text'].strip()
                })
        except Exception as e:
            print(f"  Error sampling for '{ent}': {e}")
            
    samples_df = pd.DataFrame(samples)
    out_path = 'data/processed/ambiguity_spot_checks.csv'
    samples_df.to_csv(out_path, index=False)
    print(f"\nSaved {len(samples_df)} total sampled comments to {out_path}")

if __name__ == "__main__":
    spot_check_ambiguous_names()
