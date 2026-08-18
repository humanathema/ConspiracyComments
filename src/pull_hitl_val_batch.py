"""pull_hitl_val_batch.py

Pull a new HITL labeling batch for val-set expansion using the full
defensibly-generated entity set rather than the hardcoded 11.

Entity sources:
  1. Person mavericks — maverick_candidate_entities_scored.csv (corpus_mentions >= 300),
     excluding the 11 entities already covered in round 7/8 training data,
     and excluding historical canonical figures (Tesla, Newton, etc.).
  2. Domain epistemic sources — domain_classification_lookup.csv, categories
     alt_media and leak_whistleblower.  Matched by domain key in comment text.

Stance labeling (hostile/endorsement/neutral/ambiguous/wrong_match) applies to
both persons and domains: "hostile to <naturalnews.com>" = dismissal,
"endorsement" = treating as a trusted epistemic source.

Usage:
  python3 src/pull_hitl_val_batch.py --out data/hitl/queue_expanded_entity_val_r1.csv
  python3 src/pull_hitl_val_batch.py --out data/hitl/queue_expanded_entity_val_r2.csv --seed 44
"""

import argparse
import re
import sys
import pandas as pd
import duckdb
from pathlib import Path

EMPATH   = "data/processed/empath_scores_full_mapped.parquet"
DOC_COUNTS_FILE = "data/processed/verified_entity_combined_doc_counts.csv"
DOM_FILE = "data/processed/domain_classification_lookup.csv"

TARGET_ROWS       = 410
MAX_PER_ENTITY    = 10   # cap per individual entity before final balance sample
# Combined long+short comment doc_count (see DOC_COUNTS_FILE) — replaces the
# old MIN_ENTITY_MENTIONS=300 raw-candidate threshold, which turned out to be
# long-comment-only and admitted only ~14% of the verified entity universe
# (2026-08-12 analysis). >=100 captures 130/190 (68%) of already-verified
# maverick+consensus entities with real, non-trivial corpus presence — no
# per-entity judgment calls needed since it's applied uniformly to entities
# already reviewed and confirmed by maverick_authority_verified.py /
# consensus_experts_verified.py.
MIN_COMBINED_DOC_COUNT = 100
RANDOM_STATE      = 42

# The 11 entities already covered in existing training/val data — skip them
SKIP_ENTITIES = {
    "wikileaks", "alex jones", "tucker carlson", "julian assange", "roger stone",
    "edward snowden", "matt gaetz", "glenn greenwald", "aaron swartz",
    "anthony fauci", "bill gates",
}

# Historical canonical / non-maverick figures to skip
SKIP_PERSONS = {
    "Nikola Tesla", "Neil deGrasse Tyson", "Bill Hicks", "Adam Weishaupt",
    "Oliver Stone", "Mark Dice", "Deep Throat",  # anonymous — matching unreliable
    "Jenny McCarthy",  # surname dominated by 1950s Red Scare McCarthyism in this
                        # corpus; not independently established as discussed here,
                        # not worth a disambiguation pass — see AMBIGUOUS_SURNAMES.
    "Stephen Hawking", "Carl Sagan",  # historical/canonical scientists, excluded
                                       # 2026-08-12 alongside Tesla/deGrasse Tyson.
}

# Skip categories that are historical/canonical rather than maverick/consensus
SKIP_CATEGORIES = {"free_energy_theorist", "rogan_guest_scientist"}

# Domain categories to include
DOMAIN_CATS = {"alt_media", "leak_whistleblower"}

# Domains to skip (platforms, not epistemic sources in the stance sense)
SKIP_DOMAINS = {
    "reddit.com", "youtube.com", "twitter.com", "facebook.com",
    "instagram.com", "imgur.com", "archive.is", "archive.org",
    "web.archive.org", "wikileaks.org", "wikileaks.com",  # already in person 11
}


def _bare_surname_key(entity: str) -> str:
    """Last word of a multi-word entity name, stripped of trailing punctuation."""
    parts = entity.strip().split()
    last = parts[-1].lower()
    last = re.sub(r"[.,]+$", "", last)   # "jr." → "jr"
    last = re.sub(r"'s$", "", last)       # possessive only
    return last


def _full_name_sql_cond(entity: str) -> str:
    """Require the FULL entity name as a phrase (all words in order, flexible
    whitespace between them), case-insensitive, word-boundary anchored.

    BUG FIXED 2026-08-12: matched against lower(text) but never lowercased
    the pattern itself -- e.g. 'Joe Rogan' built the literal pattern
    '\\bJoe\\s+Rogan\\b', which can never match lowercased corpus text.
    Every entity requiring full-name matching (anything with a short/
    AMBIGUOUS_SURNAMES surname -- Rogan, Icke, Ventura, and more) silently
    returned zero matches from this bug, not real corpus scarcity.
    """
    parts = entity.strip().lower().split()
    escaped_parts = [re.escape(p).replace("'", "''") for p in parts]
    pattern = r"\s+".join(escaped_parts)
    return f"regexp_matches(lower(text), '\\b{pattern}\\b')"


