# src/generate_full_corpus_entity_counts.py
import re
import os
import csv
import time
import pandas as pd
import pyarrow.parquet as pq
from concurrent.futures import ProcessPoolExecutor, as_completed

# Corpus paths
LONG_CORPUS = 'data/processed/empath_scores_full_mapped.parquet'
SHORT_CORPUS = 'data/processed/conspiracy_comments_short_lte100chars_mapped.parquet'
OUT_PATH = 'data/processed/entity_frequency_full_corpus.csv'

# Word boundary regex for tokenization
word_rx = re.compile(r'\b\w+\b')

def tokenize(text):
    return word_rx.findall(str(text).lower())

def build_trie(entities):
    trie = {}
    for ent in entities:
        tokens = tokenize(ent)
        if not tokens:
            continue
        node = trie
        for t in tokens:
            node = node.setdefault(t, {})
        node.setdefault('_end_', []).append(ent)
    return trie

def find_entities_in_text(text, trie):
    tokens = tokenize(text)
    matched = set()
    n_tokens = len(tokens)
    i = 0
    while i < n_tokens:
        node = trie
        j = i
        last_match = None
        match_len = 0
        while j < n_tokens and tokens[j] in node:
            node = node[tokens[j]]
            j += 1
            if '_end_' in node:
                last_match = node['_end_']
                match_len = j - i
        if last_match:
            matched.update(last_match)
            i += match_len
        else:
            i += 1
    return matched

# Worker initializer and processing function
_global_trie = None

def init_worker(trie):
    global _global_trie
    _global_trie = trie

def process_batch(texts):
    global _global_trie
    local_counts = {}
    
    # Track metrics for verification check targets on this batch
    verification_metrics = {
        'trump': 0,
        'netanyahu': 0,
        'hrc': 0,
        'aoc': 0
    }
    
    for text in texts:
        matched = find_entities_in_text(text, _global_trie)
        lower_matched = {m.lower() for m in matched}
        
        # 1. Update individual entity level counts
        for m in matched:
            local_counts[m] = local_counts.get(m, 0) + 1
            
        # 2. Update verification-specific metrics with proper word boundary logic
        has_trump = any(re.search(r'\btrumps?\b', m) for m in lower_matched)
        has_netanyahu = any(re.search(r'\bnetanyahu\b', m) for m in lower_matched)
        has_hrc = any(re.search(r'\bhrc\b', m) for m in lower_matched)
        has_aoc = any(re.search(r'\baoc\b|\boc+asio.cortez\b|\balexandria oc+asio\b', m) for m in lower_matched)
        
        if has_trump:
            verification_metrics['trump'] += 1
        if has_netanyahu:
            verification_metrics['netanyahu'] += 1
        if has_hrc:
            verification_metrics['hrc'] += 1
        if has_aoc:
            verification_metrics['aoc'] += 1
            
    return local_counts, verification_metrics

def load_all_entities():
    # Load from the five requested source files
    e_final = set(pd.read_csv('data/processed/entity_final_review.csv')['entity'].dropna().unique())
    e_missing = set(pd.read_csv('data/processed/missing_entity_candidates.csv')['entity'].dropna().unique())
    e_canonical = set(pd.read_csv('data/processed/canonical_entity_mentions.csv')['entity'].dropna().unique())
    e_maverick_scored = set(pd.read_csv('data/processed/maverick_candidate_entities_scored.csv')['entity'].dropna().unique())
    e_maverick_auth = set(pd.read_csv('data/processed/maverick_authority_entities.csv')['entity'].dropna().unique())
    
    all_entities = e_final | e_missing | e_canonical | e_maverick_scored | e_maverick_auth
    return sorted(list(all_entities))

def count_corpus_mentions(corpus_path, trie, pool, batch_size=100_000):
    counts = {}
    verification_totals = {'trump': 0, 'netanyahu': 0, 'hrc': 0, 'aoc': 0}
    
    pf = pq.ParquetFile(corpus_path)
    total_rows = pf.metadata.num_rows
    print(f"  Streaming {total_rows:,} rows in batches of {batch_size:,}...")
    
    futures = []
    
    start_time = time.time()
    for batch in pf.iter_batches(batch_size=batch_size, columns=['text']):
        texts = batch.to_pandas()['text'].tolist()
        futures.append(pool.submit(process_batch, texts))
        
    print(f"  Submitted {len(futures)} tasks to the process pool.")
    
    completed = 0
    for fut in as_completed(futures):
        local_counts, local_verif = fut.result()
        
        # Accumulate individual entity counts
        for ent, c in local_counts.items():
            counts[ent] = counts.get(ent, 0) + c
            
        # Accumulate verification counts
        for k, v in local_verif.items():
            verification_totals[k] += v
            
        completed += 1
        if completed % 10 == 0 or completed == len(futures):
            elapsed = time.time() - start_time
            rate = (completed * batch_size) / elapsed if elapsed > 0 else 0
            print(f"    Completed {completed}/{len(futures)} batches. Rate: {rate:,.0f} rows/sec. Elapsed: {elapsed/60:.1f} mins.")
            
    return counts, verification_totals

