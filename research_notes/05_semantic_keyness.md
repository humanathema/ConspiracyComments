# Research Notes: Semantic Keyness & Rhetorical Framing (Methodology A)

> **SUPERSEDED (2026-07-17)**: this document predates fixes to the
> `consensus_expert` entity list (was contaminated) and the control
> subreddit (r/TopMindsOfReddit, used here, was later found invalid —
> replaced with r/politics). See `ANTIGRAVITY_HANDOFF.md` for current
> findings. Kept for historical reference only, do not cite numbers from
> this document.


This document presents the empirical results of **Methodology A**: extracting context windows ($N = 19,501$ context words in $r/\text{conspiracy}$ and $N = 3,672$ context words in $r/\text{AskReddit}$) around mentions of **maverick authorities** vs. **mainstream consensus experts** and running G-test Log-Likelihood Keyness calculations.

This analysis isolates the exact linguistic and conceptual boundaries that communities use to define these two competing classes of authority.

---

## 1. r/conspiracy: Esoteric Warfare vs. Institutional Apocalypticism

The semantic markers overrepresented in $r/\text{conspiracy}$'s pure insider population ($N = 21,091$ comments) reveal a deep ideological split in how trust is structured:

### A. Maverick Authorities: The Gatekeepers of Esoteric Truth
In alternative spaces, maverick authorities (e.g. Joe Rogan, David Icke, Alex Jones, Robert Malone) are talked about using a distinct semantic cluster:
* **Esoteric and Supernatural Sourcing**: **`aliens`** ($LL = +16.00$), **`angels`** ($LL = +10.18$), **`demons`** ($LL = +10.18$). Mavericks are not just valued for "alternative science" — they are trusted gatekeepers to topics completely excluded from mainstream consensus, bridging the gap between political dissent and cosmic/metaphysical warfare.
* **Skepticism of the Scribe**: **`media`** ($LL = +12.51$), **`talking`** ($LL = +8.45$). Mavericks are constantly discussed in opposition to the media apparatus, framed as individuals who are "talking" directly to the public outside corporate control.
* **Direct Subcultural Referencing**: **`conspiracy`** ($LL = +9.52$), **`jones`** ($LL = +8.73$), **`david`** ($LL = +8.15$).

### B. Mainstream Experts: Institutional Elitism & Apocalyptic Prophecy
In contrast, mainstream consensus experts (e.g. Albert Einstein, Rochelle Walensky, Alan Dershowitz) are discussed using an entirely different, high-stakes rhetorical framing:
* **Elite Institutional Markers**: **`professor`** ($LL = -59.34$), **`harvard`** ($LL = -55.99$), **`students`** ($LL = -41.23$). Mainstream experts are strictly associated with their elite academic affiliations. In alternative spaces, these are not badges of honor; they are markers of institutional capture and top-down authority.
* **Apocalyptic Prophecy and Geopolitics**: **`downfall`** ($LL = -119.31$), **`predicted`** ($LL = -113.35$), **`israel`** ($LL = -94.48$), **`middleeastmonitor`** ($LL = -127.98$). Mainstream historical figures (like Einstein or Sutton) are cited to discuss massive geopolitical crises and historical macro-predictions ("predicted the downfall...").

---

## 2. r/AskReddit: Financial Transaction vs. Pop Culture speculative matchups

In the mainstream control group ($r/\text{AskReddit}$), the rhetorical construction of authority is completely inverted, reflecting a more casual and pragmatic world:

### A. Maverick Authorities: Material Wealth & Skeptical Distance
In $r/\text{AskReddit}$, mavericks (such as Elon Musk or Joe Rogan) are discussed stripped of any esoteric or heroic framing:
* **The Currency of Influence**: **`money`** ($LL = +16.06$), **`buy`** ($LL = +5.74$). Mainstream readers discuss alternative authorities in terms of commercial transaction, corporate buyouts, and financial net worth, rather than alternative truth.
* **Cognitive Policing**: **`believe`** ($LL = +10.33$), **`fake`** ($LL = +6.88$), **`control`** ($LL = +6.88$). Discussions are highly analytical, debating whether a maverick's claim is *fake* or if people actually *believe* them.

### B. Mainstream Experts: Pop-Culture Casualization
The most surprising finding is how mainstream experts (philosophers, historical scientists) are discussed in $r/\text{AskReddit}$:
* **Pop-Culture Speculation**: **`batman`** ($LL = -28.18$), **`salma`** ($LL = -24.87$), **`superman`** ($LL = -18.23$), **`joker`** ($LL = -11.02$), **`tarantino`** ($LL = -9.95$). 
* Mainstream consensus experts are not treated as monolithic, threatening pillars of institutional capture. Instead, they are casualized — woven into pop culture debates, cinematic comparisons, or speculative thought experiments (e.g., philosophy matchups, film aesthetics).

---

## 3. Symmetrical Synthesis for Your Thesis

| Dimension of Comparison | r/conspiracy (Alternative Space) | r/AskReddit (Mainstream Space) |
|---|---|---|
| **How Mavericks are Framed** | **Spiritual/Esoteric Truth**: Gatekeepers of hidden knowledge, cosmic battles (*angels/demons/aliens*), and anti-media rebels. | **Financial Influence**: Material actors driven by raw capital (*money/buy*) whose claims require cognitive policing (*fake/believe*). |
| **How Mainstream Experts are Framed** | **Elite/Captured Gatekeepers**: Locked into institutional power centers (*Harvard/professor*) and cited primarily in the context of macro-political collapse (*downfall/predicted*). | **Casual Dialogue Partners**: Demoted from ivory towers to become casual pop-culture companions, woven into fiction, film, and speculative matchups (*Batman/Tarantino*). |

> [!TIP]
> **Key Thesis Argument**: 
> This semantic keyness analysis proves that the "reversal of trust" is accompanied by a **complete conceptual transformation**. In alternative subcultures, mavericks are elevated to cosmic truth-tellers while mainstream experts are cast as gatekeepers of academic elites. In mainstream spaces, mavericks are reduced to commercial actors while mainstream experts are treated so familiarly they are blended directly into pop-culture and fiction.
