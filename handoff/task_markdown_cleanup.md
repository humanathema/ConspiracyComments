# Task: Small markdown cleanup

**Status: completed.**

## 1. Add "superseded" banners

`walkthrough.md` and all 7 files in `research_notes/` (`01_pe_and_insiders.md`
through `06_refined_credibility.md` plus `proposal_finegrained_credibility.md`)
are built on a contaminated entity list and an invalid control subreddit
(r/TopMindsOfReddit — confirmed to be a mockery/meta-community, not a
neutral baseline). Both problems are fixed elsewhere in this project now,
but these files have no in-file marker saying so — someone opening the
repo cold has no way to know without reading git history.

Add this exact banner to the top of each of the 8 files (after the
title, before the content):

```markdown
> **SUPERSEDED (2026-07-17)**: this document predates fixes to the
> `consensus_expert` entity list (was contaminated) and the control
> subreddit (r/TopMindsOfReddit, used here, was later found invalid —
> replaced with r/politics). See `ANTIGRAVITY_HANDOFF.md` for current
> findings. Kept for historical reference only, do not cite numbers from
> this document.
```

Don't rewrite or delete any content — just prepend the banner.

## 2. Fix two stale details in `README.md`

- The comparison-corpora list ("r/askreddit, r/TopMindsOfReddit,
  r/conspiracy_commons, r/conspiracyNOPOL, r/topconspiracy") should
  note that AskReddit and TopMindsOfReddit were both tried and rejected
  as invalid controls, and r/politics is the current valid one.
- The `src/` description ("LLM classification pipeline, Vertex AI
  fine-tuned endpoints") badly undersells what's there now — it's grown
  to cover entity curation, regression analysis, HITL tooling, and
  several external API integrations (Wikipedia, Arctic Shift, OpenAlex).
  Update to something like "entity curation, regression analysis, HITL
  rating tools, and external data pipelines (Wikipedia/Wikidata, Arctic
  Shift, OpenAlex); the original Vertex AI classification pipeline is
  one part of this, not the whole of it."

## Do not touch

`research_notes/notes.txt` — this isn't a real research note, it's raw
pasted conspiracy-theory content that looks like an accidental scratch
dump. Leave it alone, it's Nash's to deal with directly.
