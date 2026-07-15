# Research Notes: Omitted Variable Bias and Thread Size Artifacts in Epistemic Credibility

These notes document a deep-dive investigation into two key anomalies flagged in the current `ANTIGRAVITY_HANDOFF.md`:
1. **The Personal Experience (`pe_prob`) Negative Flip**: Why personal experience suddenly predicts significantly lower engagement in the cleanest insider environments.
2. **The 100% Insider Presence Threshold Drop**: Why the positive relationship between maverick authority appeals and engagement drops and loses significance when tightening the insider presence threshold from `0.875` to `1.0`.

---

## 1. The Personal Experience (`pe_prob`) Negative Flip

### The Finding: Omitted Variable Bias (OVB)
The negative relationship between personal experience and high traction in the "genuine insider environment" is a classic textbook case of **omitted variable bias** on comment length. 

1. **High Length Correlation**: Personal experience narratives are naturally much longer. There is a strong positive correlation between `pe_prob` and character length ($r = 0.305$) in the pure population.
2. **The Length Penalty**: There is a severe penalty for long-winded comments on Reddit traction. In the multivariate logit model, `log_char_length` has an extremely significant, negative coefficient of **$-0.2100$ ($p < 0.001$)**.
3. **The Uncontrolled Confounding**: Because the previous model did not control for length, `pe_prob` absorbed this penalty. Once `log_char_length` is added to the regression, the negative effect of `pe_prob` **shrinks by 70% and completely loses statistical significance ($p = 0.370$)**.

The table below demonstrates the before-and-after results for both Logit (high traction) and OLS (log upvotes):

| Model & Specification | Variable | Coefficient | Std. Err | z / t-stat | p-value | Significance |
|---|---|---|---|---|---|---|
| **Logit (High Traction)** | | | | | | |
| *No Length Control* | `pe_prob` | $-0.4347$ | $0.141$ | $-3.089$ | **$0.002$** | Significant Negative |
| *With Length Control* | `pe_prob` | $-0.1322$ | $0.148$ | $-0.896$ | **$0.370$** | *Not Significant* |
| *With Length Control* | `log_char_length` | $-0.2100$ | $0.032$ | $-6.567$ | **$< 0.001$** | Significant Negative |
| **OLS (Log Upvotes)** | | | | | | |
| *No Length Control* | `pe_prob` | $-0.0012$ | $0.000$ | $-2.542$ | **$0.011$** | Significant Negative |
| *With Length Control* | `pe_prob` | $-0.0003$ | $0.000$ | $-0.565$ | **$0.572$** | *Not Significant* |
| *With Length Control* | `log_char_length` | $-0.0006$ | $0.000$ | $-5.712$ | **$< 0.001$** | Significant Negative |

> [!TIP]
> **Thesis Recommendation**: We should update all future regression models to include a log-transformed character length (`log_char_length`) control. This completely resolves the confusing "PE negative flip" and establishes that personal experience is actually **neutrally received** ($p \approx 0.37$) by community insiders once narrative length is accounted for.

### Qualitative Context
Reviewing the top-voted vs. bottom-voted personal experience comments clarifies this dynamic:
* **High-Traction PE (Upvotes $\ge 23$, Short/Punchy)**: 
  * *Example (Length 135)*: "There's something fishy about it, fear mongering. **I remember** the Chinese videos and also the body bag videos in NY..."
  * *Example (Length 138)*: "Considering what’s in the Epstein files, **I’m suspicious** about all those kids that Madonna and her friends adopted..."
  * These comments are short, quick, and tap into shared community memories/suspicions. They do not get penalized by the "TL;DR" effect.
* **Low-Traction PE (Negative Upvotes, Long/Confrontational)**:
  * *Example (Length 1,039)*: "I swear the only people who refuse to believe Covid is a real disease are people that literally have no social life... **I know** it's hard to admit to yourself you got tricked..."
  * *Example (Length 3,349)*: "You are correct. COVID-19 was unfortunately a Biological Weapon of Mass Destruction... **I'm about** to explain below..."
  * These are massive, dense essays often engaging in hostile debates. Their length and argumentative nature invite penalties and downvotes in insider threads.

---

## 2. The 100% Insider Presence Threshold Drop

### The Finding: A Mathematical Selection Artifact
When the insider presence threshold is tightened to $1.00$ (fully insider-only threads), the point estimate for `has_maverick` drops and loses statistical significance. The quantitative breakdown reveals that this is a **structural selection artifact** of thread size rather than a change in the community's rhetoric.

By comparing the three segments of the low-elasticity + non-viral base population, we see a stark divergence:

| Metric | Group A (0.75 - 0.99) | Group B (1.00 - Fully Insider) | Group C (< 0.75) |
|---|---|---|---|
| **Comments (N)** | $17,296$ | **$10,016$** | $36,983$ |
| **Unique Threads** | $1,024$ | **$2,080$** | $3,658$ |
| **Median Thread Size** | **$23.0$** | **$6.0$** | **$31.0$** |
| **Mean Thread Size** | $29.61$ | **$10.18$** | $63.92$ |
| **High Traction Rate ($\ge 5$ upvotes)** | **$12.53\%$** | **$5.80\%$** | $14.72\%$ |
| **Mean Upvotes** | $2.21$ | **$1.55$** | $3.15$ |
| **Maverick Prevalence** | $1.85\%$ | $1.71\%$ | $1.38\%$ |
| **Personal Experience Prevalence** | $10.74\%$ | $9.30\%$ | $12.10\%$ |

### The Mechanics of the 100% Anomaly
1. **Mathematical Selection of Small Threads**: It is statistically much easier for a thread to have 100% of its commenters be insiders if the thread is very small. If a thread has only 3 comments, hitting 100% insider presence is common. If a thread has 150 comments, hitting 100% is virtually impossible. As a result, Group B (1.00) has a median thread size of **only 6 comments** (compared to 23 for Group A).
2. **Suppressed Traction Signal**: In these small, quiet threads, there is very little baseline traffic or upvoting. The rate of comments hitting high traction ($\ge 5$ upvotes) is cut in half from **$12.53\%$ in Group A to just $5.80\%$ in Group B**. Mean upvotes drop from $2.21$ to $1.55$.
3. **Loss of Statistical Power**: Because the baseline traction rate drops so heavily and the thread size is heavily restricted, the regression model is starved of "positives" (the rare class in our logistic model), which inflates standard errors and shrinks the point estimate.

> [!IMPORTANT]
> **Thesis Recommendation**: The $1.00$ (fully insider) threshold should **not** be presented as a meaningful rhetorical threshold. It is a mathematical filter for quiet, isolated, low-engagement threads that never reached traction to begin with. The **$0.75$ or $0.80$ thresholds are much more structurally defensible** for representing a "healthy insider thread environment" where upvoting dynamics can actually function.

---

## 3. Recommended Action Plan
1. **Adopt `log_char_length`**: Add `log_char_length` as a standard control to all regression models.
2. **Anchor Insider Presence at 0.75 - 0.85**: Avoid the $1.00$ threshold in the main thesis argument, using the thread size and suppressed voting metrics above to justify the decision.
