"""run_semantic_keyness.py

Execute a Log-Likelihood Keyness Analysis (Methodology A) comparing the
semantic context windows of maverick authorities vs. mainstream consensus experts
across r/conspiracy (pure population) and r/AskReddit (control).
"""

import os
import re
import math
import numpy as np
import pandas as pd
import duckdb
from collections import Counter

STAGED_PATH = "data/processed/research_corpus_staged_scores_full21m.parquet"
EMPATH_PATH = "data/processed/empath_scores_full.parquet"
THREAD_PATH = "data/processed/thread_quality_metrics.csv"
PRESENCE_PATH = "data/processed/thread_insider_presence.csv"
BRIGADE_PATH = "data/processed/comment_brigade_flags.csv"

ASKREDDIT_PATH = "data/processed/comparison_askreddit_staged_scored.parquet"
ENTITY_PATH = "data/processed/entity_final_review.csv"
OUTPUT_CSV = "data/processed/semantic_keyness_results.csv"

STOP_WORDS = set([
    "the", "a", "an", "and", "or", "but", "if", "because", "as", "until", "while",
    "of", "at", "by", "for", "with", "about", "against", "between", "into", "through",
    "during", "before", "after", "above", "below", "to", "from", "up", "down", "in",
    "out", "on", "off", "over", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "any", "both", "each", "few",
    "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "s", "t", "can", "will", "just", "don", "should", "shouldn",
    "now", "d", "ll", "m", "o", "re", "ve", "y", "was", "were", "be", "been", "being",
    "have", "has", "had", "having", "do", "does", "did", "doing", "i", "me", "my", "myself",
    "we", "our", "ours", "ourselves", "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself", "she", "her", "hers", "herself", "it", "its", "itself",
    "they", "them", "their", "theirs", "themselves", "what", "which", "who", "whom", "this",
    "that", "these", "those", "am", "is", "are", "g", "u", "co", "http", "https", "com",
    "would", "could", "get", "like", "one", "people", "think", "even", "say", "said", "know"
])

def load_entities():
    df_entity = pd.read_csv(ENTITY_PATH)
    
    mavericks = df_entity[df_entity["final_bucket_guess"] == "maverick_authority"]["entity"].dropna().astype(str).unique().tolist()
    experts = df_entity[df_entity["final_bucket_guess"] == "mainstream_expert_authority"]["entity"].dropna().astype(str).unique().tolist()
    
    # Exclude very short strings (< 3 chars) to avoid false positives
    mavericks = [m for m in mavericks if len(m) >= 3]
    experts = [e for e in experts if len(e) >= 3]
    
    return mavericks, experts

def extract_contexts_for_subreddit(df, entities, window_size=15):
    """Extract symmetric word context windows around entity mentions."""
    contexts = []
    
    # Sort entities by length in reverse to match longest names first (e.g. Robert Malone before Malone)
    entities_sorted = sorted(entities, key=len, reverse=True)
    pattern = re.compile(r"\b(" + "|".join(re.escape(e) for e in entities_sorted) + r")\b", re.IGNORECASE)
    
    for idx, row in df.iterrows():
        text = str(row['text'])
        matches = list(pattern.finditer(text))
        if not matches:
            continue
            
        # Standard tokenize
        tokens = re.findall(r"\b\w+\b", text.lower())
        token_set = set(tokens)
        
        # For each match, locate window
        for match in matches:
            ent_matched = match.group(0).lower()
            ent_tokens = re.findall(r"\b\w+\b", ent_matched)
            
            # Find index in tokens list
            # Since multiple occurrences are possible, let's find the first index of matching subsequence
            for i in range(len(tokens) - len(ent_tokens) + 1):
                if tokens[i:i+len(ent_tokens)] == ent_tokens:
                    # Found the start index of the entity
                    start = max(0, i - window_size)
                    end = min(len(tokens), i + len(ent_tokens) + window_size)
                    
                    # Context window excluding the entity tokens themselves
                    context_words = tokens[start:i] + tokens[i+len(ent_tokens):end]
                    # Filter stop words and numbers
                    context_filtered = [w for w in context_words if w not in STOP_WORDS and not w.isdigit()]
                    if context_filtered:
                        contexts.append(context_filtered)
                    break
                    
    return contexts

