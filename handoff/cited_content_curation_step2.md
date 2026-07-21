# Step 2: Curated identification of top cited URLs (r/conspiracy)

Source: `data/processed/cited_urls_ranked.csv`, ranked by distinct-author
count (despam-by-construction — see `src/rank_cited_urls_by_author.py`).
This covers the top ~50 entries by distinct authors, plus one
below-cutoff entry verified in passing. All entries are now HIGH
confidence — every item originally flagged UNVERIFIED/MEDIUM was
resolved by Nash checking directly (see notes at the bottom for the
two cases where that correction overturned an initial guess).

| url | authors | identification | type | confidence |
|---|---|---|---|---|
| ae911truth.org | 313 | Architects & Engineers for 9/11 Truth (org homepage) | alternative-authority org | HIGH |
| worldometers.info/coronavirus | 301 | Worldometer COVID dashboard | data aggregator (not "authored") | HIGH |
| cdc.gov .../vaccines/safety/adverse-events.html | 290 | CDC official VAERS/vaccine adverse-events page | institutional/official | HIGH |
| en.wikipedia.org/wiki/Operation_Mockingbird | 288 | Wikipedia: alleged CIA media-influence program | reference (Wikipedia) | HIGH |
| en.wikipedia.org/wiki/Operation_Northwoods | 285 | Wikipedia: declassified 1962 false-flag plan | reference (Wikipedia) | HIGH |
| cdc.gov .../excess_deaths.htm | 246 | CDC excess-deaths data page | institutional/official | HIGH |
| wikileaks.org/wiki/FBI_pedophile_symbols | 199 | WikiLeaks-hosted page on alleged FBI symbol codes | leak-document archive | HIGH |
| worldometers.info/coronavirus/country/us/ | 195 | Worldometer US COVID page | data aggregator | HIGH |
| wwwnc.cdc.gov/eid/article/26/5/19-0994_article | 187 | **Verified via fetch**: Xiao et al. 2020, "Nonpharmaceutical Measures for Pandemic Influenza... Personal Protective and Environmental Measures," *Emerging Infectious Diseases* 26(5), Univ. of Hong Kong team — a real, well-known citation in mask-efficacy skepticism discourse | scientific paper | HIGH (fetched) |
| cdc.gov .../lab-alert-Changes_CDC_RT-PCR...html | 185 | CDC's July 2021 notice withdrawing its RT-PCR test EUA in favor of multiplex assays — widely cited (often out of context) as "CDC admits PCR test is flawed" | institutional/official | HIGH |
| justice.gov .../largest-health-care-fraud-settlement... | 182 | **Verified (Nash)**: Pfizer/Pharmacia & Upjohn's $2.3 billion settlement, Sept 2, 2009, for illegal off-label promotion of Bextra (and Geodon/Zyvox/Lyrica) — at the time "the largest health care fraud settlement in the history of the Department of Justice." Not GSK or Purdue, my earlier guess was wrong. | institutional/official | HIGH (verified) |
| nymag.com/nymetro/news/people/n_7912/ | 182 | **Verified (Nash)**: Landon Thomas Jr., "Jeffrey Epstein: International Moneyman of Mystery," *New York Magazine*, Oct 28, 2002 — the well-known pre-scandal profile of Epstein's opaque wealth, Clinton/Trump ties, and funded-scientist network (Nowak, Kosslyn, Edelman), published years before his first conviction. Frequently cited as "they knew all along." | mainstream journalism (individual byline) | HIGH (verified) |
| cryptome.org/2012/07/gent-forum-spies.htm | 179 | **Verified (Nash)**: "The Gentleperson's Guide To Forum Spies" — a COINTELPRO-techniques-derived guide to identifying alleged government/corporate forum infiltrators and disinformation tactics ("forum sliding," "consensus cracking," etc). Notable as a self-referential artifact: it's literally a guide the community uses to identify suspected shills *within itself*, directly relevant to the "controlled opposition" framing from earlier in this investigation. | community meta-document / tactics guide | HIGH (verified) |
| cdc.gov .../covid_weekly/index.htm | 178 | CDC weekly COVID data page | institutional/official | HIGH |
| archive.org | 177 | Internet Archive (general platform, not "authored" content) | platform | HIGH |
| fda.gov .../fda-approves-first-covid-19-vaccine | 163 | FDA's Aug 2021 full approval of Pfizer/BioNTech Comirnaty | institutional/official | HIGH |
| patentscope.wipo.int docId=WO2020060606 | 163 | **Verified (Nash)**: Microsoft Technology Licensing patent WO/2020/060606, "Cryptocurrency System Using Body Activity Data" (filed 2019, published Mar 2020) — a real Microsoft patent describing hypothetical crypto-mining tied to sensed body activity. **Confirmed unrelated to coronavirus/vaccines** — this is very likely the source of "Microsoft wants to microchip you to mine crypto from your body" claims, a real but unrelated patent being misattributed to vaccine-tracking narratives. Worth citing precisely as an example of source misattribution. | patent record | HIGH (verified) |
| phmpt.org .../5.3.6-postmarketing-experience.pdf | 160 | "Public Health and Medical Professionals for Transparency" (the org that sued FDA for release) — Pfizer's own "Cumulative Analysis of Post-authorization Adverse Event Reports," the widely-circulated "Pfizer documents" | official document (leaked/FOIA'd) | HIGH |
| time.com/5936036/secret-2020-election-campaign/ | 149 | Molly Ball, "The Secret History of the Shadow Campaign That Saved the 2020 Election," *Time*, Feb 2021 — a single mainstream-published article functioning as a major "proof" artifact in election-conspiracy discourse | mainstream journalism (individual byline) | HIGH |
| en.wikipedia.org/wiki/COINTELPRO | 148 | Wikipedia: FBI covert domestic surveillance/disruption program | reference (Wikipedia) | HIGH |
| nejm.org/doi/full/10.1056/nejmoa2034577 | 146 (+61 under `NEJMoa2034577` casing — same DOI, see note) | Polack et al. 2020, Pfizer-BioNTech COVID-19 vaccine phase 3 trial, *NEJM* | scientific paper | HIGH |
| foreignpolicy.com .../propaganda-ban-spreads-government-made-news... | 142 | 2013 *Foreign Policy* piece on the Smith-Mundt Act modernization (repeal of the domestic-dissemination ban on State Dept/BBG-produced content) | mainstream journalism | HIGH |
| en.wikipedia.org/wiki/Project_MKUltra | 140 | Wikipedia: CIA mind-control research program | reference (Wikipedia) | HIGH |
| en.wikipedia.org/wiki/Operation_Paperclip | 139 | Wikipedia: post-WWII US recruitment of Nazi scientists | reference (Wikipedia) | HIGH |
| cia.gov .../Springmeier.-.Bloodlines.of.the.Illuminati...pdf | 137 | Fritz Springmeier's "Bloodlines of the Illuminati" — ironically hosted in the CIA's own declassified Abbottabad-compound (bin Laden reading material) document release | conspiracy book (leaked/declassified hosting) | HIGH |
| coronavirus.jhu.edu/data/mortality | 136 | Johns Hopkins COVID dashboard | institutional/official (reputable) | HIGH |
| corbettreport.com | 136 | **The Corbett Report — James Corbett's independent media platform.** A genuine individual "alternative expert" own-platform citation, same category as benjaminlcorey.com below. Check whether "James Corbett" is already in the maverick list. | individual's own platform | HIGH |
| medrxiv.org/content/10.1101/2021.08.24.21262415v1 | 133 | **Verified (Nash)**: Gazit et al., "Comparing SARS-CoV-2 natural immunity to vaccine-induced immunity: reinfections versus breakthrough infections" (Israeli/Maccabi Healthcare Services retrospective study; later published in *Clinical Infectious Diseases*, doi:10.1093/cid/ciac262) — the widely-cited "natural immunity beats vaccine immunity against Delta" study, central to the natural-immunity debate on both sides. | scientific preprint (later peer-reviewed) | HIGH (verified) |
| cdn.factcheck.org/.../Johnson_TrumpEpstein_Lawsuit.pdf | 132 | **Verified (Nash)**: the "Jane Doe" (publicly known as "Katie Johnson") civil complaint, *Doe v. Trump and Epstein*, filed Oct 3, 2016, SDNY (Case 1:16-cv-07673-RA) — alleges rape/sexual abuse by both defendants at parties in 1994 when plaintiff was 13. Filename references "Johnson" (the plaintiff's public pseudonym in press coverage), hosted by FactCheck.org for reference/fact-checking purposes. Notably filed weeks before the 2016 election and later voluntarily withdrawn. | primary legal document | HIGH (verified) |
| benjaminlcorey.com/... | 124 | **Benjamin L. Corey — individual progressive-Christian blogger/author's own site.** Direct example of an individual's own platform being independently cited by 124 different people. | individual's own platform | HIGH |
| bmj.com/content/375/bmj.n2635 | 118 | **Verified (Nash)**: Paul D. Thacker, "Covid-19: Researcher blows the whistle on data integrity issues in Pfizer's vaccine trial," *BMJ* 2021;375:n2635 (Nov 2021) — investigative piece built on whistleblower Brook Jackson's account of data-integrity problems at a Ventavia-run Pfizer trial site in Texas (falsified data, unblinding, inadequate adverse-event follow-up). My earlier guess (Doshi reanalysis) was wrong — different piece, different author. | scientific/investigative journalism (named whistleblower) | HIGH (verified) |
| justice.gov .../harvard-university-professor-...china-related | 120 | DOJ "China Initiative" prosecution of Charles Lieber (Harvard chemistry chair) for concealing PRC ties | institutional/official | HIGH |
| hsph.harvard.edu .../fluoride-childrens-health-grandjean-choi/ | 119 | Harvard T.H. Chan School of Public Health coverage of Philippe Grandjean's fluoride/neurodevelopment research — a real, credentialed academic and a genuinely contested research area | institutional (academic press) | HIGH |
| lawofone.info | 116 | The "Law of One"/Ra Material — channeled New Age/esoteric spiritual text (Rueckert/Elkins/McCarty). Not a credentialed-expert source at all — a distinct "spiritual/esoteric authority" category worth keeping separate from the others. | esoteric/spiritual text | HIGH |
| qmap.pub | 113 | QAnon "Q drop" archive site | movement-specific archive | HIGH |
| pfizer.com press release | 112 | Pfizer's own press release on its phase 3 trial | primary source (company) | HIGH |
| theguardian.com/world/2004/sep/25/usa.secondworldwar | 111 | **Verified (Nash)**: confirmed — Ben Aris & Duncan Campbell, "How Bush's grandfather helped Hitler's rise to power," *Guardian*, Sept 25, 2004 — on Prescott Bush's Union Banking Corporation directorship and its ties to Fritz Thyssen's Nazi-linked financing network. | mainstream journalism | HIGH (verified) |
| ine.uaf.edu/wtc7 | 108 | University of Alaska Fairbanks study on WTC7's structural collapse — a major 9/11-truth touchstone (the "official engineering study contradicts NIST" claim) | academic study (contested) | HIGH |
| thelancet.com/journals/lanmic/.../PIIS2666-5247(21)00069-0 | 45 (below top-55 cutoff, verified anyway) | **Verified (Nash)**: Olliaro, Torreele & Vaillant, "COVID-19 vaccine efficacy and effectiveness — the elephant (not) in the room," *Lancet Microbe*, April 2021 — a methodological critique of relative-vs-absolute risk reduction reporting for the major vaccine trials. | scientific paper (methodological critique) | HIGH (verified) |

## Notes on data quality

- **Fixed during this pass**: URLs were originally being wrongly split by
  http/https and trailing-slash variants (e.g. ae911truth.org was two
  separate rows, 139+116, before merging to its true 313), and separately
  a regex bug was truncating any URL containing a literal parenthesis
  (Lancet PII codes especially) at the first `(`, which risked silently
  merging genuinely different papers under one wrong truncated identity.
  Both are fixed in the current `cited_urls_ranked.csv`.
- **Known remaining gap, not yet fixed**: DOI-based journal URLs
  (nejm.org, thelancet.com) still split by letter-casing in the DOI path
  segment (`nejmoa2034577` vs `NEJMoa2034577` are the same paper — DOIs
  are case-insensitive by convention, but only the domain is
  case-normalized here, not the path, since most other domains' paths
  ARE legitimately case-sensitive). This undercounts rather than
  wrongly-merges, so it's lower severity, but the Pfizer trial paper's
  true combined reach is at least 146+61=207 distinct-author-mentions,
  not 146 — worth a targeted fix (case-insensitive matching specifically
  for known DOI-path domains) before this table is treated as final.
- **All originally-UNVERIFIED/MEDIUM rows are now resolved** (Nash checked
  the ones that hit HTTP 403 on automated fetch directly). Two notable
  corrections to my own earlier guesses: the DOJ settlement was Pfizer's
  2009 Bextra case, not GSK/Purdue as guessed; the BMJ article was
  Thacker's Ventavia whistleblower piece, not the Doshi reanalysis I
  suspected. One confirmed misattribution risk worth flagging in any
  writeup: the WIPO patent (WO/2020/060606) is a real Microsoft patent
  about hypothetical body-activity-based crypto mining, filed 2019 —
  genuinely unrelated to coronavirus/vaccines despite being cited
  alongside vaccine-skepticism content, a clean example of source
  misattribution rather than fabrication.
- Automated fetch was blocked (HTTP 403) on justice.gov, nymag.com,
  patentscope.wipo.int, bmj.com, and thelancet.com/lanmic — all resolved
  via direct human check instead. Useful data point for any future
  automation of this process: these specific domains actively block
  bot fetches, so budget for manual verification on anything hosted
  there rather than expecting automated retries to eventually succeed.
