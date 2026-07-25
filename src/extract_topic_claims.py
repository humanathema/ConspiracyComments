"""
extract_topic_claims.py

Extracts topic-level signature words and multi-word phrases (up to trigrams) using 
a deterministic relative document-frequency ratio-test. Contrasts each topic's 
confidently-assigned comments against:
1. Local Background (all other topics pooled)
2. Global Background (a random sample of the full corpus)

No LLMs, local and extremely fast. Follows strict project concurrency/atomic-write rules.
"""
import os
import sys
import re
from collections import Counter
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from utils.concurrency_utils import atomic_write_dataframe

MIN_PHRASE_COUNT = 4       # Minimum occurrences of the phrase in the target topic
MIN_SIGNATURE_RATIO = 0.70 # Minimum ratio to be considered a strong signature word/phrase
TOP_N_CLAIMS = 15          # Output top 15 phrases per topic

# Curated stop words to filter out noisy meta-discussion and high-frequency generic words
BASE_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "if", "because", "as", "until", "while", "of", "at", 
    "by", "for", "with", "about", "against", "between", "into", "through", "during", "before", 
    "after", "above", "below", "to", "from", "up", "down", "in", "out", "on", "off", "over", 
    "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how", 
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor", 
    "not", "only", "own", "same", "so", "than", "too", "very", "s", "t", "can", "will", "just", 
    "don", "should", "now", "d", "ll", "m", "o", "re", "ve", "y", "ain", "aren", "couldn", "didn", 
    "doesn", "hadn", "hasn", "haven", "isn", "ma", "mightn", "mustn", "needn", "shan", "shouldn", 
    "wasn", "weren", "won", "wouldn", "people", "just", "like", "think", "know", "did", "said", 
    "say", "does", "want", "make", "time", "way", "years", "going", "really", "got", "thing", 
    "things", "good", "bad", "actually", "reddit", "sub", "comments", "comment", "post", "posts", 
    "thread", "threads", "submission", "statement", "http", "https", "com", "www", "youtube", 
    "watch", "video", "videos", "link", "links", "deleted", "removed", "amp", "gt", "lt", 
    "get", "would", "one", "even", "someone", "something", "anyone", "anything", "everyone", 
    "everything", "us", "them", "him", "her", "they", "we", "i", "you", "me", "my", "your", 
    "their", "our", "he", "she", "it", "its", "their", "theirs", "ours", "yours", "who", "whom",
    "this", "that", "these", "those", "am", "is", "are", "was", "were", "be", "been", "being", 
    "have", "has", "had", "having", "do", "does", "did", "doing", "go", "goes", "went", "gone", 
    "look", "looks", "looking", "take", "takes", "taking", "took", "taken", "see", "sees", 
    "saw", "seen", "seeing", "find", "finds", "found", "finding", "give", "gives", "gave", 
    "given", "giving", "tell", "tells", "told", "telling", "back", "come", "comes", "came", 
    "coming", "first", "second", "third", "much", "many", "never", "always", "day", "days", 
    "year", "right", "left", "well", "still", "use", "used", "uses", "using", "also", "new", 
    "old", "different", "same", "point", "sure", "pretty", "part", "work", "world", "little", 
    "great", "another", "call", "called", "calling", "calls"
}

def clean_and_validate_phrase(phrase):
    """
    Validates if a phrase is informative (not starting/ending with a stop word, 
    not composed purely of numbers, short words, or stop words).
    """
    words = phrase.split()
    if not words:
        return None
    # Filter out if any word is pure numeric/symbol or too short
    for w in words:
        if len(w) <= 2 and not w.isalpha():
            return None
        if w.isdigit():
            return None
    # Do not start or end with a stop word
    if words[0] in BASE_STOP_WORDS or words[-1] in BASE_STOP_WORDS:
        return None
    # Ensure there is at least one non-stop word in the phrase
    if all(w in BASE_STOP_WORDS for w in words):
        return None
    return phrase

def load_assignments():
    print("Loading topic assignments sample...")
    df = pd.read_parquet('data/processed/train_topic_assignments.parquet')
    df = df[df['topic_reduced'] != -1].copy()
    
    # Load super topic mapping for clean topic names
    mapping_df = pd.read_csv('data/processed/topic_super_topic_mapping.csv')
    mapping_df = mapping_df[mapping_df['Topic'] != -1].copy()
    topic_names = dict(zip(mapping_df['Topic'], mapping_df['Topic_Name']))
    
    df['topic_name'] = df['topic_reduced'].map(topic_names)
    return df

