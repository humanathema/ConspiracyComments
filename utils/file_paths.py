"""
Centralized file path management for conspiracy comments analysis.
All output files referenced in the notebook live under BASE.
"""

from pathlib import Path
from typing import Dict, Optional


class Paths:
    """Centralized path management."""
    
    def __init__(self, base: Optional[str] = None):
        """
        Initialize paths. If base is None, defaults to the repo root
        (two directories up from this file: utils/file_paths.py -> repo root).

        Args:
            base: Base directory path. If None, uses default.
        """
        self.base = Path(base or Path(__file__).resolve().parents[1])
        
    @property
    def raw_comments(self) -> str:
        """Glob pattern for raw comment JSONL.GZ files."""
        return str(self.base / 'r_conspiracy_comments*.jsonl.gz')
    
    @property
    def raw_posts(self) -> str:
        """Glob pattern for raw posts JSONL.GZ files."""
        return str(self.base / 'r_conspiracy_posts*.jsonl.gz')
    
    @property
    def lexical(self) -> str:
        """5-dimension lexical scores (parquet)."""
        return str(self.base / 'lexical_scores_full.parquet')
    
    @property
    def empath(self) -> str:
        """11-dimension extended lexicon (parquet)."""
        return str(self.base / 'empath_scores_full.parquet')
    
    @property
    def spacy(self) -> str:
        """spaCy-attributed comments (parquet)."""
        return str(self.base / 'spacy_attributed_comments.parquet')
    
    @property
    def synthesis(self) -> str:
        """Master thread synthesis data (parquet)."""
        return str(self.base / 'master_thread_synthesis.parquet')
    
    @property
    def labels(self) -> str:
        """Human-labeled active learning set (CSV)."""
        return str(self.base / 'human_labels_active_learning.csv')
    
    @property
    def corpus_metadata(self) -> str:
        """Cached corpus statistics (JSON)."""
        return str(self.base / 'corpus_metadata.json')

    @property
    def short_comments(self) -> str:
        """Complement of `empath` -- comments with char_length<=100 (the
        raw corpus minus the length-filtered 'usable' set), same base
        schema as `empath` minus the 11 lexicon count columns. Built
        2026-07-21 so querying this population doesn't require re-scanning
        the raw gzipped JSONL every time (parquet: <1s vs ~48s)."""
        return str(self.base / 'conspiracy_comments_short_lte100chars.parquet')
    
    @property
    def high_upvote_topics(self) -> str:
        """High-upvote comments with BERTopic assignments (parquet)."""
        return str(self.base / 'high_upvote_with_topics.parquet')
    
    @property
    def domain_performance(self) -> str:
        """Domain epistemic performance metrics (CSV)."""
        return str(self.base / 'domain_epistemic_performance.csv')
    
    @property
    def cross_post_audit(self) -> str:
        """Cross-post audit results (CSV)."""
        return str(self.base / 'cross_post_audit_results.csv')
    
    @property
    def api_audit_sample(self) -> str:
        """API audit sampling results (parquet)."""
        return str(self.base / 'api_audit_sampling_1k.parquet')
    
    @property
    def bertopic_model_path(self) -> str:
        """Path to trained BERTopic model directory."""
        return str(self.base / 'bertopic_model')
    
    def all_paths(self) -> Dict[str, str]:
        """Return dictionary of all available paths."""
        return {
            'raw_comments': self.raw_comments,
            'raw_posts': self.raw_posts,
            'lexical': self.lexical,
            'empath': self.empath,
            'spacy': self.spacy,
            'synthesis': self.synthesis,
            'labels': self.labels,
            'corpus_metadata': self.corpus_metadata,
            'high_upvote_topics': self.high_upvote_topics,
            'domain_performance': self.domain_performance,
            'cross_post_audit': self.cross_post_audit,
            'api_audit_sample': self.api_audit_sample,
            'bertopic_model_path': self.bertopic_model_path,
        }


# Global default instance
_default_paths = None


def get_paths(base: Optional[str] = None) -> Paths:
    """
    Get global paths instance. Creates one if it doesn't exist.
    
    Args:
        base: Override base directory (creates new instance if provided).
        
    Returns:
        Paths instance.
    """
    global _default_paths
    if base:
        return Paths(base)
    if _default_paths is None:
        _default_paths = Paths()
    return _default_paths