def compute_log_likelihood(c1_words, c2_words):
    """Compute Log-Likelihood (G-test) keyness between two corpora."""
    freq1 = Counter(c1_words)
    freq2 = Counter(c2_words)
    
    all_vocab = set(freq1.keys()) | set(freq2.keys())
    
    n1 = sum(freq1.values())
    n2 = sum(freq2.values())
    
    if n1 == 0 or n2 == 0:
        return pd.DataFrame()
        
    results = []
    for word in all_vocab:
        f1 = freq1[word]
        f2 = freq2[word]
        
        # Expected frequencies
        e1 = n1 * (f1 + f2) / (n1 + n2)
        e2 = n2 * (f1 + f2) / (n1 + n2)
        
        # G-test formula
        ll = 0.0
        if f1 > 0:
            ll += f1 * math.log(f1 / e1)
        if f2 > 0:
            ll += f2 * math.log(f2 / e2)
        ll *= 2.0
        
        # Determine sign (positive if overrepresented in c1, negative if in c2)
        sign = 1 if (f1 / n1) > (f2 / n2) else -1
        signed_ll = sign * ll
        
        results.append({
            "word": word,
            "freq_maverick": f1,
            "freq_expert": f2,
            "pct_maverick": (f1 / n1) * 100,
            "pct_expert": (f2 / n2) * 100,
            "log_likelihood": signed_ll
        })
        
    return pd.DataFrame(results).sort_values(by="log_likelihood", ascending=False)

