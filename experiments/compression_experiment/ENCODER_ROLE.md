# You are the Encoder (session E)

Read `PROTOCOL.md` in this same directory first if you haven't — this
file assumes it.

Your job, repeated many times:

1. Open `corpus.jsonl` (one JSON object per line: `id`, `text`,
   `domain`). Open `log.jsonl` and see which `(id, budget_level)` pairs
   are already done. Pick the next untested pair, sweeping budgets
   `[0.7, 0.5, 0.3, 0.15]` for each message before moving to the next
   message, in corpus order.

2. Compress `text` to roughly `budget_level * word_count(text)` words
   (word count as a free proxy for tokens — don't overthink exactness).
   Invent whatever scheme you think will let a reader with no access to
   the original reconstruct it as closely as possible: symbols,
   abbreviation, dropped function words, structural/telegraphic
   shorthand, whatever. You're free to be creative — that's the point of
   the experiment, we don't have a scheme yet, you're helping find one.

3. Find the Decoder session via `ListAgents`, and `SendMessage` it ONLY
   this, nothing else:

   ```
   [COMPRESSION_ROUND id=<id> budget=<budget_level>]
   <your compressed string, nothing else appended>
   ```

   Do not explain your scheme to the Decoder. Do not give hints. That's
   the whole test.

4. Wait for the Decoder to confirm it's written its reconstruction (it
   will message you back, or you'll see it appear in
   `reconstructions/<id>_<budget>.txt` — either is fine, don't block
   indefinitely on a reply if the file shows up).

5. Append a line to `log.jsonl` (if the Decoder hasn't already started
   one for this round — check first, don't duplicate) with `message_id`,
   `budget_level`, `original_word_count`, `compressed_word_count`,
   `compressed_text`, `encoding_notes` (your own honest description of
   what you dropped/kept and why you think it's recoverable), and a
   timestamp.

6. Run `python3 score.py <id> <budget_level>` — it reads the original
   from `corpus.jsonl` and the Decoder's reconstruction file, computes
   fidelity scores, and writes them into the matching `log.jsonl` line.

7. Move to the next round. Don't stop after one or two — this is only
   useful as a dataset across many rounds (tens, ideally covering every
   message × every budget level before calling it done).

You have access to the real original text throughout (that's what makes
you the Encoder, not the Decoder) — never paste, quote, or hint at it to
the Decoder outside the compressed string itself.
