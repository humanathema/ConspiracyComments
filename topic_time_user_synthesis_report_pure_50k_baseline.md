# Stratified Narrative Analysis: 50,000 Sampled Pure r/conspiracy Comments

This report presents the fine-grained narrative and temporal regressions fit over a **50,000-comment representative sample** drawn randomly from the true **1,985,823 unbrigaded, veteran-heavy (75%+ insider) pure comment population**.

By running sentence-transformer-based BERTopic inference over this sample, we mapped the comments to their thematic clusters while **preserving the full upvote variance of the dependent variable**. This resolves the range restriction (selection bias) problem present in the earlier high-upvote-only (>=100 upvotes) topic analysis.

**Multiple-comparison note**: this report fits 67 separate OLS tests (across strata x variables). Every "significant" claim below is labeled with whether it survives a Bonferroni correction across all 67 tests (threshold p < 7.46e-04) or only holds at the uncorrected p < 0.05 level. All coefficient values and p-values in this report are read directly from `topic_time_regression_results_pure_50k.csv` -- none are hand-entered.

---

## 1. Regression Coefficients by Chronological Era (OLS: Log Upvotes)

The OLS models reveal the shifting value of epistemic markers across three key eras of r/conspiracy's evolution:

| Historical Era | N | `has_maverick` (Dissenting) | `has_canonical` (Mainstream) | `has_consensus` (Official) | `pe_prob` (Personal Exp.) | `ps_prob` (Procedural Skep.) |
| :--- | :---: | :--- | :--- | :--- | :--- | :--- |
| Pre-2016 Era (2008-2015) | 3,248 | +0.008* (p=3.57e-02) | -0.007 (p=5.86e-01) | N/A | +0.007 (p=7.94e-02) | -0.003 (p=3.44e-01) |
| Political Realignment Era (2016-2019) | 11,490 | +0.010* (p=4.47e-02) | +0.012 (p=3.93e-01) | N/A | +0.006 (p=2.26e-01) | -0.006 (p=7.40e-02) |
| Pandemic & Modern Era (2020-2025) | 35,262 | -0.004 (p=1.70e-01) | +0.003 (p=6.42e-01) | +0.024** (p=6.93e-03) | +0.006** (p=4.07e-03) | +0.000 (p=9.32e-01) |

### Chronological Findings (data-driven, see note above on correction status):
**No epistemic-construct cell survives Bonferroni correction** (threshold p < 7.46e-04 across 67 OLS tests). Any single "significant" cell below should be read as suggestive at best, not as a confirmed subgroup effect.

Cells significant at uncorrected p < 0.05 only (did not survive Bonferroni; report with appropriate caution):
  - `pe_prob` in *Pandemic & Modern Era (2020-2025)*: coef=+0.0057, p=4.07e-03
  - `has_consensus_expert` in *Pandemic & Modern Era (2020-2025)*: coef=+0.0238, p=6.93e-03
  - `has_maverick` in *Pre-2016 Era (2008-2015)*: coef=+0.0080, p=3.57e-02
  - `has_maverick` in *Political Realignment Era (2016-2019)*: coef=+0.0099, p=4.47e-02

---

## 2. Regression Coefficients by Thematic Super-Topic (OLS: Log Upvotes)

The models reveal how epistemic authorities and narrative structures are rewarded differently across specific conspiratorial genres:

| Thematic Super-Topic | N | `has_maverick` | `has_canonical` | `has_consensus` | `pe_prob` | `ps_prob` |
| :--- | :---: | :--- | :--- | :--- | :--- | :--- |
| 9/11 & Structural Collapses | 1,173 | +0.023 (p=1.24e-01) | +0.000 (p=nan) | N/A | +0.006 (p=5.72e-01) | -0.015 (p=6.34e-02) |
| Alex Jones & Deep State/Secret Societies | 2,240 | +0.014 (p=3.20e-01) | -0.015 (p=8.08e-01) | N/A | +0.004 (p=6.17e-01) | -0.000 (p=9.75e-01) |
| Elections, Finance & Control | 2,914 | -0.007 (p=4.81e-01) | +0.026 (p=1.71e-01) | N/A | +0.011 (p=1.27e-01) | -0.000 (p=9.52e-01) |
| Environment, Science, Health & Tech | 3,322 | -0.006 (p=6.59e-01) | +0.023 (p=3.61e-01) | N/A | +0.004 (p=6.17e-01) | +0.003 (p=5.93e-01) |
| Geopolitics, Wars & Whistleblowers | 2,033 | -0.004 (p=7.38e-01) | -0.008 (p=7.99e-01) | N/A | +0.019* (p=1.96e-02) | -0.014** (p=4.37e-03) |
| Other / General Conspiracy | 5,136 | -0.001 (p=7.06e-01) | -0.008 (p=6.53e-01) | N/A | -0.005 (p=3.26e-01) | -0.000 (p=9.09e-01) |
| Outliers | 30,915 | +0.005 (p=1.32e-01) | +0.002 (p=7.47e-01) | +0.022* (p=1.19e-02) | +0.005* (p=1.25e-02) | -0.001 (p=6.29e-01) |
| Sci-Fi, Space, UFOs & Esoteric | 2,267 | -0.022 (p=4.15e-01) | +0.009 (p=8.13e-01) | N/A | +0.008 (p=5.83e-01) | -0.029* (p=1.38e-02) |

### Thematic Findings (data-driven, see note above on correction status):
**No epistemic-construct cell survives Bonferroni correction** (threshold p < 7.46e-04 across 67 OLS tests). Any single "significant" cell below should be read as suggestive at best, not as a confirmed subgroup effect.

Cells significant at uncorrected p < 0.05 only (did not survive Bonferroni; report with appropriate caution):
  - `ps_prob` in *Geopolitics, Wars & Whistleblowers*: coef=-0.0142, p=4.37e-03
  - `has_consensus_expert` in *Outliers*: coef=+0.0216, p=1.19e-02
  - `pe_prob` in *Outliers*: coef=+0.0053, p=1.25e-02
  - `ps_prob` in *Sci-Fi, Space, UFOs & Esoteric*: coef=-0.0294, p=1.38e-02
  - `pe_prob` in *Geopolitics, Wars & Whistleblowers*: coef=+0.0195, p=1.96e-02

---

## 3. Methodological Note for Your Thesis

This sample-based approach is a defense against **selection bias**: the earlier high-upvote-only (>=100 upvotes) regressions had a range-restricted dependent variable, which distorts standard errors. Sampling 50,000 comments across the *entire* upvote distribution of the pure population restores that variance.

It does **not**, on its own, defend against multiple-comparison inflation from running many strata x variable tests -- see the Bonferroni annotations above. A coefficient losing or gaining significance across strata is also not, by itself, evidence that the true effect differs between strata; that requires an explicit interaction-term test (see `run_integrated_regressions.py`'s `run_interaction_regressions` for the pattern), which this script does not run.

---
*Report compiled on 2026-07-21 18:53:26*