# Surnames confirmed (or already known) to collide with a much more famous
# unrelated person, or to be an ordinary English word/name shared broadly
# enough that bare matching is unsafe. Full name is required for these instead
# of the bare surname. Extended 2026-08-12 after auditing
# queue_expanded_entity_val_r1.csv (34 human-labeled wrong_match rows out of
# 410): weinstein (matches Harvey Weinstein almost exclusively, not Bret),
# manning (the common verb "manning", not just Chelsea Manning), steele
# (Christopher Steele / "Steele dossier", plus a raw substring hit inside
# "Steeler"), ventura (Ace Ventura movie character). Jenny McCarthy dropped
# from the candidate list entirely (see SKIP_PERSONS) rather than
# disambiguated — the corpus attention is dominated by 1950s Red Scare
# McCarthyism, and she isn't independently established as an actively
# discussed figure in this subreddit, so a disambiguation pass isn't worth
# building for her.
AMBIGUOUS_SURNAMES = {
    "jr", "sr", "ii", "iii", "iv", "the", "von", "van", "de",
    "bell", "adams", "allen", "brand", "corsi", "gates", "hersh", "jones",
    "kory", "lake", "duke", "wolf", "wood", "truth",
    "butler", "garrison", "griffin", "peters", "roberts", "watson", "watkins",
    "weinstein", "manning", "steele", "ventura",
    # Added 2026-08-14 after the bare-surname audit (handoff/bare_surname_audit_2026-08-13.csv):
    # "malone" is dominated by the musician Post Malone -- corpus-wide only 63 of
    # 8,656 bare hits (0.7%) are the real Robert W. Malone, the worst ratio (137x)
    # of any audited entity. The preceding-capitalized-name heuristic below only
    # catches ~47% of these (most "Post Malone" references aren't immediately
    # adjacent to "Post"), so it's not sufficient alone for this one -- full-name-
    # only is the safe fallback, same tradeoff (lower recall, high precision) as
    # every other entry in this set.
    "malone",
    # "summers" (for "Larry Summers") belongs in the ordinary-English-word group
    # above (bell/wolf/wood/duke/lake/truth), not the different-person-collision
    # group -- confirmed directly: of 150 round9-pool rows, only 35 even have it
    # capitalized ("Summers"); the other 115 are the plain lowercase season word
    # ("hot summers", "worked summers as a kid"). The preceding-capitalized-name
    # heuristic can't fix this -- it's not a competing proper name, it's a common
    # noun, so full-name-phrase matching is the only safe option here too.
    "summers",
    # "carlson" (for "Tucker Carlson", one of the original 11) -- confirmed real
    # wrong-match 2026-08-14 by Nash directly while rating the new active-learning
    # queue: comment eq3bfx9 bare-matched "Tucker Carlson" but is actually about
    # Randall Carlson (Graham Hancock's podcast co-guest, discussing a comet-impact
    # theory). The preceding-capitalized-name heuristic can't catch this class of
    # error -- "Randall" was named several comments earlier in the SAME THREAD, not
    # adjacent to this specific "Carlson" mention, so no single-comment regex can
    # resolve it. This is exactly the kind of case the project's existing
    # first-name-or-surname signature-word disambiguation machinery
    # (stage_b_consolidated_corpus_pass.py / stage_c_classify_ambiguous.py,
    # already has "hunter"/"hillary"-style clusters) is built for -- worth
    # extending to a "carlson": {"Tucker Carlson": [...], "Randall Carlson": [...]}
    # cluster rather than just falling back to full-name-only here, since bare
    # "Tucker Carlson" mentions (no "Tucker") are common enough to be worth
    # recovering. Full-name-only in the meantime, same safe-fallback tradeoff as
    # everything else in this set.
    "carlson",
    # "doctors" (for entity "America's Frontline Doctors") -- not a
    # surname at all, an ordinary plural common noun picked up because
    # _bare_surname_key() just takes the entity's last word regardless of
    # whether the entity is a person or an organization. Bare "doctors"
    # bare-matched 123,311/473,447 (26%) of the full entity-mention pool
    # built 2026-08-18 -- confirmed via spot-check that literally none of
    # a random sample even referenced the organization. Forces the
    # full-phrase match instead.
    "doctors",
}


