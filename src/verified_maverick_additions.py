"""verified_maverick_additions.py

Found 2026-07-15 while fixing combined_maverick_detector.py's entity list:
the same "never promoted to final bucket" blind spot already found and
fixed for consensus_expert (see consensus_experts_verified.py) also
affects maverick_authority. 351 entities have the CORRECT weak-hint
(`weak_hint_bucket_guess == "maverick_authority"`) but `final_bucket_guess`
is blank -- the automated tiered-category promotion logic rejected them
even though the weak-hint layer got it right. Total doc_count represented
across all 351: 53,634 -- not a rounding error.

**Root cause is characterized but not yet fixed at the pipeline level**:
whistleblower/leak-organization entities specifically seem underrepresented
in the promotion logic (Chelsea Manning, Bradley Manning, John Kiriakou,
Daniel Ellsberg all have this exact pattern) -- worth checking
`is_reliable_match()` in `stage_e_wikipedia_categories.py` for whether
"whistleblower"-type Wikipedia categories are being tier-classified
correctly, but that's a pipeline fix, not done here.

**This file is NOT a full fix of that 351-entity pool** -- that pool is
genuinely noisy (mixed in with correct misses like WikiLeaks are clear
non-mavericks that were wrongly weak-hinted: Bin Laden, Nixon, Giuliani,
ADL, Exxon, Hezbollah, Adolf Hitler, the Trilateral Commission, the
Heritage Foundation, several institutions and political figures). It
needs the same individual-by-individual review the consensus_expert list
got, at roughly double the scale (351 vs ~150) -- that's real, separate
work, staged in ANTIGRAVITY_HANDOFF.md, not attempted here.

**What IS fixed here**: the single highest-value, highest-confidence miss
-- WikiLeaks (doc_count 9,502 alone, more than the #2-10 entries in that
351-entity pool combined) and its immediate whistleblower cluster
(Assange, Manning, Snowden, Ellsberg, Kiriakou) -- all unambiguous,
canonical "credentialed/insider dissident" maverick-authority figures,
the same core construct maverick_authority exists to capture.
"""

VERIFIED_MAVERICK_ADDITIONS = [
    # WikiLeaks / Assange -- doc_count 9,502 for "WikiLeaks" alone, the
    # single largest miss found in this entire session's entity work
    "WikiLeaks", "Wikileaks.org", "@Wikileaks",
    "Julian Assange's", "Julian Assange’s", "Jullian Assange",
    "Assanges", "WhereIsAssange",

    # Manning
    "Chelsea Manning", "Bradley Manning",

    # Snowden
    "Ed Snowden", "Edward Snowden's", "Edward Snowden’s", "Snowdens",

    # Ellsberg / Kiriakou
    "Daniel Ellsberg", "Ellsberg", "John Kiriakou",
]
