"""stance_window_utils.py

Shared entity-focused text-window extraction for the stance classifier.

Replaces whole-comment-text vectorization (the original design) with a
windowed approach: for a given target entity's span(s) within a comment,
extract WINDOW_WORDS words on each side of every occurrence and
concatenate. Same convention (window size, word-splitting) as
stage_b_consolidated_corpus_pass.py's extract_word_bag(), just kept as
readable text rather than a stripped word-bag, since TfidfVectorizer
already handles stopword removal on its own.

Why this exists: the whole-text classifier trained fine on single-entity
comments, but broke down on multi-entity comments split into per-entity
rows (build_stance_active_learning_queue.py, round 4) -- two rows sharing
identical full_text but different stance labels (e.g. "David Icke" rated
endorsement, "Icke" -- the same person -- rated hostile in the same
comment) are a direct contradiction for a model that only sees the whole
text. Windowing around the actual target entity fixes this at the root:
each row's input text becomes specific to what it's actually a label for.

Used by: train_stance_classifier.py (training), and every inference site
that scores stance_prob at scale (rerun_regressions_with_stance.py,
run_integrated_regressions.py's run_stance_submodels,
build_stance_active_learning_queue.py's uncertainty sampling) -- all of
these MUST use the same windowing the classifier was trained on, or the
vectorizer sees a different kind of input than it learned from.
"""
import json
import re

WINDOW_WORDS = 15


def extract_entity_window(text, spans, window_words=WINDOW_WORDS):
    """spans: list of {"start":, "end":, "text":} dicts, OR a JSON string
    of the same (as stored in the entity_spans queue column), OR None/empty.
    Returns concatenated windows around every occurrence; falls back to the
    full text if no spans are available (shouldn't normally happen for rows
    that are genuinely has_maverick/has_consensus_expert==1, but keeps
    scoring from breaking on an edge case rather than silently producing
    an empty feature vector)."""
    text = str(text)
    if isinstance(spans, str):
        try:
            spans = json.loads(spans)
        except (json.JSONDecodeError, TypeError):
            spans = []
    if not spans:
        return text

    windows = []
    for s in spans:
        start, end = s["start"], s["end"]
        before = text[:start].split()[-window_words:]
        after = text[end:].split()[:window_words]
        windows.append(" ".join(before + [s["text"]] + after))
    return " ".join(windows)


def compute_spans_for_row(text, cid, rx, lookup, candidate_to_bares):
    """Direct-regex spans for a comment; if none, falls back to
    highlighting the resolved candidate's bare form via the
    disambiguation lookup (same logic used in
    build_stance_active_learning_queue.py's queue-building, kept here so
    every scoring site can compute spans the same way instead of
    duplicating this fallback separately)."""
    text = str(text)
    spans = [{"start": m.start(), "end": m.end(), "text": m.group(0)} for m in rx.finditer(text)]
    if spans:
        return spans
    resolved = lookup.get(str(cid))
    bares = candidate_to_bares.get(resolved, [])
    for bare in bares:
        bare_rx = re.compile(r"\b" + re.escape(bare) + r"\b", re.IGNORECASE)
        spans.extend({"start": m.start(), "end": m.end(), "text": m.group(0)} for m in bare_rx.finditer(text))
    return spans
