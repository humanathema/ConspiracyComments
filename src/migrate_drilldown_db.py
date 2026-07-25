# src/migrate_drilldown_db.py
"""migrate_drilldown_db.py

Migrates the SQLite database `drilldown.sqlite` to:
1. Enable WAL mode (Write-Ahead Logging).
2. Upgrade `topic_fit_ratings` to support a `rater` namespace and update
   its unique constraint to UNIQUE(comment_id, topic_name, rater).
3. Populate existing ratings with the default rater 'nash'.
4. Create the `outlier_topic_assignments` staging table.
"""
import argparse
import os
import sqlite3

def run_migration(db_path):
    print(f"=== Running migration on {db_path} ===")
    if not os.path.exists(db_path):
        print(f"❌ Error: Database path '{db_path}' does not exist.")
        return False
        
    conn = sqlite3.connect(db_path)
    
    # 1. Turn on WAL mode immediately (outside of transactions)
    print("  Enabling Write-Ahead Logging (WAL) journal mode...")
    conn.execute("PRAGMA journal_mode=WAL;")
    res = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    print(f"  Current journal mode: {res.upper()}")
    
    try:
        conn.execute("BEGIN TRANSACTION;")
        
        # Check if the column 'rater' already exists in 'topic_fit_ratings'
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(topic_fit_ratings);")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'rater' in columns:
            print("  [SKIP] 'topic_fit_ratings' already has a 'rater' column.")
        else:
            print("  Upgrading 'topic_fit_ratings' table schema...")
            # Rename existing table
            conn.execute("ALTER TABLE topic_fit_ratings RENAME TO topic_fit_ratings_old;")
            
            # Create new table with rater column and new UNIQUE constraint
            conn.execute("""
                CREATE TABLE topic_fit_ratings (
                    comment_id TEXT,
                    topic_name TEXT,
                    rating TEXT,
                    note TEXT,
                    rater TEXT DEFAULT 'nash',
                    rated_at TEXT,
                    UNIQUE(comment_id, topic_name, rater)
                );
            """)
            
            # Copy data from old table, defaulting rater to 'nash'
            conn.execute("""
                INSERT INTO topic_fit_ratings (comment_id, topic_name, rating, note, rated_at)
                SELECT comment_id, topic_name, rating, note, rated_at FROM topic_fit_ratings_old;
            """)
            
            # Drop old table
            conn.execute("DROP TABLE topic_fit_ratings_old;")
            print("  Successfully copied ratings and added 'rater' column.")
            
        # 2. Create the outlier assignment table
        print("  Creating 'outlier_topic_assignments' staging table...")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS outlier_topic_assignments (
                comment_id TEXT,
                original_topic_name TEXT,
                assigned_topic_name TEXT,
                rater TEXT,
                assigned_at TEXT,
                UNIQUE(comment_id, rater)
            );
        """)
        
        # Create indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_outlier_assignments_comment_id ON outlier_topic_assignments(comment_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ratings_comment_id ON topic_fit_ratings(comment_id);")
        
        conn.execute("COMMIT;")
        print("💾 Transaction committed successfully.")
        
        # 3. VACUUM the database to optimize pages
        print("  Optimizing database file (VACUUM)...")
        conn.execute("VACUUM;")
        print("🎉 Migration completed successfully!")
        return True
        
    except Exception as e:
        conn.execute("ROLLBACK;")
        print(f"❌ Error during migration, rolled back: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate live drilldown.sqlite schema")
    parser.add_argument("--db", default="data/processed/drilldown.sqlite", help="Path to SQLite database")
    args = parser.parse_args()
    run_migration(args.db)
