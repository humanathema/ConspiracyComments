"""run_link_type_regressions.py

Run multidimensional link-type regressions (Methodology E) comparing
r/conspiracy vs. r/AskReddit, expanding the flat 'has_link' variable
using the project's pre-built Cell 61 Epistemic Domain Taxonomy.
"""

import os
import re
import numpy as np
import pandas as pd
import duckdb
import statsmodels.formula.api as smf

STAGED_PATH = "data/processed/research_corpus_staged_scores_full21m.parquet"
EMPATH_PATH = "data/processed/empath_scores_full.parquet"
THREAD_PATH = "data/processed/thread_quality_metrics.csv"
PRESENCE_PATH = "data/processed/thread_insider_presence.csv"
ENTITY_PATH = "data/processed/entity_final_review.csv"
BRIGADE_PATH = "data/processed/comment_brigade_flags.csv"

ASKREDDIT_PATH = "data/processed/comparison_askreddit_staged_scored.parquet"
OUTPUT_CSV = "data/processed/link_type_regression_results.csv"

# Pre-built Epistemic Domain Taxonomy (Cell 61 of master notebook)
TAXONOMY = {
    'mainstream_news': [
        'nytimes.com', 'washingtonpost.com', 'theguardian.com', 'reuters.com',
        'bbc.com', 'bbc.co.uk', 'cnn.com', 'nbcnews.com', 'cbsnews.com',
        'abcnews.go.com', 'npr.org', 'bloomberg.com', 'newsweek.com',
        'time.com', 'theatlantic.com', 'politico.com', 'thehill.com',
        'apnews.com', 'forbes.com', 'businessinsider.com', 'cnbc.com',
        'huffingtonpost.com', 'huffpost.com', 'usatoday.com', 'wsj.com',
        'latimes.com', 'independent.co.uk', 'telegraph.co.uk',
        'dailymail.co.uk', 'nypost.com', 'nydailynews.com', 'rollingstone.com'
    ],
    'alt_media': [
        'zerohedge.com', 'infowars.com', 'breitbart.com', 'rt.com',
        'globalresearch.ca', 'activistpost.com', 'beforeitsnews.com',
        'naturalnews.com', 'thefreethoughtproject.com', 'thedailysheeple.com',
        'mintpressnews.com', 'corbettreport.com', 'theintercept.com',
        'greenwald.substack.com', 'rumble.com', 'bitchute.com',
        'collective-evolution.com', 'humansarefree.com', 'yournewswire.com',
        'theepochtimes.com', 'thegatewaypundit.com', 'childrenshealthdefense.org',
        'mercola.com', 'lewrockwell.com', 'prisonplanet.com', 'whatreallyhappened.com',
        'veteranstoday.com'
    ],
    'academic_scientific': [
        'ncbi.nlm.nih.gov', 'pubmed.ncbi.nlm.nih.gov', 'nature.com',
        'sciencedirect.com', 'springer.com', 'journals.plos.org',
        'academic.oup.com', 'jamanetwork.com', 'nejm.org', 'thelancet.com',
        'bmj.com', 'annals.org', 'cell.com', 'science.org',
        'researchgate.net', 'academia.edu', 'jstor.org', 'scholar.google.com',
        'biorxiv.org', 'medrxiv.org', 'tandfonline.com', 'wiley.com'
    ],
    'government_official': [
        'cdc.gov', 'nih.gov', 'fda.gov', 'who.int', 'fbi.gov', 'cia.gov',
        'state.gov', 'whitehouse.gov', 'congress.gov', 'senate.gov',
        'house.gov', 'justice.gov', 'doj.gov', 'nsa.gov', 'nasa.gov',
        'epa.gov', 'usda.gov', 'defense.gov', 'treasury.gov',
        'federalreserve.gov', 'sec.gov', 'ftc.gov', 'un.org', 'nato.int'
    ],
    'archive_preservation': [
        'archive.is', 'archive.org', 'web.archive.org', 'archive.ph',
        'archive.fo', 'reveddit.com', 'removeddit.com', 'ceddit.com',
        'ghostarchive.org', 'timeoutinternet.com'
    ],
    'leak_whistleblower': [
        'wikileaks.org', 'wikileaks.com', 'cryptome.org', 'dcleaks.com',
        'theintercept.com', 'documentcloud.org', 'foia.state.gov', 
        'vault.fbi.gov', 'muckrock.com', 'judicialwatch.org', 'governmentattic.org'
    ],
    'legal_documents': [
        'documentcloud.org', 'courtlistener.com', 'pacer.gov',
        'law.cornell.edu', 'supremecourt.gov', 'findlaw.com',
        'justia.com', 'scribd.com'
    ],
    'social_video': [
        'youtube.com', 'youtu.be', 'm.youtube.com', 'twitter.com',
        'x.com', 'mobile.twitter.com', 'facebook.com', 'm.facebook.com',
        'instagram.com', 'tiktok.com', 'vm.tiktok.com', 'twitch.tv',
        'odysee.com', 'bitchute.com', 'rumble.com', 'dailymotion.com',
        'vimeo.com', 'streamable.com'
    ],
    'reference': [
        'en.wikipedia.org', 'en.m.wikipedia.org', 'wikipedia.org',
        'britannica.com', 'investopedia.com', 'merriam-webster.com'
    ],
    'image_screenshot': [
        'i.imgur.com', 'imgur.com', 'i.redd.it', 'pbs.twimg.com',
        'i.postimg.cc', 'files.catbox.moe', 'ibb.co', 'prnt.sc',
        'postimg.cc', 'gyazo.com'
    ]
}

