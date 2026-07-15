"""Calculate the correlation matrix across continuous construct scores and lexicons.

Joins the newly scored 21.4M staged scores with the first-gen Empath lexicon counts
to quantitatively check construct overlap and baseline associations.

Output: data/processed/construct_correlation_matrix.csv
"""
import duckdb
import pandas as pd
import time

STAGED_PATH = "/Users/nash/Projects/ConspiracyComments/data/processed/research_corpus_staged_scores_full21m.parquet"
EMPATH_PATH = "/Users/nash/Projects/ConspiracyComments/data/processed/empath_scores_full.parquet"
OUT_PATH = "/Users/nash/Projects/ConspiracyComments/data/processed/construct_correlation_matrix.csv"


def main():
    print("Connecting to DuckDB and querying 21.4M records...")
    start = time.time()
    
    con = duckdb.connect()
    
    # Query only numerical/boolean columns, joining on 'id'
    query = f"""
        SELECT 
            s.pe_prob,
            s.ps_prob,
            e.evidence_count,
            e.adversarial_count,
            e.hedge_count,
            e.certainty_count,
            e.alt_authority_count,
            e.intuitive_count,
            e.pattern_count,
            e.meta_count,
            e.demand_count,
            e.anecdotal_count,
            e.quantitative_count,
            e.char_length,
            CAST(e.has_link AS INTEGER) as has_link
        FROM '{STAGED_PATH}' s
        JOIN '{EMPATH_PATH}' e
        ON s.id = e.id
    """
    
    print("Running query...")
    df = con.query(query).df()
    elapsed_query = time.time() - start
    print(f"Data joined and loaded in {elapsed_query:.1f} seconds. Row count: {len(df):,}")
    
    print("\nComputing Pearson correlation matrix...")
    start_corr = time.time()
    corr = df.corr(method='pearson')
    elapsed_corr = time.time() - start_corr
    print(f"Correlation matrix computed in {elapsed_corr:.1f} seconds.")
    
    # Format and display
    pd.set_option('display.float_format', lambda x: '%.3f' % x)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    
    print("\n" + "="*50)
    print("           CATEGORY CORRELATION MATRIX")
    print("="*50)
    print(corr)
    print("="*50)
    
    # Save output
    corr.to_csv(OUT_PATH)
    print(f"\nSaved correlation matrix to {OUT_PATH}")


if __name__ == "__main__":
    main()
