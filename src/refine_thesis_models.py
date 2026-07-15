"""refine_thesis_models.py

Refines our thesis epistemic credibility analysis by:
1. Splitting mainstream experts into 'canonical_expert' (historical canons) and 'consensus_expert' (contemporary consensus figures).
2. Using r/TopMindsOfReddit (12 years of comments, N = 323,674) as a robust, non-temporally-biased baseline control.
3. Scoring a representative sample of r/TopMindsOfReddit using our Gen-2 classifiers.
4. Running side-by-side regressions and refined semantic keyness to prove the "Inherited Canon" effect and the "Contemporary Resistance" effect.
"""

import os
import re
import time
import math
import numpy as np
import pandas as pd
import joblib
import duckdb
import statsmodels.formula.api as smf
from collections import Counter

# Paths
MODELS_PATH = 'data/processed/staged_pipeline_models.joblib'
ENTITY_PATH = 'data/processed/entity_final_review.csv'
TOPMINDS_PATH = 'data/processed/comparison_topmindsofreddit_scored.parquet'
STAGED_PATH = 'data/processed/research_corpus_staged_scores_full21m.parquet'
EMPATH_PATH = 'data/processed/empath_scores_full.parquet'
THREAD_PATH = 'data/processed/thread_quality_metrics.csv'
PRESENCE_PATH = 'data/processed/thread_insider_presence.csv'
BRIGADE_PATH = 'data/processed/comment_brigade_flags.csv'

# Output Paths
TOPMINDS_SCORED_PATH = 'data/processed/comparison_topminds_staged_scored.parquet'
REFINED_REG_RESULTS_PATH = 'data/processed/refined_regression_results.csv'
REFINED_KEYNESS_PATH = 'data/processed/refined_semantic_keyness_results.csv'

# Lists for splitting experts
CANONICAL_EXPERTS = [
    'Plato', 'Aristotle', 'Albert Einstein', 'Einstein', 'Isaac Newton', 'Newton',
    'Charles Darwin', 'Darwin', 'Alan Turing', 'Turing', 'Nikola Tesla', 'Tesla', 'Galileo',
    'Socrates', 'Feynman', 'Richard Feynman', 'Max Planck', 'Planck', 'Leibniz', 'Kant',
    'Hegel', 'Foucault', 'Adam Smith', 'Keynes', 'Hayek', 'Asimov', 'Isaac Asimov', 'Carl Jung', 'Jung',
    'Edison', 'Thomas Edison', 'Da Vinci', 'DaVinci', 'Leonardo da Vinci', 'Louis Pasteur', 'Pasteur',
    'Edward Jenner', 'Jenner', 'Robert Koch', 'Koch', 'Schrodinger', 'Euler', 'Tolkien', 'Salk', 'Von Braun',
    'Stallman', 'Timothy Leary', 'Huxley', 'Orwell', 'Nietzsche'
]

FICTIONAL_OR_LEAKED = [
    'Batman', 'Joker', 'Superman', 'Salma', 'Salma Hayek', 'Tarantino', 'Quentin Tarantino',
    'Dark Knight', 'Wonder Woman', 'Spiderman', 'Gotham', 'Wayne', 'Bruce Wayne', 'Spirit Cooking', 'SpiritCooking', 'Strangelove', 'Abramovic', 'Marina Abramovic'
]

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

PRONOUNS = re.compile(r"\b(i|me|my|myself|we|our|us)\b", re.IGNORECASE)
LIFE_ANCHORS = re.compile(
    r"\b(family|career|brother|sister|wife|husband|job|life|school|hospital|mom|dad|mother|father|parents|kid|kids|child|children|grew up|remember|remembered|happened)\b",
    re.IGNORECASE
)
SKEPT_TERMS = re.compile(
    r"\b(evidence|proof|argument|premise|contradict|logical|validity|source|cite|citation|logic|facts|peer|study|studies|data|science|scientific|statistics)\b",
    re.IGNORECASE
)
NEGATIONS = re.compile(
    r"\b(doesn't add up|makes no sense|where is the|flaw|disprove|debunk|falsify|invalid|manipulate|bias|biased|cherry pick|cherry-picked|propaganda)\b",
    re.IGNORECASE
)

def pass_personal_experience_filter(text):
    text_str = str(text)
    return bool(PRONOUNS.search(text_str)) and bool(LIFE_ANCHORS.search(text_str))

def pass_procedural_skepticism_filter(text):
    text_str = str(text)
    return bool(SKEPT_TERMS.search(text_str)) or bool(NEGATIONS.search(text_str))

