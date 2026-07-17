# Task: Review the mainstream-expert candidate list + fix a metadata bug

**Status: staged, not started. This is judgment work — a Claude instance
should do the actual review, not Antigravity unsupervised (see guardrail
3 in the main handoff index). Antigravity's role here is the mechanical
metadata fix only, plus producing whatever grep/lookup output the review
needs.**

## The file in question

`data/processed/mainstream_expert_augmented_superset.csv` — 453
candidate names pulled via PetScan (NAS/Royal Society category scrapes)
and OpenAlex (citation-elite sweeps), frequency-filtered against the
corpus. Has a blank `decision` column — nothing here is merged into the
live `src/consensus_experts_verified.py` yet, and nothing should be
without review.

## Known problems, found by spot-checking the top 30 by doc_count (not
## an exhaustive review — treat the rest of the 453 as unchecked)

- **Elon Musk** (doc_count 2,965, tagged `academy`) — clearly not a
  neutral consensus figure in this corpus's discourse. Should be
  excluded.
- **Peter Duesberg** (doc_count 101, tagged `academy`) — already
  correctly classified `maverick_authority` elsewhere in this project
  (well-known HIV/AIDS-denialist). His NAS membership (1986) predates
  and doesn't override that reputation. Should be excluded.
- **Noam Chomsky** (doc_count 485) — genuine academic, but arguably
  better known in this discourse as a credentialed anti-establishment
  dissident than an institutional-consensus voice. Genuinely ambiguous,
  not an obvious call either way — needs a real decision, not a default.
- **Likely name-collision errors, unverified**: David Chandler (there's
  a well-known 9/11-truther physics teacher with this exact name — check
  whether the doc_count is actually about him, not the intended NAS/RS
  candidate), Andrew Jackson (the historical US President would generate
  large false-positive mention counts in this corpus), N. Cohen (too
  generic a name for a confident OpenAlex author match).

## The metadata bug

Every entry sourced from `src/consensus_experts_verified.py` (roughly 82
of the 453 rows) got blanket-tagged `domain=Public Health,
basis_type=office` in the merge step, regardless of actual category.
Confirmed on 5 spot-checked names: Carl Sagan and Stephen Hawking
(physicists/science communicators, not health officials), Janet Yellen
and Paul Krugman (economists), James Hansen and Kevin Trenberth (climate
scientists), Katalin Karikó (biochemist). This is a mechanical fix —
re-derive `domain`/`basis_type` from the comments in
`src/consensus_experts_verified.py` (the file groups entries under
section-header comments like "Mainstream/establishment economists" —
use those groupings) rather than the blanket default. This part IS safe
for Antigravity to do directly, it's not a judgment call.

## How to structure the review (once assigned to a Claude instance)

Same pattern as the original `consensus_experts_verified.py` curation:
for each of the 453 names, check real corpus mentions (`data/processed/empath_scores_full.parquet`,
`WHERE regexp_matches(text, '\bNAME\b')`, read a sample) before deciding
— not just the Wikipedia/OpenAlex description. The Baric case (real
scientist, 100% accusatory corpus mentions) is why this matters: academy
membership or citation count alone doesn't tell you how a name actually
functions in this corpus's discourse. Bar for resolving vs. flagging:
make the call directly where confidence is genuinely high (matching how
the original 82-person list was built), only escalate genuine toss-ups
like Chomsky.

## Do not

- Merge anything from this file into `src/consensus_experts_verified.py`
  without the review happening first.
- Assume the top-30 spot-check is representative of the other 423 rows —
  it isn't necessarily, it was just the highest-frequency, highest-
  impact-if-wrong subset.
