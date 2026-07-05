import duckdb
import pandas as pd
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

def generate_baseline(month, comments_glob):
    con = duckdb.connect()
    
    print(f"Extracting exhaustive Lexical Baseline for {month}...")
    
    stop_words_sql = tuple([w.replace("'", "''") for w in ENGLISH_STOP_WORDS])
    
    query = f"""
        WITH raw_text AS (
            SELECT lower(regexp_replace(body, '[^a-zA-Z]', ' ', 'g')) as cleaned_body
            FROM read_json_auto('{comments_glob}', maximum_object_size=50000000, union_by_name=True)
            WHERE body IS NOT NULL 
              AND body NOT IN ('[deleted]', '[removed]')
              AND strftime(to_timestamp(created_utc), '%Y-%m') = '{month}'
        ),
        tokens AS (
            SELECT unnest(string_split(cleaned_body, ' ')) as word
            FROM raw_text
        )
        SELECT 
            word, 
            COUNT(*) as term_frequency
        FROM tokens
        WHERE length(word) > 2  
          AND word NOT IN {stop_words_sql}
        GROUP BY word
        ORDER BY term_frequency DESC
        LIMIT 5000
    """
    
    try:
        df_baseline_vocab = con.execute(query).df()
        output_path = f'data/processed/lexical_baseline_{month}.csv'
        df_baseline_vocab.to_csv(output_path, index=False)
        print(f"Saved {month} baseline to {output_path}")
        print(df_baseline_vocab.head(5))
    except Exception as e:
        print("Execution failed:", e)

if __name__ == "__main__":
    comments_glob = 'data/raw/r_conspiracy_comments*.jsonl.gz'
    months = ['2014-08', '2023-09']
    for m in months:
        generate_baseline(m, comments_glob)