# Reverse lookup
domain_to_type = {}
for etype, domains in TAXONOMY.items():
    for d in domains:
        domain_to_type[d] = etype

def extract_domains(text):
    if not isinstance(text, str):
        return []
    urls = re.findall(r'https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,4})', text)
    return [u.lower() for u in urls]

def classify_domain(domain):
    clean = domain.replace('https://', '').replace('http://', '').replace('www.', '').strip('/')
    if clean in domain_to_type:
        return domain_to_type[clean]
    for key_domain, etype in domain_to_type.items():
        if clean == key_domain or clean.endswith('.' + key_domain):
            return etype
    if any(x in clean for x in ['.gov', '.mil']):
        return 'government_official'
    if any(x in clean for x in ['substack', 'wordpress', 'blogspot', 'medium.com']):
        return 'blog_independent'
    if any(x in clean for x in ['university', 'edu', 'ac.uk', 'ac.nz']):
        return 'academic_scientific'
    return 'other'

def compute_link_indicators(df):
    """Adds binary indicators for the 5 target link types to the dataframe."""
    df['domains'] = df['text'].apply(extract_domains)
    df['domain_types'] = df['domains'].apply(lambda doms: [classify_domain(d) for d in doms])
    
    target_types = ['leak_whistleblower', 'image_screenshot', 'academic_scientific', 'mainstream_news', 'government_official']
    for t in target_types:
        df[f'link_{t}'] = df['domain_types'].apply(lambda dtypes: 1 if t in dtypes else 0)
        
    return df

def build_maverick_regex():
    df_entity = pd.read_csv(ENTITY_PATH)
    ents = df_entity[df_entity["final_bucket_guess"] == "maverick_authority"]["entity"].dropna().astype(str).unique()
    ents_sorted = sorted(ents, key=len, reverse=True)
    return r"\b(" + "|".join(re.escape(e) for e in ents_sorted) + r")\b"

