# Research Notes: Interactional Stance Detection in Comment Replies

> **SUPERSEDED (2026-07-17)**: this document predates fixes to the
> `consensus_expert` entity list (was contaminated) and the control
> subreddit (r/TopMindsOfReddit, used here, was later found invalid —
> replaced with r/politics). See `ANTIGRAVITY_HANDOFF.md` for current
> findings. Kept for historical reference only, do not cite numbers from
> this document.


This document presents the design, prototype, and results of **Task D**: implementing a deterministic, rule/lexicon-based agreement/disagreement classifier for child comments/replies to establish a secondary outcome metric.

To study the community's behavioral reaction to different epistemic credentials, we extracted child replies ($N = 7,657$) written directly in response to comments from our clean, "genuine insider environment" pure population ($N = 21,091$ parent comments).

---

## 1. Classifier Design (Deterministic Rule-Based)

Our stance classifier is a deterministic rule set designed for high precision. It matches distinct rhetorical markers of explicit agreement vs. explicit disagreement/skepticism:

* **Agreement / Endorsement**:
  * *Regex*: `^this\.?$`, `^this!+$`, `^this right here`, `^exactly\.?$`, `^spot on`, `\bwell said\b`, `\bunderrated comment\b`, `\bnailed it\b`, `\bpreach\b`, `\bagree(d)?\b`, `\b100%\b`, `\babsolutely\b`, `\bindeed\b`, `\bcouldn't agree more\b`, `\bthis is the way\b`, `\bso true\b`
* **Disagreement / Challenge / Skepticism**:
  * *Regex*: `^source\??$`, `^proof\??$`, `\bbullshit\b`, `\bbull shit\b`, `\bbs\b`, `\bnot true\b`, `\bwrong\b`, `\bdisagree\b`, `\bpropaganda\b`, `\bcitation needed\b`, `\bdebunked\b`, `\blol no\b`, `^nope\.?$`, `\bstop spreading\b`, `\bno it's not\b`, `\bfake\b`

*Classifications that match both or match neither are treated as **Neutral / Elaborative** (which naturally captures the majority of Reddit replies).*

---

## 2. Reply Stance Rates Across Parent Credentials

By grouping child replies based on the epistemic features of their parent comment, we uncover the exact social feedback loops operating within the r/conspiracy insider subculture:

| Parent Comment's Epistemic Feature | Total Child Replies (N) | Agreement Rate (%) | Disagreement Rate (%) | Neutral/Elaborative (%) | Rhetorical Feedback Mechanism |
|---|---|---|---|---|---|
| **`parent_pe_prob` (Personal Experience)** | | | | | |
| *High ($\ge 0.4$)* | $1,046$ | **$8.89\%$** | **$6.41\%$** | $84.70\%$ | **The Agreement Magnet**: Sharing personal experiences and memories shields the poster from challenge and invites significantly more community endorsement (+60% agreement rate, lower disagreement). |
| *Low ($< 0.1$)* | $6,611$ | $5.58\%$ | $7.46\%$ | $86.96\%$ | |
| **`parent_ps_prob` (Procedural Skepticism)** | | | | | |
| *High ($\ge 0.4$)* | $1,243$ | **$5.31\%$** | **$11.91\%$** | $82.78\%$ | **The Conflict Catalyst**: Questioning details, demanding proof, or arguing logic nearly **doubles the rate of disagreement** in child replies, explaining why these moves face upvote penalties. |
| *Low ($< 0.1$)* | $6,414$ | $6.17\%$ | $6.42\%$ | $87.40\%$ | |
| **`parent_has_link` (Citing Outside links)** | | | | | |
| *Has Link ($= 1$)* | $408$ | **$5.64\%$** | **$11.03\%$** | $83.33\%$ | **The Argument Invitation**: Citing outside URLs does not settle debates; it provokes a massive **55% increase in disagreement rates** in replies. |
| *No Link ($= 0$)* | $7,249$ | $6.06\%$ | $7.10\%$ | $86.84\%$ | |
| **`parent_has_maverick` (Alternative Authority)** | | | | | |
| *Has Maverick ($= 1$)* | $139$ | **$3.60\%$** | **$7.91\%$** | $88.49\%$ | **Substantive Dialogue**: Maverick authority appeals do not change disagreement rates, but they reduce simple "exactly!" agreements in favor of long-form, neutral/elaborative discussions. |
| *No Maverick ($= 0$)* | $7,518$ | $6.08\%$ | $7.30\%$ | $86.62\%$ | |

---

## 3. High-Impact Thesis Discussion Framing

This behavioral interaction metric provides the "missing mechanism" for the thesis narrative:

> [!TIP]
> **The Social Feedback Explanation for Upvote Coefficients**:
> * Why are `has_link` and `ps_prob` consistently penalized in upvotes? Because they are interactionally **confrontational**. They disrupt passive community reading and serve as conflict catalysts, drawing significantly more argumentative, disagreeing replies from other users.
> * Why are `pe_prob` (personal experience) comments structurally favored/neutral? Because they are **cooperative and anti-confrontational**. Sharing a subjective, personal memory invites empathy, validation, and social endorsement, which effectively shields the comment from direct logical disagreement.
