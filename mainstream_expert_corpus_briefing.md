# Mainstream Expert Corpus — Briefing for Handoff

## Research context
Project studies the "credentials problem" in conspiracy discourse: comparing
named **mainstream consensus experts** against **maverick authority** figures.
Corpus currently has only **43 mainstream experts** — too small, and was built
from generic "list of scientists" Wikipedia pages, which select on notability,
not authority status. Need to scale into the hundreds/thousands with a
defensible operationalization, without diluting quality.

## Core methodological decision
Define "mainstream expert" by **institutional gatekeeping**, not fame.
Someone else (government, academy, journal, editorial board) already vetted
the person before they entered the corpus. Six source types, in order of
precision:

1. **Standing institutional office** — CMOs, CDC/FDA/Surgeon General
   directors, government chief scientific advisers, WHO SAGE, ACIP, IPCC
   author lists. Highest precision — membership list is the primary source.
2. **Academy membership** — NAS members, Royal Society Fellows, other
   national academies. Filter to living members.
3. **Citation-based (the real scaling lever)** — Clarivate Highly Cited
   Researchers (annual, downloadable, top 1% by citation); OpenAlex API
   (free, no key) queried by field + citation/h-index threshold; Semantic
   Scholar as cross-check. This is what actually takes the corpus from
   43 to thousands — programmatically, not by hand.
4. **Media/communicator gatekeepers** — science journalists, IFCN-verified
   fact-checkers. Useful because conspiracy discourse specifically frames
   these people as "establishment mouthpieces" — but see caveat below.
5. **Living Nobel laureates** — small, high-symbolic-value validation subset.
6. **Topic-specific consensus bodies** — IPCC (climate), ACIP/SAGE
   (pandemics/vaccines), etc. — best when corpus is domain-specific.

Tooling: **PetScan** (petscan.wmcloud.org) to intersect/union Wikipedia
categories and export clean lists instead of hand-scraping. **OpenAlex API**
for programmatic author pulls by field/citation threshold.

## Corpus timeframe — important correction

The underlying dataset is the full r/conspiracy subreddit history: ~40M
comments, 2008–2026 (18 years). This means **"out of date" is not a defect
for office-holder names** — a person who was CDC Director in 2021 is a valid
corpus entity because they were the sitting authority figure during
discussion in that period. The corpus needs **every officeholder across the
full 18-year span**, not a current snapshot. This actually *increases* the
office-holder category's yield: every CDC Director, FDA Commissioner,
Surgeon General, and CMO who served *at any point 2008–2026* is a valid
entry, each with their own tenure window. Treat tenure history as a feature
to capture, not noise to filter out.

## Failure modes found when a first-pass list was hand-generated (still relevant, revised)

A hand-typed candidate list (~100 names across 5 categories) was produced and
reviewed. Problems found, in order of severity:

1. **Missing tenure windows, not staleness.** The real gap in the first-pass
   list wasn't that it contained former officials (that's fine for this
   corpus) — it's that names were presented with no start/end dates, and it
   likely **missed several officeholders entirely** because only
   recent/prominent names were front-of-mind (earlier CDC Directors, FDA
   Commissioners, and Surgeon Generals from the 2008–2019 window weren't
   listed at all). Fix: pull the **complete historical roster** for each
   office across 2008–2026 — Wikipedia "List of Directors/Commissioners of X"
   pages give this directly and are undercounted in the current corpus.
2. Confirmed via search that US public health leadership had unusually high
   churn in 2025–2026 specifically (a confirmed CDC director ousted within a
   month of confirmation; the agency ran on acting directors for most of a
   year; ACIP was substantially reconstituted with vaccine-skeptical
   appointees under RFK Jr./HHS). **This is a useful corpus feature, not a
   problem** — high officeholder turnover in a period likely correlates with
   discussion volume/intensity about "who's really in charge," and is worth
   coding as a variable (e.g. `tenure_length_days`) rather than cleaned away.
