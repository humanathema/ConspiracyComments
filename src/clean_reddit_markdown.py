"""clean_reddit_markdown.py

Converts Reddit markdown to clean, readable plain text -- shared utility
for anywhere raw comment text gets shown to a human or fed to a model:
hitl_rater.py (so raters see prose, not `[link text](url)` syntax),
generate_backtranslation_paraphrase.py (formatting characters -- headers,
long dash separators, bold markers -- were sending the MT model into
degenerate repetition loops, 2026-08-19), and potentially the stance
classifier's own input (untested whether raw markdown syntax helps or
hurts the classifier; this at minimum makes that a fair thing to test
instead of confounding "does formatting help" with "is the input full of
literal asterisks and pipe characters").

Deliberately does NOT touch bare URLs or the `>` blockquote marker --
those are handled by existing, separate mechanisms elsewhere
(stance_window_utils.py's QUOTE_LINE_RE excludes quoted lines from a
commenter's own stance entirely, which is a different, more consequential
decision than just visual cleanup, so this utility stays out of its way).

CRITICAL ordering constraint, not just a style choice: entity/domain
SCANNING (build_full_entity_mention_pool.py, build_domain_entities())
must always run on RAW, uncleaned text -- domain matching works by
finding the literal domain string (e.g. "theguardian.com") inside the
raw URL in the text. This utility is only for text shown to a human
(hitl_rater.py) or fed to a downstream model AFTER target_entity is
already known (classifier input, back-translation) -- never upstream of
entity detection, or domain mentions would silently stop being found.

Markdown links keep the domain visible even when anchor text is generic
("Source", "here") -- found 2026-08-19 (Nash caught this): naively
dropping to just the anchor text would discard exactly the signal the
domain-entity stance work depends on. `[text](url)` becomes "text
(domain.com)" (or just "text" if the anchor already names the domain) --
short enough not to trip up a translator the way a full URL does, but
without losing which source was actually cited.
"""
import re

# [link text](url) -> "link text (domain.com)" when the anchor text
# doesn't already contain the domain, else just "link text". NOT a bare
# drop-to-anchor-text substitution -- found 2026-08-19 (Nash caught this):
# throwing the URL away entirely loses the cited domain whenever anchor
# text is generic ("Source", "here", "this article"), which is exactly
# the signal the domain-entity stance work depends on. Keeps the FULL url
# out of the text (that's what was tripping up the translator into
# degenerate repetition loops) while still surfacing which domain was
# cited, in a short form a model/translator can handle fine.
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")
DOMAIN_FROM_URL_RE = re.compile(r"https?://(?:www\.)?([^/\s]+)")


def _extract_domain(url: str) -> str:
    m = DOMAIN_FROM_URL_RE.match(url)
    return m.group(1) if m else ""


BARE_URL_ANCHOR_RE = re.compile(r"^https?://")


def _link_replacement(m: re.Match) -> str:
    anchor, url = m.group(1), m.group(2)
    domain = _extract_domain(url)
    # Common Reddit shorthand: the raw URL pasted as its own anchor text
    # ("[https://...](https://...)") -- collapse to just the domain,
    # don't leave the full URL sitting in the visible text.
    if BARE_URL_ANCHOR_RE.match(anchor.strip()):
        return domain or anchor
    if not domain or domain.lower() in anchor.lower():
        return anchor
    return f"{anchor} ({domain})"


# --- Placeholder protection for back-translation -------------------------
#
# Round-tripping a comment through translation (en->de->en) needs links
# protected from two things: (1) long/messy real URLs send the MT model
# into degenerate repetition loops (found 2026-08-19), (2) even a clean
# placeholder needs to survive the round trip intact enough to restore the
# ORIGINAL link afterward -- the classifier/training use case needs the
# real link back, not just a domain, since the specific article (not just
# the outlet) can be what matters (Nash's point: the entity being scored
# is often someone named in the text, not the linked domain -- the link
# can be incidental evidence, not the classification target itself).
#
# Empirically tested 2026-08-19 (Nash's idea) against the real opus-mt-
# en-de/de-en models: letter-based placeholders ("XLINK1X" etc) survive a
# SINGLE occurrence per sentence, but degrade on the 2nd/3rd occurrence in
# the same sentence (German's noun-capitalization rule flips case on
# lowercase placeholders; even all-caps ones picked up single-letter
# substitutions on later occurrences -- "XLINK2X"->"XLINk2X",
# "XLINK3X"->"XLINC3X"). Large primes with no thousands-separator survived
# with EXACT, 100% fidelity across 5 placeholders in one sentence -- no
# letters means no case-corruption risk, and "no commas" specifically
# avoids the model reformatting the number with German's opposite
# comma/period convention for thousands-separators/decimals.
BARE_URL_RE = re.compile(r"https?://\S+")

