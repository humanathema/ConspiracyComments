# Source/citation/domain coverage expansion (raised 2026-07-27/28)

Background-agent audit finding.

**Update 2026-08-03: found ranked step #1 (extend byline extraction) already
happened, undocumented, and confirmed the known date-leakage bug reproduces
at scale.** `cited_urls_ranked.csv` (thought lost, actually just sitting on
Kaggle — see `handoff/REMOTE_STORAGE_MAP.md`) was recovered, and while
locating it, found `data/processed/byline_extraction_results.csv` already
has **5,500 rows** (dated 2026-07-28), not the 500 described in
`handoff/byline_extraction_results.md` (still dated/reporting the original
2026-07-22 run) — someone already ran the extended extraction this doc's
step #1 recommends, just never wrote it up, and `src/run_byline_extraction.py`
as currently committed still hard-caps at 500 candidates
(`if len(candidates) >= 500: break`), so the 5,500-row file couldn't have
come from a plain re-run of the current script; unclear exactly how it was
produced (temporarily modified/looped script, not committed either way).
Numbers: 3,074/5,500 successful (55.9%) — json-ld 2,256, meta-tag 595,
html-pattern 223, failed 2,426. **Every single row has `verified=False`** —
none of the 5,500 have had the spot-check the original 30-row sample got.

Checked the known Statista date-leakage bug (`handoff/task_media_personality_and_byline_review.md`'s
item 2 — a date extracted as if it were a byline) against the full 5,500:
**still there, now 5 confirmed instances** (4x statista.com, 1x
yalemedicine.org, all `html-pattern` method) — up from 2 in the smaller run,
proportionally consistent, confirming this is a real, unfixed bug, not
noise. **Root cause found**: `clean_author_name()` in `src/translation.py`
(line 173) has a blacklist for boilerplate words (share/subscribe/etc.) but
no check for date-shaped strings — the `.byline`/`.author`/`.author-name`
CSS selectors in `_extract_byline()`'s "Method 3" fallback (line 289) are
grabbing a publish-date element on some page layouts instead of an author
name, and nothing downstream rejects it. Fix would be a small, deterministic
regex added to `clean_author_name()` (no LLM, no new labels) — not yet
applied, pending Nash's go-ahead since re-running extraction against the
affected rows means new outbound HTTP requests to those sites again.

**Revised next steps**, given the above:
1. ~~Fix `clean_author_name()`'s date-leakage gap~~ — **done, 2026-08-03**.
   Added a `Month D, YYYY` regex rejection in `src/translation.py`
   (`clean_author_name()`, after the existing purely-numeric-date check).
   Verified against real names first (no false positives on tricky cases
   like "May Chen"/"March Fong Eu" — the regex requires the trailing
   `D, YYYY`, which no real name matches). Then re-ran live extraction
   against the 5 known-bad URLs: all 5 statista.com/yalemedicine.org
   dates now correctly rejected. Bonus: 4 of the 5 statista.com URLs now
   resolve via the higher-priority JSON-LD method to
   `"Statista Research Department"` instead of falling through to the
   buggy html-pattern selector at all — a real, better answer, not just
   "no longer wrong." The 5th (Yale Medicine) now correctly returns
   `failed` rather than a wrong value.
2. ~~Re-run extraction on the ~5 affected rows to confirm the fix~~ —
   **done as part of #1 above.**
3. **Still open**: the actual spot-check re-validation this doc's original
   fix #2 asked for — a *fresh, non-overlapping* sample from the 5,500,
   now that `verified=False` across the board means the "100% precision"
   claim in `byline_extraction_results.md` only ever covered the original
   500, not this larger run. The date-leakage bug is fixed, but that
   doesn't mean it was the only issue at this scale — a real sample check
   is still the honest way to get a precision number for the 5,500-row
   set. Not done yet, deliberately not attempted without checking first
   since it also means new outbound requests, though smaller-scale than a
   full re-scrape (a ~30-50 URL sample, not all 5,500).
4. Update `handoff/byline_extraction_results.md` to reflect the real
   5,500-row run instead of the stale 500-row one it still describes —
   not done yet.

### Fresh spot-check, 2026-08-03 — result: `handoff/byline_spotcheck_sample_2026-08-03.csv`

Drew 30 successful-extraction rows from the 5,500, **excluding** the
original 30 URLs already hand-checked in `byline_extraction_results.md`
(random_state=7, genuinely non-overlapping — verified against the
existing hand-verified URL list first). For each, independently fetched
the live page and read the raw JSON-LD `author` field / meta author tag
directly (a separate, simpler parse, NOT reusing `clean_author_name()` —
reusing the same code being tested would just prove the code agrees with
itself) and compared against the reported byline.

