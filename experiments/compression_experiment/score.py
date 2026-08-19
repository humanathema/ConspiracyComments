"""
Score one compression-experiment round: reads the original from
corpus.jsonl, the Decoder's reconstruction from reconstructions/, and
writes fidelity scores into the matching log.jsonl line.

No heavy ML deps on this machine (no sentence-transformers/sklearn) --
uses a from-scratch TF-IDF cosine (numpy only) plus two cheap stdlib
lexical measures. Treat tfidf_cosine as the primary signal; the other
two are corroborating, not a replacement for eyeballing a few
reconstructions directly.

Usage: python3 score.py <message_id> <budget_level>
"""
import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
CORPUS = HERE / "corpus.jsonl"
LOG = HERE / "log.jsonl"
RECON_DIR = HERE / "reconstructions"


def tokenize(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def tfidf_cosine(a, b):
    docs = [tokenize(a), tokenize(b)]
    vocab = sorted(set(docs[0]) | set(docs[1]))
    if not vocab:
        return 0.0
    idx = {w: i for i, w in enumerate(vocab)}
    df = np.zeros(len(vocab))
    for doc in docs:
        for w in set(doc):
            df[idx[w]] += 1
    idf = np.log((2 + 1) / (df + 1)) + 1  # smoothed idf, 2 docs
    vecs = []
    for doc in docs:
        tf = np.zeros(len(vocab))
        counts = Counter(doc)
        for w, c in counts.items():
            tf[idx[w]] = c
        v = tf * idf
        norm = np.linalg.norm(v)
        vecs.append(v / norm if norm > 0 else v)
    return float(np.dot(vecs[0], vecs[1]))


def word_overlap_f1(a, b):
    ta, tb = set(tokenize(a)), set(tokenize(b))
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    overlap = len(ta & tb)
    precision = overlap / len(tb)
    recall = overlap / len(ta)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def load_original(message_id):
    with open(CORPUS) as f:
        for line in f:
            row = json.loads(line)
            if row["id"] == message_id:
                return row["text"]
    raise ValueError(f"{message_id} not found in corpus.jsonl")


def load_reconstruction(message_id, budget_level):
    path = RECON_DIR / f"{message_id}_{budget_level}.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found -- has the Decoder written its reconstruction yet?"
        )
    return path.read_text().strip()


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    message_id, budget_level = sys.argv[1], sys.argv[2]

    original = load_original(message_id)
    reconstruction = load_reconstruction(message_id, budget_level)

    scores = {
        "tfidf_cosine": round(tfidf_cosine(original, reconstruction), 4),
        "difflib_ratio": round(SequenceMatcher(None, original, reconstruction).ratio(), 4),
        "word_overlap_f1": round(word_overlap_f1(original, reconstruction), 4),
    }

    print(f"{message_id} @ budget={budget_level}")
    print(f"  original words:       {len(tokenize(original))}")
    print(f"  reconstruction words: {len(tokenize(reconstruction))}")
    print(f"  scores: {scores}")
    print(
        "\nAppend these scores into this round's log.jsonl line yourself "
        "(find the line by message_id+budget_level, add/overwrite its "
        "'scores' field) -- this script doesn't mutate log.jsonl "
        "automatically, since log.jsonl is meant to be a plain append-only "
        "file and this round's line may not exist yet depending on timing."
    )
    print("\nscores_json_for_convenience:", json.dumps(scores))


if __name__ == "__main__":
    main()
