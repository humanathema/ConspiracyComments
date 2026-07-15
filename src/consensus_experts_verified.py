"""consensus_experts_verified.py

Manually curated by Nash (via Claude, 2026-07-15) to replace the
contaminated `consensus` residual category in
`src/refine_thesis_models.py::load_entities_split()`.

BACKGROUND: the original script split `mainstream_expert_authority`-
bucketed entities into `canon` (matches a hardcoded CANONICAL_EXPERTS
list of historical/classical figures) and `consensus` (EVERYTHING ELSE
left over). That "everything else" catch-all is what caused the
contamination: it silently absorbed genuine contrarians/skeptics
(William Happer, Judith Curry, Peter Gøtzsche...), academic journal
names mismatched into the entity list (JAMA Cardiology, BMJ Open...),
historical/deceased pre-1990s figures who belong closer to "canon" than
"contemporary consensus" (Oppenheimer, Karl Popper, Albert Sabin...),
political/legal/intelligence figures who aren't scientific/institutional
experts at all (Merkel, Dershowitz, Robert Mercer...), and figures who
are usually invoked in r/conspiracy as VILLAINS/targets of suspicion
rather than trusted authorities (Yuval Noah Harari, Ralph Baric).

This file replaces the catch-all with an explicit, small, high-
confidence ALLOWLIST: only contemporary (post-1995-ish), institutional,
scientific/public-health figures who are cited approvingly as
"the establishment says X" -- the actual construct the analysis is
trying to measure (CDC directors, NIH officials, mainstream virologists,
Nobel laureates in an establishment institutional role, etc).

Every name below is a verified variant/alias of a real person,
cross-checked against corpus doc_count in entity_final_review.csv on
2026-07-15. Everything previously in the 147-entity residual list that
is NOT in this list should be treated as EXCLUDED from consensus_expert
-- do not add anything back into this category without the same kind of
individual review documented in ANTIGRAVITY_HANDOFF.md.

**CORRECTION (2026-07-15, same day)**: the first version of this list
(19 people) was built by only reviewing entities the Wikipedia-category
bucketing pipeline (`stage_e_wikipedia_categories.py`) had already tagged
`mainstream_expert_authority`. That pipeline requires 2+ corroborating
categories (or a tier-1 match on a sparse page) before assigning ANY
bucket -- so entities whose Wikipedia page has many/diffuse categories,
or a weak category match, get `final_bucket_guess = blank` and are
INVISIBLE to any bucket-based search, no matter how systematic. This
silently excluded **Anthony Fauci** (doc_count 975 across name variants
-- one of the single highest-frequency entities in the entire corpus,
and arguably the most obviously relevant "establishment consensus
expert" for a COVID-era conspiracy analysis) along with Deborah Birx,
Paul Offit, Scott Gottlieb, Jenny Harries, and Peter Hotez. Found by
searching `wp_description` directly for institutional-science/health
language across ALL entities regardless of `final_bucket_guess` --
do not trust `final_bucket_guess`/`weak_hint_bucket_guess` as a complete
census of candidates for this category ever again; they're a useful
starting point, not a ceiling. **This same blind spot likely exists for
non-health institutional experts too** (physics, economics, other
government-scientist roles) -- the keyword search that caught the names
above (`immunolog|epidemiolog|virolog|physician|infectious disease|
public health|pediatric|microbiolog|toxicolog|CDC|NIH|WHO official|FDA|
Surgeon General|...`) was health/COVID-focused because that's where the
obvious miss was, not a comprehensive re-scan of the full 15,988-entity
file. **Staged, not done**: rerun the same direct wp_description
keyword-search approach with broader terms (physicist, economist,
engineer, agency director, government scientist, etc.) across the WHOLE
entity_final_review.csv with no bucket-field filtering at all, and
manually review the hits the same way this correction was done -- see
ANTIGRAVITY_HANDOFF.md §15(b), updated 2026-07-15.
"""

