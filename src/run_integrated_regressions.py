"""run_integrated_regressions.py

Run OLS and Logit regressions to synthesize our constructs across the distribution
of thread elasticity (upvotes-per-comment ratio) and varying thresholds of author
insider status.

Saves coefficient grids to data/processed/synthesis_regression_results.csv.

CORRECTED 2026-07-20 (Nash's audit -- this script had gone stale in a way
that predates and is separate from the r/politics staleness found earlier
the same day): `has_maverick` here was still pulling straight from the
raw, unaudited `final_bucket_guess == 'maverick_authority'` bucket in
entity_final_review.csv -- the exact 418-entity bucket documented in
handoff/task_maverick_authority_list_cleanup.md as ~25% topic-noise
("New World Order", "Deep State", no actual entity present), superseded
months ago by VERIFIED_MAVERICK_AUTHORITY elsewhere in the codebase. This
script never got the update. Also missing entirely: has_consensus_expert
and has_canonical_expert, which the "refined v2" regression lineage
(rerun_refined_regressions_v2.py) treats as core constructs alongside
has_maverick. Fixed: entities now come from
rerun_refined_regressions_v2.load_entities_split_corrected() (same
verified allowlists + Stage B/C disambiguation lookups used everywhere
else), and has_consensus_expert/has_canonical_expert are added to every
formula this script fits. Old output
(synthesis_regression_results_filtered.csv) is left on disk untouched
for comparison, per this project's usual practice -- this run writes to
new, distinctly-named output files instead of overwriting it.
"""
import os
import re
import sys
import time
import numpy as np
import pandas as pd
import duckdb
import joblib
import statsmodels.api as sm
import statsmodels.formula.api as smf

sys.path.insert(0, os.path.dirname(__file__))
from rerun_refined_regressions_v2 import load_entities_split_corrected
from refine_thesis_models import build_regex
from combined_maverick_detector import load_maverick_disambiguation_lookup, VALID_MAVERICK_CANDIDATES, CANDIDATE_TO_BARES as MAVERICK_CANDIDATE_TO_BARES
from consensus_disambiguation_lookup import load_consensus_disambiguation_lookup, VALID_CONSENSUS_CANDIDATES, CANDIDATE_TO_BARES as CONSENSUS_CANDIDATE_TO_BARES
from stance_window_utils import extract_entity_window, compute_spans_for_row
from run_link_source_tier_regressions import determine_link_source_tier, build_source_authority_lookup

STANCE_MODEL_PATH = 'data/processed/stance_classifier.joblib'
STANCE_SUBMODEL_OUT_PATH = 'data/processed/synthesis_stance_submodels.csv'

STAGED_PATH = "data/processed/research_corpus_staged_scores_full21m.parquet"
# hedged_suspicion (hs_prob) was validated (kappa=0.872) but never scaled to the
# full corpus alongside pe_prob/ps_prob -- see src/score_hedged_suspicion_full.py.
# Kept as a separate parquet + LEFT JOIN rather than merged into STAGED_PATH so
# the already-computed pe/ps output stays untouched.
HEDGED_SUSPICION_PATH = "data/processed/hedged_suspicion_scores_full21m.parquet"
EMPATH_PATH = "data/processed/empath_scores_full.parquet"
INSIDER_PATH = "data/processed/author_insider_metrics.csv"
THREAD_PATH = "data/processed/thread_quality_metrics.csv"
ENTITY_PATH = "data/processed/entity_final_review.csv"
BRIGADE_PATH = "data/processed/comment_brigade_flags.csv"
# Keep the entity-regex-fixed-but-not-virality-filtered result
# (synthesis_regression_results.csv) intact for comparison -- this run adds
# the crosspost/brigading exclusion on top, written separately so both are
# auditable side by side rather than one silently overwriting the other.
# CORRECTED 2026-07-20: new filenames, old stale-entity outputs left in place.
OUT_PATH = "data/processed/synthesis_regression_results_corrected.csv"
INTERACTION_OUT_PATH = "data/processed/synthesis_interaction_results_corrected.csv"

MIN_SPARSE_N = 20  # below this many positive cases, drop the term from the formula for that fit