# Common nickname -> formal-given-name variants. Needed because
# _passes_surname_disambiguation treats any capitalized word preceding/
# following the surname that isn't literally the entity's recorded given
# name as a competing person -- which wrongly flags genuine mentions like
# "Jim Fetzer" (entity "James Fetzer"), "Bill Cooper" (entity "Milton
# William Cooper"), "Mike Yeadon" (entity "Michael Yeadon"). Found
# 2026-08-18 auditing round9_unlabeled_pool.parquet's disambiguation
# fails: these three alone accounted for a meaningful share of the 1,251
# rejected rows. Not exhaustive -- covers the names that actually
# collided in this corpus's verified entity lists.
NICKNAME_EQUIVALENTS = {
    "william": {"bill", "billy", "will", "willy"},
    "robert": {"bob", "bobby", "rob", "robbie"},
    "richard": {"dick", "rick", "ricky", "rich"},
    "james": {"jim", "jimmy", "jamie"},
    "michael": {"mike", "mikey", "mick"},
    "thomas": {"tom", "tommy"},
    "david": {"dave", "davey"},
    "christopher": {"chris"},
    "steven": {"steve", "stevie"},
    "stephen": {"steve", "stevie"},
    "kenneth": {"ken", "kenny"},
    "gregory": {"greg"},
    "andrew": {"andy", "drew"},
    "theodore": {"ted", "teddy"},
    "edward": {"ed", "eddie", "ted"},
    "daniel": {"dan", "danny"},
    "joseph": {"joe", "joey"},
    "charles": {"charlie", "chuck"},
    "anthony": {"tony"},
    "francis": {"frank"},
    "raymond": {"ray"},
    "lawrence": {"larry"},
    "jonathan": {"jon", "jonny"},
    "nicholas": {"nick", "nicky"},
    "patrick": {"pat"},
    "matthew": {"matt"},
    "samuel": {"sam", "sammy"},
    "benjamin": {"ben", "benny"},
    "alexander": {"alex"},
    "jeffrey": {"jeff"},
    "kimberly": {"kim"},
    "katherine": {"kathy", "kate", "katie"},
    "deborah": {"deb", "debbie"},
    "susan": {"sue", "susie"},
    "margaret": {"maggie", "meg", "peggy"},
}
# Reverse lookup: nickname -> set of formal names it can stand for.
_NICKNAME_TO_FORMAL = {}
for _formal, _nicks in NICKNAME_EQUIVALENTS.items():
    for _nick in _nicks:
        _NICKNAME_TO_FORMAL.setdefault(_nick, set()).add(_formal)

# Titles that precede a surname without being a competing name.
TITLES = {
    "dr", "doctor", "mr", "mrs", "ms", "miss", "prof", "professor",
    "sen", "senator", "rep", "president", "gov", "governor", "judge",
    "reverend", "rev", "father", "sir", "colonel", "col", "general",
    "gen", "captain", "capt", "major", "lieutenant", "lt",
}


def _lookup_given_names(surname: str, maverick_names, consensus_names) -> set[str]:
    """Derive given name(s) for a bare-surname alias entity (e.g. "Mullis")
    by finding sibling full-name entries in the verified entity lists that
    end with the same surname (e.g. "Kary Mullis" -> "kary"). Needed
    because bare-surname aliases like UNAMBIGUOUS_MAVERICK_ALIASES ("Mullis",
    "Mikovits", ...) carry no given name of their own, so passed through
    _passes_surname_disambiguation as-is they'd reject every genuine full
    mention ("Kary Mullis said...") as a false collision.
    """
    given = set()
    for name in list(maverick_names) + list(consensus_names):
        parts = name.strip().split()
        if len(parts) >= 2 and parts[-1].lower() == surname.lower():
            given.add(re.sub(r"[.,'\"]+$", "", parts[0]).lower())
    return given


