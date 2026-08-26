# Assignment 1 — Raw Source Material (excerpts only, organized by section)

**Nothing in this file is original prose written for the assignment.** Every block below is
either: (a) verbatim text from a source [with citation], (b) verbatim text you already wrote
yourself, (c) verbatim docstrings/code/output already existing in this project, or (d) the
assignment brief itself. Per the course's Level-2 "AI Planning" policy, the actual written
sentences of your submission need to be composed by you from this material — nothing here is a
drop-in answer.

---

## Your existing hypothesis drafts (already written by you, before this conversation)

**Doc: "Untitled document" (1snpV...) — full preregistration template, blank**
(This is the assignment template itself, not your content — see Assignment Brief section below,
identical text.)

**Doc: "Untitled document" (1l5IPH...) — your in-progress draft:**
> Hypothesis
>
> Linguistic alignment of users on /r/conspiracy will increase over

(cuts off here — incomplete in the source doc)

---

## Assignment Brief (verbatim, as you pasted it)

**Hypothesis** — Suggested length: 20 words max.
> Please write down one hypothesis you will test. This hypothesis should pertain to the causal
> effect of one variable on one other variable... Please come up with your hypothesis
> independently; do not specify a hypothesis suggested by AI or by another student. Your
> hypothesis should be psychological in nature (e.g., not something like "Higher salt intake
> raises the risk of heart disease").

**Rubric — Hypothesis (2 marks):** "Does the hypothesis clearly specify an effect of one variable
on another? Is the direction of the effect clear? Note: If the hypothesis was also specified in
several other submitted assignments, it will receive a mark of zero; independent work is
required."

*(Full brief + rubric table already in your message above — not re-pasted here to avoid
duplication; all section prompts, suggested lengths, and rubric criteria are exactly as you
provided them.)*

---

## Rationale for Hypothesis (180 words) — literature excerpts

**Real, verified citations that speak to time/tenure → linguistic alignment/community language:**

1. **Danescu-Niculescu-Mizil, C., West, R., Jurafsky, D., Leskovec, J., & Potts, C. (2013). No
   country for old members: User lifecycle and linguistic change in online communities.
   *Proceedings of the 22nd International Conference on World Wide Web (WWW '13)*, 307–318.
   https://doi.org/10.1145/2488388.2488416**
   — Verified via WebSearch (ACM DL, ArXiv, Semantic Scholar, ResearchGate all list this exact
   title/author list/venue/year), and full text since retrieved directly (see below). Real,
   citable, page numbers below are as printed in the PDF body — double-check the actual printed
   page number in your own copy since this extraction didn't preserve page footers reliably.
   — **Their operationalization of "tenure" (Section 3.2, "User lifecycle"), verbatim:** "To this
   end we define the *life-stage* of a user as the percentage of posts the user has already
   written, out of the total number of posts the user will ultimately write before abandoning the
   community. Thus, a life-stage of 0% corresponds to *birth*—the moment the user joined the
   community—and a life-stage of 100% corresponds to *death*—the moment the user leaves the
   community." (footnote: fractional measure only applied with confidence for users with ≥50
   posts.) **This is post-count-fraction-of-lifetime, not calendar time** — different from this
   project's existing `months_since_start` variable, which is calendar months.
   — **Their measure of alignment** is cross-entropy of a user's posts against monthly bigram
   language models (Katz back-off smoothed) — not cosine similarity, which is what this project's
   own `alignment_score` uses.
   — **Their finding, verbatim (Abstract / Section 3.2):** "users follow a determined lifecycle
   with respect to their susceptibility to linguistic change: early in her career, a user becomes
   increasingly receptive to the norms of the community up to about one third of her eventual
   lifespan, when she reaches a maximum synchrony with the language of the community (we will call
   this early period *linguistic adolescence*); from that point on, a gap between the user's
   language and that of the community forms and increases until the moment she abandons the site."
   — Per the project's own code docstring (`src/repro_temporal_lexical_trajectory.py`, written by
   a prior session in this project, NOT the paper itself): "the ONLY one of the four
   insider-scratchpad notebooks that actually ran to completion and produced a validated finding:
   'No Country for Old Members' -- lexical alignment to the community's dominant monthly
   vocabulary DROPS as users age into the community (counter to a naive 'insiders converge more
   over time' hypothesis)." **Note this project's own binned-by-calendar-month trajectory (computed
   live in this conversation) actually shows the SAME two-phase rise-then-decline shape as the
   original paper** (mean alignment_score: 0.203 at month 0 → peak ~0.28 around months 1–10 → slow
   decline to 0.15 by month 200) — the docstring's one-line summary ("drops as users age") is true
   of the long-run trend but elides the initial rising phase, which matters if you want to
   accurately characterize this prior work.

2. **Danescu-Niculescu-Mizil, C., Lee, L., Pang, B., & Kleinberg, J. (2012). Echoes of power:
   Language effects and power differences in social interaction. *Proceedings of the 21st
   International Conference on World Wide Web*, 699–708.**
   — From your Epistemic Trust notebook: "Linguistic coordination is a phenomenon in which people
   tend to unconsciously mimic the choices of function-word classes made by the people they are
   communicating with." / "Linguistic coordination is a function of the power differential between
   the speaker and the target: the lower the power of the speaker relative to that of the target,
   the more she coordinates."

3. **Ireland, M. E., Slatcher, R. B., Eastwick, P. W., Scissors, L. E., Finkel, E. J., &
   Pennebaker, J. W. (2011). Language style matching predicts relationship initiation and
   stability. *Psychological Science, 22*(1), 39–44.**
   — "Using natural language samples, we investigated whether similarity in dyads' use of function
   words, called language style matching (LSM), predicts outcomes for romantic relationships."

4. **Niederhoffer, K. G., & Pennebaker, J. W. (2002). Linguistic style matching in social
   interaction. *Journal of Language and Social Psychology, 21*(4), 337–360.**
   — "Our definition of linguistic style matching (LSM) assumes that the words one person uses
   covary with those the other person uses."

5. **Zhu, J., & Jurgens, D. (2021). The structure of online social networks modulates the rate of
   lexical change. *Proceedings of NAACL-HLT 2021*, 2201–2218.** (full PDF in hand, p.2201)
   — Abstract: "New words are regularly introduced to communities, yet not all of these words
   persist in a community's lexicon... larger size, denser connections, the lack of local clusters
   and more external contacts promote lexical innovation and retention."

6. **Ferrillo, V. (2024). r/The_Donald had a forum: How socialization in far-right social media
   communities shapes identity and spreads extreme rhetoric. *American Politics Research, 52*(4),
   432–450.** (full PDF in hand)
   — Abstract, p.432: "I find that users who engage often with a far-right community like
   r/The_Donald begin to sound more like white nationalists within three months."
   — p.436, H1: "Users who have engaged with far-right-group-relevant language after
   engagement than before engagement." *(H1 exact wording, p.436 — this is the closest existing
   published causal claim to your hypothesis's structure: engagement/tenure → increased use of
   community-specific vocabulary.)*