2. **Category labels imported the conclusion.** Labels like "frontline
   enforcers of mainstream reality" or "defend against Deep State theories"
   bake in the mainstream/maverick framing the research is supposed to be
   testing. Category names must be neutral operationalizations (office-holder
   / academy member / citation-elite / media communicator), not rhetoric
   borrowed from the discourse under study.
3. **Category mixing hid a definitional problem.** State officials,
   independent researchers, and journalists were bucketed together despite
   being structurally different authority types. Separately: some
   "communicators" (e.g. independent paranormal/UFO debunkers) are not
   institutionally credentialed at all — they're pro-mainstream advocates,
   arguably mavericks-for-the-mainstream-side rather than mainstream experts.
   These need a distinct tag, not folding into the same category.
4. **No provenance per name.** Every name needs an attached basis and source,
   or it can't be defended methodologically.
5. **Anglophone/Western skew — not actually a flaw here.** r/conspiracy is
   an English-language subreddit with a majority North American/UK/AU/NZ
   userbase, so a corpus weighted toward US/UK/CA/AU/NZ officeholders and
   institutions is *appropriate sample matching*, not bias — it mirrors who
   the discussion is actually about and who's doing the discussing. Don't
   spend Antigravity budget chasing global/non-Anglophone academy coverage
   for its own sake. The one caveat: some non-Anglophone figures do get
   discussed on the sub because they're globally salient (e.g. Tedros
   Adhanom Ghebreyesus at WHO, EU-level climate figures) — those should stay
   in on individual merit (they're discussed in the corpus), not as part of
   a deliberate geographic-balancing pass.

## Fame is not the classifier, but it's not irrelevant either

Institutional gatekeeping was chosen to *discriminate* mainstream from
maverick because fame can't do that job alone — maverick figures (Alex
Jones, RFK Jr. pre-HHS, David Icke) are often equally or more famous than
mainstream ones, so fame doesn't separate the two classes. But fame/public
salience is still doing real work and shouldn't be discarded:

- Every name in the corpus, mainstream or maverick, already had to be
  salient enough to get named in r/conspiracy discourse — a fame filter is
  baked into the extraction method itself, applied identically to both
  classes, so it doesn't need separate justification as an inclusion
  criterion.
- But "mainstream expert" status may itself be partly a media-visibility
  phenomenon rather than a purely institutional one — arguably close to the
  actual thesis of a credentials-problem paper. Collapsing fame into
  "already satisfied, ignore it" would throw away a variable worth
  measuring.
- Test case: **Carl Sagan** was reportedly *denied* NAS membership despite
  his scientific credentials, partly because peers saw him as too populist.
  Institutional gatekeeping rejecting someone precisely *because* of their
  fame shows the two axes aren't just correlated — they can cut against each
  other. (Also worth checking whether Sagan, who died in 1996, actually
  appears as a live reference in the 2008–2026 corpus or only as a
  retrospective/nostalgic mention — different analytical treatment either
  way.)

Track `public_salience` as an independent field (see schema), not as a
tiebreaker or a proxy for institutional basis. This produces a usable 2×2:
high-institution/high-fame (Fauci, Sagan), high-institution/low-fame (an
IPCC author nobody's heard of), low-institution/high-fame (where a lot of
the *maverick* class will also cluster — this is likely where the actual
"credentials problem" lives, since from inside the discourse these can look
structurally identical to mainstream figures), and low/low (probably noise).

## How to treat the hand-assembled candidate list (~100 names, 5 categories)

Keep it, but only as an **unverified seed pool**, not as validated data —
most names are plausible and would likely surface again through a proper
PetScan/OpenAlex pull anyway, so discarding it wastes usable work. Required
triage before any name from it enters the final table:

