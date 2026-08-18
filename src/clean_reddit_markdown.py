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

# **bold**, __bold__ -> bold (keep the text, strip the markers)
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
