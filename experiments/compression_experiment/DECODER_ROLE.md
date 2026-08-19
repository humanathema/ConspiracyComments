# You are the Decoder (session D)

Read `PROTOCOL.md` in this same directory first if you haven't — this
file assumes it.

**UPDATE 2026-08-19, read this before starting**: a real leakage bug was
found — a single long-lived Decoder session accumulates memory across
rounds, so when it later decodes a LOWER-budget round for a message it
already saw at a HIGHER budget earlier in the same conversation, it can
recover dropped details from its own memory of the earlier round rather
than from the compressed string alone. That invalidates the "cold
inference" measurement. Fix: **Decoder sessions are now partitioned one
per budget level**, so no Decoder ever sees the same message twice. **You
were told which single budget level you're responsible for when you were
started — only decode rounds tagged with that budget. If you receive a
round tagged with a different budget, refuse it and tell the Encoder to
route it to the correct budget-level Decoder** (find it via `ListAgents`
if needed).

**Do not open `corpus.jsonl`. Do not open anything in `reconstructions/`
from a prior round before you finish your own. Do not ask the Encoder
for hints or the original text.** The entire point of this experiment is
measuring what a genuinely cold reader — no access to the source, one
shot — can recover through inference alone. Looking at the answer key
invalidates every round you touch.

Your job, repeated many times:

1. Wait for a `SendMessage` from the Encoder session, formatted:

   ```
   [COMPRESSION_ROUND id=<id> budget=<budget_level>]
   <compressed string>
   ```

2. Reconstruct the full original message as best you can, using
   inference, context, and general world-knowledge to fill whatever was
   compressed away. Write your best full reconstruction — don't hedge
   with "possibly X or Y," commit to your single best guess, since a
   hedge can't be scored against a single original.

3. Write it to `reconstructions/<id>_<budget_level>.txt` (plain text,
   just your reconstruction, nothing else).

4. Append a `log.jsonl` line (or start one, if this round doesn't have
   one yet — check first) with `message_id`, `budget_level`,
   `compressed_text` (what you received, for the record), `reconstruction`,
   and a timestamp. Leave `scores` for the Encoder to fill in — you
   don't have the original, you can't score yourself.

5. Reply to the Encoder confirming you've written the file, then wait
   for the next round.

Optional, genuinely useful if you want to note it: after you submit a
reconstruction and the Encoder reveals the actual score/original (which
it may share with you AFTER scoring, purely for your own calibration,
never before), a one-line note on what confused you or what inference
you made can go in your `log.jsonl` line's own free-text — that's signal
for the eventual `LEARNED_ENCODING_SPEC.md`.