def build_expert_regexes():
    """Replaces the old build_expert_regex() -- see module docstring for
    why. Returns compiled regexes for all three verified constructs plus
    the disambiguation lookups needed to resolve bare-form ambiguous
    mentions the same way rerun_refined_regressions_v2.py does."""
    print("Loading verified entity lists (mavericks/canon/consensus)...")
    mavericks, canon, consensus = load_entities_split_corrected()
    print(f"  {len(mavericks)} mavericks, {len(canon)} canonical experts, {len(consensus)} consensus experts")

    rx_mav = build_regex(mavericks)
    rx_can = build_regex(canon)
    rx_con = build_regex(consensus)

    maverick_lookup = load_maverick_disambiguation_lookup()
    consensus_lookup = load_consensus_disambiguation_lookup()
    print(f"  {len(maverick_lookup)} maverick + {len(consensus_lookup)} consensus disambiguation-lookup entries loaded")

    return rx_mav, rx_can, rx_con, maverick_lookup, consensus_lookup


def load_integrated_dataset(rx_mav, rx_can, rx_con, maverick_lookup, consensus_lookup):
    print("Connecting to DuckDB and executing the full integrated dataset query...")
    start_time = time.time()

    con = duckdb.connect()

    # Ingest comments in main posts, join construct scores, author insider_score, and thread elasticity
    # Incorporate the fast regexp_matches over text directly in SQL (utilizing RE2 engine in C++)
    # FIX (2026-07-14): now joins the brigade-flags table and actually
    # excludes is_high_crosspost / brigade-flagged rows, instead of pulling
    # is_crossposted into the query and never filtering on it.
    # NOTE (found during this fix): DuckDB's regexp_matches() doesn't honor
    # Python's re.IGNORECASE -- it isn't part of the pattern string, it's
    # separate state on a compiled Python object that doesn't survive being
    # passed as a query parameter. The OLD version of this query passed the
    # pattern directly with no "(?i)" prefix, meaning it was silently
    # case-sensitive-only this whole time (undercounting any lowercase
    # mention). Fixed here by prefixing each pattern explicitly, matching
    # the documented fix in rerun_refined_regressions_v2.py's
    # _duckdb_regex_mask().
    # NOTE (fixed after an OOM kill, exit 137): the first version of this
    # query pulled raw `e.text` for all ~16.7M rows just to run link-tier
    # classification on the ~1% that have a link. That's what killed it --
    # 16.7M full comment strings materialized in the pandas frame at once,
    # on top of the concurrently-running process competing for RAM. Fixed
    # by NOT selecting text here at all; text is fetched separately, only
    # for the specific small subsets that actually need it (linked
    # comments for tier classification, maverick/consensus mentions for
    # stance sub-models), via a second, targeted query below.
    query = f"""
        SELECT
            s.id,
            s.pe_prob,
            s.ps_prob,
            h.hs_prob,
            e.upvotes,
            e.controversiality,
            CAST(e.has_link AS INTEGER) as has_link,
            CAST(regexp_matches(e.text, $1) AS INTEGER) as has_maverick_regex,
            CAST(regexp_matches(e.text, $2) AS INTEGER) as has_canonical_expert,
            CAST(regexp_matches(e.text, $3) AS INTEGER) as has_consensus_expert_regex,
            a.insider_score,
            t.elasticity_ratio,
            t.is_crossposted,
            t.is_high_crosspost,
            e.author,
            SUBSTR(e.link_id, 4) as post_id
        FROM '{STAGED_PATH}' s
        JOIN '{EMPATH_PATH}' e ON s.id = e.id
        LEFT JOIN '{HEDGED_SUSPICION_PATH}' h ON s.id = h.id
        JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
        LEFT JOIN '{INSIDER_PATH}' a ON e.author = a.author
        LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
        WHERE t.is_high_crosspost = 0
          AND COALESCE(b.brigade_upvote_flag, 0) = 0
          AND COALESCE(b.brigade_downvote_flag, 0) = 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
    """

    df = con.execute(query, ["(?i)" + rx_mav.pattern, "(?i)" + rx_can.pattern, "(?i)" + rx_con.pattern]).df()
    elapsed = time.time() - start_time
    print(f"Dataset successfully ingested in {elapsed:.2f} seconds. Row count: {len(df):,}")

    # Apply the disambiguation-lookup OR-fallback the same way
    # compute_has_maverick/compute_has_consensus_expert do elsewhere --
    # done here via a cheap id->name map lookup rather than re-loading
    # full text, since the regex match already happened in SQL above.
    print("Applying disambiguation-lookup fallback for maverick/consensus...")
    resolved_mav = df["id"].astype(str).map(maverick_lookup)
    df["has_maverick"] = (df["has_maverick_regex"].astype(bool) | resolved_mav.isin(VALID_MAVERICK_CANDIDATES)).astype(int)
    resolved_con = df["id"].astype(str).map(consensus_lookup)
    df["has_consensus_expert"] = (df["has_consensus_expert_regex"].astype(bool) | resolved_con.isin(VALID_CONSENSUS_CANDIDATES)).astype(int)
    df = df.drop(columns=["has_maverick_regex", "has_consensus_expert_regex"])

    # MEMORY FIX (after an OOM kill, exit 137, on an 8GB machine -- the
    # first fix removed the full-corpus text column, but a SECOND text_df
    # covering both linked comments AND maverick/consensus mentions
    # (2.8M rows combined) was still fetched in one shot and then held in
    # memory for the ENTIRE rest of the run, including through the huge
    # 16.7M-row interaction-model OLS fit further down, right up until
    # stance sub-models finally needed it again at the very end. That's
    # what actually killed it -- confirmed by checking which output files
    # made it to disk (everything through the interaction model saved
    # fine; only synthesis_stance_submodels.csv, the very last stage, was
    # missing). Fixed by fetching link text and mention text SEPARATELY:
    # link text is used immediately then dropped, so only the much
    # smaller mention-text subset (tens of thousands of rows, not
    # millions) is carried forward through the rest of the script.
    print("Building source-authority lookup and classifying link tiers...")
    build_source_authority_lookup()
    link_ids_df = df.loc[df['has_link'] == 1, ['id']].copy()
    print(f"Fetching text for {len(link_ids_df):,} linked comments (used immediately, then freed)...")
    con.register("link_ids_view", link_ids_df)
    text_for_links = con.execute(f"""
        SELECT e.id, e.text
        FROM '{EMPATH_PATH}' e
        JOIN link_ids_view n ON e.id = n.id
    """).df()
    print(f"  Classifying {len(text_for_links):,} linked comments...")
    text_for_links['link_source_tier'] = text_for_links['text'].apply(
        lambda t: determine_link_source_tier(t, 1))
    tier_map = dict(zip(text_for_links['id'], text_for_links['link_source_tier']))
    df['link_source_tier'] = df['id'].map(tier_map).fillna('no_link')
    del text_for_links, link_ids_df

    mention_ids_df = df.loc[(df['has_maverick'] == 1) | (df['has_consensus_expert'] == 1), ['id']].copy()
    print(f"Fetching text for {len(mention_ids_df):,} maverick/consensus mentions "
          f"(kept for the stance sub-models later)...")
    con.register("mention_ids_view", mention_ids_df)
    text_df = con.execute(f"""
        SELECT e.id, e.text
        FROM '{EMPATH_PATH}' e
        JOIN mention_ids_view n ON e.id = n.id
    """).df()
    print(f"  Fetched {len(text_df):,} mention text rows.")

    for tier in ['mainstream_reliable', 'mixed_or_low_reliability', 'aggregator_or_platform', 'unmatched_link']:
        df[f'link_{tier}'] = (df['link_source_tier'] == tier).astype(int)
    print("  Link tier counts:")
    print(df['link_source_tier'].value_counts())
    df = df.drop(columns=['link_source_tier'])

    return df, text_df