def main():
    print("=== RUNNING MULTIDIMENSIONAL LINK-TYPE REGRESSIONS ===")
    
    con = duckdb.connect()
    pattern_str = build_maverick_regex()
    
    # 1. Load r/conspiracy pure-population comments
    print("Extracting r/conspiracy pure-population comments...")
    query_parents = f"""
        SELECT
            s.id,
            s.pe_prob,
            s.ps_prob,
            e.text,
            e.upvotes,
            CAST(regexp_matches(e.text, $1) AS INTEGER) as has_maverick
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
    """
    df_con = con.execute(query_parents, [pattern_str]).df()
    print(f"Loaded {len(df_con):,} r/conspiracy comments.")
    
    # 2. Load r/AskReddit control comments
    print("Extracting r/AskReddit control comments...")
    df_ar = pd.read_parquet(ASKREDDIT_PATH)
    print(f"Loaded {len(df_ar):,} r/AskReddit comments.")
    
    # 3. Compute indicators for both
    print("Computing link indicators for r/conspiracy...")
    df_con = compute_link_indicators(df_con)
    df_con['log_char_length'] = np.log(df_con['text'].str.len() + 1)
    df_con['log_upvotes'] = np.log(df_con['upvotes'] - df_con['upvotes'].min() + 1)
    df_con['high_traction'] = (df_con['upvotes'] >= 5).astype(int)
    
    print("Computing link indicators for r/AskReddit...")
    df_ar = compute_link_indicators(df_ar)
    df_ar['log_char_length'] = np.log(df_ar['text'].str.len() + 1)
    df_ar['log_upvotes'] = np.log(df_ar['upvotes'] - df_ar['upvotes'].min() + 1)
    # AskReddit uses upvotes >= 5 as well for high traction (matching run_askreddit_control.py)
    df_ar['high_traction'] = (df_ar['upvotes'] >= 5).astype(int)
    
    # 4. Run regressions
    results = []
    
    # Identify which target link vars are actually present with positives in both datasets
    all_target_link_vars = [
        "link_leak_whistleblower", "link_image_screenshot", 
        "link_academic_scientific", "link_mainstream_news", "link_government_official"
    ]
    
    target_link_vars = [v for v in all_target_link_vars if df_con[v].sum() > 0 and df_ar[v].sum() > 0]
    print(f"Active link indicators included in regression: {target_link_vars}")
    
    formula_logit = "high_traction ~ pe_prob + ps_prob + has_maverick + " + " + ".join(target_link_vars) + " + log_char_length"
    formula_ols = "log_upvotes ~ pe_prob + ps_prob + has_maverick + " + " + ".join(target_link_vars) + " + log_char_length"
    
    print("\n" + "="*80)
    print("  REGRESSION: r/conspiracy (Low Elasticity, High Insider Presence)")
    print("="*80)
    
    print("\nRunning Logit Model...")
    m_con_logit = smf.logit(formula_logit, data=df_con).fit(disp=0, maxiter=100)
    print(m_con_logit.summary().tables[1])
    
    print("\nRunning OLS Model...")
    m_con_ols = smf.ols(formula_ols, data=df_con).fit()
    print(m_con_ols.summary().tables[1])
    
    print("\n" + "="*80)
    print("  REGRESSION: r/AskReddit (Control Baseline)")
    print("="*80)
    
    print("\nRunning Logit Model...")
    m_ar_logit = smf.logit(formula_logit, data=df_ar).fit(disp=0, maxiter=100)
    print(m_ar_logit.summary().tables[1])
    
    print("\nRunning OLS Model...")
    m_ar_ols = smf.ols(formula_ols, data=df_ar).fit()
    print(m_ar_ols.summary().tables[1])
    
    # 5. Save results to disk
    # Save coefficients for easy comparison in thesis
    for var in ["pe_prob", "ps_prob", "has_maverick", "log_char_length"] + all_target_link_vars:
        # conspiracy
        con_logit_coef = m_con_logit.params.get(var, np.nan)
        con_logit_p = m_con_logit.pvalues.get(var, np.nan)
        con_logit_se = m_con_logit.bse.get(var, np.nan)
        
        con_ols_coef = m_con_ols.params.get(var, np.nan)
        con_ols_p = m_con_ols.pvalues.get(var, np.nan)
        con_ols_se = m_con_ols.bse.get(var, np.nan)
        
        # askreddit
        ar_logit_coef = m_ar_logit.params.get(var, np.nan)
        ar_logit_p = m_ar_logit.pvalues.get(var, np.nan)
        ar_logit_se = m_ar_logit.bse.get(var, np.nan)
        
        ar_ols_coef = m_ar_ols.params.get(var, np.nan)
        ar_ols_p = m_ar_ols.pvalues.get(var, np.nan)
        ar_ols_se = m_ar_ols.bse.get(var, np.nan)
        
        results.append({
            "subreddit": "r/conspiracy",
            "model_type": "Logit",
            "variable": var,
            "coef": con_logit_coef,
            "pvalue": con_logit_p,
            "se": con_logit_se
        })
        results.append({
            "subreddit": "r/conspiracy",
            "model_type": "OLS",
            "variable": var,
            "coef": con_ols_coef,
            "pvalue": con_ols_p,
            "se": con_ols_se
        })
        results.append({
            "subreddit": "r/AskReddit",
            "model_type": "Logit",
            "variable": var,
            "coef": ar_logit_coef,
            "pvalue": ar_logit_p,
            "se": ar_logit_se
        })
        results.append({
            "subreddit": "r/AskReddit",
            "model_type": "OLS",
            "variable": var,
            "coef": ar_ols_coef,
            "pvalue": ar_ols_p,
            "se": ar_ols_se
        })
        
    df_results = pd.DataFrame(results)
    df_results.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved regression coefficients to {OUTPUT_CSV}")
    
    # 6. Beautiful side-by-side presentation
    print("\n" + "=" * 85)
    print(f" {'VARIABLE':30s} | {'r/conspiracy Logit Coef':25s} | {'r/AskReddit Logit Coef':25s}")
    print("=" * 85)
    for var in ["pe_prob", "ps_prob", "has_maverick"] + all_target_link_vars:
        con_c = m_con_logit.params.get(var, None)
        con_p = m_con_logit.pvalues.get(var, None)
        ar_c = m_ar_logit.params.get(var, None)
        ar_p = m_ar_logit.pvalues.get(var, None)
        
        if con_c is None or np.isnan(con_c):
            con_str = "N/A"
        else:
            con_sig = "***" if con_p < 0.001 else ("**" if con_p < 0.01 else ("*" if con_p < 0.05 else ""))
            con_str = f"{con_c:+.4f}{con_sig}"
            
        if ar_c is None or np.isnan(ar_c):
            ar_str = "N/A"
        else:
            ar_sig = "***" if ar_p < 0.001 else ("**" if ar_p < 0.01 else ("*" if ar_p < 0.05 else ""))
            ar_str = f"{ar_c:+.4f}{ar_sig}"
        
        print(f" {var:30s} | {con_str:>24s} | {ar_str:>24s}")
    print("=" * 85)
    print("Significance: * p < 0.05, ** p < 0.01, *** p < 0.001")

if __name__ == "__main__":
    main()

