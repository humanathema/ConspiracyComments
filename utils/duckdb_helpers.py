"""
Common DuckDB query patterns and helper functions.
"""

import duckdb
import pandas as pd
from typing import Optional, Any, List, Tuple


def get_connection(memory: bool = False) -> duckdb.DuckDBPyConnection:
    """
    Get a DuckDB connection (in-memory or file-based).
    
    Args:
        memory: If True, creates in-memory connection. If False, uses default.
        
    Returns:
        DuckDB connection object.
    """
    if memory:
        return duckdb.connect(':memory:')
    return duckdb.connect()


def query_to_df(
    con: duckdb.DuckDBPyConnection,
    query: str,
    fetch_all: bool = True
) -> pd.DataFrame:
    """
    Execute query and return as DataFrame.
    
    Args:
        con: DuckDB connection.
        query: SQL query string.
        fetch_all: If False, returns iterator (for large results).
        
    Returns:
        DataFrame or iterator of query results.
    """
    result = con.execute(query)
    return result.df() if fetch_all else result.fetch_arrow_table()


def count_records(con: duckdb.DuckDBPyConnection, table_or_path: str) -> int:
    """
    Count total records in a table or parquet file.
    
    Args:
        con: DuckDB connection.
        table_or_path: Table name or file path.
        
    Returns:
        Record count.
    """
    if table_or_path.endswith('.parquet'):
        query = f"SELECT COUNT(*) FROM '{table_or_path}'"
    else:
        query = f"SELECT COUNT(*) FROM {table_or_path}"
    
    return con.execute(query).fetchone()[0]


def load_parquet(
    con: duckdb.DuckDBPyConnection,
    path: str,
    limit: Optional[int] = None
) -> pd.DataFrame:
    """
    Load parquet file via DuckDB.
    
    Args:
        con: DuckDB connection.
        path: Path to parquet file.
        limit: Max rows to return (None for all).
        
    Returns:
        DataFrame.
    """
    limit_clause = f" LIMIT {limit}" if limit else ""
    query = f"SELECT * FROM '{path}'{limit_clause}"
    return con.execute(query).df()


def load_csv(
    con: duckdb.DuckDBPyConnection,
    path: str,
    limit: Optional[int] = None
) -> pd.DataFrame:
    """
    Load CSV file via DuckDB.
    
    Args:
        con: DuckDB connection.
        path: Path to CSV file.
        limit: Max rows to return (None for all).
        
    Returns:
        DataFrame.
    """
    limit_clause = f" LIMIT {limit}" if limit else ""
    query = f"SELECT * FROM read_csv_auto('{path}'){limit_clause}"
    return con.execute(query).df()


def describe_table(
    con: duckdb.DuckDBPyConnection,
    table_or_path: str
) -> List[Tuple]:
    """
    Get schema/column info for a table.
    
    Args:
        con: DuckDB connection.
        table_or_path: Table name or file path.
        
    Returns:
        List of column tuples (name, type, ...).
    """
    if table_or_path.endswith('.parquet'):
        query = f"DESCRIBE SELECT * FROM read_parquet('{table_or_path}')"
    else:
        query = f"DESCRIBE {table_or_path}"
    
    return con.execute(query).fetchall()


def binned_query(
    con: duckdb.DuckDBPyConnection,
    query_template: str,
    bin_column: str,
    bin_values: List[Tuple[Any, Any, str]],
    fetch_all: bool = True
) -> pd.DataFrame:
    """
    Execute a query across multiple bins (useful for stratified analysis).
    
    Args:
        con: DuckDB connection.
        query_template: SQL template with {min_val}, {max_val}, {label} placeholders.
        bin_column: Column to bin on.
        bin_values: List of (min, max, label) tuples.
        fetch_all: If False, returns iterator.
        
    Returns:
        DataFrame combining results from all bins.
    """
    results = []
    
    for min_val, max_val, label in bin_values:
        query = query_template.format(
            bin_column=bin_column,
            min_val=min_val,
            max_val=max_val,
            label=label
        )
        df = con.execute(query).df()
        results.append(df)
    
    return pd.concat(results, ignore_index=True)


def sample_records(
    con: duckdb.DuckDBPyConnection,
    table_or_path: str,
    n: int = 10,
    seed: int = 42
) -> pd.DataFrame:
    """
    Random sample of n records.
    
    Args:
        con: DuckDB connection.
        table_or_path: Table name or file path.
        n: Number of records to sample.
        seed: Random seed.
        
    Returns:
        DataFrame with sampled records.
    """
    if table_or_path.endswith('.parquet'):
        query = f"SELECT * FROM '{table_or_path}' USING SAMPLE {n} (seed {seed})"
    else:
        query = f"SELECT * FROM {table_or_path} USING SAMPLE {n} (seed {seed})"
    
    return con.execute(query).df()