def run_single_regression(df, formula, model_type, cov_type='nonrobust', group_col=None):
    """Fits a single regression model and returns stats."""
    n_obs = len(df)
    if n_obs < 30: # Need sufficient observations to run
        return None
        
    try:
        if cov_type == 'cluster' and group_col:
            df_fit = df.dropna(subset=[group_col])
            groups = df_fit[group_col].astype(str)
        else:
            df_fit = df
            groups = None

        if model_type == "OLS":
            if cov_type == 'cluster' and groups is not None:
                model = smf.ols(formula, data=df_fit).fit(cov_type='cluster', cov_kwds={'groups': groups})
            else:
                model = smf.ols(formula, data=df_fit).fit()
            params = model.params
            bse = model.bse
            pvalues = model.pvalues
            tvalues = model.tvalues
            r2 = model.rsquared
            f_p = model.f_pvalue
            return params, bse, pvalues, tvalues, r2, f_p
        elif model_type == "Logit":
            # Set disp=0 to suppress convergence messages
            if cov_type == 'cluster' and groups is not None:
                model = smf.logit(formula, data=df_fit).fit(cov_type='cluster', cov_kwds={'groups': groups}, disp=0, maxiter=100)
            else:
                model = smf.logit(formula, data=df_fit).fit(disp=0, maxiter=100)
            params = model.params
            bse = model.bse
            pvalues = model.pvalues
            tvalues = model.tvalues # really z-values
            r2 = model.prsquared
            f_p = model.llr_pvalue
            return params, bse, pvalues, tvalues, r2, f_p
    except Exception as e:
        # Gracefully skip if separation occurs or model fails to converge
        return None
    return None