def main():
    df = load_assignments()
    N_total = len(df)
    print(f"Loaded {N_total} assigned comments across {df['topic_reduced'].nunique()} topics.")

    # We will build document frequencies for unigrams, bigrams, and trigrams.
    # To keep memory footprint low, we run CountVectorizer with binary=True (document frequency).
    print("Fitting CountVectorizer to extract candidate unigrams, bigrams, and trigrams...")
    vectorizer = CountVectorizer(
        ngram_range=(1, 3), 
        binary=True, 
        stop_words='english', 
        min_df=3
    )
    
    texts = df['text'].fillna("").tolist()
    X = vectorizer.fit_transform(texts)
    feature_names = vectorizer.get_feature_names_out()
    
    # Pre-build a fast mapping of column index to cleaned and validated phrase
    print("Cleaning and validating feature phrases...")
    id_to_phrase = {}
    for idx, f in enumerate(feature_names):
        phrase = clean_and_validate_phrase(f)
        if phrase:
            id_to_phrase[idx] = phrase
            
    # Group X by topic
    topic_groups = df.groupby('topic_reduced')
    
    # Build global document counts for each feature
    # sum along axis 0 to get total document frequency per phrase
    global_df = np.array(X.sum(axis=0)).flatten()
    
    claims_rows = []
    
    print("\nExtracting signature claim phrases per topic...")
    for topic, group in topic_groups:
        topic_idx_list = group.index
        n_topic = len(group)
        if n_topic < 10:
            continue
            
        # Get slice of X for this topic's documents
        # group.index maps to the row index in df, which matches X rows
        idx_in_df = df.index.get_indexer(topic_idx_list)
        X_topic = X[idx_in_df]
        
        # Doc frequency of each phrase within this topic
        topic_df = np.array(X_topic.sum(axis=0)).flatten()
        
        # Background document counts (global count minus topic count)
        bg_df = global_df - topic_df
        n_bg = N_total - n_topic
        
        topic_name = group['topic_name'].iloc[0] if 'topic_name' in group.columns else f"Topic {topic}"
        
        # Calculate scores for each validated phrase
        candidates = []
        for feat_idx, phrase in id_to_phrase.items():
            count_topic = topic_df[feat_idx]
            if count_topic < MIN_PHRASE_COUNT:
                continue
                
            count_bg = bg_df[feat_idx]
            
            # 1. Global Contrast: topic vs full sample
            # Relative frequencies with Laplace-like smoothing (alpha=0.1)
            freq_topic = (count_topic + 0.1) / (n_topic + 0.2)
            freq_global = (global_df[feat_idx] + 0.1) / (N_total + 0.2)
            global_ratio = freq_topic / (freq_topic + freq_global)
            
            # 2. Local Contrast: topic vs all other topics combined (local background)
            freq_bg = (count_bg + 0.1) / (n_bg + 0.2)
            local_ratio = freq_topic / (freq_topic + freq_bg)
            
            # Combined distinctive score (average of both ratios)
            distinctiveness = (global_ratio + local_ratio) / 2.0
            
            if distinctiveness >= MIN_SIGNATURE_RATIO:
                candidates.append((phrase, count_topic, global_ratio, local_ratio, distinctiveness))
                
        # Sort candidates: highest distinctiveness first, then count
        candidates.sort(key=lambda x: (-x[4], -x[1]))
        
        # Take top-N claims
        top_candidates = candidates[:TOP_N_CLAIMS]
        
        # Format phrases for summary representation
        phrases_str = "; ".join([f"{p} ({c_top})" for p, c_top, _, _, _ in top_candidates])
        
        claims_rows.append({
            'topic_id': topic,
            'topic_name': topic_name,
            'n_comments': n_topic,
            'top_signature_claims': phrases_str,
            # detailed info for top 3 phrases
            'top_claim_1': top_candidates[0][0] if len(top_candidates) > 0 else "",
            'top_claim_1_local_ratio': round(top_candidates[0][3], 4) if len(top_candidates) > 0 else None,
            'top_claim_2': top_candidates[1][0] if len(top_candidates) > 1 else "",
            'top_claim_2_local_ratio': round(top_candidates[1][3], 4) if len(top_candidates) > 1 else None,
            'top_claim_3': top_candidates[2][0] if len(top_candidates) > 2 else "",
            'top_claim_3_local_ratio': round(top_candidates[2][3], 4) if len(top_candidates) > 2 else None,
        })
        
        # Print sample results for some topics to eyeball
        if len(top_candidates) > 0:
            print(f"Topic {topic} ({topic_name}) n={n_topic}:")
            for phrase, c_top, g_ratio, l_ratio, score in top_candidates[:5]:
                print(f"  - '{phrase}': count={c_top}, local_ratio={l_ratio:.4f}, global_ratio={g_ratio:.4f}, score={score:.4f}")
            print()
            
    claims_df = pd.DataFrame(claims_rows).sort_values('topic_id')
    output_path = 'data/processed/topic_central_claims.csv'
    atomic_write_dataframe(claims_df, output_path, index=False)
    print(f"Wrote topic claim signatures for {len(claims_df)} topics to {output_path}")

if __name__ == '__main__':
    main()
