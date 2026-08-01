"""build_media_personality_candidate_list.py

Scores the Wikipedia-sourced media-personality candidates from
query_media_personality_candidates.py against real corpus mention
frequency, using the exact same pyahocorasick single-pass technique as
build_maverick_candidate_list.py (full-text scan, not NER-string lookup
-- NER-string matching was found this session to have a real recall gap,
see job_topdown_entity_expansion_2026-07-28 in context-repo).

Stage 2 of handoff/task_2026-07-28c_media_personality_candidate_list_in_progress.md.

Also seeds four already-known-relevant names (the original hardcoded
whistleblower-vs-media-personality contrast: Alex Jones, Tucker Carlson,
Roger Stone, Matt Gaetz) plus Joe Rogan, since maverick_authority_verified.py's
own docstring explicitly says platform-driven commentators belong in that
list -- these are known-positive calibration rows, not assumed to be
kept, just guaranteed to be scored so their real corpus mention counts
are visible next to the new candidates.

Final keep/cut decisions are Nash's call, not automated here -- output is
a CSV with a blank `decision` column for manual review, same as
maverick_candidate_entities_scored.csv.

Output: data/processed/media_personality_candidates_scored.csv
"""
import os
import re
import time
from collections import defaultdict

import ahocorasick
import pandas as pd
import pyarrow.parquet as pq

CORPUS_PATH = "data/processed/empath_scores_full_mapped.parquet"
CANDIDATES_PATH = "data/processed/media_personality_wikipedia_candidates.csv"
OUT_PATH = "data/processed/media_personality_candidates_scored.csv"

MIN_NAME_LEN = 5

KNOWN_POSITIVE_CALIBRATION = [
    "Alex Jones", "Tucker Carlson", "Roger Stone", "Matt Gaetz", "Joe Rogan",
]


def normalize(name):
    return name.strip()


def build_automaton(names):
    A = ahocorasick.Automaton()
    for idx, name in enumerate(names):
        A.add_word(name.lower(), (idx, name))
    A.make_automaton()
    return A


WORD_CHAR = re.compile(r"\w")


def is_word_boundary_match(text, start, end):
    before_ok = start == 0 or not WORD_CHAR.match(text[start - 1])
    after_ok = end >= len(text) or not WORD_CHAR.match(text[end])
    return before_ok and after_ok


def scan_corpus(names, corpus_path, chunk_size=1_000_000):
    automaton = build_automaton(names)
    counts = defaultdict(int)
    pf = pq.ParquetFile(corpus_path)
    total = 0
    start_t = time.time()
    for i, batch in enumerate(pf.iter_batches(batch_size=chunk_size, columns=["id", "text"])):
        chunk = batch.to_pandas()
        total += len(chunk)
        for text in chunk["text"].fillna(""):
            text_l = text.lower()
            seen_this_row = set()
            for end_idx, (idx, name) in automaton.iter(text_l):
                start_idx = end_idx - len(name) + 1
                if is_word_boundary_match(text_l, start_idx, end_idx + 1):
                    seen_this_row.add(name)
            for name in seen_this_row:
                counts[name] += 1
        elapsed = time.time() - start_t
        print(f"  chunk {i+1}: {len(chunk):,} rows (cumulative {total:,}, "
              f"{elapsed/60:.1f} min elapsed)", flush=True)
    return counts, total


def main():
    cand_df = pd.read_csv(CANDIDATES_PATH)
    cand_df["name"] = cand_df["name"].apply(normalize)
    cand_df = cand_df[cand_df["name"].str.len() >= MIN_NAME_LEN]

    calibration_rows = pd.DataFrame([
        {"name": n, "domain": "Media/Commentary", "basis_type": "media_platform",
         "basis_detail": "known_positive_calibration", "source_url": "",
         "notes": "Existing contrast/allowlist name, seeded for calibration"}
        for n in KNOWN_POSITIVE_CALIBRATION
    ])
    combined = pd.concat([cand_df, calibration_rows], ignore_index=True)
    combined = combined.drop_duplicates(subset=["name"], keep="first")
    print(f"{len(combined)} unique candidates to score "
          f"({len(cand_df)} from Wikipedia categories + "
          f"{len(KNOWN_POSITIVE_CALIBRATION)} known-positive calibration names, "
          f"minus overlap)")

    names = combined["name"].tolist()
    print(f"\nScanning corpus ({CORPUS_PATH}) for {len(names)} candidates "
          f"using Aho-Corasick (single pass)...")
    counts, total = scan_corpus(names, CORPUS_PATH)
    print(f"\nScanned {total:,} total corpus rows.")

    combined["corpus_mentions"] = combined["name"].apply(lambda n: counts.get(n, 0))
    combined["decision"] = ""
    combined = combined.sort_values("corpus_mentions", ascending=False).reset_index(drop=True)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    combined.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(combined)} scored candidates to {OUT_PATH}")
    print(f"\nTop 40 by corpus mentions:")
    print(combined.head(40)[["name", "basis_detail", "corpus_mentions"]].to_string(index=False))
    print(f"\n{(combined['corpus_mentions'] == 0).sum()} candidates with zero corpus mentions "
          f"(bottom of the sort, likely not worth reviewing)")
    print(f"\nCalibration name mention counts:")
    print(combined[combined["name"].isin(KNOWN_POSITIVE_CALIBRATION)][["name", "corpus_mentions"]].to_string(index=False))


if __name__ == "__main__":
    main()