# Fixed pool of large, non-"famous" primes (no widely-known mathematical
# significance -- avoids the small chance a very well-known prime like
# 998244353, used constantly in competitive-programming modulo contexts,
# has some learned association in the model's training data that a
# genuinely obscure prime wouldn't).
_PRIME_POOL = [
    86028157, 49979693, 15485917, 32452867, 67867979, 22801763, 71976487,
    41706329, 93724837, 58831397, 27644479, 86028121, 15485867, 49979687,
    32452843, 67867967, 22801751, 71976449, 41706311, 93724813,
    # Extended 2026-08-19 for entity protection (below) sharing the same
    # pool as link protection -- one comment can now need both link AND
    # entity primes simultaneously, so 20 wasn't enough headroom.
    28728463, 14265799, 39587039, 20709497, 39476249, 14308421, 45351479,
    90388981, 42329237, 91415657, 75151231, 38754377, 64038913, 35529407,
    23141087, 60864911, 66775103, 39219319, 17634247, 52462441, 96637649,
    93370583, 19832887, 25492573, 43704923, 66851377, 27558317, 85146293,
    64543049, 43308443, 24508349, 35511941, 99245317, 32775593, 79182797,
    22534217, 42747037, 27896471, 65804273, 61053877,
]


def protect_links_for_translation(text: str):
    """Replaces every markdown link's URL (keeping the anchor text as
    normal translatable prose) and every bare URL with a unique
    large-prime placeholder, safe to send through translation. Returns
    (protected_text, mapping) where mapping is {prime_str: original_url}
    -- restoring gives "anchor text (url)", not the original markdown
    bracket syntax, matching the "readable prose with the link visible,
    not interrupting the reading flow" format this whole thing is for.

    Does NOT protect the anchor text itself -- found 2026-08-19 (real bug,
    caught by Nash asking why links were being lost): an earlier version
    replaced the WHOLE "[anchor](url)" match with one bare number,
    discarding real, often substantial anchor text ("[Alex Jones Blows
    His Cover In Austin](url)" collapsed to a lone "86028157" with
    nothing else). Sending the translator a sentence containing only an
    isolated number, with all its real content gone, produced complete
    hallucination (unrelated EU regulatory boilerplate, seen verbatim in
    testing) -- not a translation-model limitation, a bug in what got
    sent to it. Now: `[anchor](url)` -> "anchor (PRIME)", or just
    "PRIME" if the anchor is itself a bare URL (same "don't leave a raw
    URL as visible anchor text" case _link_replacement handles above).

    Raises if there are more links in one text than the prime pool covers
    (20) -- that's already well past is_too_thin_to_translate/list-dump
    territory and should have been filtered out upstream, not silently
    handled here."""
    matches = []  # (start, end, replacement_text, url)
    for m in MARKDOWN_LINK_RE.finditer(text):
        anchor, url = m.group(1), m.group(2)
        if BARE_URL_ANCHOR_RE.match(anchor.strip()):
            matches.append((m.start(), m.end(), "PRIME_PLACEHOLDER", url))
        else:
            matches.append((m.start(), m.end(), f"{anchor} (PRIME_PLACEHOLDER)", url))
    # Bare URLs not already inside a markdown link (avoid double-protecting
    # the url portion of "[text](url)").
    link_spans = [(s, e) for s, e, _, _ in matches]
    for m in BARE_URL_RE.finditer(text):
        if not any(s <= m.start() < e for s, e in link_spans):
            matches.append((m.start(), m.end(), "PRIME_PLACEHOLDER", m.group(0)))
    matches.sort(key=lambda x: x[0])

    if len(matches) > len(_PRIME_POOL):
        raise ValueError(f"{len(matches)} links in one text, more than the {len(_PRIME_POOL)}-prime pool covers")

    mapping = {}
    protected = text
    # Replace back-to-front so earlier spans' character offsets stay valid.
    for i, (start, end, replacement, url) in enumerate(reversed(matches)):
        prime = str(_PRIME_POOL[len(matches) - 1 - i])
        mapping[prime] = url
        protected = protected[:start] + replacement.replace("PRIME_PLACEHOLDER", prime) + protected[end:]
    return protected, mapping


# --- Proper-noun/acronym protection for back-translation ----------------
#
# Found 2026-08-19 (Nash's suggestion): back-translation garbles proper
# nouns and acronyms even with beam search -- "Catherine Austin Fitts" ->
# "Katherin austin fitt's", "KKK" -> "CCC" (a real content change, not just
# reworded phrasing). Reuses the exact same prime-placeholder mechanism
# already proven for links, on the theory that a name is just as
# untranslatable-without-corruption as a URL. Deliberately protects ONLY
# the row's own known target_entity (case-insensitive), not general spaCy
# NER -- tried full NER 2026-08-19, found it over-fires on dense
# conspiracy-comment text (NIH/FDA/PCR/dates all tagged ORG/etc), gutting
# whole sentences to strings of digits and defeating the actual point of
# back-translation. Corrupting a non-target proper noun is low-stakes
# phrasing drift; only the target_entity is worth this protection given
# that asymmetry (it's what the training label is actually about).
_NER_LABELS_TO_PROTECT = {"PERSON", "ORG", "EVENT", "WORK_OF_ART", "GPE", "FAC", "LAW"}