---

## Claim in Prior Study + Critique of Prior Study

**Update: "No Country for Old Members" is now verified with real text in hand** (see Rationale
section above) — it's back in play as your prior-study candidate, and is the closer topical match
(it's about tenure/lifecycle stage → linguistic alignment specifically, not far-right vocabulary
adoption). Candidate claim, verbatim: "early in her career, a user becomes increasingly receptive
to the norms of the community up to about one third of her eventual lifespan, when she reaches a
maximum synchrony with the language of the community... from that point on, a gap between the
user's language and that of the community forms and increases until the moment she abandons the
site." Still double-check the exact printed page number in your own PDF copy before citing it —
this extraction didn't reliably preserve page footers.

**Ferrillo (2024) remains the other option** if you'd rather critique a study whose page numbers
I'm more confident about (I read it from the exact PDF you uploaded, footers intact).

**Ferrillo (2024) claim candidates (verbatim, with page numbers):**
- p.432 (Abstract): "I find that users who engage often with a far-right community like
  r/The_Donald begin to sound more like white nationalists within three months."
- p.436: "H1: Users who have engaged with far-right communities will use more
  far-right-group-relevant language after engagement than before engagement."

**Ferrillo's own method (for evaluating internal validity), verbatim from the PDF:**
- p.436: "All of the data for this project is scraped from the PushShift.io API... The dataset for
  this project contains records of over 700,000 Reddit posts from between January 2015 and
  December 2017. I perform text analysis on the full text of over 69,500 posts containing more
  than 2.3 million words."
