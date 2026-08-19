# Compression round-trip experiment — protocol

## What this is

An empirical test of how far a message can be compressed (fewest tokens)
while still letting a second, completely cold Claude session (no shared
context, no access to the original) reconstruct it close to verbatim —
by inference and world-knowledge filling the gaps, not by having seen it
before. This is NOT about literally accessing model internals (not
possible) — it's about finding, empirically, how much can be left
implicit and still recovered through ordinary language inference, the
same way a human fills in an elliptical sentence or a dense expert memo.

The eventual point (once this general-purpose round works) is to run the
same test on real ConspiracyComments project information and derive a
written "encoding spec" — conventions for what can safely be dropped,
abbreviated, or structurally implied when one session needs to hand
another a lot of project state cheaply. That spec becomes a document
future sessions read and apply, not a retrained model — nothing in this
repo can actually fine-tune model weights.

## Roles — two sessions, deliberately isolated from each other

- **Encoder (session E)**: has access to `corpus.jsonl` (the messages to
  compress). Reads `ENCODER_ROLE.md`.
- **Decoder (session D)**: must NOT have access to `corpus.jsonl` or any
  original message, ever. Only sees what Encoder sends it. Reads
  `DECODER_ROLE.md`.

Nash starts both sessions fresh, points E at `ENCODER_ROLE.md` and D at
`DECODER_ROLE.md`. They communicate via the cross-session `SendMessage`
tool (`ListAgents` to find each other by name/ref).

## Round structure

One round = one (message, budget_level) pair.

1. E picks the next untested `(message_id, budget_level)` combination —
   check `log.jsonl` for what's already been run, work through
   `corpus.jsonl` in order, sweeping budget levels
   `[0.7, 0.5, 0.3, 0.15]` (fraction of the original's own word count,
   used as a free token proxy — see `score.py`) for each message before
   moving to the next message.
2. E compresses the message to fit the budget using ANY scheme it
   invents — abbreviation, symbols, structural shorthand, dropping words
   a competent reader would infer, whatever. E should note its own
   estimated word count for the compressed string so both sides can
   check it landed near the target budget (some slop is fine, don't
   burn rounds chasing an exact number).
3. E sends D **only** the compressed string via SendMessage, tagged
   with `message_id` and `budget_level` in the message so D can log it
   correctly. No hints, no meta-commentary about what got cut.
4. D reconstructs the full original as best it can, from inference
   alone. D must not ask E for clarification or additional hints — one
   shot, matching the real constraint this is testing.
5. D writes its reconstruction to
   `reconstructions/<message_id>_<budget_level>.txt` and appends a line
   to `log.jsonl` (schema below) with everything except the fidelity
   scores (D doesn't have the original to score against).
6. E (which DOES have the original) runs
   `python3 score.py <message_id> <budget_level>` — this reads the
   original from `corpus.jsonl` and the reconstruction D just wrote,
   computes the scores, and appends them to the same `log.jsonl` line
   (or a follow-up line referencing the same id+budget — either is fine,
   `score.py` handles both).
7. Repeat. Go for volume over perfection — the point is a dataset across
   many rounds, not a perfect single round. Tens of rounds minimum
   before drawing any conclusion about what encoding tricks work.

## Logging

`log.jsonl`, one line per round, append-only (same convention as
`data/session_registry.jsonl` project-wide). Fields: `message_id`,
`budget_level`, `original_word_count`, `compressed_word_count`,
`compressed_text`, `encoding_notes` (E's own free-text description of
the scheme it used — this is the thing you're mining for later),
`reconstruction`, `scores` (filled by `score.py`: `tfidf_cosine`,
`difflib_ratio`, `word_overlap_f1`), `timestamp`.

## After enough rounds

Run `python3 analyze.py` (aggregates `log.jsonl` by budget level and by
tags in `encoding_notes`) to see which compression moves correlate with
high fidelity at high compression. Write the surviving patterns up as
`LEARNED_ENCODING_SPEC.md` — a short, concrete list of "do this, not
that" rules. That file is the actual deliverable to fold back into
`SESSION_START.md`/`CLAUDE.md` conventions later, once it's been
validated on general text AND spot-checked on real project handoff
content.

## Honesty note, read this before starting

There is no mechanism available in this environment for two Claude
sessions to communicate via anything other than text (tool calls,
SendMessage payloads) — there's no shared latent space, no way to pass
activations, no bypass of language as the interface. This experiment is
measuring how good elliptical/compressed *language* can get, not testing
some other channel. Framing results that way (to Nash, to
`LEARNED_ENCODING_SPEC.md`) keeps the eventual writeup honest about what
was actually demonstrated.
