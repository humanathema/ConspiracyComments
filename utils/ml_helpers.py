"""
Machine learning utilities for factappeal and classification tasks.
"""

import re
import pandas as pd
from typing import Tuple, List, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report


def parse_fact_appeal_annotation(
    annotation_text: str,
    target_tag: str = 'Attribution'
) -> Tuple[str, int]:
    """
    Parse FactAppeal XML annotation to extract clean text and label.
    
    Args:
        annotation_text: Raw annotation string with XML tags.
        target_tag: Tag name indicating positive class (e.g., 'Attribution').
        
    Returns:
        (clean_text, label) where label is 1 if target_tag found, 0 otherwise.
    """
    # Remove all XML tags to get clean text
    clean_text = re.sub(r'<.*?>', '', annotation_text).strip()
    
    # Binary classification: 1 if target tag present, 0 otherwise
    label = 1 if target_tag in annotation_text else 0
    
    return clean_text, label


def parse_fact_appeal_csv(
    filepath: str,
    text_column: str = 'annotation',
    target_tag: str = 'Attribution'
) -> pd.DataFrame:
    """
    Parse FactAppeal CSV with annotation column.
    
    Args:
        filepath: Path to CSV file.
        text_column: Name of column containing annotations.
        target_tag: Tag name for positive class.
        
    Returns:
        DataFrame with 'text' and 'label' columns.
    """
    df_raw = pd.read_csv(filepath)
    
    parsed_data = []
    for _, row in df_raw.iterrows():
        annotation = str(row[text_column]).strip()
        clean_text, label = parse_fact_appeal_annotation(annotation, target_tag)
        
        if clean_text:  # Skip empty
            parsed_data.append({'text': clean_text, 'label': label})
    
    return pd.DataFrame(parsed_data)


def train_ngram_classifier(
    X_train: pd.Series,
    y_train: pd.Series,
    ngram_range: Tuple[int, int] = (1, 3),
    max_features: int = 15000,
    random_state: int = 42
) -> Tuple[TfidfVectorizer, LogisticRegression]:
    """
    Train TF-IDF + Logistic Regression classifier.
    
    Args:
        X_train: Training text series.
        y_train: Training labels.
        ngram_range: N-gram range (e.g., (1, 3) for unigrams to trigrams).
        max_features: Max TF-IDF features.
        random_state: Random seed.
        
    Returns:
        (vectorizer, classifier) tuple.
    """
    vectorizer = TfidfVectorizer(
        analyzer='word',
        ngram_range=ngram_range,
        max_features=max_features,
        sublinear_tf=True
    )
    
    X_train_vec = vectorizer.fit_transform(X_train)
    
    classifier = LogisticRegression(
        class_weight='balanced',
        max_iter=1000,
        random_state=random_state
    )
    classifier.fit(X_train_vec, y_train)
    
    return vectorizer, classifier


def evaluate_classifier(
    classifier: LogisticRegression,
    vectorizer: TfidfVectorizer,
    X_test: pd.Series,
    y_test: pd.Series,
    dataset_name: str = "Test"
) -> str:
    """
    Evaluate classifier and return formatted report.
    
    Args:
        classifier: Trained classifier.
        vectorizer: Fitted vectorizer.
        X_test: Test text series.
        y_test: Test labels.
        dataset_name: Name for report header.
        
    Returns:
        Classification report string.
    """
    X_test_vec = vectorizer.transform(X_test)
    y_pred = classifier.predict(X_test_vec)
    
    report = classification_report(y_test, y_pred)
    print(f"\n{'='*60}")
    print(f"  {dataset_name} Set Performance")
    print(f"{'='*60}")
    print(report)
    
    return report


def split_into_sentences(text: str, delimiters: str = '.!?') -> List[str]:
    """
    Split text into sentences.
    
    Args:
        text: Input text.
        delimiters: Sentence-ending punctuation.
        
    Returns:
        List of sentence strings.
    """
    if not text or not isinstance(text, str):
        return []
    
    # Split on punctuation followed by space
    pattern = f"(?<=[{delimiters}])\\s+"
    sentences = re.split(pattern, text)
    
    return [s.strip() for s in sentences if s.strip()]


def annotate_text_sentences(
    text: str,
    classifier: LogisticRegression,
    vectorizer: TfidfVectorizer,
    pos_tag: str = "Fact_With_Attribution",
    neg_tag: str = "Fact_No_Appeal"
) -> Tuple[str, int]:
    """
    Annotate text with per-sentence predictions.
    
    Args:
        text: Input text.
        classifier: Trained classifier.
        vectorizer: Fitted vectorizer.
        pos_tag: XML tag for positive predictions.
        neg_tag: XML tag for negative predictions.
        
    Returns:
        (annotated_text, contains_positive) tuple.
    """
    sentences = split_into_sentences(text)
    
    if not sentences:
        return "", 0
    
    # Vectorize all sentences at once
    X_vec = vectorizer.transform(sentences)
    predictions = classifier.predict(X_vec)
    
    annotated_sentences = []
    contains_positive = 0
    
    for sentence, pred in zip(sentences, predictions):
        if pred == 1:
            annotated_sentences.append(f"<{pos_tag}>{sentence}</{pos_tag}>")
            contains_positive = 1
        else:
            annotated_sentences.append(f"<{neg_tag}>{sentence}</{neg_tag}>")
    
    return " ".join(annotated_sentences), contains_positive


def batch_annotate_texts(
    texts: List[str],
    classifier: LogisticRegression,
    vectorizer: TfidfVectorizer,
    batch_size: int = 1000,
    verbose: bool = True
) -> Tuple[List[str], List[int]]:
    """
    Annotate a batch of texts efficiently.
    
    Args:
        texts: List of texts to annotate.
        classifier: Trained classifier.
        vectorizer: Fitted vectorizer.
        batch_size: Batch size for progress reporting.
        verbose: Print progress.
        
    Returns:
        (annotated_texts, contains_flags) lists.
    """
    annotated = []
    flags = []
    
    for i, text in enumerate(texts):
        ann_text, flag = annotate_text_sentences(text, classifier, vectorizer)
        annotated.append(ann_text)
        flags.append(flag)
        
        if verbose and (i + 1) % batch_size == 0:
            print(f"Processed {i + 1}/{len(texts)} texts")
    
    return annotated, flags
