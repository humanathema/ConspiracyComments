import duckdb
import pandas as pd

EMPATH_PATH = "data/processed/empath_scores_full.parquet"

def search_name(name_query):
    print(f"\nSearching for comments matching: '{name_query}'")
    query = f"""
        SELECT e.text
        FROM '{EMPATH_PATH}' e
        WHERE lower(e.text) LIKE '%{name_query.lower()}%'
        LIMIT 25
    """
    try:
        con = duckdb.connect()
        df = con.execute(query).fetchdf()
        if df.empty:
            print("  No comments found.")
        else:
            for idx, row in df.iterrows():
                print(f"\n--- Mention {idx+1} ---")
                print(row['text'].strip()[:800] + ("..." if len(row['text'].strip()) > 800 else ""))
    except Exception as e:
        print(f"  Error: {e}")

search_name("John Cook")
search_name("David Keith")
search_name("Keith David")
