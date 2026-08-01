# src/audit_missing_buckets.py
import pandas as pd

def audit_missing_buckets():
    print("=== Loading entity_final_review.csv ===")
    df = pd.read_csv('data/processed/entity_final_review.csv')
    
    # Non-empty best_identity or wp_description, but blank final_bucket_guess
    has_identity = df['best_identity'].notna() & (df['best_identity'].str.strip() != '')
    has_wp = df['wp_description'].notna() & (df['wp_description'].str.strip() != '')
    blank_bucket = df['final_bucket_guess'].isna() | (df['final_bucket_guess'].str.strip() == '')
    
    audit_mask = (has_identity | has_wp) & blank_bucket
    audit_df = df[audit_mask].copy()
    
    print(f"Audit completed: Found {len(audit_df)} rows with a valid identity/description but missing final_bucket_guess.")
    
    # Prepare output with columns resembling missing_entity_candidates.csv plus extra metadata
    audit_df['corpus_mentions'] = audit_df['doc_count']
    audit_df['example_1'] = audit_df['corpus_example']
    audit_df['example_2'] = "" # We only have one example in entity_final_review
    audit_df['decision'] = ""  # blank for Nash's review
    
    out_cols = ['entity', 'corpus_mentions', 'best_identity', 'wp_description', 'example_1', 'example_2', 'decision']
    out_df = audit_df[out_cols].sort_values(by='corpus_mentions', ascending=False)
    
    out_path = 'data/processed/missing_bucket_candidates.csv'
    out_df.to_csv(out_path, index=False)
    print(f"Saved audit output to {out_path}")
    
    # Show first 15 rows
    print("\nTop 15 missing bucket candidates for manual review:")
    print(out_df[['entity', 'best_identity', 'corpus_mentions']].head(15).to_string(index=False))

if __name__ == "__main__":
    audit_missing_buckets()