def load_entities_split():
    df_entity = pd.read_csv(ENTITY_PATH)
    
    mavericks = df_entity[df_entity["final_bucket_guess"] == "maverick_authority"]["entity"].dropna().astype(str).unique().tolist()
    experts = df_entity[df_entity["final_bucket_guess"] == "mainstream_expert_authority"]["entity"].dropna().astype(str).unique().tolist()
    
    mavericks = [m for m in mavericks if len(m) >= 3]
    experts = [e for e in experts if len(e) >= 3]
    
    canon = []
    consensus = []
    
    for e in experts:
        if any(f.lower() in e.lower() for f in FICTIONAL_OR_LEAKED):
            continue
        elif any(c.lower() in e.lower() for c in CANONICAL_EXPERTS):
            canon.append(e)
        else:
            consensus.append(e)
            
    return mavericks, canon, consensus

def build_regex(entities):
    if not entities:
        return re.compile(r"\b(never_match_this_string_xyz)\b", re.IGNORECASE)
    entities_sorted = sorted(entities, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(re.escape(e) for e in entities_sorted) + r")\b", re.IGNORECASE)

def extract_contexts(df, entities, window_size=15):
    contexts = []
    pattern = build_regex(entities)
    
    for idx, row in df.iterrows():
        text = str(row['text'])
        matches = list(pattern.finditer(text))
        if not matches:
            continue
            
        tokens = re.findall(r"\b\w+\b", text.lower())
        
        for match in matches:
            ent_matched = match.group(0).lower()
            ent_tokens = re.findall(r"\b\w+\b", ent_matched)
            
            for i in range(len(tokens) - len(ent_tokens) + 1):
                if tokens[i:i+len(ent_tokens)] == ent_tokens:
                    start = max(0, i - window_size)
                    end = min(len(tokens), i + len(ent_tokens) + window_size)
                    
                    context_words = tokens[start:i] + tokens[i+len(ent_tokens):end]
                    context_filtered = [w for w in context_words if w not in STOP_WORDS and not w.isdigit()]
                    if context_filtered:
                        contexts.append(context_filtered)
                    break
                    
    return contexts

def compute_log_likelihood(c1_words, c2_words):
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
        
        e1 = n1 * (f1 + f2) / (n1 + n2)
        e2 = n2 * (f1 + f2) / (n1 + n2)
        
        ll = 0.0
        if f1 > 0:
            ll += f1 * math.log(f1 / e1)
        if f2 > 0:
            ll += f2 * math.log(f2 / e2)
        ll *= 2.0
        
        sign = 1 if (f1 / n1) > (f2 / n2) else -1
        signed_ll = sign * ll
        
        results.append({
            "word": word,
            "freq_c1": f1,
            "freq_c2": f2,
            "pct_c1": (f1 / n1) * 100,
            "pct_c2": (f2 / n2) * 100,
            "log_likelihood": signed_ll
        })
        
    return pd.DataFrame(results).sort_values(by="log_likelihood", ascending=False)