def protect_entities_for_translation(text: str, nlp=None, target_entity: str = None, exclude_primes: set = None):
    """Replaces the target_entity span (and any spaCy-NER spans, if an
    `nlp` pipeline is passed -- off by default, see module note above) with
    prime placeholders, same mechanism as protect_links_for_translation.
    Call this AFTER protect_links_for_translation on its output, passing
    exclude_primes=set(link_mapping) so entity primes never collide with
    already-placed link primes in the same text. Returns (protected_text,
    mapping) where mapping is {prime_str: original_span_text}."""
    exclude_primes = exclude_primes or set()
    matches = []  # (start, end, original_text)
    if nlp is not None:
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ in _NER_LABELS_TO_PROTECT:
                matches.append((ent.start_char, ent.end_char, ent.text))
    if target_entity:
        pattern = re.compile(r"\b" + re.escape(target_entity) + r"\b", re.IGNORECASE)
        for m in pattern.finditer(text):
            matches.append((m.start(), m.end(), m.group(0)))
    # Dedup/merge overlaps -- prefer the longer span when two matches
    # overlap (e.g. spaCy's "Tucker" inside a target_entity "Tucker
    # Carlson" match), then drop any remaining overlaps outright rather
    # than risk a corrupted double-substitution.
    matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    kept = []
    last_end = -1
    for start, end, orig in matches:
        if start >= last_end:
            kept.append((start, end, orig))
            last_end = end
    if not kept:
        return text, {}

    available = [p for p in _PRIME_POOL if str(p) not in exclude_primes]
    if len(kept) > len(available):
        kept = kept[:len(available)]  # cap rather than fail -- entity protection is a quality improvement, not a hard requirement like link preservation

    mapping = {}
    protected = text
    for i, (start, end, orig) in enumerate(reversed(kept)):
        prime = str(available[len(kept) - 1 - i])
        mapping[prime] = orig
        protected = protected[:start] + prime + protected[end:]
    return protected, mapping


def restore_links_after_translation(text: str, mapping: dict) -> str:
    """Finds each prime placeholder in the (translated-and-back) text and
    restores the original link text. Exact string match, no fuzzy
    fallback -- the empirical test (see module docstring) showed 100%
    exact survival across 5 placeholders in one sentence, unlike the
    letter-based scheme this replaced, so exact match is the right level
    of robustness here, not overkill. Callers should check whether all
    primes in `mapping` were actually found/replaced if they need to
    detect the rare case a translation dropped one entirely."""
    for prime, original in mapping.items():
        text = text.replace(prime, original)
    return text
BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1")
# *italic*, _italic_ -> italic (single markers, applied after bold so
# "**bold**" doesn't get half-matched by the single-marker pattern first)
ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)([^\*\n]+?)\*(?!\*)|(?<!_)_(?!_)([^_\n]+?)_(?!_)")

# # Header, ## Header, etc -> Header (strip leading #'s + space)
HEADER_RE = re.compile(r"(?m)^#{1,6}\s+")

# Long separator lines (---, ___, ***, 3+ chars) -> dropped entirely,
# not just de-emphasized -- these carry no content at all.
SEPARATOR_LINE_RE = re.compile(r"(?m)^\s*([-_*])\1{2,}\s*$\n?")

# Bullet/numbered list markers at line start -> stripped, keep the text
BULLET_RE = re.compile(r"(?m)^\s*(?:[-*+]|\d+\.)\s+")

# ~~strikethrough~~ -> strikethrough
STRIKETHROUGH_RE = re.compile(r"~~(.+?)~~")

# `inline code` -> inline code
INLINE_CODE_RE = re.compile(r"`([^`]+)`")


def clean_reddit_markdown(text: str) -> str:
    text = str(text)
    text = MARKDOWN_LINK_RE.sub(_link_replacement, text)
    text = STRIKETHROUGH_RE.sub(r"\1", text)
    text = INLINE_CODE_RE.sub(r"\1", text)
    text = BOLD_RE.sub(r"\2", text)
    text = ITALIC_RE.sub(lambda m: m.group(1) or m.group(2), text)
    text = HEADER_RE.sub("", text)
    text = SEPARATOR_LINE_RE.sub("", text)
    text = BULLET_RE.sub("", text)
    # Collapse the blank-line runs left behind by removing separator lines,
    # without touching intentional paragraph breaks (single blank lines).
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


if __name__ == "__main__":
    # Quick self-check against the exact failure cases found 2026-08-19
    tests = [
        "# Nikola Tesla: \"You Will VIBRATE Differently\"\n\n[https://www.youtube.com/watch?v=Ot6GaYCzdSo](https://www.youtube.com/watch?v=Ot6GaYCzdSo)",
        "-----------------------------------------------------------------------------------------------------------\n\nU.S. Attendees of the 2008 Bilderberg Conference:",
        "**It's The Great Racket, Charlie Brown**\n\n[PCR](https://www.nytimes.com/2007/01/22/health/22whoop.html) test [pandemic.](https://www.bbc.com/news/health-54000629)",
        "As part of their **\"Silent Weapons for Quiet Wars\"** agenda of *global social engineering*",
    ]
    for t in tests:
        print("BEFORE:", repr(t[:100]))
        print("AFTER: ", repr(clean_reddit_markdown(t)[:100]))
        print()
