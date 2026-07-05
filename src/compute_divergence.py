import duckdb
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer, ENGLISH_STOP_WORDS
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

def score_divergence(month, comments_glob):
    con = duckdb.connect()
    print(f"\n--- Processing {month} ---")
    
    baseline_csv = f'data/processed/lexical_baseline_{month}.csv'
    try:
        df_base = pd.read_csv(baseline_csv)
    except FileNotFoundError:
        print(f"Error: Baseline for {month} not found at {baseline_csv}")
        return
        
    custom_stops = set(ENGLISH_STOP_WORDS).union({
        'just', 'like', 'don', 'people', 'think', 'know', 'really', 'make', 'did', 'does',
        'reddit', 'sub', 'conspiracy', 'post', 'comment', 'http', 'https', 'com', 'www',
        've', 'll', 're', 'didn', 'doesn', 'going', 'say', 'way', 'got', 'right', 'good', 'time'
    })

    df_jargon = df_base[~df_base['word'].isin(custom_stops)].copy()
    vocab = df_jargon['word'].tolist()
    corpus_counts = df_jargon['term_frequency'].values.reshape(1, -1)
    
    print(f"Loaded global baseline for {month}. Kept {len(vocab)} non-stop words for semantic scoring.")
    
    # 1. Grab all active authors for this month and their total comment counts
    query_authors = f"""
        WITH monthly_comments AS (
            SELECT author, body
            FROM read_json_auto('{comments_glob}', maximum_object_size=50000000, union_by_name=True)
            WHERE body IS NOT NULL 
              AND body NOT IN ('[deleted]', '[removed]')
              AND strftime(to_timestamp(created_utc), '%Y-%m') = '{month}'
        ),
        author_stats AS (
            SELECT author, COUNT(*) as month_comments, string_agg(body, ' ') as all_text
            FROM monthly_comments
            WHERE author NOT IN ('[deleted]', '[removed]', 'AutoModerator')
            GROUP BY author
            HAVING COUNT(*) >= 5 -- Only score users with at least a few comments
        )
        SELECT * FROM author_stats
    """
    
    print("Executing query to aggregate author comments...")
    df_authors = con.execute(query_authors).df()
    print(f"Found {len(df_authors)} qualifying authors.")
    
    if len(df_authors) == 0:
        return
        
    print("Vectorizing text and computing cosine similarity to baseline...")
    vectorizer = CountVectorizer(vocabulary=vocab)
    user_matrix = vectorizer.fit_transform(df_authors['all_text'])
    similarities = cosine_similarity(user_matrix, corpus_counts)
    
    df_authors['lexical_insider_score'] = similarities.flatten()
    
    # Categorize users by activity tier for this month
    df_authors['activity_tier'] = pd.cut(
        df_authors['month_comments'],
        bins=[4, 10, 20, 50, 100, np.inf],
        labels=['5-10', '11-20', '21-50', '51-100', '100+']
    )
    
    output_path = f'data/processed/lexical_scores_{month}.csv'
    df_authors[['author', 'month_comments', 'activity_tier', 'lexical_insider_score']].to_csv(output_path, index=False)
    print(f"Saved lexical scores to {output_path}")
    
    # Summary report
    summary = df_authors.groupby('activity_tier')['lexical_insider_score'].agg(['mean', 'median', 'count'])
    print(f"\nConvergence Summary for {month}:")
    print(summary)

if __name__ == "__main__":
    comments_glob = 'data/raw/r_conspiracy_comments*.jsonl.gz'
    months = ['2014-08', '2023-09']
    for m in months:
        score_divergence(m, comments_glob)