def main():
    print("=== REFINING THESIS CREDIBILITY ANALYSES ===")
    
    # 1. Load entities and split
    print("Splitting entities...")
    mavericks, canon, consensus = load_entities_split()
    print(f"Splits complete: {len(mavericks)} Mavericks, {len(canon)} Canonical Experts, {len(consensus)} Consensus Experts.")
    
    rx_mav = build_regex(mavericks)
    rx_can = build_regex(canon)
    rx_con = build_regex(consensus)
    
    # 2. Score r/conspiracy pure comments
    con = duckdb.connect()
    print("Loading r/conspiracy pure comments...")
    query = f"""
        SELECT s.id, e.text, e.upvotes, e.char_length, s.pe_prob, s.ps_prob, e.has_link
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
    df_con = con.execute(query).df()
    print(f"Loaded {len(df_con):,} pure r/conspiracy comments.")
    
    print("Flagging entity mentions in r/conspiracy...")
    df_con['has_maverick'] = df_con['text'].apply(lambda x: 1 if bool(rx_mav.search(str(x))) else 0)
    df_con['has_canonical_expert'] = df_con['text'].apply(lambda x: 1 if bool(rx_can.search(str(x))) else 0)
    df_con['has_consensus_expert'] = df_con['text'].apply(lambda x: 1 if bool(rx_con.search(str(x))) else 0)
    df_con['log_char_length'] = np.log(df_con['char_length'] + 1)
    df_con['log_upvotes'] = np.log(df_con['upvotes'] - df_con['upvotes'].min() + 1)
    df_con['high_traction'] = (df_con['upvotes'] >= 5).astype(int)
    
    # 3. Load and Score r/TopMindsOfReddit sample
    print("\nProcessing r/TopMindsOfReddit baseline (12 years of comments)...")
    if os.path.exists(TOPMINDS_SCORED_PATH):
        print(f"Loading pre-scored r/TopMindsOfReddit dataset from {TOPMINDS_SCORED_PATH}...")
        df_tm = pd.read_parquet(TOPMINDS_SCORED_PATH)
    else:
        print(f"Loading raw TopMinds dataset from {TOPMINDS_PATH}...")
        df_tm_raw = pd.read_parquet(TOPMINDS_PATH)
        print(f"Sampling 50,000 representative comments from {len(df_tm_raw):,} total comments...")
        df_tm = df_tm_raw.sample(n=50000, random_state=42).copy()
        
        # Load Gen-2 Models
        print(f"Loading Staged Classifiers from {MODELS_PATH}...")
        models = joblib.load(MODELS_PATH)
        pe_vec = models['personal_experience']['vec']
        pe_clf = models['personal_experience']['clf']
        ps_vec = models['procedural_skepticism']['vec']
        ps_clf = models['procedural_skepticism']['clf']
        
        print("Scoring Personal Experience on TopMinds...")
        df_tm['pe_pass_s1'] = df_tm['text'].apply(pass_personal_experience_filter)
        df_tm['pe_prob'] = 0.0
        passed_pe = df_tm[df_tm['pe_pass_s1']].index
        if len(passed_pe) > 0:
            X_pe = pe_vec.transform(df_tm.loc[passed_pe, 'text'].fillna(''))
            df_tm.loc[passed_pe, 'pe_prob'] = pe_clf.predict_proba(X_pe)[:, 1]
            
        print("Scoring Procedural Skepticism on TopMinds...")
        df_tm['ps_pass_s1'] = df_tm['text'].apply(pass_procedural_skepticism_filter)
        df_tm['ps_prob'] = 0.0
        passed_ps = df_tm[df_tm['ps_pass_s1']].index
        if len(passed_ps) > 0:
            X_ps = ps_vec.transform(df_tm.loc[passed_ps, 'text'].fillna(''))
            df_tm.loc[passed_ps, 'ps_prob'] = ps_clf.predict_proba(X_ps)[:, 1]
            
        df_tm.to_parquet(TOPMINDS_SCORED_PATH, index=False)
        print(f"Saved scored TopMinds sample to {TOPMINDS_SCORED_PATH}")
        
    print("Flagging entity mentions in r/TopMindsOfReddit...")
    df_tm['has_maverick'] = df_tm['text'].apply(lambda x: 1 if bool(rx_mav.search(str(x))) else 0)
    df_tm['has_canonical_expert'] = df_tm['text'].apply(lambda x: 1 if bool(rx_can.search(str(x))) else 0)
    df_tm['has_consensus_expert'] = df_tm['text'].apply(lambda x: 1 if bool(rx_con.search(str(x))) else 0)
    df_tm['log_char_length'] = np.log(df_tm['char_length'] + 1)
    df_tm['log_upvotes'] = np.log(df_tm['upvotes'] - df_tm['upvotes'].min() + 1)
    df_tm['high_traction'] = (df_tm['upvotes'] >= 5).astype(int)
    
    # 4. Run Regressions
    print("\n--- Running Regressions ---")
    results = []
    
    specs = [
        ("r/conspiracy", df_con),
        ("r/TopMindsOfReddit", df_tm)
    ]
    
    formula = "high_traction ~ pe_prob + ps_prob + has_link + has_maverick + has_canonical_expert + has_consensus_expert + log_char_length"
    
    for name, df_sub in specs:
        print(f"\nRunning Logit Model for {name}...")
        try:
            m = smf.logit(formula, data=df_sub).fit(disp=0, maxiter=100)
            print(m.summary().tables[1])
            
            for c in ["pe_prob", "ps_prob", "has_link", "has_maverick", "has_canonical_expert", "has_consensus_expert", "log_char_length"]:
                if c in m.params:
                    results.append({
                        "subreddit": name,
                        "variable": c,
                        "coef": m.params[c],
                        "se": m.bse[c],
                        "pvalue": m.pvalues[c],
                        "n_obs": int(m.nobs)
                    })
        except Exception as e:
            print(f"Model failed for {name}: {e}")
            
    pd.DataFrame(results).to_csv(REFINED_REG_RESULTS_PATH, index=False)
    print(f"\nSaved regression results to {REFINED_REG_RESULTS_PATH}")
    
    # 5. Extract Contexts & Compute Refined Keyness
    print("\n--- Running Refined Semantic Keyness ---")
    
    # Context extraction r/conspiracy
    print("Extracting contexts for r/conspiracy...")
    con_mav_words = [w for ctx in extract_contexts(df_con, mavericks) for w in ctx]
    con_can_words = [w for ctx in extract_contexts(df_con, canon) for w in ctx]
    con_con_words = [w for ctx in extract_contexts(df_con, consensus) for w in ctx]
    
    print(f"con_mav: {len(con_mav_words):,}, con_can: {len(con_can_words):,}, con_con: {len(con_con_words):,}")
    
    # Context extraction r/TopMindsOfReddit
    print("Extracting contexts for r/TopMindsOfReddit...")
    tm_mav_words = [w for ctx in extract_contexts(df_tm, mavericks) for w in ctx]
    tm_can_words = [w for ctx in extract_contexts(df_tm, canon) for w in ctx]
    tm_con_words = [w for ctx in extract_contexts(df_tm, consensus) for w in ctx]
    
    print(f"tm_mav: {len(tm_mav_words):,}, tm_can: {len(tm_can_words):,}, tm_con: {len(tm_con_words):,}")
    
    # G-Test Log-Likelihood Comparisons
    # A. Inherited Canon vs. Contemporary Resistance in r/conspiracy
    print("\nComparing Canonical Experts vs. Consensus Experts in r/conspiracy...")
    df_con_canon_vs_cons = compute_log_likelihood(con_can_words, con_con_words)
    df_con_canon_vs_cons["comparison"] = "canonical_vs_consensus"
    df_con_canon_vs_cons["subreddit"] = "r/conspiracy"
    
    # B. Alternative Mavericks vs. Contemporary Resistance in r/conspiracy
    print("Comparing Mavericks vs. Consensus Experts in r/conspiracy...")
    df_con_mav_vs_cons = compute_log_likelihood(con_mav_words, con_con_words)
    df_con_mav_vs_cons["comparison"] = "maverick_vs_consensus"
    df_con_mav_vs_cons["subreddit"] = "r/conspiracy"
    
    # C. Canonical vs. Consensus in r/TopMindsOfReddit
    print("Comparing Canonical Experts vs. Consensus Experts in r/TopMindsOfReddit...")
    df_tm_canon_vs_cons = compute_log_likelihood(tm_can_words, tm_con_words)
    df_tm_canon_vs_cons["comparison"] = "canonical_vs_consensus"
    df_tm_canon_vs_cons["subreddit"] = "r/TopMindsOfReddit"
    
    # Save Keyness
    df_keyness = pd.concat([df_con_canon_vs_cons, df_con_mav_vs_cons, df_tm_canon_vs_cons])
    df_keyness.to_csv(REFINED_KEYNESS_PATH, index=False)
    print(f"Saved refined keyness metrics to {REFINED_KEYNESS_PATH}")
    
    # Print Beautiful Keyness results
    print("\n" + "="*80)
    print("  REFINED KEYNESS: CANONICAL (Positive LL) vs. CONSENSUS (Negative LL) inside r/conspiracy")
    print("="*80)
    
    if not df_con_canon_vs_cons.empty:
        print("\n--- Overrepresented in CANONICAL contexts (The Inherited Canon) ---")
        df_can_top = df_con_canon_vs_cons[(df_con_canon_vs_cons["log_likelihood"] > 0) & (df_con_canon_vs_cons["freq_c1"] >= 3)].head(15)
        for idx, row in df_can_top.iterrows():
            print(f"  {row['word']:18s} | LL = {row['log_likelihood']:+8.2f} | Canon Freq: {row['freq_c1']:3d} ({row['pct_c1']:.3f}%) vs Consensus: {row['freq_c2']:3d} ({row['pct_c2']:.3f}%)")
            
        print("\n--- Overrepresented in CONTEMPORARY CONSENSUS contexts (The Active Resistance) ---")
        df_cons_top = df_con_canon_vs_cons[(df_con_canon_vs_cons["log_likelihood"] < 0) & (df_con_canon_vs_cons["freq_c2"] >= 3)].sort_values(by="log_likelihood", ascending=True).head(15)
        for idx, row in df_cons_top.iterrows():
            print(f"  {row['word']:18s} | LL = {row['log_likelihood']:+8.2f} | Canon Freq: {row['freq_c1']:3d} ({row['pct_c1']:.3f}%) vs Consensus: {row['freq_c2']:3d} ({row['pct_c2']:.3f}%)")

if __name__ == "__main__":
    main()
