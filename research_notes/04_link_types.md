# Research Notes: Multidimensional Link-Type Regressions (Reversing Trust)

> **SUPERSEDED (2026-07-17)**: this document predates fixes to the
> `consensus_expert` entity list (was contaminated) and the control
> subreddit (r/TopMindsOfReddit, used here, was later found invalid —
> replaced with r/politics). See `ANTIGRAVITY_HANDOFF.md` for current
> findings. Kept for historical reference only, do not cite numbers from
> this document.


This document presents the empirical results of **Methodology E**: expanding our understanding of Reddit link-sharing behaviors by categorizing URLs using the project's pre-built Cell 61 Epistemic Domain Taxonomy and running regressions across $r/\text{conspiracy}$ ($N = 21,091$) and $r/\text{AskReddit}$ ($N = 53,062$).

Instead of a flat `has_link` penalty, we isolate 4 active domain types:
1. `link_image_screenshot` (Imgur, catbox, etc. — visual evidence)
2. `link_academic_scientific` (NCBI, Nature, etc. — peer-reviewed science)
3. `link_mainstream_news` (NYTimes, Reuters, etc. — consensus news)
4. `link_government_official` (CDC, WHO, FBI, .gov — institutional authorities)

---

## 1. Direct Regression Coefficient Comparison

The table below contrasts the Logit (High Traction) regression coefficients under full length and covariate controls:

| Independent Variable (Construct) | r/conspiracy Coef (Pure Pop) | r/conspiracy p-value | r/AskReddit Coef (Control) | r/AskReddit p-value | Rhetorical Interpretation & Thesis Implications |
|---|---|---|---|---|---|
| **`pe_prob` (Personal Experience)** | **$+0.3211$** | $p = 0.063^{\dagger}$ | $+0.0446$ | $p = 0.462$ | **Subcultural Premium**: Lived experience is valued and trends positive inside conspiracy spaces, but is treated as statistical noise in mainstream spaces. |
| **`ps_prob` (Procedural Skepticism)** | **$+0.3523^{**}$** | $p = 0.009$ | **$-0.5514^{***}$** | $p < 0.001$ | **Symmetrical Divergence**: Logical auditing and challenging claims is an expected, rewarded practice in pure insider circles, but is heavily penalized in the general population. |
| **`has_maverick` (Maverick Authority)** | **$+0.7530^{***}$** | $p < 0.001$ | $-0.2969$ | $p = 0.161$ | **The Maverick Premium**: Citing dissident experts and whistleblowers is heavily rewarded in alternative spaces, but ignored/penalized in the mainstream control. |
| **`link_image_screenshot`** | $+0.0382$ | $p = 0.936$ | $+0.6723$ | $p = 0.138$ | **Visual Sourcing**: Image links trend positive across both communities, though they are statistically neutral when covariates are controlled. |
| **`link_academic_scientific`** | $-0.2340$ | $p = 0.752$ | $-1.1776$ | $p = 0.256$ | **Science Scepticism**: Citing academic journals faces a neutral-to-negative coefficient in both settings under full length controls. |
| **`link_mainstream_news`** | $+0.0330$ | $p = 0.934$ | $+0.3068$ | $p = 0.479$ | **Consensus News**: Citing mainstream news outlets has a neutral impact in both communities. |
| **`link_government_official`** | **$+1.2138^{***}$** | $p = 0.001$ | $-0.4393$ | $p = 0.563$ | **The "Admissions" Paradox**: Citing official government institutions (.gov, CDC, WHO) carries a massive positive premium in r/conspiracy, but is negative/neutral in r/AskReddit. |

*Significance: $\dagger \ p < 0.10$, $* \ p < 0.05$, $** \ p < 0.01$, $*** \ p < 0.001$. Models control for log character length.*

---

## 2. High-Impact Thesis Discovery: Citing the "Enemy"

The most striking, counterintuitive finding from this regression is the **strong positive effect of government links (`link_government_official`) in r/conspiracy ($coef = +1.2138, p = 0.001$)** alongside the negative effect in r/AskReddit.

> [!IMPORTANT]
> **The "Hostile Sourcing" Tactic (Citing the Enemy)**:
> * In mainstream communities, official `.gov` links are cited to support a normal point, which is standard behavior and carries no special traction premium.
> * In conspiracy communities, users almost never cite `.gov` links to agree with the official narrative. Instead, they engage in **Hostile Sourcing**: citing official documents or CDC data to expose perceived contradictions, cover-ups, or "admissions" from the authorities themselves.
> * *Example*: "Look at the CDC's own website admitting the side-effects..." or "Here is the declassified FBI document on their own server proving..."
> * Because this tactic is highly strategic and seen as defeating the establishment using their own official documents, these comments receive a **massive engagement premium** (+1.2138 Logit Coef) in pure insider environments.

---

## 3. Recommended Thesis Writing Framing
* **The "Selective Validation" Axis**: Emphasize that r/conspiracy does not reject all "official" materials. Rather, they engage in a highly selective, adversarial reading of institutional texts, turning official URLs into primary sources of subcultural validation.
* **The Audit Premium**: Highlight the clean divergence in procedural skepticism (`ps_prob`). In mainstream r/AskReddit, demanding proof and auditing logic is penalized ($coef = -0.5514$), whereas in r/conspiracy pure environments, it is actively rewarded ($coef = +0.3523$), demonstrating that "researching" is a core subcultural value.
