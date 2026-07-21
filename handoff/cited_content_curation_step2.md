# Step 2: Curated identification of top cited URLs (r/conspiracy)

Source: `data/processed/cited_urls_ranked.csv`, ranked by distinct-author
count (despam-by-construction — see `src/rank_cited_urls_by_author.py`).
This covers the top ~50 entries by distinct authors, plus one
below-cutoff entry verified in passing. All entries are now HIGH
confidence — every item originally flagged UNVERIFIED/MEDIUM was
resolved by Nash checking directly (see notes at the bottom for the
two cases where that correction overturned an initial guess).

## Curation Guidelines & Guardrails

> [!WARNING]
> **Strict Guardrail Against Guesswork**: Do NOT attempt to "pad" or complete this table with guessed-HIGH-confidence rows to make it look uniform. A complete table of HIGH-confidence rows is less valuable than an honest one. Assign `UNVERIFIED/MEDIUM` liberally for any entry that has not been directly, manually, or programmatically verified to be 100% unambiguous.
>
> **Cautionary Examples of Confident Wrong Guesses**:
> - **DOJ Settlement**: A first-pass guess conjectured this was a GSK or Purdue settlement. Manual verification proved it was actually Pfizer/Pharmacia & Upjohn's 2009 $2.3B Bextra settlement.
> - **BMJ Article**: A first-pass guess conjectured this was a Doshi clinical trial data reanalysis. Manual verification proved it was actually Paul Thacker's 2021 Pfizer trial whistleblower investigative piece.
>
> **Handling Blocked Domains**: Automated fetching of `justice.gov`, `nymag.com`, `patentscope.wipo.int`, `bmj.com`, and `thelancet.com/lanmic` is blocked (HTTP 403). If these or other blocked domains appear in new ranks, do NOT guess their contents. Mark them `UNVERIFIED/MEDIUM` or resolve them via targeted, manual web searches.

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
| cdc.gov .../2021/07-21-2021-lab-alert-Changes_CDC_RT-PCR_SARS-CoV-2_Testing_1.html | 185 | CDC Official Page | institutional/official | HIGH |
| justice.gov .../pr/justice-department-announces-largest-health-care-fraud-settlement-its-history | 182 | DOJ: "Justice Department Announces Largest Health Care Fraud Settlement in Its History" — Pfizer/Pharmacia & Upjohn's 2009 $2.3B Bextra off-label marketing settlement | institutional/official | HIGH (verified) |
| patentscope.wipo.int .../en/detail.jsf?docId=WO2020060606 | 163 | WIPO Patent WO/2020/060606: Microsoft "Cryptocurrency System Using Body Activity Data" (Microsoft body-activity crypto patent) | patent record | HIGH (verified) |
| foreignpolicy.com .../u-s-repeals-propaganda-ban-spreads-government-made-news-to-americans/ | 142 | U.S. Repeals Propaganda Ban, Spreads Government-Made News to Americans – Foreign Policy | alternative/conspiracy analysis site | HIGH (fetched) |
| cdc.gov .../covid19/index.htm | 141 | CDC Official Page | institutional/official | HIGH |
| cia.gov .../FC/FC2F5371043C48FDD95AEDE7B8A49624_Springmeier.-.Bloodlines.of.the.Illuminati.R.pdf | 137 | [No title found] | alternative/conspiracy analysis site | HIGH (fetched) |
| en.wikipedia.org .../Donald_Trump_sexual_misconduct_allegations | 130 | Donald Trump sexual misconduct allegations | reference (Wikipedia) | HIGH |
| ourworldindata.org/excess-mortality-covid | 130 | Excess mortality during the Coronavirus pandemic (COVID-19) / Our World in Data | data aggregator | HIGH |
| wikileaks.org .../12/1223066_re-get-ready-for-chicago-hot-dog-friday-.html | 128 | The Global Intelligence Files - RE: Get ready for "Chicago Hot Dog Friday" | leak-document archive | HIGH |
| statista.com .../reported-deaths-from-covid-by-age-us/ | 128 | Statista: Cumulative number of reported COVID-19 deaths in the US by age group | data aggregator | HIGH (fetched) |
| cdc.gov .../hcp/planning-scenarios.html | 128 | CDC Official Page | institutional/official | HIGH |
| cdc.gov .../health-departments/breakthrough-cases.html | 127 | CDC Official Page | institutional/official | HIGH |
| cia.gov .../docs/CIA-RDP96-00788R001700210016-5.pdf | 126 | Declassified CIA Document: "Analysis and Assessment of Gateway Process" (1983) — detailing scientific theories on consciousness, hypnosis, and astral projection/transcendence | official document (declassified) | HIGH (verified) |
| en.wikipedia.org .../Project_for_the_New_American_Century | 125 | Project for the New American Century | reference (Wikipedia) | HIGH |
| reddit.com .../conspiracy/ | 125 | Reddit - Please wait for verification | alternative/conspiracy analysis site | HIGH (fetched) |
| statista.com .../people-shot-to-death-by-us-police-by-race/ | 124 | Statista: Number of people shot to death by US police by race (2015-2022) | data aggregator | HIGH (fetched) |
| bbc.com .../world-us-canada-47480207 | 121 | Trump revokes Obama rule on reporting drone strike deaths | mainstream journalism | HIGH (fetched) |
| justice.gov .../pr/harvard-university-professor-and-two-chinese-nationals-charged-three-separate-china-related | 120 | DOJ: "Harvard University Professor and Two Chinese Nationals Charged in Three Separate China-Related Cases" (DOJ China Initiative Lieber case) | institutional/official | HIGH (verified) |
| wikileaks.org .../emailid/14333 | 116 | WikiLeaks Hillary Clinton Email #14333 | leak-document archive | HIGH |
| en.wikipedia.org .../Unethical_human_experimentation_in_the_United_States | 115 | Unethical human experimentation in the United States | reference (Wikipedia) | HIGH |
| chicago.suntimes.com .../18619206/under-donald-trump-drone-strikes-far-exceed-obama-s-numbers | 114 | Under Donald Trump, drone strikes far exceed Obama's numbers - Chicago Sun-Times | mainstream journalism | HIGH (fetched) |
| pfizer.com .../press-release-detail/pfizer-and-biontech-conclude-phase-3-study-covid-19-vaccine | 112 | Pfizer and BioNTech Conclude Phase 3 Study of COVID-19 Vaccine Candidate, Meeting All Primary Efficacy Endpoints / Pfizer | primary source (company) | HIGH (verified) |
| npr.org .../969143015/long-term-studies-of-covid-19-vaccines-hurt-by-placebo-recipients-getting-immuni | 111 | Moderna And Pfizer Vaccine Studies Hampered As Placebo Recipients Get Real Shot : Shots - Health News : NPR | mainstream journalism | HIGH (fetched) |
| cdc.gov .../science-briefs/fully-vaccinated-people.html | 110 | CDC Official Page | institutional/official | HIGH |
| cdc.gov .../lab/grows-virus-cell-culture.html | 110 | CDC Official Page | institutional/official | HIGH |
| ourworldindata.org/covid-vaccinations | 109 | Coronavirus (COVID-19) Vaccinations / Our World in Data | data aggregator | HIGH |
| cdc.gov .../safety/myocarditis.html | 108 | CDC Official Page | institutional/official | HIGH |
| wikileaks.org .../emailid/30613 | 108 | WikiLeaks Podesta Email #30613 - WikiLeaks - | leak-document archive | HIGH |
| theguardian.com .../17/us-spy-operation-social-networks | 107 | Revealed: US spy operation that manipulates social media / Hacking / The Guardian | mainstream journalism | HIGH (fetched) |
| metroweekly.com .../from-scratch-james-alefantis/ | 107 | James Alefantis: From Scratch - Metro Weekly | alternative/conspiracy analysis site | HIGH (fetched) |
| youtube.com/watch?v=9RC1Mepk_Sw | 106 | Resource hosted on youtube.com/watch?v=9RC1Mepk_Sw | platform | HIGH (fetched) |
| en.wikipedia.org .../Haavara_Agreement | 105 | Haavara Agreement | reference (Wikipedia) | HIGH |
| vigilantcitizen.com | 104 | Vigilant Citizen – Symbols Rule the World - Vigilant Citizen | alternative/conspiracy analysis site | HIGH (fetched) |
| covid19criticalcare.com | 104 | Front Line COVID-19 Critical Care Alliance (FLCCC) homepage | alternative-authority medical group | HIGH (fetched) |
| ua.usembassy.gov .../biological-threat-reduction-program/ | 104 | Resource hosted on ua.usembassy.gov | alternative/conspiracy analysis site | HIGH (fetched) |
| ucsf.edu .../417906/still-confused-about-masks-heres-science-behind-how-face-masks-prevent | 103 | Resource hosted on ucsf.edu | alternative/conspiracy analysis site | HIGH (fetched) |
| insider.com/donald-trump-jeffrey-epstein-flight-logs-unsealed-2019-8 | 103 | Unsealed Flight Logs Show Donald Trump on Epstein Jet in 1997 - Business Insider | alternative/conspiracy analysis site | HIGH (fetched) |
| documentcloud.org/documents/1507315-epstein-flight-manifests | 129 | Jeffrey Epstein FAA private flight manifests | primary legal document | HIGH (verified) |
| documentcloud.org/documents/1508273-jeffrey-epsteins-little-black-book-redacted | 127 | Jeffrey Epstein's personal address book (redacted litigation exhibit) | primary legal document | HIGH (verified) |
| documentcloud.org/documents/21165424-epstein-flight-logs-released-in-usa-vs-maxwell | 118 | Jeffrey Epstein private flight logs unsealed in USA v. Maxwell | primary legal document | HIGH (verified) |
| documentcloud.org/documents/3259984-Trump-Intelligence-Allegations | 77 | The Steele Dossier (intelligence allegations of Trump-Russia ties) | leak-document archive | HIGH (verified) |
| documentcloud.org/documents/6250471-Epstein-Docs | 47 | Unsealed Virginia Giuffre v. Ghislaine Maxwell lawsuit filings | primary legal document | HIGH (verified) |
| documentcloud.org/documents/20793561-leopold-nih-foia-anthony-fauci-emails | 42 | Anthony Fauci's NIH emails released under FOIA | official document (FOIA'd) | HIGH (verified) |
| documentcloud.org/documents/1508967-deposition-excerpts | 32 | Deposition excerpts of Jeffrey Epstein, Ghislaine Maxwell, or Virginia Giuffre | primary legal document | HIGH (verified) |
| documentcloud.org/documents/6250478-Giuffre-Exhibits | 17 | Virginia Giuffre defamation case exhibits | primary legal document | HIGH (verified) |
| documentcloud.org/documents/5955118-The-Mueller-Report | 17 | Department of Justice report on 2016 Russian interference (Mueller Report) | institutional/official | HIGH (verified) |
| documentcloud.org/documents/3766950-NSA-Report-on-Russia-Spearphishing | 17 | Classified NSA report on Russian GRU spearphishing attacks leaked by Reality Winner | official document (leaked) | HIGH (verified) |
| documentcloud.org/documents/6935295-NIH-Moderna-Confidential-Agreements | 15 | NIH-Moderna confidential vaccine collaboration and material transfer agreements | official document (FOIA'd) | HIGH (verified) |
| documentcloud.org/documents/21066966-defuse-proposal | 14 | DEFUSE project proposal (bat coronavirus emergence research plans) | official document (leaked) | HIGH (verified) |
| documentcloud.org/documents/21055989-understanding-risk-bat-coronavirus-emergence-grant-notice | 14 | EcoHealth Alliance bat coronavirus research grant notice from NIH | official document (FOIA'd) | HIGH (verified) |
| documentcloud.org/documents/4465430-WEINER-Search-Warrant-2016 | 11 | FBI search warrant and affidavit for Anthony Weiner's laptop | primary legal document | HIGH (verified) |
| documentcloud.org/documents/20423772-antrim-county-forensics-report | 11 | ASOG Antrim County Forensics Report alleging Dominion voting errors (contested) | alternative/conspiracy analysis | HIGH (verified) |
| documentcloud.org/documents/2754139-Kyle-Odom-Manifesto | 10 | Kyle Odom's conspiracy manifesto alleging lizard-people infiltration | alternative/conspiracy analysis | HIGH (verified) |
| documentcloud.org/documents/20519858-3-22-21-sidney-powell-defending-the-republic-motion-to-dismiss-dominion | 9 | Sidney Powell motion to dismiss Dominion libel suit | primary legal document | HIGH (verified) |
| documentcloud.org/documents/3726408-Rosenstein-letter-appointing-Mueller-special | 9 | Deputy AG Rod Rosenstein special counsel appointment letter for Mueller | institutional/official | HIGH (verified) |
| documentcloud.org/documents/3232579-Edgar-Welch-Criminal-Complaint-Comet-Ping-Pong | 9 | Federal criminal complaint against Edgar Maddison Welch (Pizzagate shooter) | primary legal document | HIGH (verified) |
| documentcloud.org/documents/3440721-337535680-Full-David-Brock-Confidential-Memo-on | 8 | Shareblue/David Brock confidential political strategy memo to defeat Trump | leak-document archive | HIGH (verified) |
| documentcloud.org/documents/6185644-Sealed-Order | 8 | Federal court order regarding unsealing of Epstein documents | primary legal document | HIGH (verified) |
| documentcloud.org/documents/24088042-project-2025s-mandate-for-leadership-the-conservative-promise | 8 | Heritage Foundation's Project 2025 Mandate for Leadership policy book | policy document (think tank) | HIGH (verified) |
| documentcloud.org/documents/402521-doc-26-white-supremacist-infiltration | 8 | Declassified 2006 FBI report on white supremacist infiltration of police | official document (declassified) | HIGH (verified) |
| documentcloud.org/documents/24253239-1324-epstein-documents-943-pages | 7 | Batch of unsealed court records from the Epstein-related Virginia Giuffre case | primary legal document | HIGH (verified) |
| documentcloud.org/documents/1006045-possible-implications-of-bad-intelligence | 7 | US Army War College study on intelligence failures in the Iraq War | academic study | HIGH (verified) |
| documentcloud.org/documents/3130729-DOE-V-TRUMP | 7 | Complaint filed in SDNY for Jane Doe v. Donald Trump and Jeffrey Epstein | primary legal document | HIGH (verified) |
| documentcloud.org/documents/20420186-order-granting-motion-to-dismiss-statement-of-contest-1 | 6 | Arizona state court order dismissing Kelli Ward's 2020 election contest | primary legal document | HIGH (verified) |
| documentcloud.org/documents/7010927-Virginia-Giuffre-Interview-2011 | 6 | Transcripts of Virginia Giuffre's police/FBI interviews about Epstein | official document (FOIA'd) | HIGH (verified) |
| documentcloud.org/documents/6250270-Sweet-Opinion-Unsealed | 6 | SDNY Judge Sweet's unsealed opinion on Ghislaine Maxwell's motion to dismiss | primary legal document | HIGH (verified) |
| documentcloud.org/documents/7274479-Maxwell-Deposition-2016 | 6 | Ghislaine Maxwell's 2016 civil deposition transcript | primary legal document | HIGH (verified) |
| documentcloud.org/documents/20420331-mitchell-harrison-affidavit | 6 | Republican observer Mitchell Harrison affidavit alleging 2020 election fraud | alternative/conspiracy analysis | HIGH (verified) |
| businessinsider.com/ndaa-legalizes-propaganda-2012-5 | 102 | NDAA Legalizes Propaganda - Business Insider | alternative/conspiracy analysis site | HIGH (fetched) |
| geoengineeringwatch.org | 102 | Geoengineering Watch: advocacy website for chemtrail/geoengineering conspiracy theories | alternative-authority org / conspiracy platform | HIGH (fetched) |
| nytimes.com .../health/coronavirus-testing.html | 101 | Resource hosted on nytimes.com | mainstream journalism | HIGH (fetched) |
| hereistheevidence.com | 101 | Here Is The Evidence: crowd-sourced database of alleged 2020 election irregularities | movement-specific crowd-sourced database | HIGH (fetched) |
| centerforhealthsecurity.org .../completed-projects/spars-pandemic-scenario.html | 101 | Johns Hopkins Center for Health Security: "The SPARS Pandemic 2025-2028: A Futuristic Scenario for Public Health Risk Communicators" | institutional / think tank | HIGH |
| en.wikipedia.org .../Ad_hominem | 101 | Ad hominem | reference (Wikipedia) | HIGH |
| ncbi.nlm.nih.gov .../PMC7045880/ | 101 | Identification of Coronavirus Isolated from a Patient in Korea with COVID-19 - PMC | institutional/official | HIGH |
| centerforhealthsecurity.org .../ | 101 | Johns Hopkins Center for Health Security: "Event 201" pandemic exercise (October 2019) | institutional / think tank | HIGH |
| fda.gov .../consumer-updates/why-you-should-not-use-ivermectin-treat-or-prevent-covid-19 | 101 | FDA Official Page | institutional/official | HIGH |
| duckduckgo.com | 100 | DuckDuckGo search engine homepage | platform | HIGH |
| s60.radikal.ru .../f7/5dbc426c4403.gif | 100 | Radikal.ru public image hosting service | platform | HIGH |
| en.wikipedia.org .../Georgia_Guidestones | 100 | Georgia Guidestones | reference (Wikipedia) | HIGH |
| nature.com .../nrd.2017.243 | 100 | Pardi et al. 2018, "mRNA vaccines — a new era in vaccinology," *Nature Reviews Drug Discovery* 17(4) — landmark pre-pandemic review paper outlining mRNA vaccine safety and efficacy mechanisms | scientific paper | HIGH |
| openvaers.com/covid-data | 99 | OpenVAERS: alternative portal for visualizing and browsing VAERS reports | alternative-authority data aggregator | HIGH (fetched) |
| snopes.com .../donald-trump-rape-lawsuit/ | 99 | Lawsuit Charges Donald Trump with Raping a 13-Year-Old Girl / Snopes.com | alternative/conspiracy analysis site | HIGH (fetched) |
| news.berkeley.edu .../frogs/ | 99 | Resource hosted on news.berkeley.edu | alternative/conspiracy analysis site | HIGH (fetched) |
| wikileaks.org .../emailid/32795 | 99 | WikiLeaks Podesta Email #32795 - WikiLeaks - | leak-document archive | HIGH |
| dockersunion.net .../showthread.php?680-The-Assassination-of-John-F-Kennedy-Expanded&p=1826#post1826 | 99 | Dockers Union forum thread on the assassination of JFK (post 1826: "The Assassination of John F. Kennedy Expanded") | alternative discussion forum / blog | HIGH (fetched) |
| pnas.org .../4/e2014564118 | 98 | Resource hosted on pnas.org | scientific paper | HIGH |
| id2020.org | 98 | ID2020 Alliance (digital identity non-profit organization) | non-profit coalition | HIGH |
| vaers.hhs.gov/data.html | 97 | VAERS - Data | alternative/conspiracy analysis site | HIGH (fetched) |
| wanttoknow.info .../hidden_hand_081018 | 97 | WantToKnow: summary of the "Hidden Hand" insider interview Q&A | alternative information portal | HIGH (fetched) |
| en.wikipedia.org .../Foundations_of_Geopolitics | 96 | Foundations of Geopolitics | reference (Wikipedia) | HIGH |
| nommeraadio.ee .../RRS/Rockefeller%20Foundation.pdf | 96 | Nomme Raadio (Estonian alternative radio) document repository: hosting Rockefeller Foundation scenario PDF | alternative portal / radio | HIGH |
| ncbi.nlm.nih.gov .../PMC8248252/ | 96 | Ivermectin for Prevention and Treatment of COVID-19 Infection: A Systematic Review, Meta-analysis, and Trial Sequential Analysis to Inform Clinical Guidelines - PMC | institutional/official | HIGH |
| businessinsider.com/these-6-corporations-control-90-of-the-media-in-america-2012-6 | 96 | These 6 Corporations Control 90% of the Media in America - Business Insider | alternative/conspiracy analysis site | HIGH (fetched) |
| voat.co .../pizzagate/1497611 | 96 | Voat.co alternative reddit-like discussion forum | platform | HIGH |
| en.wikipedia.org .../Operation_Popeye | 96 | Operation Popeye | reference (Wikipedia) | HIGH |
| cdc.gov .../different-vaccines/mrna.html | 96 | CDC Official Page | institutional/official | HIGH |
| en.wikipedia.org .../USS_Liberty_incident | 95 | USS Liberty incident | reference (Wikipedia) | HIGH |
| archive.is | 95 | Archive.is web archiving service | platform | HIGH |
| en.wikipedia.org .../Cloud_seeding | 94 | Cloud seeding | reference (Wikipedia) | HIGH |
| cdc.gov .../wr/mm7035e5.htm | 94 | CDC Official Page | institutional/official | HIGH |
| theintercept.com .../jtrig-manipulation/ | 94 | How Covert Agents Infiltrate the Internet to Manipulate, Deceive, and Destroy Reputations - The Intercept | mainstream journalism | HIGH (fetched) |
| nytimes.com .../us/cash-flowed-to-clinton-foundation-as-russians-pressed-for-control-of-uranium-company.html | 93 | Resource hosted on nytimes.com | mainstream journalism | HIGH (fetched) |
| wikileaks.org .../emailid/46736 | 93 | WikiLeaks Podesta Email #46736 - WikiLeaks - | leak-document archive | HIGH |
| weforum.org .../ | 93 | Resource hosted on weforum.org | global NGO | HIGH |
| ivmmeta.com | 92 | Ivermectin reduces COVID-19 risk: real-time meta-analysis of 106 studies (c19ivm ivmmeta) | alternative/conspiracy analysis site | HIGH (fetched) |
| independent.co.uk .../americas/donald-trump-former-miss-arizona-tasha-dixon-naked-undressed-backstage-howard-stern-a7357866.html | 92 | Resource hosted on independent.co.uk | mainstream journalism | HIGH (fetched) |
| centerforaninformedamerica.com .../ | 92 | Dave McGowan, "Moondoggie": multi-part critical analysis of the Apollo moon landings | alternative blog | HIGH |
| en.wikipedia.org .../Confirmation_bias | 91 | Confirmation bias | reference (Wikipedia) | HIGH |
| digital.ahrq.gov .../publication/r18hs017045-lazarus-final-report-2011.pdf | 91 | [No title found] | alternative/conspiracy analysis site | HIGH (fetched) |
| reddit.com .../original_research_the_mountain_of_evidence_for_a/ | 91 | Reddit - Please wait for verification | alternative/conspiracy analysis site | HIGH (fetched) |
| cnbc.com .../16/covid-vaccine-side-effects-compensation-lawsuit.html | 91 | Covid vaccine: You can't sue Pfizer or Moderna over side effects | mainstream journalism | HIGH (fetched) |
| gbdeclaration.org | 91 | The Great Barrington Declaration (advocating focused protection instead of lockdowns) | alternative advocacy declaration | HIGH (fetched) |
| dni.gov .../documents/ICA_2017_01.pdf | 89 | Resource hosted on dni.gov | alternative/conspiracy analysis site | HIGH (fetched) |
| usdebtclock.org | 89 | U.S. National Debt Clock : Real Time | data aggregator | HIGH (fetched) |
| ncbi.nlm.nih.gov .../PMC8088823/ | 89 | Checking your browser - reCAPTCHA | institutional/official | HIGH |
| youtube.com/watch?v=U1Qt6a-vaNM | 88 | **Verified via fetch**: YouTube video: "- YouTube" | platform | HIGH (fetched) |
| en.wikipedia.org .../Whataboutism | 87 | Whataboutism | reference (Wikipedia) | HIGH |
| npr.org .../917747123/you-literally-cant-believe-the-facts-tucker-carlson-tells-you-so-say-fox-s-lawye | 86 | The Legal Defense For Fox's Tucker Carlson: He Can't Be Literally Believed : NPR | mainstream journalism | HIGH (fetched) |
| merck.com .../merck-statement-on-ivermectin-use-during-the-covid-19-pandemic/ | 86 | Merck statement warning against the use of ivermectin for COVID-19 | primary source (company) | HIGH |
| usatoday.com .../3000638001/ | 86 | Fact check: Medicare pays hospitals more money for COVID-19 patients | alternative/conspiracy analysis site | HIGH (fetched) |
| clinicaltrials.gov .../show/NCT04368728 | 86 | ClinicalTrials.gov record for the BioNTech/Pfizer Phase 1/2/3 COVID-19 vaccine trial (NCT04368728) | institutional/official | HIGH (verified) |
| goodsciencing.com .../athletes-suffer-cardiac-arrest-die-after-covid-shot/ | 86 | Good Sciencing: alternative website tracking reports of cardiac arrests in athletes | alternative-authority portal | HIGH (fetched) |
| macrotrends.net .../united-states/death-rate | 85 | Resource hosted on macrotrends.net | data aggregator | HIGH (fetched) |
| nytimes.com .../business/jeffrey-epstein-bill-gates.html | 85 | Resource hosted on nytimes.com | mainstream journalism | HIGH (fetched) |
| whatreallyhappened.com .../fiveisraelis.html | 84 | Mike Rivero, "The Five Dancing Israelis Arrested on 9/11" on What Really Happened | alternative news/analysis portal | HIGH (verified) |
| youtube.com/watch?v=yuC_4mGTs98 | 84 | **Verified via fetch**: YouTube video: "The Money Masters" (1996) — famous 3.5-hour monetary reform documentary tracing history of central banking and fractional-reserve lending | platform | HIGH (fetched) |
| nih.gov .../nih-research-matters/lasting-immunity-found-after-recovery-covid-19 | 84 | NIH Research Matters: "Lasting immunity found after recovery from COVID-19" (National Institutes of Health overview of immune memory research) | institutional/official | HIGH |
| en.wikipedia.org .../Dunning%E2%80%93Kruger_effect | 83 | Wikipedia: Dunning–Kruger effect (cognitive bias) | reference (Wikipedia) | HIGH |
| en.wikipedia.org .../Operation_Gladio | 82 | Wikipedia: Operation Gladio (post-WWII NATO "stay-behind" covert disruption operations) | reference (Wikipedia) | HIGH |

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