def main():
    print("=== STARTING THE GRAND SYNTHESIS INTEGRATED REGRESSIONS ===")
    
    # 1. Build regexes + disambiguation lookups
    rx_mav, rx_can, rx_con, maverick_lookup, consensus_lookup = build_expert_regexes()

    # 2. Ingest data
    df, text_df = load_integrated_dataset(rx_mav, rx_can, rx_con, maverick_lookup, consensus_lookup)
    
    # 3. Compute scaled metrics
    print("Preprocessing variables...")
    min_upvotes = df['upvotes'].min()
    df['log_upvotes'] = np.log(df['upvotes'] - min_upvotes + 1)
    df['high_traction'] = (df['upvotes'] >= 5).astype(int)
    
    # 4. Bin elasticity continuously into terciles
    df['elasticity_bin'] = pd.qcut(df['elasticity_ratio'], 3, labels=['Low', 'Medium', 'High'])
    print("Elasticity tercile thresholds:")
    for bin_name in ['Low', 'Medium', 'High']:
        subset_ratio = df[df['elasticity_bin'] == bin_name]['elasticity_ratio']
        print(f"  {bin_name:6s} Elasticity: min={subset_ratio.min():.4f}, max={subset_ratio.max():.4f}, N={len(subset_ratio):,}")
        
    # Define design factors
    elasticity_strata = ['Unfiltered', 'Low', 'Medium', 'High']
    insider_thresholds = [None, -0.5, 0.0, 0.5, 1.0, 1.5]
    # has_link replaced with the 5-tier source-quality taxonomy (no_link is
    # the implicit reference category, dropped from the formula).
    link_terms = "link_mainstream_reliable + link_mixed_or_low_reliability + link_aggregator_or_platform + link_unmatched_link"
    constructs = ['pe_prob', 'ps_prob', 'hs_prob',
                  'link_mainstream_reliable', 'link_mixed_or_low_reliability',
                  'link_aggregator_or_platform', 'link_unmatched_link',
                  'has_maverick', 'has_canonical_expert', 'has_consensus_expert']

    formula_ols = (f"log_upvotes ~ pe_prob + ps_prob + hs_prob + {link_terms} + has_maverick "
                   "+ has_canonical_expert + has_consensus_expert")
    formula_contro = (f"controversiality ~ pe_prob + ps_prob + hs_prob + {link_terms} + has_maverick "
                      "+ has_canonical_expert + has_consensus_expert")
    formula_traction = (f"high_traction ~ pe_prob + ps_prob + hs_prob + {link_terms} + has_maverick "
                        "+ has_canonical_expert + has_consensus_expert")

    models_config = [
        ("OLS_log_upvotes", formula_ols, "OLS"),
        ("Logit_controversiality", formula_contro, "Logit"),
        ("Logit_high_traction", formula_traction, "Logit")
    ]
    
    results_records = []
    clustered_results_records = []
    
    print("\nRunning regressions across parameter grids...")
    start_fits = time.time()
    fit_count = 0
    
    for strata in elasticity_strata:
        # Filter by elasticity strata
        if strata == 'Unfiltered':
            df_strata = df
        else:
            df_strata = df[df['elasticity_bin'] == strata]
            
        for threshold in insider_thresholds:
            # Filter by insider threshold
            if threshold is None:
                df_subset = df_strata
                threshold_label = "None"
            else:
                df_subset = df_strata[df_strata['insider_score'] > threshold]
                threshold_label = f"> {threshold}"
                
            n_obs = len(df_subset)
            
            for model_name, formula, m_type in models_config:
                # has_consensus_expert is rare (~0.1% of comments) -- many
                # strata/threshold cells will have too few positive cases
                # for a stable coefficient. Drop it from the formula for
                # this cell only rather than let it fit garbage or blow up
                # the model, same MIN_SPARSE_N guard rerun_refined_regressions_v2.py
                # uses for the same reason.
                n_consensus_cell = int(df_subset['has_consensus_expert'].sum()) if len(df_subset) else 0
                formula = formula.replace(" + has_consensus_expert", "") if n_consensus_cell < MIN_SPARSE_N else formula

                # 1. Fit Naive model (original behavior to preserve EXACT schema/results of the naive runs)
                fit_res_naive = run_single_regression(df_subset, formula, m_type)
                
                record_naive = {
                    "elasticity_strata": strata,
                    "insider_threshold": threshold_label,
                    "model_name": model_name,
                    "n_obs": n_obs,
                    "r2_or_pseudo_r2": np.nan,
                    "model_sig_pvalue": np.nan
                }
                for c in constructs:
                    record_naive[f"{c}_coef"] = np.nan
                    record_naive[f"{c}_se"] = np.nan
                    record_naive[f"{c}_pvalue"] = np.nan
                    record_naive[f"{c}_tstat"] = np.nan
                    
                if fit_res_naive is not None:
                    params, bse, pvalues, tvalues, r2, f_p = fit_res_naive
                    record_naive["r2_or_pseudo_r2"] = r2
                    record_naive["model_sig_pvalue"] = f_p
                    for c in constructs:
                        if c in params:
                            record_naive[f"{c}_coef"] = params[c]
                            record_naive[f"{c}_se"] = bse[c]
                            record_naive[f"{c}_pvalue"] = pvalues[c]
                            record_naive[f"{c}_tstat"] = tvalues[c]
                            
                results_records.append(record_naive)

                # 2. Fit comparative models (Naive, Thread-clustered, and Author-clustered) for side-by-side clustered output
                cov_types = [
                    ("naive", 'nonrobust', None),
                    ("thread", 'cluster', 'post_id'),
                    ("author", 'cluster', 'author')
                ]
                for cov_name, cov_type, group_col in cov_types:
                    fit_count += 1
                    fit_res = run_single_regression(df_subset, formula, m_type, cov_type=cov_type, group_col=group_col)
                    
                    record_clust = {
                        "elasticity_strata": strata,
                        "insider_threshold": threshold_label,
                        "model_name": model_name,
                        "cov_type": cov_name,
                        "n_obs": n_obs,
                        "r2_or_pseudo_r2": np.nan,
                        "model_sig_pvalue": np.nan
                    }
                    for c in constructs:
                        record_clust[f"{c}_coef"] = np.nan
                        record_clust[f"{c}_se"] = np.nan
                        record_clust[f"{c}_pvalue"] = np.nan
                        record_clust[f"{c}_tstat"] = np.nan
                        
                    if fit_res is not None:
                        params, bse, pvalues, tvalues, r2, f_p = fit_res
                        record_clust["r2_or_pseudo_r2"] = r2
                        record_clust["model_sig_pvalue"] = f_p
                        for c in constructs:
                            if c in params:
                                record_clust[f"{c}_coef"] = params[c]
                                record_clust[f"{c}_se"] = bse[c]
                                record_clust[f"{c}_pvalue"] = pvalues[c]
                                record_clust[f"{c}_tstat"] = tvalues[c]
                                
                    clustered_results_records.append(record_clust)
                
    elapsed_fits = time.time() - start_fits
    print(f"Finished {fit_count} regression fits in {elapsed_fits:.2f} seconds.")
    
    # 5. Save results to CSVs
    df_results = pd.DataFrame(results_records)
    df_results.to_csv(OUT_PATH, index=False)
    print(f"Saved complete synthesis regression results table to {OUT_PATH}")

    OUT_CLUSTERED_PATH = "data/processed/synthesis_regression_results_filtered_clustered.csv"
    pd.DataFrame(clustered_results_records).to_csv(OUT_CLUSTERED_PATH, index=False)
    print(f"Saved comparative clustered regression results table to {OUT_CLUSTERED_PATH}")
    
    # 6. Output Gorgeous Summary Trajectories
    pd.set_option('display.float_format', lambda x: '%.4f' % x)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    
    print("\n" + "="*95)
    print("            GRAND SYNTHESIS: CONSTRUCT COEFFICIENT TRAJECTORIES ACROSS ELASTICITY")
    print("="*95)
    print("Comparing how continuous constructs relate to Engagement under different elasticity environments")
    print("Values shown are for OLS Log-Upvotes and Logit High-Traction models (Insider score cutoff: None)")
    print("-"*95)
    
    for construct in constructs:
        print(f"\nConstruct: {construct.upper()}")
        print(f"{'Elasticity Bin':15s} | {'OLS Log-Upvotes Coef (p-val)':30s} | {'Logit High-Traction Coef (p-val)':30s} | {'Obs Count':10s}")
        print("-"*95)
        for strata in ['Unfiltered', 'Low', 'Medium', 'High']:
            ols_row = df_results[(df_results['elasticity_strata'] == strata) & 
                                 (df_results['insider_threshold'] == 'None') & 
                                 (df_results['model_name'] == 'OLS_log_upvotes')].iloc[0]
            logit_row = df_results[(df_results['elasticity_strata'] == strata) & 
                                   (df_results['insider_threshold'] == 'None') & 
                                   (df_results['model_name'] == 'Logit_high_traction')].iloc[0]
            
            ols_coef = ols_row[f"{construct}_coef"]
            ols_p = ols_row[f"{construct}_pvalue"]
            logit_coef = logit_row[f"{construct}_coef"]
            logit_p = logit_row[f"{construct}_pvalue"]
            
            ols_str = f"{ols_coef:+.4f} (p={ols_p:.2e})" if not np.isnan(ols_coef) else "N/A"
            logit_str = f"{logit_coef:+.4f} (p={logit_p:.2e})" if not np.isnan(logit_coef) else "N/A"
            
            print(f"{strata:15s} | {ols_str:30s} | {logit_str:30s} | {ols_row['n_obs']:,}")
        print("-"*95)
        
    print("\n" + "="*95)
    print("        SENSITIVITY ANALYSIS: COEFFICIENT SHIFTS ACROSS AUTHOR INSIDER THRESHOLDS")
    print("="*95)
    print("Demonstrates how coefficients shift as we narrow the population to purer insider communities")
    print("Values shown are for OLS Log-Upvotes in the Low Elasticity Stratum (Organic discussion trenches)")
    print("-"*95)
    
    print(f"{'Insider Threshold':18s} | " + " | ".join(f"{c[:12]:12s}" for c in constructs) + " | Obs Count")
    print("-"*95)
    for threshold in ['None', '> -0.5', '> 0.0', '> 0.5', '> 1.0', '> 1.5']:
        row = df_results[(df_results['elasticity_strata'] == 'Low') & 
                         (df_results['insider_threshold'] == threshold) & 
                         (df_results['model_name'] == 'OLS_log_upvotes')].iloc[0]
        
        coefs_str = []
        for c in constructs:
            coef = row[f"{c}_coef"]
            p_val = row[f"{c}_pvalue"]
            if np.isnan(coef):
                coefs_str.append(f"{'N/A':12s}")
            else:
                # Put an asterisk next to significant findings
                sig_star = "*" if p_val < 0.05 else " "
                coefs_str.append(f"{coef:+.4f}{sig_star:1s}")
                
        print(f"{threshold:18s} | " + " | ".join(coefs_str) + f" | {row['n_obs']:,}")
    print("-"*95)
    print("Note: * indicates p-value < 0.05")
    print("="*95)
    
    # 7. Formal interaction-term test (FIX 2026-07-14): the strata comparison
    # above compares four SEPARATE regressions by eye -- a coefficient losing
    # significance in a smaller/noisier subsample doesn't prove the true
    # effect differs. Run ONE pooled model with explicit construct x
    # elasticity_bin interaction terms and read off THEIR p-values as the
    # actual test of "does this construct's effect on engagement genuinely
    # differ across elasticity strata".
    run_interaction_regressions(df)

    # 8. Mention-only stance sub-models (added 2026-07-20, "final" version
    # per Nash). NOT folded into the main formulas above -- has_maverick/
    # has_consensus_expert are binary and deterministically imply
    # stance_prob==0 wherever they're 0, so putting a continuous stance
    # variable in the SAME formula as the binary presence indicator
    # produces severe collinearity (r=0.97 in an earlier attempt this
    # session, coefficients as large as +12.6 log-odds -- a numerical
    # artifact, not a real effect). Run as separate mention-only-subset
    # models instead, same design as rerun_regressions_with_stance.py.
    run_stance_submodels(df, text_df, rx_mav, rx_con, maverick_lookup, consensus_lookup)

    print("\nGrand Synthesis Complete!")


