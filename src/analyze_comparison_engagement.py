import duckdb
import pandas as pd

def analyze_engagement(corpus_name):
    con = duckdb.connect()
    parquet_file = f"data/processed/comparison_{corpus_name}_scored.parquet"
    
    query = f"""
        WITH categorized AS (
            SELECT 
                CASE 
                    WHEN demand_count > 0 THEN '1. Demands Proof'
                    WHEN quantitative_count > 0 THEN '2. Cites Stats/Data'
                    WHEN evidence_count > 0 THEN '3. Cites Evidence/Docs'
                    WHEN alt_authority_count > 0 THEN '4. Cites Alt-Authority'
                    WHEN meta_count > 0 THEN '5. Meta-Debate / Logic'
                    WHEN anecdotal_count > 0 THEN '6. Uses Lived Experience'
                    WHEN pattern_count > 0 THEN '7. Pattern Recognition'
                    WHEN intuitive_count > 0 THEN '8. Uses Intuition'
                    WHEN adversarial_count > 0 THEN '9. Adversarial / Rhetoric'
                    WHEN hedge_count > 0 THEN '10. Hedging / Tentative'
                    WHEN certainty_count > 0 THEN '11. Certitude / Bravado'
                    ELSE '12. General / No Key Move'
                END as primary_move,
                upvotes,
                controversiality
            FROM '{parquet_file}'
        )
        SELECT 
            primary_move,
            COUNT(*) as count,
            ROUND(AVG(upvotes), 2) as avg_upvotes,
            ROUND(AVG(controversiality), 4) as avg_controversy
        FROM categorized
        GROUP BY primary_move
        ORDER BY avg_upvotes DESC
    """
    
    try:
        df = con.execute(query).df()
        output_file = f"data/processed/comparison_{corpus_name}_engagement.csv"
        df.to_csv(output_file, index=False)
        print(f"\n=== Engagement Profile: {corpus_name} ===")
        print(df.to_string(index=False))
    except Exception as e:
        print(f"Error analyzing {corpus_name}: {e}")

if __name__ == "__main__":
    corpora = ["askreddit", "conspiracy_commons", "topmindsofreddit"]
    for c in corpora:
        analyze_engagement(c)
