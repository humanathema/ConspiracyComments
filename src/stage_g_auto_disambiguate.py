"""Generalizes the Bill/Hunter/Kennedy/Clinton/Sanders approach (Stage B/C)
from 7 hand-picked clusters to as many of the 2,800 ambiguous-bare-name
entities (found via Stage F's bottom-up category clustering) as have
discoverable candidates -- automatically, not by manually reading examples
for each one.

Key difference from Stage B/C: candidate discovery is now fully automated
by mining our OWN already-collected corpus entity list
(corpus_entity_frequency_final.csv, 526,202 entities from the original NER
mining pass) for any "<word> <Surname>" pattern matching the bare name,
rather than needing a human to notice "Bill Gates/Bill Clinton/Bill
Kristol" by reading examples. This turned out more robust than trying to
scrape Wikipedia's disambiguation/surname-page structure, which is
inconsistent across names (some list people directly, some redirect to a
separate "List of people with surname X" page, some are pure etymology
pages with no people list at all -- confirmed on Harris/Jones/Barr before
abandoning that approach).

Same word-bag + signature-word + per-instance classification machinery as
Stage B/C, generalized to loop over however many clusters got discovered
this way instead of a hardcoded dict.

Output:
    data/processed/stage_g_word_bags.json
    data/processed/stage_g_classified.csv (per-instance)
    data/processed/stage_g_signature_words.json
"""
import json
import re
import time
from collections import Counter, defaultdict

import ahocorasick
import pandas as pd
import pyarrow.parquet as pq

REVIEW_PATH = "data/processed/entity_final_review.csv"
FULL_ENTITY_LIST_PATH = "data/processed/corpus_entity_frequency_final.csv"
CORPUS_PATH = "data/processed/empath_scores_full.parquet"

WORDBAGS_OUT = "data/processed/stage_g_word_bags.json"
CLASSIFIED_OUT = "data/processed/stage_g_classified.csv"
SIGNATURE_OUT = "data/processed/stage_g_signature_words.json"

BARE_NAME_MIN_DOC_COUNT = 100     # which ambiguous bare names to even try
CANDIDATE_MIN_DOC_COUNT = 10      # candidate full-name must clear this to count
MAX_CANDIDATES_PER_CLUSTER = 6    # cap -- keep clusters interpretable
WINDOW_WORDS = 15
MAX_SAMPLES_PER_CANDIDATE = 1000
STOPWORDS = set("""the a an and or but if of to in on at for with by from as is
are was were be been being this that these those it its he she they them his
her their i you we me my your our not no so do does did have has had will
would can could should just very really like about""".split())


def discover_clusters(bare_names_df, full_entity_df):
    """For each bare name, find candidate full-name variants already
    present in our own corpus-mined entity list ("<word> <BareName>"
    pattern), above CANDIDATE_MIN_DOC_COUNT, capped at
    MAX_CANDIDATES_PER_CLUSTER."""
    full_entity_df = full_entity_df.dropna(subset=["entity"])
    clusters = {}
    for _, row in bare_names_df.iterrows():
        bare = str(row["entity"])
        pattern = re.compile(rf"^\w+\s+{re.escape(bare)}$", re.IGNORECASE)
        matches = full_entity_df[full_entity_df["entity"].astype(str).str.match(pattern)]
        matches = matches[matches["doc_count"] >= CANDIDATE_MIN_DOC_COUNT]
        matches = matches.sort_values("doc_count", ascending=False).head(MAX_CANDIDATES_PER_CLUSTER)
        if len(matches) >= 2:
            clusters[bare] = matches["entity"].tolist()
    return clusters


def extract_word_bag(text, match_start, match_end, exclude_words):
    before = text[:match_start].split()[-WINDOW_WORDS:]
    after = text[match_end:].split()[:WINDOW_WORDS]
    words = [w.strip(".,!?;:\"'()[]").lower() for w in before + after]
    return [w for w in words
            if w and w not in STOPWORDS and w not in exclude_words and len(w) > 2
            and "http" not in w and not w.replace(":", "").replace("-", "").isdigit()]


