"""
Data loading utilities with caching support.
"""

import json
import os
from pathlib import Path
from typing import Any, Optional, Dict
import pandas as pd


def load_cached_json(
    cache_path: str,
    load_fn: callable,
    force_refresh: bool = False
) -> Any:
    """
    Load data with JSON cache fallback.
    
    If cache exists, load from it. Otherwise, call load_fn(),
    then save result to cache for future runs.
    
    Args:
        cache_path: Path to cache JSON file.
        load_fn: Callable that loads data if cache doesn't exist.
        force_refresh: If True, ignore cache and reload.
        
    Returns:
        Loaded data (dict or other JSON-serializable type).
    """
    if os.path.exists(cache_path) and not force_refresh:
        print(f"Loading from cache: {cache_path}")
        with open(cache_path, 'r') as f:
            return json.load(f)
    
    print(f"Computing and caching to: {cache_path}")
    data = load_fn()
    
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    return data


def save_cache(cache_path: str, data: Dict[str, Any]) -> None:
    """
    Save data to JSON cache file.
    
    Args:
        cache_path: Path to save cache.
        data: Data to cache (must be JSON-serializable).
    """
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Cache saved to: {cache_path}")


def load_parquet_sample(
    path: str,
    n: int = 1000,
    random: bool = True
) -> pd.DataFrame:
    """
    Load a sample of rows from a parquet file.
    
    Args:
        path: Path to parquet file.
        n: Number of rows to sample.
        random: If True, random sample. If False, first n rows.
        
    Returns:
        DataFrame with sampled rows.
    """
    df = pd.read_parquet(path, engine='pyarrow')
    
    if random:
        return df.sample(n=min(n, len(df)), random_state=42)
    else:
        return df.head(n)


def load_csv_chunk(
    path: str,
    chunksize: int = 10000,
    nrows: Optional[int] = None
):
    """
    Load CSV in chunks (memory-efficient for large files).
    
    Args:
        path: Path to CSV file.
        chunksize: Rows per chunk.
        nrows: Total rows to load (None for all).
        
    Yields:
        DataFrame chunks.
    """
    for chunk in pd.read_csv(path, chunksize=chunksize, nrows=nrows):
        yield chunk


def load_jsonl(path: str, nrows: Optional[int] = None) -> pd.DataFrame:
    """
    Load JSONL file into DataFrame.
    
    Args:
        path: Path to JSONL file.
        nrows: Max rows to load.
        
    Returns:
        DataFrame.
    """
    records = []
    with open(path, 'r') as f:
        for i, line in enumerate(f):
            if nrows and i >= nrows:
                break
            records.append(json.loads(line))
    
    return pd.DataFrame(records)


def ensure_parquet_exists(
    path: str,
    create_fn: callable
) -> str:
    """
    Ensure a parquet file exists. If not, create it using create_fn.
    
    Args:
        path: Expected parquet file path.
        create_fn: Callable that creates/loads the parquet file.
        
    Returns:
        Path to parquet file.
    """
    if os.path.exists(path):
        print(f"Parquet exists: {path}")
        return path
    
    print(f"Creating parquet: {path}")
    df = create_fn()
    df.to_parquet(path, engine='pyarrow', compression='snappy')
    print(f"Saved to: {path}")
    return path
