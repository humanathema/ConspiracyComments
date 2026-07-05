import duckdb
import os
import sys
import time

# Add utils to path so we can import the lexicon
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from utils.epistemic_lexicon import lex
except ImportError:
    print("Error: Could not import utils.epistemic_lexicon.lex")
    sys.exit(1)

def score_corpus(corpus_name, input_glob):
    con = duckdb.connect()
    output_file = f"data/processed/comparison_{corpus_name}_scored.parquet"
    
    if os.path.exists(output_file):
        print(f"Skipping {corpus_name}: {output_file} already exists.")
        return
        
    print(f"\n--- Scoring {corpus_name} ---")
    print("Building SIMD string search query for 11 dimensions...")

    category_columns = []
    for cat, words in lex.items():
        term_checks = []
        for word in words:
            clean_word = word.replace('-', ' ').replace("'", "''").lower()
            term_checks.append(f"contains(clean_text, ' {clean_word} ')::INT")
            
        cat_sum_sql = " + \n            ".join(term_checks)
        category_columns.append(f"({cat_sum_sql}) as {cat}_count")

    category_sql = ",\n        ".join(category_columns)

    query = f"""
        WITH raw_comments AS (
            SELECT 
                id,
                author,
                COALESCE(score, 0) as upvotes,
                COALESCE(try_cast(controversiality as INT), 0) as controversiality,
                parent_id,
                link_id,
                created_utc,
                length(body) as char_length,
                CASE WHEN body LIKE '%http%' THEN 1 ELSE 0 END as has_link,
                body as text,
                ' ' || regexp_replace(lower(body), '[^a-z0-9]', ' ', 'g') || ' ' as clean_text
            FROM read_json_auto('{input_glob}', maximum_object_size=50000000, ignore_errors=true)
            WHERE body IS NOT NULL 
              AND body NOT IN ('[deleted]', '[removed]')
              AND length(body) > 50
        )
        SELECT 
            id,
            author,
            upvotes,
            controversiality,
            parent_id,
            link_id,
            created_utc,
            char_length,
            has_link,
            text,
            {category_sql}
        FROM raw_comments
    """

    print(f"Executing and saving to {output_file}...")
    start = time.time()
    try:
        con.execute(f"COPY ({query}) TO '{output_file}' (FORMAT PARQUET, COMPRESSION 'zstd')")
        elapsed = (time.time() - start) / 60
        print(f"Done in {elapsed:.1f} minutes \u2014 saved to {output_file}")
    except Exception as e:
        print(f"Failed scoring {corpus_name}: {e}")

if __name__ == "__main__":
    corpora = {
        "askreddit": "data/raw/r_askreddit_comments.jsonl",
        "conspiracy_commons": "data/raw/r_conspiracy_commons_comments.jsonl",
        "topmindsofreddit": "data/raw/r_topmindsofreddit_comments.jsonl"
    }
    
    for name, glob_path in corpora.items():
        score_corpus(name, glob_path)