VERIFIED_CONSENSUS_EXPERTS = [
    # CDC / NIH / national public-health officials (contemporary, institutional)
    "Anthony Fauci", "Dr Fauci", "Tony Fauci",  # doc_count ~1,258 combined -- the single biggest miss, added 2026-07-15
    "Deborah Birx", "Birx",
    "Rochelle Walensky", "Walensky",
    "Francis Collins",
    "Julie Gerberding",
    "Christine Grady",
    "Scott Gottlieb",  # former FDA Commissioner
    "Jenny Harries",  # UK Deputy Chief Medical Officer
    "Tegnell",  # Anders Tegnell, Swedish state epidemiologist -- official capacity
    "Wu Zunyou", "Zunyou",  # Chinese CDC chief epidemiologist -- official capacity
    "Tedros Adhanom Ghebreyesus", "Tedros Adhanom", "Tedros",  # WHO Director-General
    "Janet Woodcock",  # FDA senior official / acting commissioner
    "Marty Makary", "Makary",  # FDA Commissioner
    "Frank DeStefano",  # CDC vaccine-safety epidemiologist
    "Robert Kadlec",  # HHS Assistant Secretary for Preparedness and Response
    "Katalin Karikó",  # Nobel laureate, mRNA vaccine co-pioneer with Drew Weissman (below)

    # CDC Director / FDA Commissioner / US Surgeon General historical roster,
    # 2008-2026 -- verified via Wikipedia wikitext (embedded primary-source
    # refs) 2026-07-15, full sourced table in data/processed/us_health_office_rosters.csv.
    # Excludes very-brief/obscure acting officials unlikely to appear in the
    # corpus (Kyle Diamantas, Stephanie Haridopolos, Matthew Buzzelli, Susan
    # Orsega, Denise Hinton, Sylvia Trent-Adams, Frank M. Torti) -- add from
    # the roster CSV if doc_count check shows they're actually mentioned.
    "Richard Besser", "Anne Schuchat", "Brenda Fitzgerald",
    "Robert R. Redfield",  # CAUTION: entity_final_review.csv has an unresolved AMBIGUOUS_NAME collision with a historical anthropologist of the same name (1897-1958) -- disambiguate by context before trusting a bare "Redfield" match
    "Nirav D. Shah", "Susan Monarez", "Jim O'Neill",
    "Joshua M. Sharfstein", "Margaret Hamburg", "Stephen Ostroff",
    "Norman Sharpless", "Brett Giroir", "Stephen Hahn",
    "Steven K. Galson", "Regina Benjamin", "Boris Lushniak", "Vivek Murthy",
    # NOTE: Mandy Cohen and Jerome Adams were already effectively covered
    # (Mandy Cohen added below; Jerome Adams is genuinely new, added below)
    "Mandy Cohen", "Jerome Adams",
    # Jay Bhattacharya is DELIBERATELY EXCLUDED despite being the current
    # (Feb 2026-incumbent) CDC Director: for nearly the entire 2008-2026
    # corpus window he was known as a lockdown-policy CONTRARIAN
    # (Great Barrington Declaration co-author), not an institutional
    # consensus figure -- a static binary flag would misclassify almost all
    # of his corpus mentions, which predate his appointment. This is a
    # genuine time-varying-status edge case the current binary
    # maverick/consensus architecture can't represent; flagging rather than
    # forcing a wrong answer either way. Needs a tenure-aware treatment if
    # it matters to the thesis (see mainstream_expert_corpus_briefing's
    # own schema, which tracks tenure_start/tenure_end for exactly this
    # reason).
    "Stanley Plotkin",  # "father of modern vaccines", mainstream vaccinologist

    # Mainstream/establishment virologists, immunologists, epidemiologists
    "David Baltimore",
    "Robert Gallo",
    "Christian Drosten", "Drosten",
    "Amesh Adalja",
    "Angela Rasmussen",
    "Michael Osterholm",
    "Drew Weissman",
    "Tim Spector",
    "Kevin Folta", "Folta",
    "Charlotte Thålin",
    "Andrew Read",
    "John Oxford",
    "Paul Offit",  # pediatric immunologist, vaccine-safety establishment figure
    "Peter Hotez",  # pediatrician/vaccine scientist, frequent establishment-vs-antivax discourse figure

    # Globally-recognized mainstream science establishment figures
    "Neil Degrasse Tyson",
    "Stephen Hawking", "Steven Hawking", "Hawking",
    "Carl Sagan", "Carl Sagan's", "Sagan",  # science-communicator predecessor to Tyson, same role in public discourse
    "James Hansen",  # NASA climate scientist, mainstream climate-science establishment
    "Kevin Trenberth",  # NCAR climate scientist, mainstream climate-science establishment
    "Satoshi Ōmura",  # Nobel laureate biochemist (co-discovered ivermectin) -- borderline given ivermectin's own conspiracy-adjacent baggage, included as he is not personally a COVID contrarian

    # Mainstream/establishment economists (Fed chairs, Nobel laureates) --
    # added 2026-07-15 per the broadened institutional-consensus search;
    # economics is a distinct domain from health/science but the same
    # "institution says X" framing applies
    "Janet Yellen", "Yellen",  # Fed Chair, Treasury Secretary
    "Alan Greenspan", "Greenspan",  # Fed Chair 1987-2006
    "Ben Bernanke", "Bernanke",  # Fed Chair 2006-2014
    "Lawrence Summers", "Larry Summers",  # Treasury Secretary, Harvard president
    "Paul Krugman", "Krugman",  # Nobel laureate economist
    "Gary Becker",  # Nobel laureate economist (Chicago school)
    "John Kenneth Galbraith",  # mainstream Keynesian economist, publicly relevant into the 2000s
]