def _edit_distance_le1(a: str, b: str) -> bool:
    """True if a and b differ by at most one single-character insertion,
    deletion, or substitution. Cheap length-gated check, not a full DP
    edit-distance table -- only needs to answer <=1, not the exact value."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1 or min(la, lb) < 3:
        return False
    if la == lb:
        diffs = sum(1 for x, y in zip(a, b) if x != y)
        return diffs <= 1
    shorter, longer = (a, b) if la < lb else (b, a)
    i = j = skipped = 0
    while i < len(shorter) and j < len(longer):
        if shorter[i] != longer[j]:
            skipped += 1
            if skipped > 1:
                return False
            j += 1
        else:
            i += 1
            j += 1
    return True


_GIVEN_NAME_CACHE: dict[str, set[str]] = {}


def _looked_up_given_names(surname: str) -> set[str]:
    """Cached wrapper around _lookup_given_names -- lazily imports the
    verified entity lists (avoids a module-load-time import cycle/cost)
    and memoizes per surname since this runs per-row at scan time."""
    key = surname.lower()
    if key not in _GIVEN_NAME_CACHE:
        sys.path.insert(0, str(Path(__file__).parent))
        from maverick_authority_verified import VERIFIED_MAVERICK_AUTHORITY
        from consensus_experts_verified import VERIFIED_CONSENSUS_EXPERTS
        _GIVEN_NAME_CACHE[key] = _lookup_given_names(
            surname, VERIFIED_MAVERICK_AUTHORITY, VERIFIED_CONSENSUS_EXPERTS
        )
    return _GIVEN_NAME_CACHE[key]


def _is_bare_surname_mode(entity: str) -> bool:
    """True if _person_sql_cond() will match this entity via the bare
    surname (the mode the disambiguation check below applies to), False if
    it falls back to full-name-phrase matching (already unambiguous by
    construction -- nothing to disambiguate). Mirrors _person_sql_cond's
    own branching; kept as a separate function rather than having
    _person_sql_cond return a flag, so the (name, cond, category) tuple
    shape pull_all_entities()/scan_corpus() already consume doesn't change.

    Single-token entities (e.g. "Mullis") used to always return False here
    -- meaning bare-surname aliases went through the whole pipeline with
    NO disambiguation applied at all, not because they're safe, but because
    the check had nothing to compare against. Fixed 2026-08-18: now gated
    (and checked with a looked-up given name from a sibling full-name
    entry, e.g. "Mullis" -> "Kary") whenever such a lookup succeeds. Left
    ungated when it doesn't -- confirmed via "Tedros" (Tedros Adhanom
    Ghebreyesus, a mononym used as a FIRST name, not a surname -- the
    lookup finds no sibling "X Tedros" entry and returns empty, and gating
    with an empty given-name set caused real "Tedros Ghebreyesus" mentions
    to be wrongly rejected as colliding with an unrecognized "Tedros").
    Better to skip disambiguation than guess wrong with no information.
    """
    last = _bare_surname_key(entity)
    if len(last) < 6 or last in AMBIGUOUS_SURNAMES:
        return False
    parts = entity.strip().split()
    if len(parts) == 1:
        return bool(_looked_up_given_names(last))
    return True


def _passes_surname_disambiguation(text: str, entity: str) -> bool:
    """Reject a bare-surname match if EVERY occurrence of the surname in
    `text` looks like it belongs to someone else's full name -- checked in
    BOTH directions:
    - preceded by a different capitalized token (e.g. "Post Malone", "Bill
      Cooper" for target entity "Cooper" -- the surname is being used as
      someone else's surname), or
    - immediately followed by a different capitalized token (e.g. "Gregory
      Peck" for target entity "Dick Gregory" -- the surname is being used
      as someone ELSE's first name, the mirror-image error).
    Preceded by the target's OWN given name/initial is treated as decisive
    (clean regardless of what follows -- that's a real full-name mention).
    A single clean occurrence is enough to keep the row -- one genuine
    mention is a genuine mention even if the same comment also references
    an unrelated person who happens to share the surname.

    Validated 2026-08-13/14 (handoff/task_2026-08-13_session_handoff_round9_pipeline_and_hitl_fixes.md
    section 10) on the backward direction alone; the forward direction was
    added 2026-08-14 after Nash caught a real miss while rating the active-
    learning queue directly: "Dick Gregory" bare-matched a comment that was
    actually about "Gregory Peck" the actor ("On the Beach starring Gregory
    Peck") -- backward-only checking sees "staring" (lowercase) before
    "Gregory" and calls it clean, missing that "Peck" follows it. This is
    the exact case the original entity-disambiguation diagnosis already
    named but the first implementation didn't act on ("'Gregory' is someone
    else's first name in [Bateson/Mankiw/Mannarino], the matcher doesn't
    check word position at all" -- handoff section 10). Known limitation
    either direction: undercatches non-adjacent collisions (Robert W.
    Malone, handled via AMBIGUOUS_SURNAMES instead) -- this is a floor on
    precision, not a ceiling.
    """
    parts = entity.strip().split()
    surname = re.sub(r"[.,]+$", "", parts[-1])
    given = {re.sub(r"[.,'\"]+$", "", p).lower() for p in parts[:-1]}
    if not given:
        # Bare-surname alias entity (e.g. "Mullis") -- look up given
        # name(s) from sibling full-name entries in the verified lists
        # (e.g. "Kary Mullis") so a real full mention isn't rejected for
        # lacking a given name the entity string never carried in the
        # first place. See _lookup_given_names().
        given = _looked_up_given_names(surname)

    def _own_or_nickname(stripped: str) -> bool:
        if stripped in given or stripped == surname.lower():
            return True
        # e.g. "Bill" for given name "william"
        if _NICKNAME_TO_FORMAL.get(stripped, set()) & given:
            return True
        # Tolerate common misspellings/variant spellings of the given name
        # only (not the surname -- that would loosen real collision
        # detection). Confirmed real cases: "Anne Coulter" (entity "Ann
        # Coulter"), "Kerry Mullis"/"Kari Mullis" (entity "Mullis" ->
        # looked-up given name "kary") -- both genuine mentions rejected
        # by exact string match alone. Edit distance <=1 is deliberately
        # tight -- catches a single added/dropped/swapped letter, not a
        # different name entirely.
        return any(_edit_distance_le1(stripped, g) for g in given)

    def _is_other_name(word: str) -> bool:
        if not word or not word[0].isupper():
            return False
        stripped = word.lower().strip(".").strip("'")
        if stripped in TITLES:
            return False
        return not _own_or_nickname(stripped)

    def _is_sentence_initial(text_before_word: str) -> bool:
        """True if the word immediately after `text_before_word` opens a
        sentence/clause/list item rather than being a genuine adjacent
        proper name -- e.g. "The Collins Bloodline", "Well Ellsberg is...",
        "1. The Giuliani photo". Ordinary capitalized words at these
        positions (headline style, list items, sentence starts) were being
        misread as competing names. Found 2026-08-18 auditing
        round9_unlabeled_pool.parquet. `text_before_word` already excludes
        the word itself (caller passes preceding[:pw.start()]).
        """
        stripped_before = text_before_word.rstrip()
        if not stripped_before:
            return True  # very start of the text
        return bool(re.search(r'[.!?\n"‘’“”(]\s*(?:[-*•]|\d+[.)])?\s*$', stripped_before))

    # Case-sensitive on purpose: this checks whether the surname appears as a
    # capitalized proper noun. A case-insensitive match would also catch
    # ordinary lowercase words that happen to collide with a surname (e.g.
    # "summers" the season, for entity "Larry Summers") and, since those are
    # typically preceded by a lowercase word, get counted as a "clean"
    # occurrence -- silently passing rows that never actually reference the
    # person. (Recall for genuinely-lowercase-written mentions of the person
    # is intentionally sacrificed here -- the underlying SQL pull is already
    # case-insensitive for recall; this check only needs one clean signal to
    # keep a row, so being conservative here just means occasionally falling
    # through to "not found_any" rather than confirming via a real match.)
    occ_pat = re.compile(r"\b" + re.escape(surname) + r"\b")
    found_any = False
    for m in occ_pat.finditer(text):
        found_any = True
        preceding = text[:m.start()]
        pw = re.search(r"([A-Za-z][A-Za-z.']*)\s*$", preceding)
        preceded_by_own_name = False
        preceded_by_other_name = False
        if pw:
            word = pw.group(1)
            if word[0].isupper():
                stripped = word.lower().strip(".").strip("'")
                if stripped in TITLES:
                    pass  # neutral: a title isn't a competing name
                elif _own_or_nickname(stripped):
                    preceded_by_own_name = True
                elif _is_sentence_initial(preceding[:pw.start()]):
                    pass  # neutral: capitalized only by sentence/list position
                else:
                    preceded_by_other_name = True
        if preceded_by_own_name:
            return True  # unambiguous: the target's own full name

        following = text[m.end():]
        fw = re.match(r"\s+([A-Za-z][A-Za-z.']*)", following)  # only whitespace between --
        # a period/comma right after means end of clause, not a tight "Surname Nextword" phrase
        followed_by_other_name = bool(fw) and _is_other_name(fw.group(1))

        if not preceded_by_other_name and not followed_by_other_name:
            return True  # nothing suspicious in either direction -- clean
        # else: this occurrence looks like someone else's name either way -- check the rest
    return not found_any  # surname not actually found (shouldn't happen post-SQL-match) -- don't reject on nothing


def _person_sql_cond(entity: str) -> str:
    """Bare surname is the default (this is what actually surfaces real
    mentions — most maverick figures are referred to by surname alone, not
    full name, in casual comments). Falls back to requiring the full name
    phrase only for single/short surnames or ones in AMBIGUOUS_SURNAMES.

    No hand-picked "signature words" shortcut here: recovering bare-surname
    recall for an AMBIGUOUS_SURNAMES entity needs context words *derived from
    the corpus* (co-occurrence with confirmed full-name mentions), not guessed
    from general knowledge — not built yet, full-name-only is the safe
    fallback in the meantime.
    """
    parts = entity.strip().split()
    if len(parts) == 1:
        key = entity.lower()
        escaped = re.escape(key).replace("'", "''")
        return f"regexp_matches(lower(text), '\\b{escaped}\\b')"

    last = _bare_surname_key(entity)
    if len(last) >= 6 and last not in AMBIGUOUS_SURNAMES:
        escaped = re.escape(last).replace("'", "''")
        return f"regexp_matches(lower(text), '\\b{escaped}\\b')"

    return _full_name_sql_cond(entity)


def _domain_key(domain: str) -> str:
    """Strip TLD to get a matchable key, e.g. 'naturalnews.com' → 'naturalnews'."""
    key = re.sub(r"\.(com|org|net|io|co|ca|uk|gov|edu|info|biz)(\.[a-z]{2})?$", "", domain.lower())
    # Remove leading 'www.' if present
    key = re.sub(r"^www\.", "", key)
    return key


def _collect_excluded_pairs() -> tuple[set, set]:
    """Returns (excluded_id_entity_pairs, excluded_text_entity_pairs) --
    NOT a bare id set. A comment can genuinely mention multiple entities;
    already having a labeled row for that comment under one entity's
    [ENTITY: X] conditioning does not make it stale for a DIFFERENT
    entity's conditioning -- that's a distinct training example (fixed
    2026-08-12, was excluding by id alone and silently discarding real,
    still-needed rows for any entity that shared an id with an
    already-used comment).

    Two separate sets because the canonical training parquets
    (stance_classifier_training_data*.parquet) have no `id` column at all
    -- only `text` -- while HITL queue CSVs do have `id`. Checked directly,
    not assumed: confirm before "fixing" this again.
    """
    id_pairs = set()
    text_pairs = set()
    for path in Path("data/processed").glob("stance_classifier_training_data*.parquet"):
        try:
            cols = pd.read_parquet(path).columns
            if "target_entity" not in cols:
                continue
            if "id" in cols:
                df = pd.read_parquet(path, columns=["id", "target_entity"])
                df = df.dropna(subset=["id", "target_entity"])
                id_pairs.update(zip(df["id"].astype(str), df["target_entity"].str.lower()))
            elif "text" in cols:
                df = pd.read_parquet(path, columns=["text", "target_entity"])
                df = df.dropna(subset=["text", "target_entity"])
                text_pairs.update(zip(df["text"].astype(str), df["target_entity"].str.lower()))
        except Exception:
            pass
    for path in Path("data/hitl").glob("queue_*.csv"):
        try:
            cols = pd.read_csv(path, nrows=0).columns
            if "target_entity" not in cols or "id" not in cols:
                continue
            df = pd.read_csv(path, usecols=["id", "target_entity"])
            df = df.dropna(subset=["id", "target_entity"])
            id_pairs.update(zip(df["id"].astype(str), df["target_entity"].str.lower()))
        except Exception:
            pass
    return id_pairs, text_pairs


def _collect_excluded_ids() -> set:
    """Deprecated shape -- kept only so anything still importing this name
    doesn't hard-crash. Prefer _collect_excluded_pairs()."""
    id_pairs, _ = _collect_excluded_pairs()
    return {i for i, _ in id_pairs}


def build_person_entities(skip_original_11: bool = True) -> list[tuple[str, str, str]]:
    """Return list of (canonical_name, sql_condition, category).

    Source: the hand-reviewed VERIFIED_MAVERICK_AUTHORITY / _ADDITIONS /
    VERIFIED_CONSENSUS_EXPERTS lists (already decided, not raw candidates),
    filtered by real combined long+short doc_count (see DOC_COUNTS_FILE /
    MIN_COMBINED_DOC_COUNT above) — no new per-entity judgment calls, just a
    uniform frequency floor applied to entities already reviewed.

    skip_original_11: when True (default, matches every existing caller's
    behavior), SKIP_ENTITIES drops the 11 entities already covered by
    training/val data from early project rounds -- correct for THIS
    module's original purpose (don't generate redundant new HITL labeling
    requests for ground already covered). Pass False for full-corpus
    INFERENCE coverage instead (e.g. build_full_entity_mention_pool.py) --
    found 2026-08-18 that leaving this on silently dropped Tucker Carlson,
    Alex Jones, Roger Stone, Matt Gaetz, Aaron Swartz, Bill Gates, and
    WikiLeaks entirely from a pool meant to cover every verified entity
    (Assange/Snowden/Greenwald/Fauci partially survived only by accident,
    via a bare-alias string that happens not to match the literal
    SKIP_ENTITIES string, then get relabeled to the full canonical name on
    display -- an inconsistency, not by design).
    """
    sys.path.insert(0, str(Path(__file__).parent))
    from maverick_authority_verified import VERIFIED_MAVERICK_AUTHORITY
    from consensus_experts_verified import VERIFIED_CONSENSUS_EXPERTS
    # VERIFIED_MAVERICK_ADDITIONS deliberately excluded here: it's messy alias
    # patterns (possessives, misspellings, hashtags) for entities already
    # covered by their clean canonical form in VERIFIED_MAVERICK_AUTHORITY —
    # using an alias like "Edward Snowden's" as the primary match name would
    # badly under-match (regex would require the literal possessive).

    maverick_names = set(VERIFIED_MAVERICK_AUTHORITY)
    consensus_names = set(VERIFIED_CONSENSUS_EXPERTS)
    all_names = {n: "maverick" for n in maverick_names}
    for n in consensus_names:
        all_names[n] = "consensus" if n not in all_names else all_names[n] + ";consensus"

    doc_counts = pd.read_csv(DOC_COUNTS_FILE).set_index("best_identity")["combined_doc_count"].to_dict()
    review = pd.read_csv("data/processed/entity_final_review.csv")
    best_identity_lookup = review.set_index(review["entity"].str.lower())["best_identity"].to_dict()
    # entity_frequency_full_corpus.csv is the authoritative full-corpus count
    # (see handoff docs) -- used as a fallback below for names whose
    # best_identity resolution is missing/blank, since DOC_COUNTS_FILE has
    # real coverage gaps for exactly those (confirmed 2026-08-14: Mark Lane,
    # Victor Marchetti, Rashid Buttar, Stefan Molyneux all have real corpus
    # presence here despite no row in DOC_COUNTS_FILE keyed either way).
    freq_lookup = (
        pd.read_csv("data/processed/entity_frequency_full_corpus.csv")
        .assign(entity_lower=lambda d: d["entity"].str.lower())
        .set_index("entity_lower")["combined"].to_dict()
    )
    # SKIP_PERSONS names must be resolved through best_identity too, not just
    # matched literally: consensus_experts_verified.py deliberately includes
    # alias variants of skipped people (e.g. "Steven Hawking" misspelling,
    # "Sagan"/"Carl Sagan's" bare/possessive aliases of Carl Sagan) that don't
    # equal the canonical SKIP_PERSONS string but resolve to the same person.
    skip_identities = {best_identity_lookup.get(n.lower()) for n in SKIP_PERSONS} - {None}

    entities = []
    seen = set()
    for name, cat in all_names.items():
        if (skip_original_11 and name.lower() in SKIP_ENTITIES) or name in SKIP_PERSONS:
            continue
        best_id = best_identity_lookup.get(name.lower())
        # pd.notna(), not a bare truthiness check: best_id can be a literal
        # float NaN (a real row in entity_final_review.csv with a blank
        # best_identity cell, distinct from "no row at all" which gives
        # None) -- and bool(float('nan')) is True in Python, so `best_id or
        # name`/`if best_id` silently treated NaN as a valid resolved
        # identity instead of falling back to `name`. Found 2026-08-14:
        # this collapsed Mark Lane/Victor Marchetti/Rashid Buttar/Stefan
        # Molyneux (and Mark Dice, separately already excluded via
        # SKIP_PERSONS) onto the same bad dedup key, and independently
        # zeroed their doc-count lookup -- both silently dropped all four
        # from every pull this project has ever run, despite each having
        # 129-446 real corpus mentions (entity_frequency_full_corpus.csv).
        has_best_id = pd.notna(best_id)
        if has_best_id and best_id in skip_identities:
            continue
        count = doc_counts.get(best_id, 0) if has_best_id else 0
        if count < MIN_COMBINED_DOC_COUNT:
            count = freq_lookup.get((best_id if has_best_id else name).lower(), 0)
        if count < MIN_COMBINED_DOC_COUNT:
            continue
        # Dedup by best_identity (aliases in VERIFIED_MAVERICK_ADDITIONS like
        # "Ed Snowden" would otherwise create a second, redundant entry for
        # the same person already covered by the canonical form).
        dedup_key = best_id if has_best_id else name
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        cond = _person_sql_cond(name)
        # Use the resolved canonical identity as the label wherever we have
        # one, not whichever raw alias happened to survive dedup -- found
        # 2026-08-14 (Nash noticed a "Folta" link resolving to bare surname
        # "Folta" instead of "Kevin Folta" as target_entity): 41 entities had
        # this mismatch, all cosmetic/label-only, matching pattern was
        # unaffected since `cond` is still built from whichever raw name
        # survived.
        display_name = best_id if has_best_id else name
        entities.append((display_name, cond, cat))
    return entities


def build_domain_entities() -> list[tuple[str, str, str]]:
    """Return list of (domain_name, sql_condition, category).

    Always matches the full domain string (e.g. "nature.com"), both sides
    word-boundary-anchored -- NOT a bare stripped key. Domains almost
    always appear as literal strings in text (people cite/link the actual
    domain), unlike person names where bare-surname matching is the
    common real-world case. Bare-key matching used to be the default here
    and was a real, repeated bug source: state.gov/"state" alone matched
    1,324,296 rows (more than the entire 476K-row entity pool combined),
    science.org/"science" 276,129, house.gov/"house" 265,114, and more
    (2026-08-18) -- an AMBIGUOUS_DOMAIN_KEYS blocklist was tried first but
    that's the wrong shape of fix (chasing individual bad words instead of
    fixing the wrong default). Detecting genuine bare-organization-name
    mentions ("wrote a piece for Nature", no ".com") is real but rare
    compared to domain citations, and needs the same kind of strict,
    signature-word-gated disambiguation the person side uses for short
    surnames -- not attempted here, deliberately out of scope until that
    mechanism exists; recall loss on bare-name mentions is the accepted
    tradeoff for not re-introducing the false-match risk.
    """
    dom = pd.read_csv(DOM_FILE)
    dom = dom[dom["category"].isin(DOMAIN_CATS)]
    dom = dom[~dom["domain"].isin(SKIP_DOMAINS)]

    entities = []
    for _, row in dom.iterrows():
        domain = row["domain"]
        escaped = re.escape(domain.lower()).replace("'", "''")
        cond = f"regexp_matches(lower(text), '\\b{escaped}\\b')"
        entities.append((domain, cond, row["category"]))
    return entities


def pull_all_entities(
    con,
    entities: list[tuple[str, str, str]],
    source_kind: str,
    excluded_id_pairs: set,
    excluded_text_pairs: set,
    max_per_entity: int,
    seed: int,
    disambiguate: bool = False,
) -> pd.DataFrame:
    """Single-pass scan: build one big CASE/WHEN query so the parquet is read once."""
    if not entities:
        return pd.DataFrame()

    # Build: CASE WHEN <cond1> THEN '<name1>' WHEN ... ELSE NULL END AS target_entity
    # Only grab rows that match at least one entity
    when_clauses = "\n    ".join(
        f"WHEN ({cond}) THEN '{name.replace(chr(39), chr(39)+chr(39))}'"
        for name, cond, _ in entities
    )
    any_match = " OR ".join(f"({cond})" for _, cond, _ in entities)
    cat_map = {name: cats for name, cond, cats in entities}

    q = f"""
        SELECT id, text, parent_id, link_id,
               CASE
                   {when_clauses}
               ELSE NULL
               END AS target_entity
        FROM read_parquet('{EMPATH}')
        WHERE text IS NOT NULL
          AND length(trim(text)) > 50
          AND ({any_match})
    """
    print(f"  Scanning parquet for {len(entities)} {source_kind} entities ...", flush=True)
    df = con.execute(q).df()
    df = df[df["target_entity"].notna()]
    # Exclude by (id, entity) AND (text, entity) pair -- not by bare id/text,
    # since the same comment can be legitimate new data for a different
    # entity's conditioning (fixed 2026-08-12).
    id_key = list(zip(df["id"].astype(str), df["target_entity"].str.lower()))
    text_key = list(zip(df["text"].astype(str), df["target_entity"].str.lower()))
    keep = [
        (idk not in excluded_id_pairs) and (txk not in excluded_text_pairs)
        for idk, txk in zip(id_key, text_key)
    ]
    df = df[keep]
    print(f"  {len(df):,} rows after dedup", flush=True)

    # Cap per entity
    frames = []
    for name, _, cats in entities:
        chunk = df[df["target_entity"] == name]
        if disambiguate and _is_bare_surname_mode(name):
            before = len(chunk)
            chunk = chunk[chunk["text"].apply(lambda t: _passes_surname_disambiguation(t, name))]
            dropped = before - len(chunk)
            if dropped:
                print(f"    {name}: dropped {dropped} likely wrong-entity rows (surname disambiguation)")
        if len(chunk) == 0:
            print(f"    {name}: 0 rows")
            continue
        n = min(max_per_entity, len(chunk))
        sampled = chunk.sample(n=n, random_state=seed)
        sampled = sampled.copy()
        sampled["entity_category"] = cats
        sampled["source_kind"] = source_kind
        frames.append(sampled)
        print(f"    {name}: {n} rows")

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/hitl/queue_expanded_entity_val_r1.csv")
    ap.add_argument("--seed", type=int, default=RANDOM_STATE)
    ap.add_argument("--target", type=int, default=TARGET_ROWS,
                    help="Target number of rows in output")
    ap.add_argument("--max_per_entity", type=int, default=MAX_PER_ENTITY)
    args = ap.parse_args()

    seed = args.seed

    # Refuse to overwrite a queue that already has human labels in it
    out_path = Path(args.out)
    if out_path.exists():
        existing = pd.read_csv(out_path)
        n_labeled = existing["human_label"].notna().sum() if "human_label" in existing.columns else 0
        if n_labeled > 0:
            print(f"ERROR: {args.out} already has {n_labeled} human labels — refusing to overwrite.")
            print("Use --out to specify a different output path (e.g. queue_expanded_entity_val_r2.csv).")
            return

    print("Collecting excluded (id/text, entity) pairs ...")
    excluded_id_pairs, excluded_text_pairs = _collect_excluded_pairs()
    print(f"  {len(excluded_id_pairs):,} id-pairs, {len(excluded_text_pairs):,} text-pairs to exclude")

    person_entities = build_person_entities()
    domain_entities = build_domain_entities()
    print(f"Person entities: {len(person_entities)}")
    print(f"Domain entities: {len(domain_entities)}")

    con = duckdb.connect()

    print("\n--- Person entities (single scan) ---")
    person_df = pull_all_entities(con, person_entities, "person_maverick", excluded_id_pairs, excluded_text_pairs, args.max_per_entity, seed, disambiguate=True)

    print("\n--- Domain entities (single scan) ---")
    domain_df = pull_all_entities(con, domain_entities, "domain_source", excluded_id_pairs, excluded_text_pairs, args.max_per_entity, seed)

    frames = [df for df in [person_df, domain_df] if len(df) > 0]

    if not frames:
        print("No rows found — check EMPATH path and filters.")
        return

    pool = pd.concat(frames, ignore_index=True)
    pool = pool.drop_duplicates(subset=["id"])
    n_entities = pool["target_entity"].nunique()
    print(f"\nRaw pool: {len(pool):,} rows across {n_entities} entities")

    # Subsample to target, balanced by entity_category. Within each category,
    # guarantee at least 1 row per matched entity before filling any
    # remaining budget randomly -- a flat chunk.sample() over the whole
    # category pool (the old approach) has zero guarantee any specific
    # entity survives; found 2026-08-12 via Jesse Ventura/David Duke
    # (thousands of real corpus matches each, both randomly zeroed out of
    # a 410-row batch by category-level sampling variance, not a matching
    # bug -- confirmed by tracing the raw CASE/WHEN scan directly).
    cats_present = pool["entity_category"].unique()
    per_cat = max(1, args.target // len(cats_present))

    sampled = []
    for cat in cats_present:
        chunk = pool[pool["entity_category"] == cat]
        cat_target = min(len(chunk), per_cat)
        entities_in_cat = chunk["target_entity"].unique()

        guaranteed = pd.concat(
            [chunk[chunk["target_entity"] == e].sample(n=1, random_state=seed) for e in entities_in_cat],
            ignore_index=True,
        )
        if len(guaranteed) >= cat_target:
            # More distinct entities than this category's budget -- keep
            # coverage (1/entity) rather than depth, trim down to budget.
            sampled.append(guaranteed.sample(n=cat_target, random_state=seed))
        else:
            remaining_budget = cat_target - len(guaranteed)
            rest = chunk[~chunk["id"].astype(str).isin(guaranteed["id"].astype(str))]
            topup = rest.sample(n=min(remaining_budget, len(rest)), random_state=seed) if len(rest) else rest
            sampled.append(pd.concat([guaranteed, topup], ignore_index=True))

    batch = pd.concat(sampled, ignore_index=True)

    # Top up to target from remaining rows if we're short
    if len(batch) < args.target:
        used_ids = set(batch["id"].astype(str))
        remainder = pool[~pool["id"].astype(str).isin(used_ids)]
        topup = min(args.target - len(batch), len(remainder))
        if topup > 0:
            batch = pd.concat(
                [batch, remainder.sample(n=topup, random_state=seed)],
                ignore_index=True
            )

    # Final shuffle
    batch = batch.sample(frac=1, random_state=seed).reset_index(drop=True)

    # Format for HITL rater
    out = pd.DataFrame({
        "id": batch["id"],
        "full_text": batch["text"],
        "target_entity": batch["target_entity"],
        "entity_category": batch["entity_category"],
        "source_kind": batch["source_kind"],
        "parent_id": batch["parent_id"] if "parent_id" in batch.columns else None,
        "link_id": batch["link_id"] if "link_id" in batch.columns else None,
        "human_label": None,
        "notes": None,
        "rater_id": None,
    })

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"\nSaved {len(out):,} rows → {args.out}")
    print("\nEntity category breakdown:")
    print(out["entity_category"].value_counts().to_string())
    print("\nTop entities by row count:")
    print(out["target_entity"].value_counts().head(30).to_string())


if __name__ == "__main__":
    main()