**Result: 23/30 (76.7%) independently confirmed correct** by direct raw
evidence, **4/30 (13.3%) institutional/organization-level bylines**
(publication Twitter handles, "NBC News" as publisher-of-record for a
video with no named reporter) — not wrong, matches the same convention
already accepted in the original 30-row check (`heritage.org`'s
`@heritage` was marked "Correct, institutional twitter handle
extracted"), just lower-specificity than a real byline. **3/30 (10%)
plausible-but-unconfirmed** — either blocked by Cloudflare (403) during
this check, or this check's simpler independent JSON-LD parser didn't
capture evidence the production code's more thorough recursive parser
would (academic-journal and Nature schema nesting differs from
news-site schema) — the reported names match real, findable people/
institutions in every case, just not independently reconfirmed by raw
evidence *this time*.

**Two genuinely new issues found, neither present in the original
30-row check:**
1. **New bug class — Reddit-archive-mirror domains produce nonsense
   output.** `libertysoft4.github.io` (a static GitHub Pages mirror of
   r/conspiracy comment threads, not a real news article) got a
   `html-pattern` byline of `"130naturalproducer2016-10-02"` — a Reddit
   username concatenated with a date, accepted as if it were a real
   author name. Not covered by `EXCLUDE_DOMAINS` in
   `run_byline_extraction.py`, since that list only covers
   platforms/references (Wikipedia, YouTube, etc.), not third-party
   mirror sites. Worth checking `cited_urls_ranked.csv` for other
   `*.github.io` or similar static-mirror domains before extending
   further.
2. **Minor noise — literal "No Author" passing through as a name.**
   `pewforum.org`'s own meta tag content is literally the string
   `"No Author"`, and the pipeline faithfully extracted it as if it were
   a real byline. Not incorrect exactly (it's what the page's metadata
   says), but it inflates the "success" count with a non-name. A small
   blacklist addition to `clean_author_name()` (alongside the existing
   boilerplate-word list) would catch this and similar placeholder
   strings (`"n/a"`, `"anonymous"`, `"staff"`).

**Net read**: the date-leakage fix from earlier today held up under
independent re-checking (no date-leakage-shaped rows appeared in this
fresh sample), and overall precision on this bigger, unverified 5,500-row
run looks genuinely good (~90%+ counting institutional bylines as
acceptable, consistent with the original small-sample precision claim)
— but it is not literally "100%," and the two new issues above are real,
worth a small follow-up fix each. Neither is done yet.

## The finding

Less than 1% of citation events rest on actual human-verified
classification, on **either** platform:

- **Reddit**: only 0.79% of citations are `curated` (hand-verified) out
  of 4.67M citation rows across 132,009 distinct domains; 74.9%
  `unreviewed`, 24.3% `provisional_heuristic` (rule-based fallback, not
  verified).
- **ATS**: 0.51% of 25,024 distinct domains match the classification
  lookup at all, covering just 8% of citation mentions — no curated layer
  exists for ATS.
- **Manual curation table** (`handoff/cited_content_curation_step2.md`):
  139 URLs, hand-classified, careful methodology (documented
  self-corrections, explicit anti-padding guardrail) — against
  1,763,438 distinct URLs in `cited_urls_ranked.csv`. That's 0.008% of
  the long tail.

**Concentration matters for how bad this is**: Reddit's top 20 domains
cover 59.7% of citation rows (domain-level tiering is at least defensible
for the head), but ATS's top 20 only cover 24.4% — a flatter, more
fragmented distribution (older, more idiosyncratic web-1.0 forum, sites
like `rense.com`/`geocities.com`) where domain-level tiering alone can't
explain most of the corpus.

## What's already good, worth keeping

- URL normalization/dedup logic is solid (documented, self-corrected bugs
  like parenthesis-truncation and http/https splitting).
- Byline/article-level extraction (`src/translation.py`) is real and
  precision-validated at small scale (500 URLs, 352 successful) — see
  `handoff/task_media_personality_and_byline_review.md` for the caveat on
  how that precision claim was validated, before trusting it further.
- The curation table's confidence-tagging discipline (refusing to pad
  `UNVERIFIED` rows to `HIGH`) is a real methodological strength.

## Ranked next steps (feasible without new labeled training data)

1. **Extend byline extraction mechanically** — it already works at
   validated precision on json-ld/meta-tag sources; running it against
   the next 5,000-10,000 URLs by citation volume (already ranked, no new
   labels needed) would take Reddit-side article-author coverage from
   ~0.02% of URLs to something defensible, entirely with existing
   deterministic code, no LLM calls.
2. **Fix the DOI-casing undercounting bug** already flagged in the
   curation notes (`nejmoa2034577` vs `NEJMoa2034577` splitting identical
   papers into two entries) — small, deterministic, immediately improves
   accuracy for the single most-cited scientific paper in the dataset.
3. **Wire the byline/article layer into the explorer** — it exists
   (`build_domain_source_encyclopedia_export.py` produces
   `top_cited_urls_with_quality.csv`) but isn't surfaced anywhere a reader
   sees it. Integration work, not new analysis.
4. **Requires new labeled data or LLM assistance** (needs explicit
   sign-off first, per the standing no-unplanned-LLM-spend rule): building
   a genuinely representative domain-classification lookup beyond the
   current 268 hand-picked domains, to move past the 0.2-0.5% match rate.
   Could plausibly reuse the same AIITL-judge technique already proven
   this session (`domain_epistemic_type_sample.parquet` /
   `domain_epistemic_judged.parquet` already exist from a first pass —
   check those before starting a new one) rather than a fresh design.