# EXPLICITLY CONSIDERED AND EXCLUDED during the 2026-07-15 broadened scan --
# these all have scientist/physician/institutional-sounding wp_descriptions
# and WOULD match a naive keyword filter, but are contrarian/critical
# figures relative to mainstream consensus on the specific issues they're
# associated with in this corpus, not neutral establishment voices. Listed
# here so nobody re-adds them without re-litigating the same judgment call:
# Jay Bhattacharya, Scott Atlas, Vladimir Zelenko/Zelenko, Paul Marik,
# Pierre Kory, Geert Vanden Bossche, John Ioannidis/P.A. Ioannidis,
# Roy Spencer, John Christy (both climate contrarians, UAH satellite data),
# Chris Exley/Christopher Exley, Martin Pall, Diane Harper, Angus Dalgleish,
# Tom Jefferson (the epidemiologist, not the president), Vinay Prasad,
# Kary Mullis/Mullis/Kerry Mullis, Suzanne Humphries, Wolfgang Wodarg,
# Marcia Angell, Frances Haugen (whistleblower, not institutional),
# John Lott, Richard Wolff, Charles Krauthammer (commentator, not active
# scientist), Sidney Gottlieb/Bruce Ivins/Colin A. Ross/John Mack
# (CIA/fringe-adjacent, not consensus), Norman Finkelstein, Peter Dale
# Scott, Sam Harris, Richard Dawkins/Dawkins (combative public commentator,
# not institutional-consensus framing), Zbigniew Brzezinski/Condoleezza
# Rice/Samantha Power (political/diplomatic, not scientific), John
# Brennan/William Colby/Louis Freeh/Steve Kappes/Dov Zakheim/John
# Poindexter (intelligence/defense officials, not science-consensus
# framing), Kash Patel, Eric Schmidt.
#
# GAP FOUND 2026-07-15 (via Antigravity's mainstream_expert_augmented_superset.csv
# pull): Ralph Baric and Yuval Noah Harari were excluded via judgment in
# this file's docstring (see top of file) but never actually added to
# THIS list, which is the one downstream scripts/agents parse as the
# machine-readable blocklist. Baric surfaced again as a candidate in the
# augmented superset as a result. Adding both here now: Ralph Baric,
# Ralph S. Baric (villain/lab-leak-suspicion figure, not neutrally-cited
# consensus authority), Yuval Noah Harari, Yuval Harari, Harari (WEF-linked
# target/villain in this corpus's discourse, not neutrally-cited).
#
# ALSO FOUND 2026-07-15, NOT YET RESOLVED -- needs individual review, not
# a blocklist entry (these are either genuinely ambiguous or represent a
# new failure MODE, not just missing names): Peter Duesberg (academy
# membership predates his later HIV/AIDS-denialist reputation -- already
# correctly bucketed maverick_authority elsewhere in this pipeline;
# academy membership alone doesn't override that), Elon Musk (huge
# doc_count, clearly not a neutral consensus figure in this corpus's
# discourse, whatever academy affiliation triggered his inclusion),
# Noam Chomsky (genuine academic, but arguably better known here as a
# credentialed anti-establishment dissident than an institutional voice
# -- deliberately unresolved, not a clear exclude or include).
