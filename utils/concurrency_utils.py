import os
import sys
import tempfile
import json
import pandas as pd

def atomic_write(file_path, write_func):
    """
    Writes data to a file atomically.
    write_func is a callable that takes a filepath (string) and performs the write.
    """
    # Ensure the parent directory exists
    dir_name = os.path.dirname(os.path.abspath(file_path))
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
        
    # Use a temporary file in the same directory to guarantee atomic replace (same filesystem)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_atomic_")
    try:
        os.close(fd)  # close the fd so write_func can safely open and write to it
        write_func(tmp_path)
        # Flush to disk (most frameworks do this automatically when closing, but os.replace finishes it)
        os.replace(tmp_path, file_path)
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        raise e

def atomic_write_dataframe(df, file_path, index=False, **kwargs):
    """
    Writes a pandas DataFrame to CSV or Parquet atomically.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.parquet':
        atomic_write(file_path, lambda tmp: df.to_parquet(tmp, index=index, **kwargs))
    else:
        atomic_write(file_path, lambda tmp: df.to_csv(tmp, index=index, **kwargs))

def atomic_write_json(data, file_path, indent=2, **kwargs):
    """
    Writes data to a JSON file atomically.
    """
    def write_json(tmp):
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, **kwargs)
    atomic_write(file_path, write_json)

def atomic_write_text(content, file_path, encoding='utf-8', **kwargs):
    """
    Writes text to a file atomically.
    """
    def write_text(tmp):
        with open(tmp, 'w', encoding=encoding, **kwargs) as f:
            f.write(content)
    atomic_write(file_path, write_text)
