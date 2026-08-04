# Author Byline Extraction Results

Executed on: 2026-07-22 (original 500-URL run below). **Extended to 5,500
URLs at some point around 2026-07-28 without this doc being updated to
match** — found and reconciled 2026-08-03, see the update section right
below. Read that before trusting the "500 URLs"/"100% precision" numbers
immediately under this line as current.

## Update 2026-08-03 — real scale is 5,500 URLs, not 500; the Statista fix below didn't fully hold

`data/processed/byline_extraction_results.csv` actually has **5,500
rows** (3,074 successful, 55.9%: json-ld 2,256 / meta-tag 595 /
html-pattern 223 / failed 2,426) — this doc's numbers below were never
updated to match. Full detail in `handoff/task_citation_coverage_expansion.md`.

**The Statista date-leakage fix described below (removing the
`[class*='author']` wildcard selector) turned out to be necessary but
not sufficient** — re-checking the full 5,500-row run found the exact
same failure mode still live: `"May 7, 2026"`, `"Jul 13, 2022"`,
`"Mar 6, 2026"`, `"Feb 22, 2024"` (the very same Sweden-deaths URL cited
in the original spot-check row below) and a `yalemedicine.org` case, all
still html-pattern method. The site's own markup puts a real publish
date inside an exact `.byline`/`.author` class, not just the removed
wildcard — so narrowing the selector list didn't close the actual gap.
**Fixed properly 2026-08-03** with a value-level check instead of a
selector-level one: `clean_author_name()` now rejects any string shaped
like `Month D, YYYY` regardless of which selector produced it (see
`src/translation.py`). Verified against all 5 known-bad URLs (all now
correctly rejected, 4 of the 5 statista.com ones actually resolve via
JSON-LD to `"Statista Research Department"` instead) and against
tricky real names ("May Chen", "March Fong Eu") to confirm no false
positives.

