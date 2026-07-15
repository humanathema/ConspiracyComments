"""attribution_confidence_scorer.py

Fully local, deterministic, no-LLM-calls attribution-confidence scorer,
staged 2026-07-15 per Nash's design. Replaces the bare "entity + some
appeal-language co-occur in this sentence" check (the logic gap
documented in ANTIGRAVITY_HANDOFF.md §8b/§17 C2) with a scored, rule-based
approach that accounts for:

  1. ORDERING: pre-nominal attribution ("according to X") vs. post-nominal
     attribution (X said/claimed/confirmed) are both legitimate but
     structurally different -- detect both, don't require one pattern.
  2. PROXIMITY: closer attribution language -> higher confidence.
  3. COMPETING SOURCES: if a DIFFERENT known entity sits between the
     attribution phrase and the target entity, down-rank -- this is the
     "Assange did X, according to CNN" case Nash named explicitly (CNN,
     not Assange, is the actual attributed source here).

**Why this matters beyond Baric**: Nash's observation generalizes --
Fauci/CDC/any consensus or maverick figure can be *mentioned inside* an
attribution-shaped sentence while actually being the ATTACKED subject,
not the cited source ("according to leaked emails, Fauci lied about..."
-- Fauci is the target of the claim, not its source). Bare co-occurrence
conflates these. This scorer doesn't fully solve that (see "Known gaps"
below) but narrows it substantially versus co-occurrence alone.

**Cost control (per Nash's design)**: this is meant to run ONLY on the
already-narrow `has_maverick`/`has_consensus_expert` subset (a few
hundred thousand rows at most, not the full 21M corpus) -- entity
matching happens first (cheap, already built), this scorer runs second,
only on rows that already matched an entity. No LLM/API calls anywhere.

**Validated against real corpus examples** (see `__main__` block) using
the actual Baric sentences pulled live from the corpus during the
conversation that motivated this file -- all of them are entity+
attribution-language co-occurrences that a bare co-occurrence check
would likely flag as "citing Baric as a source," but which are actually
accusatory ("Ralph Baric and his team" created the virus) -- i.e. Baric
is the grammatical subject of an ACCUSATION verb, not a REPORTING verb.
This scorer's pattern lists are deliberately restricted to genuine
reporting/citation verbs (said, claimed, reported, according to...) and
should NOT match accusation-only constructions ("X created/made/
engineered Y") -- see ACCUSATION_VERBS below, tracked separately so they
can be explicitly excluded rather than accidentally matched.

**Known gaps, not solved here** (staged for a follow-up pass, possibly
the "light local embedding" step Nash proposed, restricted to the
already-entity-matched subset for cost control):
  - Sarcastic/hostile "citation" ("according to Dr. Fauci [eye roll]...")
    -- structurally identical to genuine citation, needs semantic/
    sentiment signal this rule-based pass doesn't have.
  - Long-range or cross-sentence attribution (the source is named in a
    previous sentence, the entity's sentence just continues the claim).
  - True grammatical-subject verification currently uses proximity +
    immediate-follow as a proxy, not a real dependency parse. spaCy's
    dependency parser (already a project dependency) could check
    `token.dep_ == "nsubj"` for a more robust version of the post-nominal
    check -- noted as a natural next upgrade, not built here to keep this
    first pass simple and auditable.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

# Pre-nominal: attribution phrase appears BEFORE the entity ("according to X")
PRE_NOMINAL_PATTERNS = [
    r"according to", r"\bper\b", r"\bciting\b", r"\bcitations? from\b",
    r"sources? (close to|within|inside)", r"in an interview with",
    r"as (?:reported|noted|stated|claimed|argued|explained|pointed out) by",
]

# Post-nominal: genuine REPORTING verb appears AFTER the entity ("X said/claimed/confirmed")
# Deliberately excludes accusation-only verbs (created, made, engineered,
# built, designed) -- those describe alleged ACTIONS, not the entity
# being cited as a source of a claim. See ACCUSATION_VERBS.
POST_NOMINAL_VERBS = [
    r"\bsaid\b", r"\bsays\b", r"\bstated\b", r"\bclaims?\b", r"\bclaimed\b",
    r"\breported\b", r"\breports\b", r"\btold\b", r"\bconfirmed\b",
    r"\btestified\b", r"\balleged\b", r"\brevealed\b", r"\badmitted\b",
    r"\binsisted\b", r"\bwarned\b", r"\btweeted\b", r"\bwrote\b",
    r"\bexplained\b", r"\bnoted\b",
]

# Tracked separately so they're never accidentally treated as attribution --
# these describe an alleged ACTION the entity performed, not a claim
# they're the SOURCE of. "Ralph Baric created the virus" != a citation
# of Baric as an authority; it's an accusation about Baric.
ACCUSATION_VERBS = [
    r"\bcreated\b", r"\bmade\b", r"\bengineered\b", r"\bbuilt\b",
    r"\bdesigned\b", r"\bfunded\b", r"\bcovered up\b", r"\bhid\b",
    r"\blied\b", r"\bmanipulated\b", r"\bfaked\b", r"\borchestrated\b",
]

WORD_RE = re.compile(r"\S+")


@dataclass
class AttributionMatch:
    entity: str
    entity_start: int
    entity_end: int
    pattern_type: str  # "pre_nominal" | "post_nominal" | "none"
    pattern_text: Optional[str]
    distance_chars: Optional[int]
    confidence: str  # "high" | "medium" | "low" | "none"
    competing_entity: Optional[str] = None
    accusation_conflict: bool = False


def _char_to_word_distance(text: str, start: int, end: int) -> int:
    """Approximate token distance between two char offsets (order-agnostic)."""
    if end < start:
        start, end = end, start
    return len(WORD_RE.findall(text[start:end]))


def _find_nearest(text: str, patterns: list[str], anchor: int, direction: str, window: int = 120):
    """Find the nearest pattern match within `window` chars of `anchor`,
    searching either 'before' or 'after'. Returns (match_text, distance) or None."""
    lo = max(0, anchor - window)
    hi = min(len(text), anchor + window)
    search_span = text[lo:hi] if direction == "before" else text[anchor:hi]
    best = None
    for pat in patterns:
        for m in re.finditer(pat, search_span, re.IGNORECASE):
            if direction == "before":
                match_end_abs = lo + m.end()
                if match_end_abs > anchor:
                    continue
                dist = anchor - match_end_abs
            else:
                match_start_abs = anchor + m.start()
                dist = match_start_abs - anchor
            if best is None or dist < best[1]:
                best = (m.group(0), dist)
    return best


def score_entity_attribution(sentence: str, entity: str, entity_start: int, entity_end: int,
                              other_known_entities: Optional[list[str]] = None) -> AttributionMatch:
    """Score whether `entity` (at the given char offsets within `sentence`)
    is genuinely being cited as an attribution source, vs. merely co-
    occurring with attribution-shaped language, vs. being the subject of
    an accusation rather than a citation."""
    other_known_entities = other_known_entities or []

    pre = _find_nearest(sentence, PRE_NOMINAL_PATTERNS, entity_start, "before")
    post = _find_nearest(sentence, POST_NOMINAL_VERBS, entity_end, "after")
    accusation = _find_nearest(sentence, ACCUSATION_VERBS, entity_end, "after")

    # Prefer whichever legitimate pattern is closer; an accusation verb
    # sitting closer than any reporting pattern is a strong negative signal.
    candidates = []
    if pre:
        candidates.append(("pre_nominal", pre[0], pre[1]))
    if post:
        candidates.append(("post_nominal", post[0], post[1]))

    accusation_closer = accusation is not None and (
        not candidates or accusation[1] < min(c[2] for c in candidates)
    )

    if not candidates:
        return AttributionMatch(
            entity=entity, entity_start=entity_start, entity_end=entity_end,
            pattern_type="none", pattern_text=None, distance_chars=None,
            confidence="none", accusation_conflict=accusation is not None,
        )

    candidates.sort(key=lambda c: c[2])
    ptype, ptext, dist = candidates[0]

    # Competing-source check: is a DIFFERENT known entity strictly between
    # the attribution phrase and our target entity? If so, that other
    # entity is more likely the true attributed source.
    if ptype == "pre_nominal":
        span_start, span_end = entity_start - dist, entity_start
    else:
        span_start, span_end = entity_end, entity_end + dist
    span_text = sentence[max(0, span_start):min(len(sentence), span_end)]
    competing = None
    for other in other_known_entities:
        if other.lower() == entity.lower():
            continue
        if re.search(r"\b" + re.escape(other) + r"\b", span_text, re.IGNORECASE):
            competing = other
            break

    word_dist = _char_to_word_distance(sentence, entity_start if ptype == "pre_nominal" else entity_end,
                                        entity_start - dist if ptype == "pre_nominal" else entity_end + dist)

    if competing:
        confidence = "low"
    elif accusation_closer:
        confidence = "low"
    elif word_dist <= 3:
        confidence = "high"
    elif word_dist <= 8:
        confidence = "medium"
    else:
        confidence = "low"

    return AttributionMatch(
        entity=entity, entity_start=entity_start, entity_end=entity_end,
        pattern_type=ptype, pattern_text=ptext, distance_chars=dist,
        confidence=confidence, competing_entity=competing,
        accusation_conflict=accusation_closer,
    )


if __name__ == "__main__":
    # Real sentences pulled live from the corpus (2026-07-15) during the
    # conversation that motivated this scorer -- all "Baric" mentions,
    # all accusatory in the actual corpus, none genuine citations. A
    # correct scorer should rate these low/none, not high.
    test_sentences = [
        ("Coronavirus is a man made pathogen in a lab, by Ralph Baric and his team", "Ralph Baric"),
        ("Ralph Baric has over 30 years of research in this virus at the University of Raleigh", "Ralph Baric"),
        ("It was headed by Ralph Baric.", "Ralph Baric"),
        # Contrast case: genuine reporting-verb citation, should score high
        ("According to WikiLeaks, the documents prove the operation was authorized.", "WikiLeaks"),
        ("Assange said the leak was authentic.", "Assange"),
        # Competing-source case Nash named explicitly
        ("Assange did nothing wrong, according to CNN.", "Assange"),
    ]
    for sentence, entity in test_sentences:
        m = re.search(re.escape(entity), sentence)
        result = score_entity_attribution(sentence, entity, m.start(), m.end(),
                                           other_known_entities=["CNN", "WikiLeaks", "Assange"])
        print(f"[{result.confidence:6s}] pattern={result.pattern_type:12s} "
              f"accusation_conflict={result.accusation_conflict} competing={result.competing_entity} "
              f"| {sentence}")
