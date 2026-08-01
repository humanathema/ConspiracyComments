"""src/prototype_ats_implied_net_engagement.py

Models the "Implied Net Engagement" for AboveTopSecret (ATS) comments as an 
operationalization of "Implied Downvotes" (collective disapproval) using the 
two-stage cascade stance classifier.

Since ATS has no downvote button, community-endorsed disagreement ("ratioing") 
manifests when a hostile reply receives massive star counts relative to its parent.
This script calculates:
  Implied Downvotes(P) = Sum( Hostility(R_i) * Stars(R_i) )
  Net Engagement(P) = Stars(P) - Implied Downvotes(P)

To maintain computational and memory safety on a 7.15M comment corpus, this 
prototype runs over all comments belonging to the top 100 most active threads, 
allowing full parent-reply threading trees to be mapped and analyzed.
"""
import os
import sys
import re
import pandas as pd
import numpy as np
import duckdb
import joblib

# Paths
STANCE_MODEL_PATH = 'data/processed/stance_classifier_2stage_pooled.joblib'
ATS_CORPUS_PATH = 'data/processed/ats_comments_final.parquet'
ATS_CLEANED_PATH = 'data/processed/ats_comments_final.parquet'
OUT_CSV_PATH = 'data/processed/ats_implied_net_engagement_prototype.csv'


def load_model():
    if not os.path.exists(STANCE_MODEL_PATH):
        print(f"Error: Model file not found at {STANCE_MODEL_PATH}. Please train it first.")
        sys.exit(1)
        
    print(f"Loading two-stage cascade model from {STANCE_MODEL_PATH}...")
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec = stance_model['vec']
    clf_stage1 = stance_model['clf_stage1']
    clf_stage2 = stance_model['clf_stage2']
    print("Model loaded successfully.")
    return vec, clf_stage1, clf_stage2


def get_comments_sample(con):
    # Determine which parquet file to use (use cleaned if available)
    input_path = ATS_CLEANED_PATH if os.path.exists(ATS_CLEANED_PATH) else ATS_CORPUS_PATH
    print(f"Reading comments from: {input_path}")
    
    # Let's inspect columns to see if body_clean exists
    cols_df = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{input_path}')").df()
    col_names = cols_df['column_name'].tolist()
    text_col = 'body_clean' if 'body_clean' in col_names else 'body'
    print(f"Using text column: '{text_col}'")
    
    # 1. Identify the top 100 threads by comment volume
    print("Identifying the top 100 most active threads...")
    top_threads = con.execute(f"""
        SELECT thread_id, COUNT(*) AS comment_count
        FROM read_parquet('{input_path}')
        WHERE thread_id IS NOT NULL
        GROUP BY thread_id
        ORDER BY comment_count DESC
        LIMIT 100
    """).df()
    
    thread_ids = top_threads['thread_id'].tolist()
    print(f"Selected 100 threads spanning {sum(top_threads['comment_count']):,} total comments.")
    
    # 2. Pull all comments for these threads
    print("Loading comments for selected threads...")
    con.register("target_threads", pd.DataFrame({'thread_id': thread_ids}))
    
    comments_df = con.execute(f"""
        SELECT 
            c.post_id,
            c.thread_id,
            c.author,
            c.starred,
            c.{text_col} AS text,
            c.reply_to_post_ids
        FROM read_parquet('{input_path}') c
        JOIN target_threads t ON c.thread_id = t.thread_id
        WHERE c.post_id IS NOT NULL
    """).df()
    
    print(f"Loaded {len(comments_df):,} comments for network threading.")
    return comments_df


def classify_hostility(comments_df, vec, clf_stage1, clf_stage2):
    print("\nRunning stance classifier over comments to detect reply hostility...")
    texts = comments_df['text'].fillna('').astype(str).tolist()
    
    # Vectorize and predict in a single batch
    print(f"  Vectorizing {len(texts):,} comments...")
    X = vec.transform(texts)
    
    print("  Evaluating Stage 1 (clear vs. other)...")
    s1_classes = list(clf_stage1.classes_)
    p_stage1 = clf_stage1.predict_proba(X)
    p_other = p_stage1[:, s1_classes.index('other')]
    p_clear = 1.0 - p_other
    
    print("  Evaluating Stage 2 (hostile vs. endorsement)...")
    s2_classes = list(clf_stage2.classes_)
    p_stage2 = clf_stage2.predict_proba(X)
    p_hostile_given_clear = p_stage2[:, s2_classes.index('hostile')]
    
    # Calculate end-to-end P(hostile)
    p_hostile = p_clear * p_hostile_given_clear
    
    comments_df['p_hostile'] = p_hostile
    comments_df['p_other'] = p_other
    print("  Stance scoring completed.")
    return comments_df


