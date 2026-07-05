import duckdb
import pandas as pd
import json

def initialize_db_connection():
    """Initializes and returns a DuckDB connection."""
    return duckdb.connect()

def extract_media_titles(file_path: str, target_limit: int = 10000) -> pd.DataFrame:
    """
    Streams a massive JSONL file natively in Python to bypass SQL schema crashes,
    extracting clean oembed media titles.
    """
    extracted_records = []
    print("Streaming file natively in Python to bypass SQL schema crashes...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                media = data.get('media')
                
                if isinstance(media, dict):
                    oembed = media.get('oembed', {})
                    if isinstance(oembed, dict):
                        title = oembed.get('title')
                        if title:
                            extracted_records.append({
                                'id': data.get('id', ''),
                                'author': data.get('author', ''),
                                'score': data.get('score', 0),
                                'url': data.get('url', ''),
                                'link_title': title,
                                'link_description': oembed.get('description') or '' 
                            })
                            if len(extracted_records) >= target_limit:
                                break
            except json.JSONDecodeError:
                continue
                
    links_df = pd.DataFrame(extracted_records)
    if not links_df.empty:
        links_df['combined_payload'] = links_df['link_title'] + " - " + links_df['link_description']
    
    print(f"Extraction successful. Retained {len(links_df)} rich media-link records.")
    return links_df

def extract_top_battlegrounds(file_paths_list: list, limit: int = 500) -> pd.DataFrame:
    """
    Combines multiple files, drops overlapping duplicates based on comment ID, 
    and crunches reply counts to find top battleground threads.
    """
    paths_str = str(file_paths_list)
    query = f"""
        WITH deduplicated_comments AS (
            SELECT DISTINCT id, parent_id
            FROM read_json_auto({paths_str})
        )
        SELECT 
            parent_id, 
            COUNT(*) as reply_count
        FROM deduplicated_comments
        WHERE parent_id LIKE 't1_%'
        GROUP BY parent_id
        ORDER BY reply_count DESC
        LIMIT {limit}
    """
    print("Scanning multiple files, filtering out overlaps, and crunching numbers...")
    return duckdb.query(query).df()

def extract_thread(file_paths_list: list, target_id: str) -> pd.DataFrame:
    """
    Extracts a conversation thread (parent comment + direct replies) for a specific ID.
    """
    paths_str = str(file_paths_list)
    clean_target = target_id.replace('t1_', '').replace('t3_', '')
    query = f"""
        SELECT id, parent_id, author, score, body
        FROM read_json_auto({paths_str})
        WHERE id = '{clean_target}' OR parent_id = 't1_{clean_target}'
    """
    print(f"Extracting the conversation thread for {target_id}...")
    return duckdb.query(query).df()

def get_timeline_boundaries(file_paths_list: list) -> pd.DataFrame:
    """
    Scans files for the earliest and most recent comment timestamps.
    """
    paths_str = str(file_paths_list)
    query = f"""
        SELECT 
            MIN(to_timestamp(CAST(created_utc AS BIGINT))) AS earliest_comment,
            MAX(to_timestamp(CAST(created_utc AS BIGINT))) AS most_recent_comment
        FROM read_json_auto({paths_str})
    """
    print("Scanning files for the timeline boundaries...")
    return duckdb.query(query).df()