- p.436, "Community and User Sampling": "The average Reddit user is regularly exposed to posts
  from a variety of communities they did not subscribe to. This is because Reddit employs a flat,
  uncensored, and user-generated content promotion system that treats content engagement and
  quality as synonymous."

**Week 2 concepts to apply to this critique (verbatim, from the course's own Week 2 slides +
Rohrer 2018 — matched to what's actually relevant to a pre/post engagement comparison design):**

- **Temporal precedence / repeated measures:** "Such a feedback loop can be modeled in a DAG (to
  some extent) by taking the temporal order into account and adding nodes for repeated measures.
  For example, a DAG could be drawn to show that intelligence in early childhood causally
  influences educational attainment, which in turn influences intelligence in adulthood... the
  often arbitrary spacing between time points can have a considerable influence on estimates,
  making causal inference even more complicated." (Rohrer, 2018, p.29, note 3)

- **Confounding, defined:** "The central problem of observational data is confounding, that is,
  the presence of a common cause that lurks behind the potential cause of interest (the
  independent variable...) and the outcome of interest (the dependent variable)." (Rohrer, 2018,
  p.30)

- **Attrition bias** (relevant if a "before/after engagement" comparison loses users who stop
  posting): "Assume that we are conducting a longitudinal study... over time, respondents
  inevitably dropped out of the study... this attrition was likely selective... If only the
  respondents remaining in the panel are included in the analysis, spurious associations between
  all causes of attrition can arise." (Rohrer, 2018, p.34–35, Fig. 5 caption)

- **Selection effects on who "engages often":** the Week 2 slides' "bad approach" critique —
  cross-sectional/observational studies that smuggle in causal language in the Discussion despite
  disclaiming it in Limitations — is exactly the pattern to check Ferrillo (or any prior study
  you pick) against: "Discussion > Limitations: Say study was observational, therefore cannot make
  causal claims / Rest of discussion: Claims that assume causal effects demonstrated." (Week 2
  slides, "How (not) to make causal inferences")

- **Full DAG glossary** (chains/forks/inverted forks/colliders/mediators/back-door paths) is
  reproduced in full in the tool output above if you need exact wording for any specific term.

---

## Design

**Existing project design already implemented for this exact hypothesis** —
`src/repro_temporal_lexical_trajectory.py` docstring (verbatim):
> "Cohort definition: authors with >=12 distinct active months AND >100 total comments ('legacy
> users' -- 40,534 in the original run). Per month: build a CountVectorizer vocabulary (max 5000
> features, English stopwords removed) from a 10%-sampled community text blob for that month;
> vectorize each cohort author's aggregated comments for that month; cosine-similarity each
> author-month vector against the community-month vector -> `alignment_score`."

This is an **observational, longitudinal (panel) design on secondary/archival data** — every
active-month observation per author, not a single pre/post snapshot.

**Comparable designs from the literature, verbatim:**
- Zhu & Jurgens (2021), p.2203: "A subreddit community C_n is further discretized into multiple
  monthly subreddit communities c_n(t) based on its actual life span in the monthly time step
  t... For each c_n(t), we extracted all individual comments except those marked as [deleted] and
  performed tokenization via SpaCy."