def run_interaction_regressions(df):
    print("\n" + "="*95)
    print("   FORMAL INTERACTION-TERM TEST: does each construct's effect genuinely differ by stratum?")
    print("="*95)
    print("Pooled model with construct*elasticity_bin interactions -- reference category is 'Medium'.")
    print("A significant interaction term means that construct's effect on engagement really is")
    print("different in that stratum vs. the reference, not just 'lost significance in a smaller sample'.")
    print("-"*95)

    df = df.copy()
    df['elasticity_bin'] = df['elasticity_bin'].astype(str)
    # Medium as reference so both Low and High show as explicit contrasts
    df['elasticity_bin'] = pd.Categorical(df['elasticity_bin'], categories=['Medium', 'Low', 'High'])

    link_terms = "link_mainstream_reliable + link_mixed_or_low_reliability + link_aggregator_or_platform + link_unmatched_link"
    formula = (f"log_upvotes ~ (pe_prob + ps_prob + hs_prob + {link_terms} + has_maverick "
               "+ has_canonical_expert + has_consensus_expert) * C(elasticity_bin)")

    # 1. Original Naive Interaction Run
    interaction_records = []
    try:
        model = smf.ols(formula, data=df).fit()
        print(model.summary())
        for term, coef in model.params.items():
            interaction_records.append({
                "term": term,
                "coef": coef,
                "se": model.bse[term],
                "pvalue": model.pvalues[term],
                "tstat": model.tvalues[term],
                "n_obs": int(model.nobs),
                "r2": model.rsquared,
            })
    except Exception as e:
        print(f"Naive Interaction model failed: {e}")

    if interaction_records:
        pd.DataFrame(interaction_records).to_csv(INTERACTION_OUT_PATH, index=False)
        print(f"\nSaved naive interaction-term results to {INTERACTION_OUT_PATH}")

        print("\n--- Interaction terms specifically (the actual 'does it differ by stratum' test) ---")
        for r in interaction_records:
            if ":" in r["term"]:
                sig = "*" if r["pvalue"] < 0.05 else " "
                print(f"  {r['term']:55s} coef={r['coef']:+.4f}{sig} p={r['pvalue']:.2e}")

    # 2. Clustered Interaction Runs
    clustered_interaction_records = []
    cov_types = [
        ("naive", 'nonrobust', None),
        ("thread", 'cluster', 'post_id'),
        ("author", 'cluster', 'author')
    ]
    for cov_name, cov_type, group_col in cov_types:
        print(f"\nRunning Interaction OLS with covariance clustered by {cov_name}...")
        try:
            if cov_type == 'cluster' and group_col:
                df_fit = df.dropna(subset=[group_col])
                groups = df_fit[group_col].astype(str)
                model_clust = smf.ols(formula, data=df_fit).fit(cov_type='cluster', cov_kwds={'groups': groups})
            else:
                df_fit = df
                model_clust = smf.ols(formula, data=df_fit).fit()
                
            for term, coef in model_clust.params.items():
                clustered_interaction_records.append({
                    "term": term,
                    "cov_type": cov_name,
                    "coef": coef,
                    "se": model_clust.bse[term],
                    "pvalue": model_clust.pvalues[term],
                    "tstat": model_clust.tvalues[term],
                    "n_obs": int(model_clust.nobs),
                    "r2": model_clust.rsquared,
                })
        except Exception as e:
            print(f"Clustered Interaction model ({cov_name}) failed: {e}")

    if clustered_interaction_records:
        INTERACTION_OUT_CLUSTERED_PATH = "data/processed/synthesis_interaction_results_clustered.csv"
        pd.DataFrame(clustered_interaction_records).to_csv(INTERACTION_OUT_CLUSTERED_PATH, index=False)
        print(f"Saved comparative clustered interaction-term results to {INTERACTION_OUT_CLUSTERED_PATH}")

        print("\n--- Interaction terms specifically (clustered comparisons) ---")
        for cov_name in ["naive", "thread", "author"]:
            print(f"\nCovariance type: {cov_name}")
            for r in clustered_interaction_records:
                if r["cov_type"] == cov_name and ":" in r["term"]:
                    sig = "*" if r["pvalue"] < 0.05 else " "
                    print(f"  {r['term']:55s} coef={r['coef']:+.4f}{sig} p={r['pvalue']:.2e}")


