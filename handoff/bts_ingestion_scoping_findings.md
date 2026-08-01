# BelowTopSecret.com ingestion — scoping findings (2026-07-26)

Findings for steps 1-3 of `handoff/task_belowtopsecret_ingestion.md` (that
file lives in the main repo checkout, not this worktree — it's new/
uncommitted and didn't carry over). **No scraper built, per the task
file's explicit stop-before-building instruction.** Written from this
worktree; nothing touched in the main checkout or `data/raw/`.

## 1. Site relationship — CONFIRMED, matches Nash's description

Fetched ATS's own `/about.html` via a 2008 Wayback snapshot (both live
sites are dead, per Nash — Wayback/CDX only). Verbatim from ATS's own
about page:

> "...our 'off-topic' discussion board at BelowTopSecret.com provide[s]
> our members with a wide range of general discussion, entertainment,
> and fun forums..."

Same top-nav bar on every ATS page (`class='networkmenu'`) lists
BelowTopSecret alongside AboveTopSecret and AbovePolitics.com as one
family of boards run by the same operator ("The Above Network"). BTS's
listed sub-forums are exactly what "chitchat" suggests: General Chit
Chat, Rant, Music, Movies, Jokes/Puns/Pranks, Relationships, Dreams &
Personal Predictions, Sports, Television — no conspiracy-topic
categories at all. This is a genuine, officially-documented sister
forum, not a copycat or rebrand.

## 2. Archive coverage — comparable method works, but coverage collapses after ~2010

Same CDX approach as `ingest_ats_archive.py` (Wayback CDX API,
`url=belowtopsecret.com/forum/thread...`) returns real data. But the
full-domain CDX pull (289,092 raw capture records, all paths/statuses)
shows two problems:

- **Two different URL/template generations**, not one:
  - Older scheme, no `/forum/` prefix: `belowtopsecret.com/thread####/pg#`
    — dominant 2004-2006 (~65% of all real content captures).
  - Newer scheme, `/forum/` prefix: `belowtopsecret.com/forum/thread####/pg#`
    — 2007-2010, this is the one that matches ATS's *current* URL shape
    and `ingest_ats_archive.py`'s `THREAD_REGEX`
    (`r'/forum/thread(\d+)/pg(\d+|lastpost)?'`), which **requires** the
    `/forum/` segment and would silently miss the majority-share older
    scheme if reused unmodified. Step 4's "verify rather than assume"
    caution was correct — this isn't a straight reuse, the regex needs
    extending to cover both path shapes before any real parsing starts.
- **Coverage effectively ends by 2010-2011.** Year distribution of
  status-200 thread-page captures (90,652 distinct thread+page URLs,
  either scheme):

  | Year | 200-status thread-page captures |
  |---|---|
  | 2004 | 51,814 |
  | 2005 | 8,351 |
  | 2006 | 1,654 |
  | 2007 | 11,087 |
  | 2008 | 15,269 |
  | 2009 | 3,741 |
  | 2010 | 1,790 |
  | 2011-2025 | 24 (total) |

  99.97% of real captured content is 2004-2010. The 2018/2019 spikes
  visible in the raw (all-status) domain dump are **301-redirect noise**
  from the dead/squatted domain, not content — confirmed by cross-
  checking status codes per year (2018: 1,992 captures, all but 6 are
  `301`; 2019: 5,909 captures, all but 2 are `301`).

## 3. Volume estimate

- 53,470 distinct thread IDs, 90,652 distinct captured (thread, page)
  URLs at status 200.
- Applied ATS's own known comments-per-captured-page ratio (7,147,196
  ingested comments / 530,571 ingested (thread,page) captures = 13.47
  comments/page) as the extrapolation factor, since BTS ran on
  apparently the same forum software family and thread/page shape is
  structurally similar (BTS: ~1.7 pages/thread vs ATS: ~1.56
  pages/thread — close enough to trust the ratio transfer).