- Klein, Clutton & Dunn (2019), p.4: "We undertook an exploratory analysis using a case control
  study design, examining the language use and posting patterns of Reddit users who would go on to
  post in r/conspiracy... We compared the r/conspiracy group to matched controls who began by
  posting in the same subreddits at the same time, but who never posted in the r/conspiracy
  subreddit."

---

## Data Collection Procedure

**Existing pipeline (already built, already run) — data provenance:**
- Source data: `data/processed/monthly_partitions/` (raw r/conspiracy comments partitioned by
  month as Parquet; per the archive doc, ~5.6GB, already built).
- Output already computed: `/Volumes/Backup/processed/lifecycle_trajectories_local.csv` — 1,264,652
  rows, 40,534 authors, columns `author, month_str, months_since_start, alignment_score,
  total_comments`.
- Cohort inclusion rule (from the script, verbatim): `HAVING active_months >= 12 AND
  total_comments > 100`.

**Comparable inclusion/exclusion procedures from the literature (verbatim), for justifying yours:**
- Corso et al. (2026), p.12998: "we removed comments authored by known bots or suspicious accounts
  using predefined lists (Rollo et al., 2022). Furthermore, for each mainstream subreddit, we
  excluded users who posted fewer than 20 comments within that community. This threshold was
  applied to ensure that our analysis includes users with a strong and consistent signal of
  engagement."
- Zhu & Jurgens (2021), p.2203: "we removed numbers, emojis, urls, punctuations and stop words, and
  set a cutoff frequency of 10 over the entire dataset to exclude infrequent typos or misspellings.
  Only those monthly subreddits c_n(t) with more than 500 words or 50 users after preprocessing are
  retained."
- Klein, Clutton & Dunn (2019), p.5: "To remove accounts associated with automated programs known
  as bots... A list was compiled of usernames whose forum diversity was more than 15 standard
  deviations above the mean."

---

## Sample Size and Rationale

**Real numbers, computed directly from the existing dataset** (`/Volumes/Backup/processed/lifecycle_trajectories_local.csv`)
in this conversation — not written up, just the raw computed facts:

- N = 1,264,652 author-month observations, 40,534 unique authors, mean 31.2 observations/author.
- Pooled Pearson r (months_since_start, alignment_score) = **−0.1064**.
- Author-clustered OLS: β = **−0.000524**/month, cluster-robust SE = 0.000017, **p ≈ 1×10⁻²⁰⁶**,
  R² = 0.0113, Cohen's **f² = 0.0115**.
- Author-level ICC of alignment_score = **0.328**; design effect (Kish) ≈ **10.9**; N_effective
  (clustering-adjusted) ≈ **116,117**.
- At N_effective = 116,117: minimum detectable f² at α=.05, power=.80 ≈ **0.0000676** — the
  observed effect (f²=0.0115) is ~169× larger than that floor.
- N_effective required to detect the observed f² at power=.80: **≈687**; translated back through
  the same clustering structure (deff=10.9, 31.2 obs/author) ≈ **240 authors**.

**Course material on how to frame this (verbatim):**
- NHST slides: "Given some inputs, including Type of analysis / Hypothesised effect size /
  Alpha/significance level, we can estimate the sample size necessary to have a particular
  probability of producing a statistically significant result. We call this probability
  'statistical power.' Often set to a target of 80%."
- Discussion forum (Matt Williams, course coordinator): "for a regression model with a single
  predictor, the correlation (r) is indeed just the square root of the explained variance, R2."

---

## Stopping Rule

Assignment brief text (verbatim, already quoted above): "Specify how you will decide when to stop
collecting data... consider that any exclusion criteria you apply below may mean that your final
sample size is smaller than the initial number of participants you recruit."

