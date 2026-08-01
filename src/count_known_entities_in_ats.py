"""count_known_entities_in_ats.py

Counts mentions of the SAME entity names already known from the r/conspiracy
side (canonical_entity_mentions.csv + other_entities_mentions.csv +
missing_entity_candidates.csv, 224 names combined, deduped) against the ATS
corpus. Deliberately NOT fresh NER mining -- this only asks "how often does a
name we already track on reddit show up in ATS," not "what new entities does
ATS have that reddit doesn't." A comparable, apples-to-apples entity view
across both corpora for now; discovering ATS-specific new entities is a
separate, bigger task if wanted later.

Same case-insensitive whole-word regex approach already verified this session
(entity_monthly's construction, and the direct spot-checks done for Trump/
HRC/Netanyahu/AOC) -- longest names first so multi-word names win over their
own substrings (e.g. "Bill Gates" matches before bare "Gates").

Output: data/processed/ats_known_entity_counts.csv
  entity, ats_mentions
"""
import csv
import re
import duckdb

NAMES_PATH = "data/processed/known_entity_names.csv"
CORPUS_PATH = "data/processed/ats_comments_final.parquet"
OUT_PATH = "data/processed/ats_known_entity_counts.csv"

with open(NAMES_PATH, encoding="utf-8") as f:
    names = [row["entity"].strip() for row in csv.DictReader(f) if row["entity"].strip()]

names.sort(key=len, reverse=True)
escaped = [re.escape(n) for n in names]
pattern = r"\b(" + "|".join(escaped) + r")\b"

con = duckdb.connect()
con.execute("PRAGMA memory_limit='4GB'")

print(f"Counting {len(names)} known entity names against {CORPUS_PATH}...")
rows = con.execute(
    """
    SELECT lower(matched) AS matched_lower, COUNT(*) AS mentions
    FROM (
        SELECT regexp_extract(body, ?, 1, 'i') AS matched
        FROM read_parquet(?)
        WHERE body IS NOT NULL
    )
    WHERE matched != ''
    GROUP BY 1
    """,
    [pattern, CORPUS_PATH],
).fetchall()

# Map back to original (cased) name -- pick whichever known name matches case-insensitively.
lower_to_original = {n.lower(): n for n in names}
counts = {lower_to_original.get(m, m): c for m, c in rows}

if "WHO" in counts:
    # Same ambiguity handled in build_drilldown_backend_db.py's entity_monthly query --
    # case-insensitive 'who' collides with the common pronoun. Redo as an exact-case count.
    who_exact = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE regexp_matches(body, '\\bWHO\\b')",
        [CORPUS_PATH],
    ).fetchone()[0]
    print(f"WHO: case-insensitive gave {counts['WHO']:,}, exact-case gives {who_exact:,} -- using exact-case.")
    counts["WHO"] = who_exact

with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["entity", "ats_mentions"])
    for name in names:
        w.writerow([name, counts.get(name, 0)])

print(f"Saved {OUT_PATH}")
nonzero = sum(1 for n in names if counts.get(n, 0) > 0)
print(f"{nonzero}/{len(names)} known entities appear at least once in ATS.")