- **Estimated BTS volume: ~1.2M posts** (90,652 × 13.47 ≈ 1,221,000).
  That's ~17x smaller than the 7.15M-comment ATS corpus, and it's
  concentrated entirely in a 2004-2010 window that ATS itself already
  covers.

## Go/no-go recommendation

**No-go, for the volume rationale specifically that motivated this
investigation.** The original ask was to close the post-2016 volume gap
against reddit (ATS-vs-reddit only comparable 2008-2012, reddit 10-100x
larger from 2016 on). BTS's Wayback coverage stops almost entirely by
2010-2011 — it cannot contribute anything to the 2016+ window at all.
Ingesting it would not move the volume-comparability problem it was
proposed to solve.

The tone/register hypothesis (chitchat register closer to reddit's) is
independently confirmed as *plausible* by the site-relationship finding
in §1 — but every year BTS actually has usable coverage for (2004-2010)
already overlaps ATS's own corpus, which already spans that period. So
even a purely tone-focused re-scope would add a second, register-
different data source layered onto a time window where volume-parity
was never the problem to begin with — a different, smaller project than
what's in the task file, and a separate decision for Nash to make
explicitly rather than something this scoping pass should default into.

**Not proceeding to step 4 (parser/scraper design) for BTS.** Flagging
back per the task file's delegation note.

**Revision on the volume framing (Nash, 2026-07-26):** the no-go above
was scoped narrowly to "does BTS close the post-2016 reddit-volume gap"
— it doesn't, and that stands. But BTS's 2004-2010 window still
legitimately *supplements* ATS for that period even though it doesn't
touch the reddit-comparability problem. Also worth remembering: the
post-2016 reddit-dominance number isn't just an archive-coverage
artifact — r/conspiracy's composition itself changes materially around
then (The_Donald ban migration, MAGA/Trump-era users joining), so "ATS
can't be extended past 2016" and "conspiracy discourse looks different
after 2016" are two separate, both-true facts, not one explaining the
other. Neither point changes the go/no-go verdict on BTS closing the
volume gap, but both are relevant framing for the thesis text around
this decision.

## AbovePolitics.com — same operator, third board in the family

Same "Above Network" (see §1) also runs `abovepolitics.com`, described
in ATS's own about page as the "alternate 'non-divisive political'
discussion board," explicitly positioned as more moderated/debate-
oriented than ATS's own political threads — categories: General
Ideological Topics, U.S. Politics, Social Issues, Slug-Fest, Middle-East
Conflict, Breaking Political News, Politics of War, Military & Security
Issues, Conservative, Religion in Government, etc.

**Archive coverage**: much smaller footprint than either ATS or BTS —
15,225 total raw CDX captures across the whole domain, 8,972 distinct
status-200 (thread, page) URLs across 4,743 distinct threads. Same
collapse pattern as BTS: 99.8% of real content is 2007-2009 (2007:
4,759, 2008: 3,675, 2009: 880, 2010: 13, then nothing). Same `/forum/
thread####/pg#` URL scheme as ATS's current parser expects (no
old-scheme split like BTS had) — a straight-reuse of
`ingest_ats_archive.py`'s regex would actually work here, unlike BTS.

Also has non-forum URL shapes worth knowing about before writing a
parser (per the "shape of URLs for scraping" ask): `/single/<id>.html`
(individual post permalinks), `/pages/<slug>.html` (static content
pages), `/authors/<name>.html` (per-author archive pages) — same
in-house CMS family as ATS/BTS, not a different platform, but not pure
forum-thread pages either.

**Volume estimate**: ~121,000 posts (8,972 captured pages × ATS's 13.47
comments/page ratio) — smaller than even BTS, and covering an even
narrower, earlier window (2007-2009 almost entirely). Same conclusion
as BTS on the volume-gap rationale: this cannot help the post-2016
reddit-comparability problem, its usable years are already inside ATS's
own coverage. Unlike BTS, it isn't chitchat/tone-diversifying either —
it's political debate, which ATS's own forums already cover directly.
Weakest case of the three boards for inclusion unless there's a
specific reason to want a "more moderated" political-discourse contrast
sample, which isn't a stated goal here.