def main():
    print("=== RUNNING SEMANTIC KEYNESS & FRAMING ANALYSIS ===")
    
    # 1. Load entities
    print("Loading maverick and mainstream expert entities...")
    mavericks, experts = load_entities()
    print(f"Loaded {len(mavericks)} maverick and {len(experts)} mainstream expert entities.")
    
    # 2. Extract r/conspiracy pure comments
    con = duckdb.connect()
    print("Loading r/conspiracy pure-population comments...")
    query_parents = f"""
        SELECT s.id, e.text
        FROM '{STAGED_PATH}' s
        JOIN '{EMPATH_PATH}' e ON s.id = e.id
        JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
        LEFT JOIN '{PRESENCE_PATH}' p ON SUBSTR(e.link_id, 4) = p.post_id
        LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
        WHERE t.elasticity_ratio <= (SELECT quantile(elasticity_ratio, 0.33) FROM '{THREAD_PATH}')
          AND t.is_high_crosspost = 0
          AND p.insider_presence_ratio >= 0.75
          AND COALESCE(b.brigade_upvote_flag, 0) = 0
          AND COALESCE(b.brigade_downvote_flag, 0) = 0
    """
    df_con = con.execute(query_parents).df()
    print(f"Loaded {len(df_con):,} pure r/conspiracy comments.")
    
    # 3. Load AskReddit control comments
    print("Loading r/AskReddit control comments...")
    df_ar = pd.read_parquet(ASKREDDIT_PATH)
    print(f"Loaded {len(df_ar):,} r/AskReddit comments.")
    
    # 4. Extract context windows for r/conspiracy
    print("Extracting context windows for r/conspiracy...")
    con_mav_contexts = extract_contexts_for_subreddit(df_con, mavericks)
    con_exp_contexts = extract_contexts_for_subreddit(df_con, experts)
    
    con_mav_words = [w for ctx in con_mav_contexts for w in ctx]
    con_exp_words = [w for ctx in con_exp_contexts for w in ctx]
    print(f"r/conspiracy: extracted {len(con_mav_words):,} words for Mavericks, {len(con_exp_words):,} words for Experts.")
    
    # 5. Extract context windows for r/AskReddit
    print("Extracting context windows for r/AskReddit...")
    ar_mav_contexts = extract_contexts_for_subreddit(df_ar, mavericks)
    ar_exp_contexts = extract_contexts_for_subreddit(df_ar, experts)
    
    ar_mav_words = [w for ctx in ar_mav_contexts for w in ctx]
    ar_exp_words = [w for ctx in ar_exp_contexts for w in ctx]
    print(f"r/AskReddit: extracted {len(ar_mav_words):,} words for Mavericks, {len(ar_exp_words):,} words for Experts.")
    
    # 6. Compute keyness for r/conspiracy
    print("\nComputing log-likelihood keyness for r/conspiracy...")
    df_con_ll = compute_log_likelihood(con_mav_words, con_exp_words)
    
    # 7. Compute keyness for r/AskReddit
    print("Computing log-likelihood keyness for r/AskReddit...")
    df_ar_ll = compute_log_likelihood(ar_mav_words, ar_exp_words)
    
    # Save both to CSV
    if not df_con_ll.empty:
        df_con_ll["subreddit"] = "r/conspiracy"
    if not df_ar_ll.empty:
        df_ar_ll["subreddit"] = "r/AskReddit"
        
    df_combined = pd.concat([df_con_ll, df_ar_ll])
    df_combined.to_csv(OUTPUT_CSV, index=False)
    print(f"Saved complete keyness metrics to {OUTPUT_CSV}")
    
    # 8. Present the findings beautifully
    print("\n" + "="*80)
    print("  TOP SEMANTIC FRAMING MARKERS: r/conspiracy")
    print("="*80)
    
    if not df_con_ll.empty:
        print("\n--- Overrepresented in MAVERICK contexts (Positive Keyness) ---")
        # Filter terms with count >= 3 to avoid extreme outliers
        df_con_mav_top = df_con_ll[(df_con_ll["log_likelihood"] > 0) & (df_con_ll["freq_maverick"] >= 3)].head(15)
        for idx, row in df_con_mav_top.iterrows():
            print(f"  {row['word']:18s} | LL = {row['log_likelihood']:+8.2f} | Mav Freq: {row['freq_maverick']:3d} ({row['pct_maverick']:.3f}%) vs Expert: {row['freq_expert']:3d} ({row['pct_expert']:.3f}%)")
            
        print("\n--- Overrepresented in MAINSTREAM EXPERT contexts (Negative Keyness) ---")
        df_con_exp_top = df_con_ll[(df_con_ll["log_likelihood"] < 0) & (df_con_ll["freq_expert"] >= 3)].sort_values(by="log_likelihood", ascending=True).head(15)
        for idx, row in df_con_exp_top.iterrows():
            print(f"  {row['word']:18s} | LL = {row['log_likelihood']:+8.2f} | Mav Freq: {row['freq_maverick']:3d} ({row['pct_maverick']:.3f}%) vs Expert: {row['freq_expert']:3d} ({row['pct_expert']:.3f}%)")
            
    print("\n" + "="*80)
    print("  TOP SEMANTIC FRAMING MARKERS: r/AskReddit")
    print("="*80)
    
    if not df_ar_ll.empty:
        print("\n--- Overrepresented in MAVERICK contexts (Positive Keyness) ---")
        df_ar_mav_top = df_ar_ll[(df_ar_ll["log_likelihood"] > 0) & (df_ar_ll["freq_maverick"] >= 3)].head(15)
        for idx, row in df_ar_mav_top.iterrows():
            print(f"  {row['word']:18s} | LL = {row['log_likelihood']:+8.2f} | Mav Freq: {row['freq_maverick']:3d} ({row['pct_maverick']:.3f}%) vs Expert: {row['freq_expert']:3d} ({row['pct_expert']:.3f}%)")
            
        print("\n--- Overrepresented in MAINSTREAM EXPERT contexts (Negative Keyness) ---")
        df_ar_exp_top = df_ar_ll[(df_ar_ll["log_likelihood"] < 0) & (df_ar_ll["freq_expert"] >= 3)].sort_values(by="log_likelihood", ascending=True).head(15)
        for idx, row in df_ar_exp_top.iterrows():
            print(f"  {row['word']:18s} | LL = {row['log_likelihood']:+8.2f} | Mav Freq: {row['freq_maverick']:3d} ({row['pct_maverick']:.3f}%) vs Expert: {row['freq_expert']:3d} ({row['pct_expert']:.3f}%)")

if __name__ == "__main__":
    main()
