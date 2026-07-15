"""Stage A of the entity-disambiguation work program (see ANTIGRAVITY_HANDOFF.md
§12 for the full staged plan). Zero corpus access, zero API calls -- flags
single-token entities that are just ordinary English words (spaCy NER
false positives: "Universe", "Funny", "GTFO", bare "Oxford", etc.) using the
local macOS system dictionary (/usr/share/dict/words, 235,976 words, no
internet needed).

Deliberately restricted to single-token entities only: multi-word phrases
composed of common words are often still genuine named entities ("Natural
News", "Project Veritas"), so flagging those would risk false positives on
real candidates. Single bare tokens exactly matching a dictionary word are a
much safer signal.

This does not delete anything -- it adds an `is_dictionary_word` column so
later stages (and human review) can deprioritize these without losing them.

Input:  data/processed/entity_unbucketed_with_context.csv
Output: data/processed/entity_stage_a_filtered.csv
"""
import re

import pandas as pd

IN_PATH = "data/processed/entity_unbucketed_with_context.csv"
OUT_PATH = "data/processed/entity_stage_a_filtered.csv"
WORDLIST_PATH = "/usr/share/dict/words"


def load_wordlist():
    """The system wordlist (Webster's web2) mixes true common nouns with a
    proper-names supplement, both alphabetized together. Casing in the file
    is the only signal distinguishing them: "universe"/"funny" appear only
    lowercase (true common words); "Bernie" appears only capitalized
    (proper-name-only entry, e.g. from a biographical-names supplement);
    "Bill"/"bill" appear both ways (genuinely dual-purpose). So: only count
    a word as "ordinary" if its lowercase form is present in the file AS
    LOWERCASE -- a word that's exclusively capitalized in the source file is
    a name, not flagged as junk here even though `str.lower()` would match
    it case-insensitively."""
    with open(WORDLIST_PATH, encoding="utf-8", errors="ignore") as f:
        raw_words = {line.strip() for line in f if line.strip()}
    lowercase_entries = {w for w in raw_words if w.islower()}
    return lowercase_entries


def is_single_token(entity):
    return bool(re.fullmatch(r"[A-Za-z]+", entity.strip()))


def main():
    df = pd.read_csv(IN_PATH)
    wordlist = load_wordlist()
    print(f"Loaded {len(wordlist)} dictionary words from {WORDLIST_PATH}")

    df["is_single_token"] = df["entity"].astype(str).map(is_single_token)
    df["is_dictionary_word"] = df.apply(
        lambda r: r["is_single_token"] and r["entity"].strip().lower() in wordlist,
        axis=1,
    )

    # Dictionary-word status alone is too noisy to act on directly: common
    # English words and surnames overlap heavily (Tucker/Rich/Sanders/Delta/
    # Times/Sun are all real, frequently-cited entities that also happen to
    # be ordinary words). Only treat as *likely pure junk* when there's no
    # independent evidence of entityhood -- i.e. Tier 1 found no Wikipedia
    # match at all. If it resolved to something, dictionary-word status is
    # just noted (dual-purpose), not treated as exclusionary.
    has_wp_match = df["wp_title"].notna() & (df["wp_title"] != "")
    df["likely_pure_junk"] = df["is_dictionary_word"] & ~has_wp_match
    df["dual_purpose_word"] = df["is_dictionary_word"] & has_wp_match

    print(f"is_dictionary_word (raw signal, noisy): {df['is_dictionary_word'].sum()}")
    print(f"likely_pure_junk (dictionary word AND no Wikipedia match at all): {df['likely_pure_junk'].sum()}")
    print(f"dual_purpose_word (dictionary word BUT has a real Wikipedia match -- NOT junk): {df['dual_purpose_word'].sum()}")
    print(f"\nSample likely_pure_junk (should be genuine noise like Universe/Funny/GTFO):")
    print(df[df["likely_pure_junk"]].sort_values("doc_count", ascending=False)
          [["entity", "doc_count"]].head(20).to_string(index=False))
    print(f"\nSample dual_purpose_word (real entities that happen to share a common word -- keep these):")
    print(df[df["dual_purpose_word"]].sort_values("doc_count", ascending=False)
          [["entity", "doc_count", "wp_title"]].head(15).to_string(index=False))

    df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(df)} rows (all rows kept, just flagged) to {OUT_PATH}")


if __name__ == "__main__":
    main()
