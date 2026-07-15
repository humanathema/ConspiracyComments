"""Bottom-up named-entity frequency mining over the r/conspiracy corpus.

Complements the top-down candidate lists (src/build_maverick_candidate_list.py,
sourced from Wikipedia whistleblower/conspiracy-theorist/etc. lists) with a
data-driven pass: what named entities actually get mentioned most often in
this corpus, independent of any presupposed list? The output is meant to be
manually bucketed (mainstream_source / alternative_source /
mainstream_expert_authority / maverick_authority / villain / hero /
mainstream_figure_not_source / other) -- this script only mines and
frequency-ranks, it does not classify.

Full-corpus spaCy NER (21.4M rows) benchmarks at ~183 docs/sec even with
8-way multiprocessing -- about 32 hours, not viable in one sitting. Instead
this scans two subsets:
  1. All rows where alt_authority_count>0 or evidence_count>0 (existing
     lexicon columns from the earlier scoring pipeline) -- ~1.6M rows.
     Biased toward comments already carrying authority/evidence-appeal
     language, i.e. exactly where source/authority mentions live, but will
     under-catch bare villain/hero namings that don't trip either lexicon.
  2. A random sample (~1M rows, seed=42) of the remaining unflagged rows,
     for broader coverage of mainstream figures, villains, heroes etc. that
     don't carry evidential/authority language.

Output: data/processed/corpus_entity_frequency.csv
    entity, label, doc_count, in_candidate_list, example_1, example_2, bucket
`bucket` is left blank for manual review.
"""
import random
import time
from collections import defaultdict

import pandas as pd
import pyarrow.parquet as pq
import spacy

CORPUS_PATH = "data/processed/empath_scores_full.parquet"
CANDIDATE_PATH = "data/processed/maverick_candidate_entities_scored.csv"
OUT_PATH = "data/processed/corpus_entity_frequency.csv"

KEEP_LABELS = {"PERSON", "ORG", "NORP"}
RANDOM_SAMPLE_TARGET = 1_000_000
RANDOM_SEED = 42
MIN_NAME_LEN = 3
MAX_EXAMPLES_PER_ENTITY = 2

random.seed(RANDOM_SEED)


def collect_texts(corpus_path, chunk_size=1_000_000):
    """Stream the corpus once, returning (flagged_texts, sampled_texts).

    Sampling fraction for the random arm is estimated on the fly from the
    running count of unflagged rows seen so far, so it doesn't require a
    pre-pass to know the total.
    """
    pf = pq.ParquetFile(corpus_path)
    total_rows = pf.metadata.num_rows

    flagged_texts = []
    sampled_texts = []
    seen_unflagged = 0
    start = time.time()

    for i, batch in enumerate(pf.iter_batches(
            batch_size=chunk_size,
            columns=["text", "alt_authority_count", "evidence_count"])):
        df = batch.to_pandas()
        flagged_mask = (df["alt_authority_count"] > 0) | (df["evidence_count"] > 0)
        flagged_texts.extend(df.loc[flagged_mask, "text"].fillna("").tolist())

        unflagged = df.loc[~flagged_mask, "text"].fillna("")
        seen_unflagged += len(unflagged)
        # Reservoir-ish approximate sampling: sample a fraction of this
        # chunk's unflagged rows proportional to remaining target/remaining
        # estimated unflagged rows in corpus.
        remaining_target = max(RANDOM_SAMPLE_TARGET - len(sampled_texts), 0)
        remaining_est_unflagged = max(total_rows - (i + 1) * chunk_size, 1)
        frac = min(remaining_target / max(remaining_est_unflagged, 1), 1.0) if remaining_target > 0 else 0
        if frac > 0:
            sampled_texts.extend(unflagged.sample(frac=frac, random_state=RANDOM_SEED + i).tolist())

        print(f"  chunk {i+1}: flagged so far {len(flagged_texts):,}, "
              f"sampled so far {len(sampled_texts):,} "
              f"({(time.time()-start)/60:.1f} min elapsed)", flush=True)

    return flagged_texts, sampled_texts


def run_ner(nlp, texts, counts, examples, source_tag, n_process=7, batch_size=200):
    start = time.time()
    for j, doc in enumerate(nlp.pipe(texts, batch_size=batch_size, n_process=n_process)):
        seen_this_doc = set()
        for ent in doc.ents:
            if ent.label_ not in KEEP_LABELS:
                continue
            key = ent.text.strip().strip("\"'.,-  ")
            if len(key) < MIN_NAME_LEN:
                continue
            seen_this_doc.add((key, ent.label_))
        for key, label in seen_this_doc:
            counts[(key, label)] += 1
            if len(examples[(key, label)]) < MAX_EXAMPLES_PER_ENTITY:
                examples[(key, label)].append(doc.text[:200])
        if (j + 1) % 200_000 == 0:
            elapsed = time.time() - start
            print(f"    [{source_tag}] {j+1:,}/{len(texts):,} docs "
                  f"({elapsed/60:.1f} min elapsed)", flush=True)


def main():
    print("Loading spaCy (NER-only pipeline)...")
    nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer", "tagger", "attribute_ruler"])

    print("Streaming corpus to build flagged + random-sample text sets...")
    flagged_texts, sampled_texts = collect_texts(CORPUS_PATH)
    print(f"\nFinal sets: {len(flagged_texts):,} flagged, {len(sampled_texts):,} random-sampled")

    counts = defaultdict(int)
    examples = defaultdict(list)

    print("\nRunning NER on flagged subset...")
    run_ner(nlp, flagged_texts, counts, examples, "flagged")

    print("\nRunning NER on random-sample subset...")
    run_ner(nlp, sampled_texts, counts, examples, "sampled")

    print(f"\n{len(counts)} unique (entity, label) pairs found")

    candidates = set()
    try:
        cand_df = pd.read_csv(CANDIDATE_PATH)
        candidates = set(cand_df["entity"].str.lower())
    except FileNotFoundError:
        pass

    rows = []
    for (entity, label), doc_count in counts.items():
        ex = examples[(entity, label)]
        rows.append({
            "entity": entity,
            "label": label,
            "doc_count": doc_count,
            "in_candidate_list": entity.lower() in candidates,
            "example_1": ex[0] if len(ex) > 0 else "",
            "example_2": ex[1] if len(ex) > 1 else "",
            "bucket": "",
        })

    out = pd.DataFrame(rows).sort_values("doc_count", ascending=False).reset_index(drop=True)
    out.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(out)} entities to {OUT_PATH}")
    print("\nTop 50 by doc_count:")
    print(out.head(50)[["entity", "label", "doc_count", "in_candidate_list"]].to_string(index=False))


if __name__ == "__main__":
    main()
