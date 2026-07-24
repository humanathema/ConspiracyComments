# Task: Extend the cited-URL curation table past the top ~55

**Status: PARTIALLY SUPERSEDED (2026-07-22) — the "top ~55" framing is
stale. The curation table already grew to 139+ rows via today's
documentcloud.org curation (`task_domain_taxonomy_followups.md`, marked
COMPLETED). Re-check the actual current row count in
`cited_content_curation_step2.md` before resuming this specific task —
the "ranks ~56-155" range below may already be covered. Separately, see
`task_author_byline_extraction.md` for a related-but-distinct new task
(extracting actual author BYLINES from cited articles, not just
identifying/classifying the URL itself — different technical step, not
just a bigger version of this one).**

## Why

`handoff/cited_content_curation_step2.md` identifies and classifies the
top ~55 most-cited URLs in r/conspiracy (`data/processed/cited_urls_ranked.csv`,
ranked by distinct-author count) — CDC/institutional pages, Wikipedia,
scientific papers, individual "alternative expert" platforms (Corbett
Report, etc.), leak archives. This is real groundwork for
`task_credentials_problem_integration.md` (what KIND of source gets
cited, cross-tabbed against stance/traction) but currently only covers
~55 of 1.76M distinct URLs in the ranked file. Extending it further down
the distinct-author-count tail gives more data for that eventual
cross-tab without anyone having to make the credentials-problem judgment
call yet.

## What to build

Extend the SAME markdown table in `handoff/cited_content_curation_step2.md`
(same columns: `url | authors | identification | type | confidence`) for
roughly the next 100 rows by distinct_authors count (ranks ~56-155,
distinct_authors ranging ~79-112 — pull the actual next N from
`data/processed/cited_urls_ranked.csv` sorted descending by
`distinct_authors`, don't hardcode the list here since the file itself
is the source of truth).

Follow the exact confidence-tagging convention already established in
the file:
- **HIGH**: identification is unambiguous from the URL/domain/title alone.
- **HIGH (verified)** / **HIGH (fetched)**: had to actually check the
  content (fetch the page, or reason from domain knowledge) — mark as
  such, and if a human (Nash) already resolved something like it in the
  existing table, that's a useful pattern-match but re-verify, don't
  assume.
- **UNVERIFIED/MEDIUM**: genuinely uncertain. **Use this liberally where
  warranted — do NOT guess and mark something HIGH to make the table
  look more complete.** The existing table has direct precedent for this
  going wrong: two of Nash's own earlier guesses (a DOJ settlement, a
  BMJ article) were confidently wrong on first pass and had to be
  corrected after he checked directly — see "Notes on data quality" at
  the bottom of the file for both corrections. If you can't identify
  something confidently, flag it as UNVERIFIED and move on rather than
  padding the table with unverified-but-labeled-HIGH rows.

## Known gotchas (already documented in the file, don't rediscover them)

- URL-splitting bugs (http/https, trailing slash, parenthesis-truncation)
  were already fixed in `cited_urls_ranked.csv` — you shouldn't see
  obviously-duplicate rows for the same real URL, but if you do, that's
  worth flagging as a regression, not silently working around.
- DOI-based journal URLs (nejm.org, thelancet.com) still undercount due
  to case-sensitive path matching (documented, not yet fixed) — don't
  "fix" this as a side effect of this task, just be aware duplicate
  identifications across casing variants are a known, separate issue.
- These domains actively block automated fetches (HTTP 403 last time):
  justice.gov, nymag.com, patentscope.wipo.int, bmj.com,
  thelancet.com/lanmic. If any show up in the next 100 rows, mark
  UNVERIFIED/MEDIUM rather than spending a long time retrying — Nash
  will resolve those directly, same as last time.

## Guardrails

- Append to the existing table, don't restructure or rewrite what's
  already there.
- Update the "Notes on data quality" section at the bottom if you find
  anything new worth flagging (new bugs, new blocked domains, new
  misattribution examples like the WIPO patent one already documented) —
  don't just silently note it in your own head.
- This is identification/classification only — do NOT attempt to build
  the actual credentials-problem cross-tabulation
  (`task_credentials_problem_integration.md`) as part of this task, even
  if it seems like a natural next step once the table is bigger. That
  integration is explicitly scoped as Claude/Nash judgment work, not
  Antigravity's, per `ANTIGRAVITY_HANDOFF.md`'s guardrails.