Note: this is secondary/archival data already collected in full (the r/conspiracy corpus through
its available date range) — there is no prospective recruitment happening. That framing detail is
yours to reconcile with the template's participant-recruitment language.

---

## Measured Variables / Indices/Scores

**Exact operationalization already implemented in code** (`src/repro_temporal_lexical_trajectory.py`):

```
months_since_start = (current_date.year - start_date.year) * 12
                    + (current_date.month - start_date.month)

comm_vec = normalize(vectorizer.transform([community_text]), norm="l1")
user_vecs = normalize(vectorizer.transform(user_texts["body"]), norm="l1")
alignment_score = cosine_similarity(user_vecs, comm_vec)
```
CountVectorizer: `stop_words="english", max_features=5000`, fit fresh per month on a 10% random
sample of that month's comments.

---

## Data Exclusions

Already-applied exclusions in the existing pipeline (verbatim from code):
- `WHERE author != '[deleted]'`
- Cohort: `active_months >= 12 AND total_comments > 100`

Comparable exclusion language from the literature for justifying thresholds (already quoted above
in Data Collection Procedure): Corso et al.'s 20-comment activity floor, Zhu & Jurgens's
frequency-10/500-word/50-user thresholds, Klein et al.'s bot-detection cutoff (>15 SD forum
diversity).

Andy Field, *Discovering Statistics Using R* (discovr_06, "The Beast of Bias"), p.269 — on
outliers, relevant if you need to justify NOT excluding extreme alignment_score values:
> "I'd reiterate that even though outliers can bias models they are, in general, best retained in
> the data... Unless you have concrete evidence that an outlier doesn't reflect the population of
> interest, you retain it... Ideally you'd pre-register these sorts of exclusion criteria."

---

## Missing Data

No missingness in the existing `alignment_score`/`months_since_start` columns (every retained
author-month row has both by construction — the join is inner). If a section is needed anyway, the
above Field (2024) quote on retaining data absent concrete evidence otherwise is the most relevant
existing excerpt.

---

## Statistical Model

**Already run, verbatim output** (author-clustered OLS, statsmodels):
```
alignment_score ~ months_since_start
Intercept              0.2557   (SE 0.001,  z=356.1, p<.001)
months_since_start    -0.0005   (SE 1.71e-05, z=-30.68, p<.001)
Covariance Type: cluster (clustered by author)
R-squared: 0.011
```

---

## Inference Criteria

NHST slides (verbatim, already quoted above): "In psychology we typically use an alpha level of
0.05." Discussion-forum thread on effect sizes for single-predictor regression (already quoted
above) is directly relevant if your Statistical Model is this same OLS spec.

---

## Limitations

**Real, already-documented limitations of this exact dataset/pipeline** (from
`ANTIGRAVITY_HANDOFF.md` / `handoff/ARCHIVE_full_session_history.md`, written by prior sessions in
this project — not the assignment, but real methodological facts about the data you'd be using):

> "this script, `src/compute_baselines.py`'s on-demand `lexical_baseline_{month}.csv`, and the
> persisted 216-month `monthly_baselines/baseline_{month}.csv` series all independently construct
> 'the month's community vocabulary' slightly differently (word counts close but not identical
> between the first two — e.g. 'wiki' at 30,586 vs. 15,836 for the same month — and this script
> alone uses a 10%-sample vectorizer rather than an exhaustive count)."

That's a real, citable **measurement/construct-validity limitation**: the vocabulary baseline
against which alignment is measured is a random 10% sample, re-drawn independently each month,
not the exhaustive monthly vocabulary used elsewhere in this same project.

