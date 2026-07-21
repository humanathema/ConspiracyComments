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

# Reddit markdown blockquote lines ("> quoted text", or the HTML-escaped
# "&gt; quoted text" seen in ~11K rows, presumably from an un-decoded
# export). An entity mention whose span falls entirely inside one of these
# lines is someone else's text being quoted, not the commenter's own words
# -- scoring it as the commenter's stance would attribute a stranger's
# opinion to them. QUOTE_LINE_RE is multiline (?m) so each line of a
# multi-line quote block is matched individually.
QUOTE_LINE_RE = re.compile(r'(?m)^[ \t]*(?:>|&gt;)[ \t]*.*$')


def quoted_line_ranges(text):
    text = str(text)
    return [(m.start(), m.end()) for m in QUOTE_LINE_RE.finditer(text)]


def filter_quoted_spans(text, spans):
    """Drops spans that fall entirely inside a quoted line. No-op (returns
    spans unchanged) if the text has no quote markers at all, which is the
    overwhelming majority of comments -- avoids paying the regex scan cost
    twice for nothing."""
    if not spans:
        return spans
    ranges = quoted_line_ranges(text)
    if not ranges:
        return spans
    return [s for s in spans if not any(qs <= s["start"] and s["end"] <= qe for qs, qe in ranges)]


URL_RE = re.compile(r'https?://\S+')
MIN_WINDOW_URLS_FOR_LIST_DUMP = 2


def is_list_or_link_dump_window(window_text):
    """True if the entity's own +-15-word window (not the whole comment)
    contains 2+ URLs -- confirmed against two real Jones quality-check
    misses (2026-07-21): both were link-dump comments (a wall of RT/
    YouTube links, a Google-search dump) where the target entity's
    immediate context is other links, not evaluative language about the
    entity at all. The classifier reads "no hostile-coded words nearby" as
    endorsement, so these get scored confidently-endorsing (0.68-0.73)
    while a human calls them neutral/unclear. Checking the WINDOW rather
    than the full comment matters -- a comment can legitimately cite one
    source while genuinely commenting on the entity elsewhere; it's only a
    problem when the citation dump is what surrounds the mention itself."""
    return len(URL_RE.findall(str(window_text))) >= MIN_WINDOW_URLS_FOR_LIST_DUMP


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


def compute_spans_for_row(text, cid, rx, lookup, candidate_to_bares, filter_quotes=True):
    """Direct-regex spans for a comment; if none, falls back to
    highlighting the resolved candidate's bare form via the
    disambiguation lookup (same logic used in
    build_stance_active_learning_queue.py's queue-building, kept here so
    every scoring site can compute spans the same way instead of
    duplicating this fallback separately).

    filter_quotes=True (default) drops spans inside quoted lines at each
    stage (direct match, then fallback) before falling through -- so a
    mention that's ONLY quoted still lets the fallback bare-form search
    run, same as if the direct regex had found nothing at all."""
    text = str(text)
    spans = [{"start": m.start(), "end": m.end(), "text": m.group(0)} for m in rx.finditer(text)]
    if filter_quotes:
        spans = filter_quoted_spans(text, spans)
    if spans:
        return spans
    resolved = lookup.get(str(cid))
    bares = candidate_to_bares.get(resolved, [])
    for bare in bares:
        bare_rx = re.compile(r"\b" + re.escape(bare) + r"\b", re.IGNORECASE)
        spans.extend({"start": m.start(), "end": m.end(), "text": m.group(0)} for m in bare_rx.finditer(text))
    if filter_quotes:
        spans = filter_quoted_spans(text, spans)
    return spans
