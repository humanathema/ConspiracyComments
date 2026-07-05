"""
Conspiracy Comments Analysis Utilities
Shared modules for path management, data loading, and common operations.
"""

# Always available
from .file_paths import Paths, get_paths
from .data_loaders import load_cached_json, save_cache, load_parquet_sample, load_jsonl, ensure_parquet_exists
from .visualization import setup_display_styles, show_dataframe, format_number, print_section_header, print_stats_table

# Lazy imports (optional - only loaded when specifically imported)
def __getattr__(name):
    """Lazy load modules with external dependencies."""
    if name in ('query_to_df', 'load_parquet', 'count_records', 'describe_table', 'sample_records'):
        from . import duckdb_helpers
        return getattr(duckdb_helpers, name)
    
    if name in ('parse_fact_appeal_annotation', 'parse_fact_appeal_csv',
                'train_ngram_classifier', 'evaluate_classifier',
                'split_into_sentences', 'annotate_text_sentences', 'batch_annotate_texts'):
        from . import ml_helpers
        return getattr(ml_helpers, name)
    
    raise AttributeError(f"module {__name__} has no attribute {name}")

__all__ = [
    # Always available
    'Paths', 'get_paths',
    'load_cached_json', 'save_cache', 'load_parquet_sample', 'load_jsonl', 'ensure_parquet_exists',
    'setup_display_styles', 'show_dataframe', 'format_number', 'print_section_header', 'print_stats_table',
    # Lazy loaded (DuckDB)
    'query_to_df', 'load_parquet', 'count_records', 'describe_table', 'sample_records',
    # Lazy loaded (ML)
    'parse_fact_appeal_annotation', 'parse_fact_appeal_csv',
    'train_ngram_classifier', 'evaluate_classifier',
    'split_into_sentences', 'annotate_text_sentences', 'batch_annotate_texts',
]
