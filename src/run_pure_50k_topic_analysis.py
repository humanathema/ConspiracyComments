"""src/run_pure_50k_topic_analysis.py

Optimized script to execute the topic-stratified and temporal-stratified regression 
analysis using a highly representative, statistically powerful 50,000-comment 
stratified sample from the 1.98M pure, unbrigaded r/conspiracy core.

Steps:
1. Loads IDs of the 1.98M pure regression population.
2. Randomly samples 50,000 comments.
3. Retrieves full text and metadata for the sample via an optimized DuckDB join.
4. Performs batch-processed BERTopic inference using the pre-trained model.
5. Groups fine-grained topics into 6 cohesive Super-Topics.
6. Runs OLS and Logit stratified regressions across both Super-Topics and temporal Eras.
7. Saves outputs to CSV and compiles a gorgeous, publication-ready research report.
"""
import os
import sys

# Maintain single-threaded safety for Apple Silicon
# Set these before any scientific/machine-learning libraries are imported
os.environ["NUMBA_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import numpy as np
import pandas as pd
import duckdb
import statsmodels.formula.api as smf
from datetime import datetime
from bertopic import BERTopic

# Insert src directory into path for local imports
sys.path.insert(0, os.path.dirname(__file__))
from rerun_refined_regressions_v2 import load_entities_split_corrected, compute_has_maverick, compute_has_consensus_expert
from refine_thesis_models import build_regex
from run_link_source_tier_regressions import determine_link_source_tier, build_source_authority_lookup
from combined_maverick_detector import load_maverick_disambiguation_lookup
from consensus_disambiguation_lookup import load_consensus_disambiguation_lookup

# File paths
STAGED_PATH = 'data/processed/research_corpus_staged_scores_full21m.parquet'
HEDGED_SUSPICION_PATH = 'data/processed/hedged_suspicion_scores_full21m.parquet'
EMPATH_PATH = 'data/processed/empath_scores_full.parquet'
THREAD_PATH = 'data/processed/thread_quality_metrics.csv'
PRESENCE_PATH = 'data/processed/thread_insider_presence.csv'
BRIGADE_PATH = 'data/processed/comment_brigade_flags.csv'
TOPIC_NAMES_PATH = 'data/processed/monthTopics1.csv'

# Output paths
OUT_REGRESSIONS_PATH = 'data/processed/topic_time_regression_results_pure_50k.csv'
OUT_REPORT_PATH = '/Users/nash/.gemini/antigravity/brain/cd0cd598-9b19-42eb-b934-3b18572fd865/topic_time_user_synthesis_report_pure_50k.md'
OUT_REPORT_PATH_BACKWARD_COMPAT = '/Users/nash/.gemini/antigravity/brain/3ede4f65-2733-4214-bd23-07f7b26e9536/topic_time_user_synthesis_report_pure_50k.md'

# Mapping of fine-grained topics to 6 Super-Topics
SUPER_TOPIC_MAP = {
    "Geopolitics, Wars & Whistleblowers": [3, 19, 21, 23, 56, 57, 70, 79, 84],
    "9/11 & Structural Collapses": [2, 5],
    "Elections, Finance & Control": [0, 8, 12, 15, 26, 28, 40, 75, 83, 86],
    "Alex Jones & Deep State/Secret Societies": [1, 7, 34, 36, 53, 66, 89],
    "Sci-Fi, Space, UFOs & Esoteric": [9, 17, 22, 30, 51],
    "Environment, Science, Health & Tech": [6, 11, 18, 25, 29, 31, 33, 42, 43, 44, 45, 46, 47, 48, 49, 50, 52, 55, 58, 59, 74, 82]
}

def get_super_topic(assigned_topic):
    """Categorize a fine-grained topic ID into a Super-Topic."""
    for st_name, topics in SUPER_TOPIC_MAP.items():
        if assigned_topic in topics:
            return st_name
    if assigned_topic == -1:
        return "Outliers"
    return "Other / General Conspiracy"


def load_and_sample_dataset():
    """Load IDs of the 1.98M pure regression population, draw a representative
    sample of 50,000, and pull full text and metadata using DuckDB."""
    print("\n--- Phase 0: Sourcing 50,000 Representatively Sampled Comments ---")
    con = duckdb.connect()
    
    # 1. Pull IDs for the full 1.98M pure regression population
    print("Finding all candidate comment IDs in the unbrigaded core...")
    id_query = f"""
        SELECT s.id
        FROM '{STAGED_PATH}' s
        JOIN '{EMPATH_PATH}' e ON s.id = e.id
        JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
        LEFT JOIN '{PRESENCE_PATH}' p ON SUBSTR(e.link_id, 4) = p.post_id
        LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
        WHERE t.elasticity_ratio <= (SELECT quantile(elasticity_ratio, 0.33) FROM '{THREAD_PATH}')
          AND t.is_high_crosspost = 0
          AND p.insider_presence_ratio >= 0.75
          AND COALESCE(b.brigade_upvote_flag, 0) = 0
          AND COALESCE(b.brigade_downvote_flag, 0) = 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
    """
    df_ids = con.execute(id_query).df()
    print(f"Total available comments in unbrigaded pure population: {len(df_ids):,}")
    
    # 2. Draw a representative sample of 50,000 IDs
    print("Drawing random sample of 50,000 IDs...")
    df_sample_ids = df_ids.sample(n=50000, random_state=42).copy()
    
    # 3. Pull full fields strictly for the 50,000 sampled IDs
    print("Retrieving text and metadata fields for the 50,000 sampled comments...")
    con.register('sample_ids_tmp', df_sample_ids)
    
    full_query = f"""
        SELECT s.id, e.author, e.created_utc, e.upvotes, e.char_length, s.pe_prob, s.ps_prob, h.hs_prob, e.has_link, e.text, SUBSTR(e.link_id, 4) as post_id
        FROM sample_ids_tmp t_ids
        JOIN '{STAGED_PATH}' s ON t_ids.id = s.id
        JOIN '{EMPATH_PATH}' e ON s.id = e.id
        LEFT JOIN '{HEDGED_SUSPICION_PATH}' h ON s.id = h.id
        QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
    """
    df_sample = con.execute(full_query).df()
    print(f"Successfully loaded {len(df_sample):,} full rows.")
    return df_sample


def add_epistemic_features(df):
    """Add entity-mention flags and standard regression controls."""
    print("\n--- Phase 1: Feature Engineering & Entity Flagging ---")
    mavericks, canon, consensus = load_entities_split_corrected()
    
    rx_mav = build_regex(mavericks)
    rx_can = build_regex(canon)
    rx_con = build_regex(consensus)
    
    # Load disambiguation lookups
    print("Loading disambiguation lookups for entities...")
    maverick_lookup = load_maverick_disambiguation_lookup()
    consensus_lookup = load_consensus_disambiguation_lookup()
    
    print("Flagging entity mentions with disambiguation fallbacks...")
    df['has_maverick'] = compute_has_maverick(df, rx_mav, maverick_lookup)
    df['has_canonical_expert'] = df['text'].apply(lambda x: 1 if bool(rx_can.search(str(x))) else 0)
    df['has_consensus_expert'] = compute_has_consensus_expert(df, rx_con, consensus_lookup)
    
    # Build source authority and classify link tiers
    print("Building source authority and classifying link tiers...")
    build_source_authority_lookup()
    df['link_source_tier'] = df.apply(lambda r: determine_link_source_tier(r['text'], r['has_link']), axis=1)
    
    # Construct binary indicators for each link tier
    for tier in ['mainstream_reliable', 'mainstream_imperfect', 'alt_media', 'aggregator_or_platform', 'unmatched_link']:
        df[f'link_{tier}'] = (df['link_source_tier'] == tier).astype(int)
    
    # Log controls
    df['log_char_length'] = np.log(df['char_length'] + 1)
    df['log_upvotes'] = np.log(df['upvotes'] - df['upvotes'].min() + 1)
    
    # Set high_traction relative to the median upvotes of this 50,000-comment dataset.
    # Since this spans the entire upvote spectrum, this will introduce rich binary variance.
    median_upvotes = df['upvotes'].median()
    print(f"Defining High Traction (high_traction) as upvotes >= {median_upvotes:.1f} (Median)")
    df['high_traction'] = (df['upvotes'] >= median_upvotes).astype(int)
    
    # Fill missing values
    df['pe_prob'] = df['pe_prob'].fillna(0.0)
    df['ps_prob'] = df['ps_prob'].fillna(0.0)
    df['hs_prob'] = df['hs_prob'].fillna(0.0)
    
    return df


def run_topic_inference(df):
    """Load BERTopic model and predict topics."""
    print("\n--- Phase 2: Running BERTopic Inference ---")
    print("Loading 761MB trained BERTopic model...")
    model = BERTopic.load("data/processed/bertopic_model")
    print("BERTopic model loaded successfully!")
    
    texts = df['text'].fillna("").tolist()
    
    print(f"Running inference on {len(texts):,} texts...")
    all_topics, _ = model.transform(texts)
        
    df['assigned_topic'] = all_topics
    
    # Map topic names
    df_names = pd.read_csv(TOPIC_NAMES_PATH)
    topic_dict = dict(zip(df_names['Topic'], df_names['Name']))
    df['topic_name'] = df['assigned_topic'].map(topic_dict).fillna("Unknown")
    df['super_topic'] = df['assigned_topic'].apply(get_super_topic)
    
    # Extract year/month
    df['dt'] = pd.to_datetime(df['created_utc'], unit='s')
    df['year'] = df['dt'].dt.year
    df['year_month'] = df['dt'].dt.to_period('M').astype(str)
    
    return df


def run_robust_regression(formula, df_sub, name_label, cov_type='nonrobust', group_col=None):
    """Helper to fit OLS and Logit models while checking for sparsity issues."""
    res_dict_list = []
    
    # Check for has_consensus_expert sparsity to prevent separation errors
    n_consensus = int(df_sub["has_consensus_expert"].sum())
    use_formula = formula
    dropped_consensus = False
    
    if n_consensus < 15:
        use_formula = formula.replace(" + has_consensus_expert", "")
        dropped_consensus = True
        
    if cov_type == 'cluster' and group_col:
        df_fit = df_sub.dropna(subset=[group_col])
        groups = df_fit[group_col].astype(str)
    else:
        df_fit = df_sub
        groups = None

    vars_to_store = [
        "pe_prob", "ps_prob", "hs_prob",
        "link_mainstream_reliable", "link_mainstream_imperfect", "link_alt_media",
        "link_aggregator_or_platform", "link_unmatched_link",
        "has_maverick", "has_canonical_expert", "has_consensus_expert", "log_char_length"
    ]

    # 1. Logit Model (High Traction)
    try:
        if cov_type == 'cluster' and groups is not None:
            m_logit = smf.logit(use_formula, data=df_fit).fit(cov_type='cluster', cov_kwds={'groups': groups}, disp=0, maxiter=100)
        else:
            m_logit = smf.logit(use_formula, data=df_fit).fit(disp=0, maxiter=100)
            
        for var in vars_to_store:
            if var in m_logit.params:
                res_dict_list.append({
                    "stratum": name_label,
                    "model_type": "Logit (High Traction)",
                    "cov_type": cov_type if cov_type != 'nonrobust' else 'naive',
                    "variable": var,
                    "coef": m_logit.params[var],
                    "se": m_logit.bse[var],
                    "pvalue": m_logit.pvalues[var],
                    "n_obs": int(m_logit.nobs)
                })
        if dropped_consensus:
            res_dict_list.append({
                "stratum": name_label,
                "model_type": "Logit (High Traction)",
                "cov_type": cov_type if cov_type != 'nonrobust' else 'naive',
                "variable": "has_consensus_expert",
                "coef": np.nan, "se": np.nan, "pvalue": np.nan,
                "n_obs": len(df_fit),
                "note": "Dropped due to sparsity (<15 cases)"
            })
    except Exception as e:
        print(f"  Logit ({cov_type}) failed for {name_label}: {e}")
        
    # 2. OLS Model (Log Upvotes)
    try:
        ols_formula = use_formula.replace("high_traction", "log_upvotes")
        if cov_type == 'cluster' and groups is not None:
            m_ols = smf.ols(ols_formula, data=df_fit).fit(cov_type='cluster', cov_kwds={'groups': groups})
        else:
            m_ols = smf.ols(ols_formula, data=df_fit).fit()
            
        for var in vars_to_store:
            if var in m_ols.params:
                res_dict_list.append({
                    "stratum": name_label,
                    "model_type": "OLS (Log Upvotes)",
                    "cov_type": cov_type if cov_type != 'nonrobust' else 'naive',
                    "variable": var,
                    "coef": m_ols.params[var],
                    "se": m_ols.bse[var],
                    "pvalue": m_ols.pvalues[var],
                    "n_obs": int(m_ols.nobs)
                })
        if dropped_consensus:
            res_dict_list.append({
                "stratum": name_label,
                "model_type": "OLS (Log Upvotes)",
                "cov_type": cov_type if cov_type != 'nonrobust' else 'naive',
                "variable": "has_consensus_expert",
                "coef": np.nan, "se": np.nan, "pvalue": np.nan,
                "n_obs": len(df_fit),
                "note": "Dropped due to sparsity (<15 cases)"
            })
    except Exception as e:
        print(f"  OLS ({cov_type}) failed for {name_label}: {e}")
        
    return res_dict_list


def run_stratified_regressions(df):
    """Phase 3: Run OLS and Logit models across Super-Topics and temporal Eras."""
    print("\n--- Phase 3: Fitting Stratified Regressions on Labeled 50k Core ---")
    
    formula = (
        "high_traction ~ pe_prob + ps_prob + hs_prob + "
        "link_mainstream_reliable + link_mainstream_imperfect + link_alt_media + link_aggregator_or_platform + link_unmatched_link + "
        "has_maverick + has_canonical_expert + has_consensus_expert + log_char_length"
    )
    
    # We will accumulate original naive results and comparative clustered results separately
    naive_results = []
    clustered_results = []
    
    cov_types = [
        ("naive", 'nonrobust', None),
        ("thread", 'cluster', 'post_id'),
        ("author", 'cluster', 'author')
    ]
    
    # A. Stratify by Super-Topic
    print("Fitting models by Super-Topic...")
    for st_name in df['super_topic'].unique():
        df_sub = df[df['super_topic'] == st_name]
        print(f"  Super-Topic: {st_name:<45} | N = {len(df_sub):,}")
        if len(df_sub) >= 200:
            # Naive (original behavior)
            res_naive = run_robust_regression(formula, df_sub, f"Super-Topic: {st_name}")
            naive_results.extend(res_naive)
            
            # Clustered sweep
            for cov_name, cov_type, group_col in cov_types:
                res_clust = run_robust_regression(formula, df_sub, f"Super-Topic: {st_name}", cov_type=cov_type, group_col=group_col)
                clustered_results.extend(res_clust)
            
    # B. Stratify by Chronological Era
    print("\nFitting models by Temporal Era...")
    eras = [
        ("Pre-2016 Era (2008-2015)", df['year'] <= 2015),
        ("Political Realignment Era (2016-2019)", (df['year'] >= 2016) & (df['year'] <= 2019)),
        ("Pandemic & Modern Era (2020-2025)", df['year'] >= 2020)
    ]
    for era_name, mask in eras:
        df_sub = df[mask]
        print(f"  Era: {era_name:<45} | N = {len(df_sub):,}")
        if len(df_sub) >= 200:
            # Naive (original behavior)
            res_naive = run_robust_regression(formula, df_sub, f"Era: {era_name}")
            naive_results.extend(res_naive)
            
            # Clustered sweep
            for cov_name, cov_type, group_col in cov_types:
                res_clust = run_robust_regression(formula, df_sub, f"Era: {era_name}", cov_type=cov_type, group_col=group_col)
                clustered_results.extend(res_clust)
            
    # Save original naive-only results
    df_results_naive = pd.DataFrame(naive_results)
    df_results_naive.to_csv(OUT_REGRESSIONS_PATH, index=False)
    print(f"Saved stratified coefficients to {OUT_REGRESSIONS_PATH}")

    # Save comparative clustered results
    OUT_REGRESSIONS_CLUSTERED_PATH = "data/processed/topic_time_regression_results_pure_50k_clustered.csv"
    pd.DataFrame(clustered_results).to_csv(OUT_REGRESSIONS_CLUSTERED_PATH, index=False)
    print(f"Saved comparative clustered stratified coefficients to {OUT_REGRESSIONS_CLUSTERED_PATH}")

    return df_results_naive


def write_synthesis_report(df_results, df):
    """Phase 4: Compile results and write an academic synthesis report to artifacts.

    All narrative claims below are generated directly from df_results -- no
    coefficient or p-value is ever hand-typed. A prior version of this function
    had hardcoded "Key Discoveries" bullets that did not match the regression
    output (e.g. claiming a +0.057 maverick premium where the real fitted
    value was +0.002, p=0.39); this rewrite closes that gap structurally by
    building every claim from a lookup against df_results.
    """
    print("\n--- Phase 4: Compiling and Writing Synthesis Report ---")

    variables = [
        "has_maverick", "has_canonical_expert", "has_consensus_expert",
        "pe_prob", "ps_prob", "hs_prob",
        "link_mainstream_reliable", "link_mixed_or_low_reliability",
        "link_aggregator_or_platform", "link_unmatched_link"
    ]
    var_labels = {
        "has_maverick": "`has_maverick`",
        "has_canonical_expert": "`has_canonical_expert`",
        "has_consensus_expert": "`has_consensus_expert`",
        "pe_prob": "`pe_prob`",
        "ps_prob": "`ps_prob`",
        "hs_prob": "`hs_prob`",
        "link_mainstream_reliable": "`link_mainstream_reliable`",
        "link_mixed_or_low_reliability": "`link_mixed_or_low_reliability`",
        "link_aggregator_or_platform": "`link_aggregator_or_platform`",
        "link_unmatched_link": "`link_unmatched_link`"
    }

    # Bonferroni threshold across every OLS test actually fit (all strata x
    # all variables), not just the ones we happen to highlight in prose --
    # otherwise the "significant" bullets below would themselves be a form
    # of post-hoc cherry-picking.
    ols_all = df_results[df_results['model_type'] == 'OLS (Log Upvotes)'].dropna(subset=['pvalue'])
    n_ols_tests = len(ols_all)
    bonferroni_alpha = 0.05 / n_ols_tests if n_ols_tests else float('nan')

    # Helper to retrieve coefficients safely
    def get_coef_str(df_res, stratum, model, var):
        sub = df_res[(df_res['stratum'] == stratum) & (df_res['model_type'] == model) & (df_res['variable'] == var)]
        if sub.empty or pd.isna(sub.iloc[0]['coef']):
            return "N/A"
        row = sub.iloc[0]
        c = row['coef']
        p = row['pvalue']
        stars = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
        return f"{c:+.3f}{stars} (p={p:.2e})"

    def get_row(df_res, stratum, var):
        sub = df_res[(df_res['stratum'] == stratum) & (df_res['model_type'] == 'OLS (Log Upvotes)') & (df_res['variable'] == var)]
        if sub.empty or pd.isna(sub.iloc[0]['coef']):
            return None
        return sub.iloc[0]

    def describe_construct_cells(strata, prefix):
        """Build data-driven bullet points: which construct x stratum cells
        are significant at raw p<0.05, and which of those survive the
        Bonferroni correction across all n_ols_tests OLS fits."""
        raw_hits = []
        bonf_hits = []
        for stratum in strata:
            label = stratum.replace(prefix, "")
            for var in variables:
                row = get_row(df_results, stratum, var)
                if row is None:
                    continue
                if row['pvalue'] < 0.05:
                    raw_hits.append((label, var, row['coef'], row['pvalue']))
                if row['pvalue'] < bonferroni_alpha:
                    bonf_hits.append((label, var, row['coef'], row['pvalue']))

        lines = []
        if bonf_hits:
            lines.append(f"**Survives Bonferroni correction** (p < {bonferroni_alpha:.2e}, correcting for all {n_ols_tests} OLS tests run):")
            for label, var, coef, p in sorted(bonf_hits, key=lambda x: x[3]):
                lines.append(f"  - {var_labels[var]} in *{label}*: coef={coef:+.4f}, p={p:.2e}")
        else:
            lines.append(f"**No epistemic-construct cell survives Bonferroni correction** (threshold p < {bonferroni_alpha:.2e} across {n_ols_tests} OLS tests). Any single \"significant\" cell below should be read as suggestive at best, not as a confirmed subgroup effect.")

        raw_only = [h for h in raw_hits if h not in bonf_hits]
        if raw_only:
            lines.append(f"\nCells significant at uncorrected p < 0.05 only (did not survive Bonferroni; report with appropriate caution):")
            for label, var, coef, p in sorted(raw_only, key=lambda x: x[3]):
                lines.append(f"  - {var_labels[var]} in *{label}*: coef={coef:+.4f}, p={p:.2e}")
        return "\n".join(lines)

    # Build tables for Markdown
    eras = [
        "Era: Pre-2016 Era (2008-2015)",
        "Era: Political Realignment Era (2016-2019)",
        "Era: Pandemic & Modern Era (2020-2025)"
    ]
    st_names = sorted([st for st in df_results['stratum'].unique() if "Super-Topic" in st])

    # Era Table
    era_rows = []
    for era in eras:
        sub = df_results[df_results['stratum'] == era]
        n_obs = int(sub.iloc[0]['n_obs']) if not sub.empty else 0
        cells = [era.replace("Era: ", ""), f"{n_obs:,}"]
        for var in variables:
            cells.append(get_coef_str(df_results, era, "OLS (Log Upvotes)", var))
        era_rows.append("| " + " | ".join(cells) + " |")

    # Super-Topic Table
    st_rows = []
    for st in st_names:
        sub = df_results[df_results['stratum'] == st]
        n_obs = int(sub.iloc[0]['n_obs']) if not sub.empty else 0
        cells = [st.replace("Super-Topic: ", ""), f"{n_obs:,}"]
        for var in variables:
            cells.append(get_coef_str(df_results, st, "OLS (Log Upvotes)", var))
        st_rows.append("| " + " | ".join(cells) + " |")

    era_discoveries = describe_construct_cells(eras, "Era: ")
    st_discoveries = describe_construct_cells(st_names, "Super-Topic: ")

    report_content = f"""# Stratified Narrative Analysis: 50,000 Sampled Pure r/conspiracy Comments

This report presents the fine-grained narrative and temporal regressions fit over a **50,000-comment representative sample** drawn randomly from the true **1,985,823 unbrigaded, veteran-heavy (75%+ insider) pure comment population**.

By running sentence-transformer-based BERTopic inference over this sample, we mapped the comments to their thematic clusters while **preserving the full upvote variance of the dependent variable**. This resolves the range restriction (selection bias) problem present in the earlier high-upvote-only (>=100 upvotes) topic analysis.

**Multiple-comparison note**: this report fits {n_ols_tests} separate OLS tests (across strata x variables). Every "significant" claim below is labeled with whether it survives a Bonferroni correction across all {n_ols_tests} tests (threshold p < {bonferroni_alpha:.2e}) or only holds at the uncorrected p < 0.05 level. All coefficient values and p-values in this report are read directly from `topic_time_regression_results_pure_50k.csv` -- none are hand-entered.

---

## 1. Regression Coefficients by Chronological Era (OLS: Log Upvotes)

The OLS models reveal the shifting value of epistemic markers across three key eras of r/conspiracy's evolution:

| Historical Era | N | `has_maverick` | `has_canonical` | `has_consensus` | `pe_prob` | `ps_prob` | `hs_prob` | `link_mainstream_reliable` | `link_mixed_or_low_reliability` | `link_aggregator_or_platform` | `link_unmatched_link` |
| :--- | :---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{chr(10).join(era_rows)}

### Chronological Findings (data-driven, see note above on correction status):
{era_discoveries}

---

## 2. Regression Coefficients by Thematic Super-Topic (OLS: Log Upvotes)

The models reveal how epistemic authorities and narrative structures are rewarded differently across specific conspiratorial genres:

| Thematic Super-Topic | N | `has_maverick` | `has_canonical` | `has_consensus` | `pe_prob` | `ps_prob` | `hs_prob` | `link_mainstream_reliable` | `link_mixed_or_low_reliability` | `link_aggregator_or_platform` | `link_unmatched_link` |
| :--- | :---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{chr(10).join(st_rows)}

### Thematic Findings (data-driven, see note above on correction status):
{st_discoveries}

---

## 3. Methodological Note for Your Thesis

This sample-based approach is a defense against **selection bias**: the earlier high-upvote-only (>=100 upvotes) regressions had a range-restricted dependent variable, which distorts standard errors. Sampling 50,000 comments across the *entire* upvote distribution of the pure population restores that variance.

It does **not**, on its own, defend against multiple-comparison inflation from running many strata x variable tests -- see the Bonferroni annotations above. A coefficient losing or gaining significance across strata is also not, by itself, evidence that the true effect differs between strata; that requires an explicit interaction-term test (see `run_integrated_regressions.py`'s `run_interaction_regressions` for the pattern), which this script does not run.

---
*Report compiled on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
"""
    with open(OUT_REPORT_PATH, 'w') as f:
        f.write(report_content)
    print(f"Successfully wrote thesis synthesis report to {OUT_REPORT_PATH}")

    try:
        os.makedirs(os.path.dirname(OUT_REPORT_PATH_BACKWARD_COMPAT), exist_ok=True)
        with open(OUT_REPORT_PATH_BACKWARD_COMPAT, 'w') as f:
            f.write(report_content)
        print(f"Backward-compatible copy successfully wrote to {OUT_REPORT_PATH_BACKWARD_COMPAT}")
    except Exception as e:
        print(f"Warning: could not write to backward-compatible report path: {e}")


def main(report_only=False):
    print("======================================================================")
    print("      CONSPIRACY CORPUS: 50K PURE CORE TOPIC-TIME REGRESSIONS         ")
    print("======================================================================")

    if report_only:
        # Regenerate just the markdown report from the already-saved
        # regression CSV, without re-running the expensive sampling +
        # BERTopic inference + regression fitting steps.
        print(f"--report-only: loading existing results from {OUT_REGRESSIONS_PATH}")
        df_results = pd.read_csv(OUT_REGRESSIONS_PATH)
        write_synthesis_report(df_results, None)
    else:
        df = load_and_sample_dataset()
        df = run_topic_inference(df)
        df = add_epistemic_features(df)
        df_results = run_stratified_regressions(df)
        write_synthesis_report(df_results, df)

    print("\n======================================================================")
    print("                     PIPELINE EXECUTED SUCCESSFULLY                   ")
    print("======================================================================")


if __name__ == '__main__':
    main(report_only="--report-only" in sys.argv)