def main():
    print("=== Loading entities ===")
    entities = load_all_entities()
    print(f"Loaded {len(entities):,} unique entities.")
    
    print("\n=== Building Trie ===")
    trie = build_trie(entities)
    print("Trie built successfully.")
    
    # Initialize the process pool with 7 workers (the machine has 7 or 8 cores, n_process=7 in ner)
    n_workers = min(7, os.cpu_count() or 4)
    print(f"\n=== Initializing Process Pool with {n_workers} workers ===")
    
    with ProcessPoolExecutor(max_workers=n_workers, initializer=init_worker, initargs=(trie,)) as pool:
        
        print("\n=== Processing Long Comments Corpus ===")
        long_counts, long_verif = count_corpus_mentions(LONG_CORPUS, trie, pool)
        
        print("\n=== Processing Short Comments Corpus ===")
        short_counts, short_verif = count_corpus_mentions(SHORT_CORPUS, trie, pool)
        
    print("\n=== Compiling Results ===")
    all_seen_entities = set(long_counts.keys()) | set(short_counts.keys()) | set(entities)
    
    rows = []
    for ent in all_seen_entities:
        lc = long_counts.get(ent, 0)
        sc = short_counts.get(ent, 0)
        rows.append({
            'entity': ent,
            'long_count': lc,
            'short_count': sc,
            'combined': lc + sc
        })
        
    df = pd.DataFrame(rows).sort_values(by='combined', ascending=False)
    df.to_csv(OUT_PATH, index=False)
    print(f"Saved complete counts to {OUT_PATH}")
    
    print("\n=== VERIFICATION CHECK ===")
    print("Combined target reference numbers comparison:")
    targets = {
        'trump': {'pattern': '\\btrumps?\\b', 'ref_long': 1262366, 'ref_short': 299905, 'ref_comb': 1562271, 'val_long': long_verif['trump'], 'val_short': short_verif['trump']},
        'aoc': {'pattern': 'AOC, etc.', 'ref_long': 10353, 'ref_short': 3385, 'ref_comb': 13738, 'val_long': long_verif['aoc'], 'val_short': short_verif['aoc']},
        'netanyahu': {'pattern': '\\bNetanyahu\\b', 'ref_long': 14084, 'ref_short': 2490, 'ref_comb': 16574, 'val_long': long_verif['netanyahu'], 'val_short': short_verif['netanyahu']},
        'hrc': {'pattern': '\\bHRC\\b', 'ref_long': 13674, 'ref_short': 1922, 'ref_comb': 15596, 'val_long': long_verif['hrc'], 'val_short': short_verif['hrc']}
    }
    
    passed_all = True
    for name, t in targets.items():
        v_comb = t['val_long'] + t['val_short']
        diff = v_comb - t['ref_comb']
        pct_diff = (diff / t['ref_comb'] * 100) if t['ref_comb'] > 0 else 0
        # Allow up to 0.25% difference for minor variations in string matching (e.g. spelling variations)
        status = "PASSED ✅" if abs(pct_diff) < 0.25 else "FAILED ❌"
        if "FAILED" in status:
            passed_all = False
        print(f"Entity: {name}")
        print(f"  Long Count:  Found {t['val_long']:,} vs Reference {t['ref_long']:,}")
        print(f"  Short Count: Found {t['val_short']:,} vs Reference {t['ref_short']:,}")
        print(f"  Combined:    Found {v_comb:,} vs Reference {t['ref_comb']:,}")
        print(f"  Difference:  {diff:+,} ({pct_diff:+.2f}%) - Status: {status}")
        
    if passed_all:
        print("\n🎉 ALL VERIFICATION CHECK GATES PASSED PERFECTLY!")
    else:
        print("\n⚠️ WARNING: Some verification check gates are outside tolerance limits!")

if __name__ == "__main__":
    main()