Two more small fixes landed the same day: a literal `"No Author"`/`"N/A"`/
`"Anonymous"`-type placeholder string was passing through as if it were
a real byline (pewforum.org's own meta tag literally says `"No Author"`)
— now blacklisted. And `libertysoft4.github.io`, a static mirror of an
r/conspiracy comment thread (not a real article), was producing a Reddit
username+date as a "byline" via html-pattern — added to
`EXCLUDE_DOMAINS` in `run_byline_extraction.py`. Every other `*.github.io`
domain in the ranked citation list was checked individually and confirmed
to be a legitimate personal project/tool site, not a mirror — this was
a single-domain fix, not a blanket exclusion.

A **fresh, non-overlapping 30-URL spot-check** (independent of the
30-row sample below — different URLs, verified by directly reading raw
JSON-LD/meta tags rather than reusing `clean_author_name()`) found
~90%+ precision on the bigger run once institutional/organization-level
bylines are counted as acceptable (same convention already established
below), not literally 100% — see `handoff/byline_spotcheck_sample_2026-08-03.csv`
and `handoff/task_citation_coverage_expansion.md` for the full
row-by-row breakdown.

## Extraction Metrics (original 2026-07-22 run — 500 URLs, now superseded by the 5,500-URL figure above)

- **Total URLs Attempted**: 500
- **Successful Extractions**: 352 (70.4%)
- **Extraction Methods Breakdown**:
  - `json-ld`: 232
  - `failed`: 148
  - `meta-tag`: 75
  - `html-pattern`: 45

## Hand-Verified Sample (30 URLs)

> [!NOTE]
> Below is a draft sample of 30 extracted bylines. We will manually check these against the live pages and verify their correctness to measure extractor precision.

| url | distinct_authors | extracted_byline | extraction_method | domain | title | live_byline_check | verified | notes |
|---|---|---|---|---|---|---|---|---|
| [https://www.forbes.com/sites/eliseknutsen/2013/...](https://www.forbes.com/sites/eliseknutsen/2013/01/28/israel-foribly-injected-african-immigrant-women-with-birth-control/) | 40 | Elise Knutsen | json-ld | forbes.com | Israel Forcibly Injected African Immi... | Elise Knutsen | [x] || Correct 
| [https://www.mintpressnews.com/mega-group-maxwel...](https://www.mintpressnews.com/mega-group-maxwells-mossad-spy-story-jeffrey-epstein-scandal/261172/) | 52 | Whitney Webb | meta-tag | mintpressnews.com | Mega Group, Maxwells and Mossad: The ... | Whitney Webb | [x] || Correct 
| [https://blogs.scientificamerican.com/observatio...](https://blogs.scientificamerican.com/observations/we-have-no-reason-to-believe-5g-is-safe/) | 65 | Joel M. Moskowitz | json-ld | blogs.scientificamerican.com | We Have No Reason to Believe 5G Is Sa... | Joel M. Moskowitz | [x] || Correct 
| [https://www.dailymail.co.uk/news/article-218385...](https://www.dailymail.co.uk/news/article-2183858/All-presidents-bar-directly-descended-medieval-English-king.html) | 47 | Snejana Farberov | json-ld | dailymail.co.uk | All presidents bar one are directly d... | Snejana Farberov | [x] || Correct 
| [https://www.nytimes.com/interactive/2021/world/...](https://www.nytimes.com/interactive/2021/world/covid-vaccinations-tracker.html) | 53 | Josh Holder | json-ld | nytimes.com | Covid World Vaccination Tracker - The... | Josh Holder | [x] || Correct 
| [https://www.heritage.org/voterfraud](https://www.heritage.org/voterfraud) | 50 | @heritage | meta-tag | heritage.org | Voter Fraud Map: Election Fraud Datab... | The Heritage Foundation | [x] || Correct, institutional twitter handle extracted 
| [https://www.mintpressnews.com/shocking-origins-...](https://www.mintpressnews.com/shocking-origins-jeffrey-epstein-blackmail-roy-cohn/260621/) | 77 | Whitney Webb | meta-tag | mintpressnews.com | Hidden in Plain Sight: The Shocking O... | Whitney Webb | [x] || Correct 
| [https://jamanetwork.com/journals/jama/fullartic...](https://jamanetwork.com/journals/jama/fullarticle/2749214) | 63 | Lewis J. Radonovich Jr, MD | json-ld | jamanetwork.com | N95 Respirators vs Medical Masks for ... | Lewis J. Radonovich Jr, MD | [x] || Correct 
| [https://thecanadianreport.ca/is-this-leaked-mem...](https://thecanadianreport.ca/is-this-leaked-memo-really-trudeaus-covid-plan-for-2021-you-decide/) | 39 | canadian report | meta-tag | thecanadianreport.ca | Is this leaked info really Trudeau&#0... | The Canadian Report | [x] || Correct, publisher fallback 
| [https://www.cnbc.com/2018/02/22/medical-errors-...](https://www.cnbc.com/2018/02/22/medical-errors-third-leading-cause-of-death-in-america.html) | 59 | Ray Sipherd, special to CNBC.com | json-ld | cnbc.com | Medical errors third-leading cause of... | Ray Sipherd | [x] || Correct, includes special credit 
| [https://nypost.com/2020/10/14/email-reveals-how...](https://nypost.com/2020/10/14/email-reveals-how-hunter-biden-introduced-ukrainian-biz-man-to-dad/) | 59 | Emma-Jo Morris, Gabrielle Fonrouge | json-ld | nypost.com | Exclusive \| Emma-Jo Morris, Gabrielle Fonrouge | [x] | [ ] || Correct 
| [https://share.google/jLMGahKlCzfV1RHZq](https://share.google/jLMGahKlCzfV1RHZq) | 42 | Kate Briquelet | json-ld | share.google | Jeffrey Epstein’s Ex Says He Boasted ... | Kate Briquelet | [x] || Correct 
| [https://www.cbsnews.com/news/how-jewish-america...](https://www.cbsnews.com/news/how-jewish-american-pedophiles-hide-from-justice-in-israel/) | 40 | ByIan Lee | html-pattern | cbsnews.com | How Jewish American pedophiles hide f... | Ian Lee | [x] || ByIan Lee concatenated; fixed in refined clean_author_name code 
| [https://www.law.cornell.edu/uscode/text/42/300a...](https://www.law.cornell.edu/uscode/text/42/300aa-22) | 43 | Office of the Law Revision Counsel | json-ld | law.cornell.edu | 42 U.S. Code &sect; 300aa-22 - Standa... | Office of the Law Revision Counsel | [x] || Correct, institutional author 
| [https://www.theguardian.com/politics/2002/apr/2...](https://www.theguardian.com/politics/2002/apr/21/uk.medicalscience) | 51 | Antony Barnett | json-ld | theguardian.com | Millions were in germ war tests \| Antony Barnett | [x] | [ ] || Correct 
| [https://news.mit.edu/2019/storing-vaccine-histo...](https://news.mit.edu/2019/storing-vaccine-history-skin-1218) | 75 | Anne Trafton | html-pattern | news.mit.edu | Storing medical information below the... | Anne Trafton | [x] || Correct 
| [https://www.nasa.gov/feature/goddard/2016/carbo...](https://www.nasa.gov/feature/goddard/2016/carbon-dioxide-fertilization-greening-earth) | 35 | Karl B. Hille | json-ld | nasa.gov | Carbon Dioxide Fertilization Greening... | Karl B. Hille | [x] || Correct 
| [https://www.politico.com/story/2017/01/ukraine-...](https://www.politico.com/story/2017/01/ukraine-sabotage-trump-backfire-233446) | 58 | Kenneth P. Vogel, David Stern | json-ld | politico.com | Ukrainian efforts to sabotage Trump b... | Kenneth P. Vogel, David Stern | [x] || Correct 
| [https://www.nytimes.com/2001/05/20/world/taliba...](https://www.nytimes.com/2001/05/20/world/taliban-s-ban-on-poppy-a-success-us-aides-say.html) | 34 | Barbara Crossette | json-ld | nytimes.com | Taliban&#x27;s Ban On Poppy A Success... | Barbara Crossette | [x] || Correct 
| [https://www.haaretz.com/print-edition/news/odig...](https://www.haaretz.com/print-edition/news/odigo-says-workers-were-warned-of-attack-1.70579) | 51 | Yuval Dror | json-ld | haaretz.com | Odigo Says Workers Were Warned of Att... | Yuval Dror | [x] || Correct 
| [https://www.forbes.com/sites/arielcohen/2021/01...](https://www.forbes.com/sites/arielcohen/2021/01/11/bill-gates-backed-climate-solution-gains-traction-but-concerns-linger/) | 39 | Ariel Cohen | json-ld | forbes.com | A Bill Gates Venture Aims To Spray Du... | Ariel Cohen | [x] || Correct 
| [https://medium.com/@leibowitt/of-course-fidel-c...](https://medium.com/@leibowitt/of-course-fidel-castro-is-justin-trudeaus-dad-nobody-has-debunked-anything-4db6fc8a9042) | 65 | Karen Leibowitcz | json-ld | medium.com | Medium | Karen Leibowitcz | [x] || Correct 
| [https://www.statista.com/statistics/525353/swed...](https://www.statista.com/statistics/525353/sweden-number-of-deaths/) | 42 | Feb 22, 2024 | html-pattern | statista.com | Sweden excess deaths 2023\| None | [ ] | [ ] || Date extracted due to greedy wildcard; fixed in refined selectors list 
| [https://www.politico.com/story/2019/08/09/epste...](https://www.politico.com/story/2019/08/09/epstein-mar-a-lago-trump-1456221) | 56 | Josh Gerstein | json-ld | politico.com | Unsealed documents detail alleged Eps... | Josh Gerstein | [x] || Correct 
| [https://uncoverdc.com/2020/04/07/was-the-covid-...](https://uncoverdc.com/2020/04/07/was-the-covid-19-test-meant-to-detect-a-virus/) | 35 | uncoverdc.com | json-ld | uncoverdc.com | Was the COVID-19 Test Meant to Detect... | uncoverdc.com | [x] || Correct, publisher-level fallback in JSON-LD 
| [https://www.usatoday.com/story/news/factcheck/2...](https://www.usatoday.com/story/news/factcheck/2020/04/24/fact-check-medicare-hospitals-paid-more-covid-19-patients-coronavirus/3000638001/) | 86 | Michelle Rogers | json-ld | usatoday.com | Fact check: Medicare pays hospitals m... | Michelle Rogers | [x] || Correct 
| [https://www.nature.com/articles/d41586-021-0208...](https://www.nature.com/articles/d41586-021-02081-w) | 38 | Sara Reardon | json-ld | nature.com | Flawed ivermectin preprint highlights... | Sara Reardon | [x] || Correct 
| [https://www.theguardian.com/technology/2011/mar...](https://www.theguardian.com/technology/2011/mar/17/us-spy-operation-social-networks) | 107 | Ian Cobain | json-ld | theguardian.com | Revealed: US spy operation that manip... | Ian Cobain | [x] || Correct 
| [https://www.washingtonpost.com/politics/trump-c...](https://www.washingtonpost.com/politics/trump-called-epstein-a-terrific-guy-before-denying-relationship-with-him/2019/07/08/a01e0f00-a1be-11e9-bd56-eac6bb02d01d_story.html) | 56 | David A. Fahrenthold, Beth Reinhard, Kimberly Kindy | json-ld | washingtonpost.com | Trump called Epstein a ‘terrific guy’... | David A. Fahrenthold, Beth Reinhard, Kimberly Kindy | [x] || Correct 
| [https://usafacts.org/visualizations/covid-vacci...](https://usafacts.org/visualizations/covid-vaccine-tracker-states/) | 56 | USAFacts | json-ld | usafacts.org | How did COVID-19 affect people in the... | USAFacts | [x] || Correct, institutional publisher fallback 


## Precision & Error Mode Analysis

Based on the manual spotcheck of 30 randomly sampled successful extractions from our 352 results, we analyze the performance and safety of the extractor below:

### 1. Performance Metrics
- **Raw Extract Precision (First-Pass)**: **93.3% (28/30)**
- **Refined Precision (After Code Refinements)**: **100.0% (30/30)**

### 2. Identified Error Modes & Code Refinements

We identified exactly two opportunities for extraction errors during the spotcheck and immediately deployed corresponding code fixes to `src/translation.py`:

#### A. Greedy CSS wildcards (Statista Case)
*   **Symptom**: Extracted `"Feb 22, 2024"` instead of an author name.
*   **Cause**: The CSS selector wildcard `[class*='author']` matched a container containing a publication date.
*   **Refinement**: Removed `[class*='author']` from the `selectors` list inside `_extract_byline()` and replaced it with the exact standard class `".author"`. This prevents date or metadata leakage while maintaining compatibility with standard class hierarchies.

#### B. Concatenated leading prefixes (CBS News Case)
*   **Symptom**: Extracted `"ByIan Lee"` instead of `"Ian Lee"`.
*   **Cause**: The source HTML formatted the byline as `<span>By</span><span>Ian Lee</span>` or similar, which `.get_text(strip=True)` concatenated as `"ByIan Lee"`. Because there was no space, the standard `re.sub(r"(?i)^by\s+", ...)` rule was not triggered.
*   **Refinement**: Added an uppercase-boundary prefix stripping rule to `clean_author_name()`:
    ```python
    name = re.sub(r"^By([A-Z])", r"\1", name).strip()
    ```
    This correctly strips `"By"` from strings like `"ByIan"` or `"ByJane"` while safely leaving non-byline names like `"Byron"` intact.

### 3. Extraction Method Reliability Analysis

The spotcheck confirms our reliability hierarchy:
1.  **`json-ld`**: Exceptionally high reliability. It consistently extracts clean, structured author strings or lists of names (such as multi-author lists for *The Washington Post* and *NY Post*).
2.  **`meta-tag`**: Highly reliable, though sometimes falls back to publisher-level metadata (such as `@heritage`) when no specific journalist is listed.
3.  **`html-pattern`**: Moderately reliable, but is the only method susceptible to styling artifacts (like date matching or concatenated prefixes). Removing the wildcard selector makes this method safe.

## Complete Extraction Results

**2026-08-03: this section previously inlined all 500 rows of the original
run. Replaced with a pointer instead of extending it to all 5,500 current
rows** — a markdown table that size doesn't belong in a git-tracked
handoff doc. Full results: `data/processed/byline_extraction_results.csv`
(url, distinct_authors, extracted_byline, extraction_method, domain,
title, verified columns).
