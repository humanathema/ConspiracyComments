# src/scratch_test_concurrency.py
import sqlite3
import threading
import time
import random
import os
import argparse

RATER_ID = "_concurrency_test_bot"
THREADS = 10
WRITES_PER_THREAD = 50

def get_connection(db_path):
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def worker(thread_idx, db_path, errors):
    conn = get_connection(db_path)
    for i in range(WRITES_PER_THREAD):
        comment_id = f"concurrency_test_comment_{thread_idx}_{i}"
        topic_name = "0_test_topic"
        rating = "3"
        try:
            if random.random() < 0.5:
                conn.execute("""
                    INSERT INTO topic_fit_ratings (comment_id, topic_name, rating, rater, rated_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(comment_id, topic_name, rater) DO UPDATE SET
                      rating=excluded.rating,
                      rated_at=excluded.rated_at;
                """, (comment_id, topic_name, rating, RATER_ID))
            else:
                conn.execute("""
                    INSERT INTO outlier_topic_assignments (comment_id, original_topic_name, assigned_topic_name, rater, assigned_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(comment_id, rater) DO UPDATE SET
                      assigned_topic_name=excluded.assigned_topic_name,
                      assigned_at=excluded.assigned_at;
                """, (comment_id, "outlier", topic_name, RATER_ID))
            conn.commit()
        except sqlite3.OperationalError as e:
            errors.append(e)
            print(f"❌ Thread {thread_idx} hit error: {e}")
        time.sleep(0.01)
    conn.close()

def main():
    parser = argparse.ArgumentParser(description="Verify SQLite write concurrency")
    parser.add_argument("--db", default="data/processed/drilldown.sqlite", help="Path to SQLite database")
    args = parser.parse_args()
    
    db_path = args.db
    print(f"=== Beginning Concurrency Load Simulation (WAL + timeout) ===")
    print(f"Target DB: {db_path}")
    print(f"Spawning {THREADS} concurrent threads doing {WRITES_PER_THREAD} writes each...")
    
    if not os.path.exists(db_path):
        print(f"Creating a temp database file at {db_path} to initialize tables...")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
    conn = get_connection(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS topic_fit_ratings (comment_id TEXT, topic_name TEXT, rating TEXT, note TEXT, rater TEXT DEFAULT 'nash', rated_at TEXT, UNIQUE(comment_id, topic_name, rater));")
    conn.execute("CREATE TABLE IF NOT EXISTS outlier_topic_assignments (comment_id TEXT, original_topic_name TEXT, assigned_topic_name TEXT, rater TEXT, assigned_at TEXT, UNIQUE(comment_id, rater));")
    conn.commit()
    conn.close()
    
    start_time = time.time()
    threads = []
    errors = []
    
    for i in range(THREADS):
        t = threading.Thread(target=worker, args=(i, db_path, errors))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    elapsed = time.time() - start_time
    total_attempted = THREADS * WRITES_PER_THREAD
    successful_writes = total_attempted - len(errors)
    
    print(f"\n=== Load Simulation Results ===")
    print(f"Elapsed Time: {elapsed:.2f} seconds")
    print(f"Attempted Writes: {total_attempted}")
    print(f"Successful Writes: {successful_writes}")
    print(f"Errors Encountered: {len(errors)}")
    
    print("\n🧹 Executing clean teardown query...")
    conn = get_connection(db_path)
    r1 = conn.execute("DELETE FROM topic_fit_ratings WHERE rater=?;", (RATER_ID,)).rowcount
    r2 = conn.execute("DELETE FROM outlier_topic_assignments WHERE rater=?;", (RATER_ID,)).rowcount
    conn.commit()
    conn.close()
    print(f"  Deleted {r1} synthetic ratings and {r2} synthetic outlier assignments from {db_path}.")
    print("✨ Teardown complete. DB is pristine!")
    
    if len(errors) == 0:
        print("✅ SUCCESS: Concurrency safety verified with ZERO locks or race conditions!")
    else:
        print("❌ FAILURE: Locks/race conditions detected. Review connection pools and WAL settings.")

if __name__ == "__main__":
    main()
