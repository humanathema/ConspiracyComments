# Learned encoding spec — compression round-trip experiment results

Derived from 49 scored rounds (of 51 logged) across all 15 general-purpose
corpus messages × 4 budget levels (0.7/0.5/0.3/0.15 of original word
count), run by two isolated Claude sessions (Encoder/Decoder,
communicating only via `SendMessage`, Decoder never given the original
text — see `PROTOCOL.md`). Scored via `all-MiniLM-L6-v2` embedding
cosine similarity (`semantic_cosine`) between original and
reconstruction.

**Read the honesty note in `PROTOCOL.md` before using this anywhere**:
this measures how good elliptical/inference-dependent *language* can
get between two model instances, not access to any shared
representation beneath language. There is no other channel.

## Headline numbers

Mean `semantic_cosine` by budget level:

| budget | mean score | n |
|---|---|---|
| 0.7 | 0.940 | 15 |
| 0.5 | 0.939 | 9 |
| 0.3 | 0.894 | 10 |
| 0.15 | 0.810 | 15 |

Clean, roughly monotonic degradation — compression cost is real but
mild until deep into the 0.15 regime, and even there mean fidelity
stays above 0.8. The interesting variance is *within* a budget level,
by genre, not the budget curve itself.

## Findings, ranked by how load-bearing they are

**1. Genre determines compressibility more than budget does.** The
single best predictor of whether a round survived heavy compression was
not the budget level but the *type* of text:
- **Named-entity / technical / procedural / math content** (osmosis
  definition, router-reset steps, train-speed word problem) tolerated
  extreme compression (down to ~10 words from 50-65) with near-perfect
  reconstruction (0.98-0.996), because domain terminology and numbers
  anchor recovery — world knowledge fills the connective tissue reliably.
- **Argument/philosophical prose** is structurally robust — thesis and
  conclusion survive compression well even when every supporting example
  is dropped — but this comes at a cost (see #3).
- **Customer-service and warning/instruction registers** were the most
  compression-tolerant across *all* budget levels, likely because both
  Encoder and Decoder share a strong template prior for these genres.
- **Unstructured dialogue with no narration is the failure case**: the
  single worst round in the dataset (0.336) came from compressing a
  terse back-and-forth exchange to 7 words. Below some genre-dependent
  floor, compression doesn't degrade gracefully — it stops being
  "lossy-but-recoverable" and the Decoder invents a *different
  presentational mode entirely* (narrated summary instead of quoted
  dialogue) rather than a compressed version of the same text.

**2. Dropped concrete details get replaced by invented ones, not left
blank — and this is genre-specific, not random.** Argument/philosophical
prose reliably triggered the Decoder inventing new illustrative examples
not in the original when supporting details were compressed away (a
terse claim reads as an invitation to elaborate). A recipe round at
0.15 correctly recovered exact ingredient names from genre convention
alone, but also invented an explanatory rationale that was never there.
This is mostly harmless when it's genre-appropriate embellishment, but
is the mechanism behind the dialogue failure above when the genre floor
is crossed.

**3. Two concrete compression moves were found to actively mislead,
not just save words** (both flagged live by the Encoder mid-experiment,
worth stating as anti-patterns):
- Reusing the same word to imply a causal/conditional link (e.g. "wrong
  blink = wrong button" intended to mean "no blink") reads ambiguously
  and the Decoder guessed the wrong interpretation.
- An unglossed symbolic operator (bare `=`) standing in for a causal
  link has the same failure mode — it saves characters but costs
  correctness at low budget specifically, where there's no surrounding
  context left to disambiguate it.

**4. `semantic_cosine` measures more than fact-recovery — it also
penalizes register drift.** A reconstruction that preserves every fact
but adds unwarranted formality or elaboration scores lower than the
metric's face value suggests. Worth treating the embedding score as a
fidelity *proxy*, not a pure correctness measure, when citing these
numbers — corroborated by `difflib_ratio`/`word_overlap_f1` in
`log.jsonl` for the same rounds if a stricter read is needed.

**5. A genuinely correct, calibrated Decoder behavior was observed and
is worth naming as a positive pattern**: when a compressed round
(sports recap) produced an internally inconsistent reconstruction (the
stated scoring events didn't arithmetically match the stated final
margin — a pre-existing inconsistency in the original text, not
introduced by compression), the Decoder reported the outcome at face
value and flagged the discrepancy rather than silently "fixing" the
math to make it self-consistent. That's the right behavior for a
downstream system that shouldn't paper over source inconsistencies.

## Practical takeaway for handing project state between sessions

The load-bearing genre split maps fairly directly onto this project's
own handoff-doc content:
- **Numbers, entity names, file paths, exact thresholds, kappa values**
  — treat like the technical/procedural genre. Never compress these;
  they're exactly the "least inferable" content this experiment
  identified. This is already CLAUDE.md's standing rule for
  `experiment_log.jsonl` — this experiment gives it independent support.
- **Narrative reasoning / decision rationale** — closer to the
  argument/philosophical genre. Safe to compress the connective tissue,
  but expect a compressed version to lose *specific* supporting
  examples in favor of the general shape of the argument, and expect a
  reader reconstructing it to invent plausible-sounding specifics to
  fill gaps — which is exactly the failure mode `SESSION_START.md`
  already guards against by pointing to the underlying data/logs rather
  than a compressed summary for anything a real decision depends on.
- **Anything resembling a live exchange/negotiation between two
  parties** (closest analogue in this project: real-time cross-session
  coordination messages) — do not compress. This experiment's worst
  failure case specifically. Send it in full or not at all.

## Known limitations of this run

- n=15 messages, general-purpose corpus, not yet run against real
  project content (handoff docs, experiment_log entries) — the genre
  categories above are a reasonable prior, not validated on this
  project's own text.
- c001 has two logged-but-permanently-unscoreable rounds (0.3, 0.15) —
  contaminated by the Decoder-isolation bugs found mid-experiment
  (cross-round memory, then shared-log.jsonl exposure), both real and
  both fixed in `DECODER_ROLE.md` for any future run, but c001's early
  rounds predate the fix and can't be recovered.
- Single scoring model (`all-MiniLM-L6-v2`); a second embedding model
  or a human spot-check would be a reasonable next validation step
  before leaning hard on any specific number here.