def run_stance_submodels(df, text_df, rx_mav, rx_con, maverick_lookup, consensus_lookup):
    print("\n" + "="*95)
    print("   MENTION-ONLY STANCE SUB-MODELS (does hostile vs. endorsement stance predict")
    print("   engagement WITHIN mentions -- separate from the main pooled has_X models above)")
    print("="*95)

    if not os.path.exists(STANCE_MODEL_PATH):
        print(f"MISSING: {STANCE_MODEL_PATH}. Run src/train_stance_classifier.py first -- skipping stance sub-models.")
        return
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec, clf = stance_model['vec'], stance_model['clf']
    print(f"Loaded stance classifier (cv_kappa={stance_model['cv_kappa']:.3f}, "
          f"cv_auc={stance_model['cv_auc']:.3f}) -- treat weaker domains as provisional (see train_stance_classifier.py CV report).")

    link_terms = "link_mainstream_reliable + link_mixed_or_low_reliability + link_aggregator_or_platform + link_unmatched_link"
    outcome_formulas = [
        ("OLS_log_upvotes", f"log_upvotes ~ stance_prob + pe_prob + ps_prob + hs_prob + {link_terms}", "OLS"),
        ("Logit_controversiality", f"controversiality ~ stance_prob + pe_prob + ps_prob + hs_prob + {link_terms}", "Logit"),
        ("Logit_high_traction", f"high_traction ~ stance_prob + pe_prob + ps_prob + hs_prob + {link_terms}", "Logit"),
    ]

    text_lookup = dict(zip(text_df['id'], text_df['text']))

    records = []
    for construct, has_col, rx, lookup, candidate_to_bares in [
        ("maverick", "has_maverick", rx_mav, maverick_lookup, MAVERICK_CANDIDATE_TO_BARES),
        ("consensus", "has_consensus_expert", rx_con, consensus_lookup, CONSENSUS_CANDIDATE_TO_BARES),
    ]:
        mask = df[has_col] == 1
        print(f"\nScoring stance for {construct} mentions (N={mask.sum():,})...")
        df_mentions = df.loc[mask].copy()
        df_mentions['text'] = df_mentions['id'].map(text_lookup)
        if len(df_mentions) > 0:
            windows = [
                extract_entity_window(text, compute_spans_for_row(text, cid, rx, lookup, candidate_to_bares))
                for cid, text in zip(df_mentions['id'].astype(str), df_mentions['text'].fillna(''))
            ]
            X = vec.transform(windows)
            df_mentions['stance_prob'] = clf.predict_proba(X)[:, 1]
        else:
            df_mentions['stance_prob'] = pd.Series(dtype=float)

        for strata in ['Unfiltered', 'Low', 'Medium', 'High']:
            if strata == 'Unfiltered':
                df_sub = df_mentions
            else:
                df_sub = df_mentions[df_mentions['elasticity_bin'] == strata]
            n = len(df_sub)
            print(f"  [{construct}/{strata}] N={n}")

            for model_name, formula, m_type in outcome_formulas:
                record = {
                    "construct": construct, "elasticity_strata": strata,
                    "model_name": model_name, "n_obs": n,
                    "stance_prob_coef": np.nan, "stance_prob_se": np.nan,
                    "stance_prob_pvalue": np.nan, "stance_prob_tstat": np.nan,
                }
                if n < MIN_SPARSE_N:
                    record["note"] = f"too sparse (N={n})"
                    records.append(record)
                    continue
                fit_res = run_single_regression(df_sub, formula, m_type)
                if fit_res is not None:
                    params, bse, pvalues, tvalues, r2, f_p = fit_res
                    if "stance_prob" in params:
                        record["stance_prob_coef"] = params["stance_prob"]
                        record["stance_prob_se"] = bse["stance_prob"]
                        record["stance_prob_pvalue"] = pvalues["stance_prob"]
                        record["stance_prob_tstat"] = tvalues["stance_prob"]
                else:
                    record["note"] = "model failed to fit"
                records.append(record)

    pd.DataFrame(records).to_csv(STANCE_SUBMODEL_OUT_PATH, index=False)
    print(f"\nSaved stance sub-model results to {STANCE_SUBMODEL_OUT_PATH}")


if __name__ == "__main__":
    main()