def parse_replies(reply_val):
    """Safely parse reply_to_post_ids column which could be strings split by | or lists."""
    if pd.isna(reply_val):
        return []
    if isinstance(reply_val, list):
        return [str(x).strip() for x in reply_val if str(x).strip()]
    if isinstance(reply_val, np.ndarray):
        return [str(x).strip() for x in reply_val.tolist() if str(x).strip()]
    val_str = str(reply_val).strip()
    if not val_str:
        return []
    # If it is formatted as string split by |
    return [x.strip() for x in val_str.split('|') if x.strip()]


def main():
    print("================================================================")
    print("=== AboveTopSecret (ATS) Implied Net Engagement Prototype ===")
    print("================================================================")
    
    # 1. Load model
    vec, clf_stage1, clf_stage2 = load_model()
    
    # 2. Connect to DuckDB and load comments
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='4GB'")
    df = get_comments_sample(con)
    
    # 3. Classify comments
    df = classify_hostility(df, vec, clf_stage1, clf_stage2)
    
    # Ensure stars is treated as integer
    df['starred'] = df['starred'].fillna(0).astype(int)
    
    # Build dictionary of post_id to index/attributes for quick lookup
    post_lookup = df.set_index('post_id').to_dict(orient='index')
    
    # 4. Map the threading relationship and compute implied downvotes
    print("\nThreading parent-reply network graph...")
    # Dictionary to collect parent comments and list of their replies (reply_id, reply_stars, reply_hostility)
    parent_replies = {}
    
    for _, row in df.iterrows():
        comment_id = row['post_id']
        raw_replies = row['reply_to_post_ids']
        parents = parse_replies(raw_replies)
        
        for parent_id in parents:
            # Only track replies if the parent is within our sample
            if parent_id in post_lookup:
                parent_replies.setdefault(parent_id, []).append({
                    'reply_id': comment_id,
                    'stars': row['starred'],
                    'p_hostile': row['p_hostile'],
                    'author': row['author']
                })
                
    print(f"Mapped direct replies for {len(parent_replies):,} parent posts.")
    
    # 5. Compute Implied Downvotes and Net Engagement
    print("\nComputing Net Engagement scores...")
    results = []
    for _, row in df.iterrows():
        pid = row['post_id']
        parent_stars = row['starred']
        
        replies = parent_replies.get(pid, [])
        implied_downvotes = 0.0
        reply_count = len(replies)
        
        for rep in replies:
            # Implied Downvotes contribution = P(hostile) * reply_stars
            implied_downvotes += rep['p_hostile'] * rep['stars']
            
        net_engagement = parent_stars - implied_downvotes
        
        results.append({
            'post_id': pid,
            'thread_id': row['thread_id'],
            'author': row['author'],
            'stars': parent_stars,
            'reply_count': reply_count,
            'implied_downvotes': round(implied_downvotes, 3),
            'net_engagement': round(net_engagement, 3),
            'text_preview': str(row['text'])[:200].replace('\n', ' ')
        })
        
    res_df = pd.DataFrame(results)
    
    # 6. Analyze Distributions and Print Summaries
    print("\n=== Implied Net Engagement Distribution Summary ===")
    print(res_df[['stars', 'reply_count', 'implied_downvotes', 'net_engagement']].describe().to_string())
    
    # Find highly "ratioed" posts: high implied downvotes, negative net engagement
    ratioed = res_df[res_df['net_engagement'] < 0].sort_values('net_engagement', ascending=True)
    print(f"\nFound {len(ratioed):,} 'ratioed' posts (Net Engagement < 0) out of {len(res_df):,} sampled posts.")
    
    print("\n=== Top 5 Most 'Ratioed' Posts (Collective Disapproval) ===")
    top_ratioed = ratioed.head(5)
    for idx, r in top_ratioed.iterrows():
        print(f"\n------------------------------------------------------------")
        print(f"Parent Post ID: {r['post_id']} by {r['author']}")
        print(f"Parent Stars: {r['stars']} | Reply Count: {r['reply_count']}")
        print(f"Implied Downvotes: {r['implied_downvotes']:.2f} | Net Engagement: {r['net_engagement']:.2f} (RATIOED)")
        print(f"Parent Text: \"{r['text_preview']}...\"")
        
        # Display the highly starred hostile replies causing the ratio
        p_replies = parent_replies.get(r['post_id'], [])
        # Sort replies by contribution (hostility * stars)
        p_replies = sorted(p_replies, key=lambda x: x['p_hostile'] * x['stars'], reverse=True)
        print(f"Key Hostile Rebuttals:")
        for rep in p_replies[:3]:
            rep_text = post_lookup[rep['reply_id']]['text']
            print(f"  - Reply by {rep['author']}: Stars={rep['stars']} | P(hostile)={rep['p_hostile']:.3f}")
            print(f"    Text: \"{str(rep_text)[:120].strip()}...\"")
            
    # Save the output
    res_df.to_csv(OUT_CSV_PATH, index=False)
    print(f"\nSaved all prototype scores to {OUT_CSV_PATH}")


if __name__ == "__main__":
    main()
