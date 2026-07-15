"""Fix for the corpus-context-pull gap: the original NER-mining pass stored
doc.text[:200] (first 200 chars of the whole comment) as each entity's
"example", not a window around the actual mention -- so ~73% of examples
never even contained the entity name. This re-scans the full corpus with
Aho-Corasick (single pass, same approach as build_maverick_candidate_list.py)
and captures a proper context window centered on the real match position.

Output: data/processed/entity_context_windows.csv
    entity, doc_count, examples (up to 3, "..." + ~200 chars centered on match + "...")
"""
import time
from collections import defaultdict

import ahocorasick
import pandas as pd
import pyarrow.parquet as pq

CORPUS_PATH = "data/processed/empath_scores_full.parquet"
UNBUCKETED_PATH = "data/processed/entity_unbucketed_with_context.csv"
OUT_PATH = "data/processed/entity_context_windows.csv"

WINDOW = 100  # chars each side of the match
MAX_EXAMPLES = 3


def build_automaton(names):
    A = ahocorasick.Automaton()
    for idx, name in enumerate(names):
        A.add_word(name.lower(), (idx, name))
    A.make_automaton()
    return A


def main():
    target_df = pd.read_csv(UNBUCKETED_PATH, usecols=["entity", "doc_count"])
    names = target_df["entity"].dropna().unique().tolist()
    print(f"{len(names)} entities to re-scan for context windows")

    automaton = build_automaton(names)
    examples = defaultdict(list)

    pf = pq.ParquetFile(CORPUS_PATH)
    total = 0
    start = time.time()
    for i, batch in enumerate(pf.iter_batches(batch_size=1_000_000, columns=["text"])):
        chunk = batch.to_pandas()
        total += len(chunk)
        for text in chunk["text"].fillna(""):
            text_l = text.lower()
            for end_idx, (idx, name) in automaton.iter(text_l):
                key = name.lower()
                if len(examples[key]) >= MAX_EXAMPLES:
                    continue
                start_idx = end_idx - len(name) + 1
                w_start = max(0, start_idx - WINDOW)
                w_end = min(len(text), end_idx + 1 + WINDOW)
                snippet = text[w_start:w_end].replace("\n", " ").strip()
                prefix = "..." if w_start > 0 else ""
                suffix = "..." if w_end < len(text) else ""
                examples[key].append(f"{prefix}{snippet}{suffix}")
        print(f"  chunk {i+1}: {total:,} rows scanned ({(time.time()-start)/60:.1f} min elapsed)", flush=True)

    target_df["key"] = target_df["entity"].str.lower()
    target_df["examples"] = target_df["key"].map(lambda k: " || ".join(examples.get(k, [])))
    target_df = target_df.drop(columns=["key"])

    found = (target_df["examples"] != "").sum()
    print(f"\nFound at least one properly-centered example for {found}/{len(target_df)} entities")

    target_df.to_csv(OUT_PATH, index=False)
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