1. Delete the original category labels entirely (they imported the
   mainstream/maverick framing — see failure mode #2 above). Replace with
   neutral `basis_type`.
2. Split by evidentiary strength, not original bucket. Office/academy/
   citation names (Fauci, Whitty, Mann, NAS members) are strong candidates.
   "Communicator/skeptic" names (Mick West, Joe Nickell, Michael Shermer)
   may have **no institutional basis at all** — don't let them inherit
   institutional-looking status just because they were in a "gatekeeper"
   category originally; code them as `public_salience`-only unless a real
   institutional basis is found.
3. No name counts as validated without a `source_url` and tenure dates —
   the list gives candidates, not verified rows.
4. Dedupe against the existing 43 before merging in.



| Field | Description |
|---|---|
| `name` | Full name |
| `domain` | e.g. Public Health, Climate, Cybersecurity/Election, Aerospace |
| `basis_type` | One of: office \| academy \| citation_elite \| media \| nobel \| none (see public_salience below) |
| `basis_detail` | Specific claim, e.g. "CDC Director," "NAS member," "Clarivate HCR 2025," "IPCC AR6 Lead Author" |
| `public_salience` | Independent axis, not a substitute for basis_type — evidence of mass-audience crossover (bestselling books, regular mainstream press/TV presence, major public awards, large following). Can be Y/N or a short note. A name can have strong `public_salience` and null `basis_type`, or vice versa — the two are deliberately not conflated. See rationale below. |
| `source_url` | Direct source for the claim |
| `tenure_start` | Date office/status began (or "ongoing"/blank if not office-based) |
| `tenure_end` | Date office/status ended (blank if still current or N/A) |
| `in_corpus_window` | Y/N — does tenure overlap 2008–2026 at all (should be Y for nearly everyone) |
| `notes` | e.g. overlap with existing 43, predecessor/successor, country |

Example rows:

| name | domain | basis_type | basis_detail | source_url | tenure_start | tenure_end | in_corpus_window | notes |
|---|---|---|---|---|---|---|---|---|
| Anthony Fauci | Public Health | office | NIAID Director | (fill) | 1984 | 2022-12 | Y | pre-dates and outlasts most of corpus |
| Rochelle Walensky | Public Health | office | CDC Director | (fill) | 2021-01 | 2023-06 | Y | — |
| Erica Schwartz | Public Health | office | CDC Director (nominee) | npr.org/... | 2026 (pending) | ongoing | Y | unconfirmed as of briefing date |
| Michael E. Mann | Climate | citation_elite + media | IPCC contributor; Clarivate HCR | (fill) | (fill) | ongoing | Y | — |

## Division of labor given limited remaining compute

**Do now, cheaply, in this session (before handoff):**
- Seed the table above with the existing 43 experts, backfilling
  `basis_type`/`basis_detail`/`source_url` where already known — this is
  just reformatting existing data, not new research.
- One small, targeted OpenAlex API pull (single field, e.g. virology or
  climatology, citation threshold >50) to prove the pipeline works and
  add a first tranche of citation-elite names programmatically.
- Pull the complete historical roster (with tenure dates) for the two or
  three highest-value US public health offices (CDC Director, FDA
  Commissioner, Surgeon General) as a template — this is a single
  Wikipedia "List of ___" page per office and cheap to do, and gives
  Antigravity a concrete pattern to replicate at scale.

**Hand to Antigravity:**
- Full-scale PetScan category pulls (NAS, Royal Society, CMO categories,
  per-country) and merge/dedupe against the existing corpus.
- Broader OpenAlex sweeps across all target domains, with h-index/citation
  thresholds tuned per field.
- Full historical-roster pass (with tenure windows) for every office
  category identified in the six source types — not just US public
  health, all countries/domains — so every officeholder active at any
  point 2008–2026 is captured, not just current or most-recent ones.
- Building out the media/communicator and topic-specific-body categories
  with proper provenance, keeping them tagged separately from
  institutionally-credentialed entries.
- Globally salient non-Anglophone figures should be added only when
  independently verified as discussed in the corpus (e.g. WHO leadership),
  not as a deliberate geographic-balancing pass — see note on sample
  matching above.

**For antigravity_handoff.md:** the "failure modes" section above is the
highest-value thing to carry forward verbatim — it prevents Antigravity
from re-deriving the same mistakes (loaded category labels, missing
provenance, stale office-holders, conflating credentialed experts with
pro-mainstream advocates) that cost time in this session.