def build_automaton(patterns_with_meta):
    """patterns_with_meta: list of (pattern_str, meta) tuples."""
    A = ahocorasick.Automaton()
    for idx, (pat, meta) in enumerate(patterns_with_meta):
        A.add_word(pat.lower(), (idx, pat, meta))
    A.make_automaton()
    return A


def main():
    review = pd.read_csv(REVIEW_PATH, on_bad_lines="skip", engine="python")
    bare_names = review[
        (review["bucket_confidence"] == "ambiguous_bare_name_low_priority")
        & (review["doc_count"] >= BARE_NAME_MIN_DOC_COUNT)
    ]
    print(f"{len(bare_names)} bare names above doc_count>={BARE_NAME_MIN_DOC_COUNT} to try")

    full_entities = pd.read_csv(FULL_ENTITY_LIST_PATH, on_bad_lines="skip", engine="python")
    clusters = discover_clusters(bare_names, full_entities)
    print(f"{len(clusters)}/{len(bare_names)} got 2+ auto-discovered candidates "
          f"(the rest had 0-1 -- likely non-person acronyms/terms like MMR/ICU/ABC, "
          f"correctly left unclustered)")

    total_candidate_strings = sum(len(v) for v in clusters.values())
    print(f"{total_candidate_strings} total candidate full-name strings across all clusters")

    # build one combined pattern set: (pattern_string, (cluster_key, kind, candidate_name_or_None))
    patterns = []
    for bare, candidates in clusters.items():
        patterns.append((bare, (bare, "bare", None)))
        for cand in candidates:
            patterns.append((cand, (bare, "labeled", cand)))
    # longest-match-first handled by pyahocorasick automatically via automaton structure
    automaton = build_automaton(patterns)

    word_bags = {bare: {"__bare__": [], **{c: [] for c in cands}} for bare, cands in clusters.items()}
    sample_counts = defaultdict(int)
    # precompute once, not per-match -- avoids re-scanning all patterns on
    # every single hit across 21.4M rows
    cluster_exclude_words = {
        bare: {bare.lower()} | {c.lower() for c in cands}
        for bare, cands in clusters.items()
    }

    pf = pq.ParquetFile(CORPUS_PATH)
    total = 0
    start = time.time()
    for i, batch in enumerate(pf.iter_batches(batch_size=1_000_000, columns=["text"])):
        chunk = batch.to_pandas()
        total += len(chunk)
        for text in chunk["text"].fillna(""):
            text_l = text.lower()
            found_here = defaultdict(list)  # cluster_key -> list of (kind, candidate, start, end)
            for end_idx, (idx, pat, meta) in automaton.iter(text_l):
                cluster_key, kind, cand = meta
                start_idx = end_idx - len(pat) + 1
                found_here[cluster_key].append((kind, cand, start_idx, end_idx))
            for cluster_key, hits in found_here.items():
                has_labeled = any(h[0] == "labeled" for h in hits)
                for kind, cand, s, e in hits:
                    if kind == "bare" and has_labeled:
                        continue  # a full name is present too, don't double count as bare
                    key = cand if kind == "labeled" else "__bare__"
                    sample_key = (cluster_key, key)
                    if sample_counts[sample_key] >= MAX_SAMPLES_PER_CANDIDATE:
                        continue
                    bag = extract_word_bag(text_l, s, e + 1, cluster_exclude_words[cluster_key])
                    if not bag:
                        continue
                    sample_counts[sample_key] += 1
                    if kind == "labeled":
                        word_bags[cluster_key][cand].append(bag)
                    else:
                        word_bags[cluster_key]["__bare__"].append(bag)
        print(f"  chunk {i+1}: {total:,} rows scanned ({(time.time()-start)/60:.1f} min elapsed)", flush=True)

    with open(WORDBAGS_OUT, "w") as f:
        json.dump(word_bags, f)
    print(f"\nSaved word bags for {len(word_bags)} clusters to {WORDBAGS_OUT}")


if __name__ == "__main__":
    main()
