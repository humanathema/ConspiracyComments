# BelowTopSecret.com ingestion (scoping done, download in progress, 2026-07-27)

**Status update (2026-07-27): scope decision made — all three "Above
Network" boards (ATS, BTS, AbovePolitics) will be combined into one
corpus for topic modeling specifically**, per Nash — this is the
explicit merge decision the guardrail below said to wait for, now made.
Narrow to topic modeling for now; doesn't imply the three should be
merged everywhere else (e.g. stance/entity work) unless Nash says so
separately.

**AbovePolitics is fully done, not "not ingested yet" as this file
said before** — confirmed by direct query: `data/processed/bts_abovepolitics_comments_final_cleaned.parquet`,
67,633 comments, finished 2026-07-26 evening (`src/bts_ingest_abovepolitics.py`
was in fact run, contrary to the original scoping note below).

**BTS download in progress, ~58% done as of this update**: 47,876 /
82,462 pages downloaded into `data/raw/bts_raw_html/` (up from 27,566
at the last check). No parsed/final BTS parquet yet — download must
finish and then go through parse/to-parquet before it's usable.

**This is now the blocker for `task_ats_topic_modeling.md`** —
`src/train_bertopic_ats_overlap.py` is intentionally not running yet;
the plan is to fit the native topic model against the combined
ATS+BTS+AbovePolitics corpus once BTS finishes, not ATS alone. See that
task file for detail.

**Status update (2026-07-26, later same day):** Steps 1-3 (scoping) are
done — see `handoff/bts_ingestion_scoping_findings.md` for the full
writeup. Site relationship confirmed (BTS is ATS's official chitchat
sister board, same "Above Network" operator, verified via ATS's own
`/about.html`). Archive coverage checked via the same Wayback CDX
approach as `ingest_ats_archive.py`: BTS has two URL/template
generations (pre-2007 no `/forum/` prefix, 2007-2010 with it — the
regex needed extending to cover both, a straight reuse of the existing
`THREAD_REGEX` would have silently missed the majority pre-2007 share),
coverage collapses almost entirely by 2010-2011 (99.97% of real content
is 2004-2010), estimated volume ~1.2M posts (~17x smaller than ATS).

**Go/no-go verdict**: no-go on the original rationale (closing the
post-2016 reddit-volume gap) — BTS's coverage doesn't reach 2016 at all,
so it can't touch that problem. **Nash revised the framing same day**:
even though it doesn't solve the volume-comparability problem, BTS's
2004-2010 window still legitimately supplements ATS for that period, so
ingestion is going ahead on that narrower basis, not the original one —
this is a real scope narrowing, not a full reversal of the no-go.

**Now downloading** (`src/bts_ingest_archive.py download`, running as of
2026-07-26 evening): 82,462 metadata entries queued
(`data/processed/bts_metadata.json`), 27,566 pages downloaded so far
into `data/raw/bts_raw_html/` — in progress, not complete. Same
generic download/parse machinery from `ingest_ats_archive.py`, imported
not modified, per the script's own docstring (keeps this fully separate
from the concurrent ATS-parity work touching that file).

**Also scoped in passing, same session**: `abovepolitics.com`, a third
board in the same "Above Network" family — smaller footprint (~121,000
estimated posts, 2007-2009 almost entirely), same URL-scheme reuse
works cleanly (no old/new-scheme split like BTS had). Weakest case of
the three for inclusion — it's political debate, not chitchat/tone-
diversifying, and ATS's own political forums already cover that
directly. Not being ingested yet; flagged for a separate decision if
there's ever a specific reason to want a "more moderated" political-
discourse contrast sample. See `src/bts_ingest_abovepolitics.py`
(script exists, not run) and the scoping-findings doc's final section.

---

Original task file below, kept for the rationale that led to the above:

New corpus idea, separate from the five ATS-parity sibling tasks indexed in
`ANTIGRAVITY_HANDOFF.md` — not part of that dependency chain, don't block
on or collide with it (entity disambiguation, stance classification, topic
modeling, engagement normalization, unified schema all run against the
existing ATS corpus and shouldn't need to know this exists yet).

## Why

Raised while working `task_ats_topic_modeling.md`. Two things came up:

1. **Volume**: ATS and reddit (r/conspiracy) are only comparable in yearly
   comment volume for 2008–2012. From 2013 reddit overtakes ATS, and past
   2016 reddit outweighs it 10-100x (verified by direct query against
   `empath_scores_full_mapped.parquet` + `conspiracy_comments_short_lte100chars_mapped.parquet`
   vs `ats_comments_final.parquet`, both grouped by year). ATS alone can't
   close that gap for the post-2016 period.
2. **Tone**: `belowtopsecret.com` is described (by Nash, not yet verified
   independently) as ATS's "chitchat" sister site — same community, same
   people largely, but a less-serious, more off-topic/meme-heavy register.
   Hypothesis: pulling this in could both add volume and bring ATS's tone
   closer to reddit's, making cross-platform topic/register comparisons
   less confounded by "forum decorum" differences alone.

Neither of these is verified yet — that's the first job here, not an
assumption to build on.

## What already exists (checked 2026-07-26, direct grep, not guessed)

Nothing. The only hit for "belowtopsecret" anywhere in this repo is
`src/ingest_ats_archive.py:605`, and it's unrelated to actual content —
it's a guard that *skips* mis-parsed nav-bar chrome text (a cross-site
link to belowtopsecret.com that occasionally got misparsed as if it were
a comment body) during ATS ingestion. There is no BTS text, no scrape, no
partial ingest anywhere in `data/`. This is a from-scratch pipeline.

## First steps (scoping before any heavy lifting)

1. **Confirm the actual relationship between the two sites** before
   assuming "same community, different register" — check whether
   belowtopsecret.com is genuinely a sister/chitchat forum under the same
   operator (ATS is run by a company; check their own site descriptions,
   footer/about text) or something else entirely (a copycat, a dead
   rebrand, an unrelated site that just gets linked). Don't build a
   pipeline on an unverified assumption about what the site is.
2. **Check archival availability.** `ingest_ats_archive.py` was built
   against whatever archive source ATS's own ingestion used (Wayback
   Machine / direct scrape / CDX — check that script's top-of-file
   comments and `src/audit_missing_buckets.py` for the pattern used).
   Confirm belowtopsecret.com has comparable coverage before assuming the
   same approach transfers — it may have far worse archive coverage than
   ATS, which would undercut the volume rationale on its own.
3. **Estimate real volume and date range** from whatever archive index is
   available (page/thread counts, date span) before committing to a full
   scrape — this is the same "cheap diagnostic before the expensive
   commitment" discipline used for the ATS topic-modeling fit-new-vs-
   transfer decision. If BTS turns out to be small or its archive is thin,
   the volume rationale collapses and this may not be worth the ingest
   effort at all.
4. Only after 1–3 come back positive: design the actual scrape/parse
   pipeline, following `src/ingest_ats_archive.py`'s pattern (same repo,
   same forum-software family presumably, so the HTML structure may be
   close enough to reuse most of the parsing logic — verify rather than
   assume, forum software versions/templates can differ across the same
   company's properties).

## Guardrails (same as the rest of this repo)

- 8GB RAM dev machine — same constraints as `ANTIGRAVITY_HANDOFF.md` and
  the machine-constraints notes elsewhere: stream/chunk, don't hold a
  multi-million-row corpus's full text in memory at once.
- Prefix new files clearly (`bts_` or `belowtopsecret_`) so this doesn't
  collide with the five in-flight ATS-parity sessions or the ATS topic-
  modeling diagnostic work, all of which are using `ats_`-prefixed
  filenames in the same `data/processed/` and `src/` directories.
- This is a **new-corpus scoping decision**, not an extension of existing
  ATS work — don't fold its outputs into `ats_comments_final.parquet` or
  any `ats_`-prefixed artifact; keep it a separate corpus until/unless
  Nash decides to merge them later.

## Suitability for delegation

Good candidate for a fresh session/Antigravity run, but steps 1-3 above
should produce a short findings writeup (site relationship, archive
coverage, estimated volume/date range) for Nash to review **before** any
scraper gets built — this is exactly the kind of real cost/scope decision
point that shouldn't be defaulted through silently, same as the
fit-new-vs-transfer call on the topic-modeling task.
