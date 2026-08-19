"""
Score one compression-experiment round: reads the original from
corpus.jsonl, the Decoder's reconstruction from reconstructions/, and
writes fidelity scores into the matching log.jsonl line.

Semantic similarity via all-MiniLM-L6-v2 (sentence-transformers) -- the
same embedding model the rest of this project uses for topic modeling --
plus two cheap stdlib lexical measures as corroborating signal.

MUST run under the project's canonical Python env
(/Users/nash/miniforge3/bin/python3, Python 3.12, has sentence-
transformers/torch/etc) -- NOT bare `python3` on PATH, which can silently
resolve to a near-empty system Python (see data/infra_map.jsonl's
"local_python_environment" entries, 2026-08-20, for why this bit a
session directly). The guard below fails loudly rather than falling back
to a weaker method if the real package isn't importable.

Usage: /Users/nash/miniforge3/bin/python3 score.py <message_id> <budget_level>
"""
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
except ImportError as e:
    sys.exit(
        f"Missing package: {e}. You are almost certainly running the wrong "
        "Python -- use /Users/nash/miniforge3/bin/python3 explicitly, not "
        "bare `python3` (which can resolve to the system Homebrew Python on "
        "this machine; see data/infra_map.jsonl). Check: `which python3` "
        "should print /Users/nash/miniforge3/bin/python3."
    )

HERE = Path(__file__).parent
CORPUS = HERE / "corpus.jsonl"
LOG = HERE / "log.jsonl"
RECON_DIR = HERE / "reconstructions"

_model = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def semantic_cosine(a, b):
    model = get_model()
    emb = model.encode([a, b], normalize_embeddings=True)
    return float(np.dot(emb[0], emb[1]))


def tokenize(text):
    return re.findall(r"[a-z0-9]+", text.lower())


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
        "semantic_cosine": round(semantic_cosine(original, reconstruction), 4),
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
