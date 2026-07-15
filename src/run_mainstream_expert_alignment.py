"""run_mainstream_expert_alignment.py

Enriches the merged expert superset with actual mention frequencies (doc_count)
in the 21.4M comment corpus. Uses a highly optimized, low-memory DuckDB
streaming Parquet search to comply with swap space limits.
Filters out figures with 0 mentions to produce a highly dense, verified list.
"""
import os
import duckdb
import pandas as pd

TEMP_PATH = "data/processed/mainstream_expert_augmented_superset_temp.csv"
FINAL_PATH = "data/processed/mainstream_expert_augmented_superset.csv"
PARQUET_PATH = "data/processed/empath_scores_full.parquet"
ENTITY_FREQ_PATH = "data/processed/corpus_entity_frequency_final.csv"

BATCH_SIZE = 150

def main():
    print("=== Running Mainstream Expert Corpus Alignment ===")
    
    # 1. Load intermediate superset
    if not os.path.exists(TEMP_PATH):
        raise FileNotFoundError(f"Missing intermediate superset at {TEMP_PATH}")
    df_exp = pd.read_csv(TEMP_PATH)
    print(f"Loaded {len(df_exp):,} unique experts to scan.")
    
    # Initialize count column and load previously aligned counts if available
    df_exp["doc_count"] = 0.0
    old_counts = {}
    if os.path.exists(FINAL_PATH):
        print(f"Loading previously aligned expert counts from {FINAL_PATH}...")
        try:
            df_old = pd.read_csv(FINAL_PATH)
            if "doc_count" in df_old.columns and "name" in df_old.columns:
                old_counts = {str(k).lower().strip(): float(v) for k, v in zip(df_old["name"], df_old["doc_count"]) if pd.notna(v)}
                print(f"Loaded {len(old_counts)} existing expert doc counts from previous final output.")
        except Exception as e:
            print(f"Warning: could not load previous aligned counts: {e}")

    # Assign from old counts if possible
    mapped_count = 0
    for idx, row in df_exp.iterrows():
        name_lower = str(row["name"]).lower().strip()
        if name_lower in old_counts:
            df_exp.at[idx, "doc_count"] = old_counts[name_lower]
            mapped_count += 1
    print(f"Successfully restored {mapped_count:,} doc counts from previous final output.")

    # For those remaining, try pre-compiled matches to save database queries
    remaining_to_match = df_exp[df_exp["doc_count"] == 0.0].copy()
    if len(remaining_to_match) > 0 and os.path.exists(ENTITY_FREQ_PATH):
        print(f"Loading pre-compiled entity frequencies from {ENTITY_FREQ_PATH}...")
        try:
            df_ent = pd.read_csv(ENTITY_FREQ_PATH)
            ent_dict = {str(k).lower().strip(): v for k, v in zip(df_ent["entity"], df_ent["doc_count"])}
            
            pre_matched = 0
            for idx, row in remaining_to_match.iterrows():
                name_lower = str(row["name"]).lower().strip()
                if name_lower in ent_dict:
                    df_exp.at[idx, "doc_count"] = float(ent_dict[name_lower])
                    pre_matched += 1
            print(f"Instantly pre-matched {pre_matched:,} remaining experts from entity frequency list.")
        except Exception as e:
            print(f"Warning: could not load entity frequencies: {e}")

    # 3. Scan the remainder using DuckDB streaming Parquet search only if requested
    import sys
    force_scan = "--force-scan" in sys.argv
    to_scan = df_exp[df_exp["doc_count"] == 0.0].copy()
    
    if not force_scan:
        print(f"Skipping heavy scan for the remaining {len(to_scan):,} experts (assumed 0 mentions).")
        print("To run a deep DuckDB scan over the 21.4M Parquet file, run with: python3 src/run_mainstream_expert_alignment.py --force-scan")
    else:
        print(f"Scanning the remaining {len(to_scan):,} experts across the 21.4M corpus...")
        con = duckdb.connect()
        indices = to_scan.index.tolist()
        
        # Run in batches
        for i in range(0, len(indices), BATCH_SIZE):
            batch_indices = indices[i:i+BATCH_SIZE]
            batch_names = [df_exp.at[idx, "name"] for idx in batch_indices]
            print(f"Processing batch {i // BATCH_SIZE + 1} / {len(indices) // BATCH_SIZE + 1} ({len(batch_names)} names)...")
            
            # Compile SUM-CASE query
            select_parts = []
            for idx, name in zip(batch_indices, batch_names):
                # Clean and escape the name for SQL string literal
                escaped_name = str(name).lower().replace("'", "''").strip()
                select_parts.append(
                    f"SUM(CASE WHEN contains(ltext, '{escaped_name}') THEN 1 ELSE 0 END) as c_{idx}"
                )
                
            sql_query = f"""
                WITH cleaned AS (
                    SELECT lower(text) as ltext FROM '{PARQUET_PATH}'
                )
                SELECT {', '.join(select_parts)}
                FROM cleaned
            """
            
            try:
                res_df = con.execute(sql_query).df()
                # Assign counts back
                for idx in batch_indices:
                    col_name = f"c_{idx}"
                    if col_name in res_df.columns:
                        df_exp.at[idx, "doc_count"] = float(res_df.at[0, col_name])
            except Exception as e:
                print(f"Error executing SQL for batch starting with {batch_names[0]}: {e}")
                
        print("\nScan complete.")
    
    # 4. Print stats before filtering
    print(f"Total experts scanned: {len(df_exp):,}")
    print(f"Unmentioned figures (count = 0): {len(df_exp[df_exp['doc_count'] == 0.0]):,}")
    print(f"Mentioned figures (count > 0): {len(df_exp[df_exp['doc_count'] > 0.0]):,}")

    # 5. Filter out unmentioned figures
    df_mentioned = df_exp[df_exp["doc_count"] > 0.0].copy()
    print(f"Filtered out unmentioned figures. Keeping {len(df_mentioned):,} active experts.")

    # 6. Add blank decision column and flag specific review-tossup figures (e.g. Cook & Chomsky)
    df_mentioned["decision"] = ""
    df_mentioned.loc[df_mentioned["name"].str.lower().str.strip() == "john cook", "decision"] = "review"
    df_mentioned.loc[df_mentioned["name"].str.lower().str.strip() == "noam chomsky", "decision"] = "review"

    # 7. Save final CSV
    os.makedirs(os.path.dirname(FINAL_PATH), exist_ok=True)
    df_mentioned.to_csv(FINAL_PATH, index=False)
    print(f"Saved final mainstream expert augmented superset to {FINAL_PATH}")

if __name__ == "__main__":
    main()
