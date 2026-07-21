# Task: AboveTopSecret Wayback Machine archive recovery (exploratory)

**Status: exploratory scoping only (2026-07-22), NOT started as a real
extraction project, NOT blocking anything in the main thesis pipeline.**
Raised in response to a methodological critique (a correspondent, "Bob",
argued r/conspiracy is too heavily moderated to represent "real"
conspiracy communities, and specifically suggested AboveTopSecret --
abovetopsecret.com -- as a less-moderated historical alternative/
supplement). This is a genuine possible follow-on data source, not a
near-term thesis addition -- see the "Scope" section before doing
significant work here.

## Why (context)

- ATS has been operating since at least December 1998 (earliest CDX
  capture: `19981205001831`), making it one of the internet's oldest
  conspiracy-theory forums -- older than Reddit itself.
- Current live-site status is murky as of 2026-07-22: uptime monitors
  report "no issues" but the homepage appears to be a stale CloudFlare
  snapshot from January 2025, and reloading gives "page not found."
  There's an apparent migrated community at `forum.abovetopsecret.xyz`.
  Verify current status directly before assuming either "dead" or "alive."
- No confirmed academic work uses ATS as a primary research corpus the
  way Reddit gets used (checked 2026-07-22 -- a Frontiers 2018 topic-
  modeling paper that came up in search is actually about r/conspiracy on
  Reddit, not ATS; don't cite it as ATS research). ATS shows up in passing
  in some conspiracy-narrative literature but isn't a well-established
  research dataset already. Worth a direct Google Scholar check for
  `"abovetopsecret.com"` before assuming either way.

## What's already been established (2026-07-22, via a 200K-row CDX sample)

Pulled via:
```
curl "http://web.archive.org/cdx/search/cdx?url=abovetopsecret.com&matchType=domain&collapse=digest&limit=200000" -o scratch/ats_cdx_dump.txt
```
saved at `scratch/ats_cdx_dump.txt` (32MB, 200,000 rows). Analysis script:
`scratch/analyze_ats_cdx.py` (run: `python scratch/analyze_ats_cdx.py <path>`).

**Confirmed URL schema** (empirically, not assumed): `/forum/thread{ID}/pg{N}`
is the real thread-content pattern.

> [!IMPORTANT]
> **Major Discovery (2026-07-22): Alphabetical Truncation in the 200K Dump**
> The initial finding that "most thread-ID references are malformed and unrecoverable" was a **methodological artifact** of CDX index sorting. 
> Because the Wayback Machine CDX API returns results sorted alphabetically by URL key, and our query used a raw domain search with a `limit=200000`, the dump was truncated at `com,abovetopsecret)/forum/168/pg3/top_politics.php`.
> Since numbers and special characters sort before the letter `t`, **virtually no clean thread URLs (which start with `/forum/thread...`) were actually in the 200K sample!**
> The only thread IDs in the sample were from malformed URLs with early-sorting prefixes (e.g. `%20forum/thread`, `%1Fforum/thread`, `/ats/forum/thread`, `/authors/forum/...`), leading to a false conclusion that most threads are unrecoverable.
>
> **Real Thread Recoverability**:
> When querying the prefix `abovetopsecret.com/forum/thread` directly to bypass the alphabetical truncation, we find **hundreds of thousands of perfectly clean, status-200 `/forum/thread{ID}/pg{N}` captures** with excellent historical coverage (across 2010 to 2023+).
> * **High Recoverability**: Clean thread pages are plentiful, with `text/html` mimetype and `statuscode=200`, including captures for both page 1 (`pg1`) and subsequent pages.
> * **Malformations are the minority**: The garbled URLs (with spaces, HTML tags, and control characters) are merely crawler garbage from poorly pasted links, not representative of the actual site captures.

**Time-distribution caveat**: February 2019 alone has 44,396 captures in
the sample -- 5-10x every other month. This is very likely a single bulk
re-crawl event by the Internet Archive, not a signal of real site
activity. Don't use raw per-year/per-month snapshot counts as an activity
proxy -- use distinct-thread-first-seen dates instead if that question
matters.

**Junk present, needs filtering**: ad-network artifacts (doubleclick.net
content oddly nested under the domain), CSS/JS/font assets, what looks
like unrelated e-commerce content possibly from ad-serving cross-domain
capture artifacts, and the malformed link garbage described above.

## Next steps, if this gets picked up as a real project

1. **Targeted CDX Prefix Querying**: Instead of doing a generic domain-level match (which gets clogged with board pages and junk), query the CDX API specifically with the prefix `abovetopsecret.com/forum/thread` to immediately retrieve clean, high-probability thread page captures.
2. **Full pagination**: Since the total thread count is likely in the hundreds of thousands, use the CDX API's `resumeKey` (or the `cdx_toolkit` Python library) to handle pagination and retrieve the full capture history.
3. **Rate limiting**: Internet Archive rate-limits aggressively from datacenter IPs -- budget for a residential proxy or a slow overnight run for anything beyond a few thousand requests.
4. **HTML parsing**: ATS's forum software uses a custom scheme (`/forum/thread{ID}/pg{N}`). Generic forum-scraping templates won't directly apply; a custom parser is needed once actual page HTML is pulled.
5. **Established tooling for the extraction-to-dataset step**: The [Archives Unleashed Toolkit](https://archivesunleashed.org/aut/) (Apache Spark-based, purpose-built for turning WARC captures into structured research datasets -- text extraction, link/network analysis) is the standard academic tool for this, not something to build from scratch. [IIPC](https://netpreserve.org/web-archiving/tools-and-software/) is the umbrella standards body if broader context is needed.
6. **Cross-check Common Crawl** as a supplementary/alternative index -- independent of the Internet Archive, sometimes has different coverage for the same site/period.
7. **Alternative forum.abovetopsecret.xyz**: Checked on 2026-07-22 and **confirmed dead/unresolvable** (host could not be resolved). Scraping a live migrated forum is not an option; archive recovery of `abovetopsecret.com` is the only viable path.

## Scope note (read before investing real time)

This is a genuinely large, separate data-engineering undertaking layered on top of an already-substantial existing pipeline. However, our discovery on 2026-07-22 shows that **thread recovery is far cleaner and more structured than previously feared**, as the vast majority of captures under `abovetopsecret.com/forum/thread` are clean, status-200, HTML files.

The honest recommendation discussed with Nash remains: write this up as future-work/limitations material in the thesis (a legitimate, low-cost, expected move for any single-platform study) rather than attempt a real extraction now, unless there's genuinely significant remaining time budget before submission. If it does get picked up, it is highly feasible but should be treated as its own independent project with its own success criteria.