**Course material for framing validity consequences (verbatim, already quoted above in Critique
section):** Rohrer (2018) on internal vs. external validity trade-offs (p.28); confounding (p.30);
attrition bias (p.34–35); measurement error inflating false positives at large N (p.37, "the false
positive rate can reach very high levels, approaching almost 100%... Somewhat counterintuitively,
the false positive rate increases when sample sizes are large" — directly relevant given N≈1.26M).

---

## References (verified real sources — full bibliographic info)

- Corso, F., Russo, G., Pierri, F., & De Francisci Morales, G. (2026). Among us: Language of
  conspiracy theorists on mainstream Reddit. *Proceedings of the 64th Annual Meeting of the
  Association for Computational Linguistics (Volume 1: Long Papers)*, 12996–13017.
- Danescu-Niculescu-Mizil, C., Lee, L., Pang, B., & Kleinberg, J. (2012). Echoes of power: Language
  effects and power differences in social interaction. *Proceedings of the 21st International
  Conference on World Wide Web*, 699–708.
- Danescu-Niculescu-Mizil, C., West, R., Jurafsky, D., Leskovec, J., & Potts, C. (2013). No country
  for old members: User lifecycle and linguistic change in online communities. *Proceedings of the
  22nd International Conference on World Wide Web*, 307–318. https://doi.org/10.1145/2488388.2488416
  *(verified to exist via WebSearch; you must pull the actual quote/page yourself before citing a
  specific page number)*
- Ferrillo, V. (2024). r/The_Donald had a forum: How socialization in far-right social media
  communities shapes identity and spreads extreme rhetoric. *American Politics Research, 52*(4),
  432–450.
- Ireland, M. E., Slatcher, R. B., Eastwick, P. W., Scissors, L. E., Finkel, E. J., & Pennebaker, J.
  W. (2011). Language style matching predicts relationship initiation and stability.
  *Psychological Science, 22*(1), 39–44.
- Klein, C., Clutton, P., & Dunn, A. G. (2019). Pathways to conspiracy: The social and linguistic
  precursors of involvement in Reddit's conspiracy theory forum. *PLOS ONE, 14*(11), e0225098.
- Niederhoffer, K. G., & Pennebaker, J. W. (2002). Linguistic style matching in social interaction.
  *Journal of Language and Social Psychology, 21*(4), 337–360.
- Prinster, G. H., Smith, C. E., Tan, C., & Keegan, B. C. (2024). Community archetypes: An
  empirical framework for guiding research methodologies to reflect user experiences of sense of
  virtual community. *Proceedings of the ACM on Human-Computer Interaction, 8*(CSCW1), Article 33.
- Rohrer, J. M. (2018). Thinking clearly about correlations and causation: Graphical causal models
  for observational data. *Advances in Methods and Practices in Psychological Science, 1*(1),
  27–42.
- Zhu, J., & Jurgens, D. (2021). The structure of online social networks modulates the rate of
  lexical change. *Proceedings of the 2021 Conference of the North American Chapter of the
  Association for Computational Linguistics: Human Language Technologies*, 2201–2218.

**Every entry above is either a paper you uploaded (full PDF text seen directly) or was verified
by live WebSearch. None were pulled from memory alone. Field (2024, discovr) and Corso/Klein/
Ferrillo/Zhu&Jurgens page numbers are from the actual PDFs you gave me — double check page numbers
against your own PDF viewer since PDF-to-text extraction can occasionally misnumber.**

---

## Appendix: Power Analysis Protocol material

Already-executed computation (this conversation) — the real numbers, for you to write up or embed
as code per the brief's instructions ("If you conducted a power analysis in R, please include the
code necessary to reproduce your power analysis" — the brief wants R code specifically; what's
below is the Python computation actually run, which you'd need to port or redo in R yourself):

```
ICC (alignment_score, by author): 0.3275
mean cluster size (obs/author): 31.20
design effect: 10.891
N raw obs: 1,264,652  ->  N effective (clustering-adjusted): 116,117
F critical (alpha=.05, df1=1, df2=116115): 3.8415
Minimum detectable f2 at power=.80: 0.0000676
N_eff required for power=.80 to detect observed f2=0.01145: 687
Translated N_authors required (same clustering, deff=10.891): 240
```
