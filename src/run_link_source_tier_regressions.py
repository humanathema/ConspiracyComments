"""run_link_source_tier_regressions.py

Run refined regressions with the flat 'has_link' variable replaced by
a 5-tier categorical 'link_source_tier' variable, mapped using institutional
source-authority scores (MBFC & SJR) and the project's pre-built domain taxonomy.

Tiers:
  - no_link: Comment has no links (reference group).
  - mainstream_reliable: Cites high/very high/mostly factual news, official gov agency, or SJR Q1/Q2 journal.
  - mixed_or_low_reliability: Cites mixed/low/very low factual news (e.g. Daily Mail, NY Post) or SJR Q3/Q4 journal.
  - aggregator_or_platform: Cites generic platforms/aggregators (Reddit, YouTube, Wikipedia, Twitter, Imgur, etc.).
  - unmatched_link: Cites any other domain not present in the scored listings (e.g. WikiLeaks).
"""
import os
import sys
import re
import numpy as np
import pandas as pd
import joblib
import duckdb
import statsmodels.formula.api as smf

sys.path.insert(0, os.path.dirname(__file__))
from refine_thesis_models import (
    pass_personal_experience_filter, pass_procedural_skepticism_filter,
    build_regex,
)
from rerun_refined_regressions_v2 import load_entities_split_corrected

MODELS_PATH = 'data/processed/staged_pipeline_models.joblib'
POLITICS_PATH = 'data/processed/comparison_politics_scored.parquet'
STAGED_PATH = 'data/processed/research_corpus_staged_scores_full21m.parquet'
EMPATH_PATH = 'data/processed/empath_scores_full.parquet'
THREAD_PATH = 'data/processed/thread_quality_metrics.csv'
PRESENCE_PATH = 'data/processed/thread_insider_presence.csv'
BRIGADE_PATH = 'data/processed/comment_brigade_flags.csv'

POLITICS_SCORED_PATH = 'data/processed/comparison_politics_staged_scored.parquet'
SOURCE_AUTHORITY_PATH = 'data/processed/source_authority_scores.csv'
OUTPUT_CSV = 'data/processed/link_source_tier_regression_results.csv'

MAX_SAMPLE = 50000

# Platform / aggregator domains that shouldn't be mapped onto news/journal scales
PLATFORM_DOMAINS = {
    'reddit.com', 'old.reddit.com', 'np.reddit.com', 'redd.it', 'i.redd.it', 'v.redd.it', 'i.reddituploads.com',
    'youtube.com', 'youtu.be', 'm.youtube.com',
    'twitter.com', 'x.com', 'mobile.twitter.com',
    'wikipedia.org', 'en.wikipedia.org', 'en.m.wikipedia.org',
    'imgur.com', 'i.imgur.com',
    'archive.is', 'archive.org', 'web.archive.org', 'archive.ph', 'archive.fo', 'archive.today', 'ghostarchive.org',
    'google.com', 'amazon.com', 'facebook.com', 'github.com', 'reveddit.com', 'removeddit.com', 'ceddit.com',
    'snewd.com', 'catbox.moe', 'postimg.cc', 'gyazo.com'
}

# Expand on run_link_type_regressions.py taxonomy
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
    ]
}

def extract_domains(text):
    if not isinstance(text, str):
        return []
    urls = re.findall(r'https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,4})', text)
    return [u.lower() for u in urls]

def clean_extracted_domain(raw_dom):
    clean = str(raw_dom).replace('https://', '').replace('http://', '').lower().strip()
    if clean.startswith('www.'):
        clean = clean[4:]
    return clean

def is_platform(domain):
    parts = domain.split('.')
    for i in range(len(parts) - 1):
        parent = '.'.join(parts[i:])
        if parent in PLATFORM_DOMAINS:
            return True
    return False

def normalize_text(text):
    if not isinstance(text, str):
        return ""
    text = text.lower().strip()
    if text.startswith("the "):
        text = text[4:].strip()
    return re.sub(r'[^a-z0-9]', '', text)

# Matching structures to load from df_sa
news_domain_map = {}
journal_entity_map = {}
gov_entity_map = {}

def build_source_authority_lookup():
    df_sa = pd.read_csv(SOURCE_AUTHORITY_PATH)
    for idx, row in df_sa.iterrows():
        cat = row['category']
        entity = row['entity']
        matched_name = row['matched_name'] if isinstance(row['matched_name'], str) else ""
        
        if cat == 'news':
            if matched_name and '.' in matched_name:
                news_domain_map[matched_name.lower()] = row
            else:
                news_domain_map[normalize_text(entity)] = row
        elif cat == 'journal':
            journal_entity_map[normalize_text(entity)] = row
            if matched_name:
                journal_entity_map[normalize_text(matched_name)] = row
        elif cat == 'gov':
            gov_entity_map[normalize_text(entity)] = row
            if matched_name:
                gov_entity_map[normalize_text(matched_name)] = row

def classify_single_domain(domain):
    if is_platform(domain):
        return 'aggregator_or_platform'
        
    # Check exact/subdomain news domain match in df_sa
    parts = domain.split('.')
    for i in range(len(parts) - 1):
        parent = '.'.join(parts[i:])
        if parent in news_domain_map:
            row = news_domain_map[parent]
            rel = str(row['reliability_label']).lower()
            if rel in ['high', 'very high', 'mostly factual', 'unclassified news']:
                return 'mainstream_reliable'
            elif rel in ['mixed', 'low', 'very low']:
                # Operational Split: mainstream imperfect vs alternative media
                if domain in TAXONOMY['alt_media'] or domain in ['zerohedge.com', 'infowars.com', 'breitbart.com', 'rt.com']:
                    return 'alt_media'
                return 'mainstream_imperfect'
                
    # Check run_link_type_regressions.py taxonomy
    if domain in TAXONOMY['mainstream_news']:
        if 'dailymail.co.uk' in domain or 'nypost.com' in domain:
            return 'mainstream_imperfect'
        return 'mainstream_reliable'
        
    if domain in TAXONOMY['academic_scientific']:
        return 'mainstream_reliable'
        
    if domain in TAXONOMY['government_official'] or domain.endswith('.gov') or domain.endswith('.mil'):
        return 'mainstream_reliable'
        
    if domain in TAXONOMY['alt_media']:
        return 'alt_media'
        
    # Check substring/normalized match of entity in domain
    norm_dom = normalize_text(domain.split('.')[-2]) if len(domain.split('.')) >= 2 else normalize_text(domain)
    
    # Check gov
    for norm_ent, row in gov_entity_map.items():
        if norm_ent in norm_dom or norm_dom in norm_ent:
            return 'mainstream_reliable'
            
    # Check journals
    for norm_ent, row in journal_entity_map.items():
        if norm_ent in norm_dom or norm_dom in norm_ent:
            rel = str(row['reliability_label']).lower()
            if rel in ['q1', 'q2']:
                return 'mainstream_reliable'
            else:
                return 'mainstream_imperfect'
                
    # Check news
    for norm_ent, row in news_domain_map.items():
        if norm_ent in norm_dom or norm_dom in norm_ent:
            if len(norm_ent) >= 4:
                rel = str(row['reliability_label']).lower()
                if rel in ['high', 'very high', 'mostly factual', 'unclassified news']:
                    return 'mainstream_reliable'
                else:
                    if domain in TAXONOMY['alt_media'] or domain in ['zerohedge.com', 'infowars.com', 'breitbart.com', 'rt.com']:
                        return 'alt_media'
                    return 'mainstream_imperfect'
                    
    return 'unmatched_link'

def determine_link_source_tier(text, has_link):
    if has_link == 0:
        return 'no_link'
    domains = extract_domains(text)
    if not domains:
        return 'no_link'
        
    tiers = [classify_single_domain(d) for d in domains]
    
    # Precedence order resolution
    if 'mainstream_reliable' in tiers:
        return 'mainstream_reliable'
    if 'mainstream_imperfect' in tiers:
        return 'mainstream_imperfect'
    if 'alt_media' in tiers:
        return 'alt_media'
    if 'aggregator_or_platform' in tiers:
        return 'aggregator_or_platform'
    if 'unmatched_link' in tiers:
        return 'unmatched_link'
        
    return 'no_link'

def main():
    print("=== RUNNING LINK SOURCE TIER REGRESSIONS ===")
    
    cache_path = 'data/processed/citations_cache.parquet'
    if not os.path.exists(cache_path):
        print(f"Error: Missing centralized cache file: {cache_path}. Run build_citations_cache.py first.")
        sys.exit(1)
        
    print("Loading pre-computed citation cache...")
    cache_df = pd.read_parquet(cache_path)
    
    # 5-tier Mapping (mapping split tiers to mixed_or_low_reliability for legacy parity)
    cache_df['tier_5'] = cache_df['link_source_tier'].replace({
        'mainstream_imperfect': 'mixed_or_low_reliability',
        'alt_media': 'mixed_or_low_reliability'
    })
    
    precedence_5 = {
        'mainstream_reliable': 4,
        'mixed_or_low_reliability': 3,
        'aggregator_or_platform': 2,
        'unmatched_link': 1,
        'no_link': 0
    }
    cache_df['prec_5'] = cache_df['tier_5'].map(precedence_5).fillna(0)
    comment_tiers_5 = cache_df.sort_values('prec_5', ascending=False).drop_duplicates('comment_id').set_index('comment_id')['tier_5'].to_dict()
    
    # 6-tier Split Mapping (mainstream_reliable > mainstream_imperfect > alt_media > aggregator_or_platform > unmatched_link)
    precedence_6 = {
        'mainstream_reliable': 5,
        'mainstream_imperfect': 4,
        'alt_media': 3,
        'aggregator_or_platform': 2,
        'unmatched_link': 1,
        'no_link': 0
    }
    cache_df['prec_6'] = cache_df['link_source_tier'].map(precedence_6).fillna(0)
    comment_tiers_6 = cache_df.sort_values('prec_6', ascending=False).drop_duplicates('comment_id').set_index('comment_id')['link_source_tier'].to_dict()
    
    print("Splitting entities...")
    mavericks, canon, consensus = load_entities_split_corrected()
    rx_mav = build_regex(mavericks)
    rx_can = build_regex(canon)
    rx_con = build_regex(consensus)
    
    con = duckdb.connect()
    print("\nLoading r/conspiracy pure comments...")
    query = f"""
        SELECT s.id, e.text, e.upvotes, e.char_length, s.pe_prob, s.ps_prob, e.has_link
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
    df_con = con.execute(query).df()
    print(f"Loaded {len(df_con):,} pure r/conspiracy comments.")
    
    print("Flagging entity mentions and link tiers in r/conspiracy...")
    df_con['has_maverick'] = df_con['text'].apply(lambda x: 1 if bool(rx_mav.search(str(x))) else 0)
    df_con['has_canonical_expert'] = df_con['text'].apply(lambda x: 1 if bool(rx_can.search(str(x))) else 0)
    df_con['has_consensus_expert'] = df_con['text'].apply(lambda x: 1 if bool(rx_con.search(str(x))) else 0)
    df_con['log_char_length'] = np.log(df_con['char_length'] + 1)
    df_con['log_upvotes'] = np.log(df_con['upvotes'] - df_con['upvotes'].min() + 1)
    df_con['high_traction'] = (df_con['upvotes'] >= 5).astype(int)
    
    # Assign comment-level tiers from pre-computed dictionary mapping
    df_con['link_source_tier'] = df_con['id'].map(comment_tiers_5).fillna('no_link')
    df_con['link_source_tier_split'] = df_con['id'].map(comment_tiers_6).fillna('no_link')
    
    print("\nProcessing r/politics control sample...")
    df_pol = pd.read_parquet(POLITICS_SCORED_PATH)
    print(f"Loaded {len(df_pol):,} r/politics comments.")
    
    print("Flagging entity mentions and link tiers in r/politics...")
    df_pol['has_maverick'] = df_pol['text'].apply(lambda x: 1 if bool(rx_mav.search(str(x))) else 0)
    df_pol['has_canonical_expert'] = df_pol['text'].apply(lambda x: 1 if bool(rx_can.search(str(x))) else 0)
    df_pol['has_consensus_expert'] = df_pol['text'].apply(lambda x: 1 if bool(rx_con.search(str(x))) else 0)
    df_pol['log_char_length'] = np.log(df_pol['char_length'] + 1)
    df_pol['log_upvotes'] = np.log(df_pol['upvotes'] - df_pol['upvotes'].min() + 1)
    df_pol['high_traction'] = (df_pol['upvotes'] >= 5).astype(int)
    
    # Assign comment-level tiers from pre-computed dictionary mapping
    df_pol['link_source_tier'] = df_pol['id'].map(comment_tiers_5).fillna('no_link')
    df_pol['link_source_tier_split'] = df_pol['id'].map(comment_tiers_6).fillna('no_link')
    
    # Quick sanity-check printout of link source tier distributions
    for name, df_sub in [("r/conspiracy", df_con), ("r/politics", df_pol)]:
        print(f"\n[{name}] Link Source Tier Distribution (Legacy 5-tier):")
        counts = df_sub['link_source_tier'].value_counts()
        pcts = df_sub['link_source_tier'].value_counts(normalize=True) * 100
        for cat in ['no_link', 'mainstream_reliable', 'mixed_or_low_reliability', 'aggregator_or_platform', 'unmatched_link']:
            c = counts.get(cat, 0)
            p = pcts.get(cat, 0.0)
            print(f"  - {cat:25s}: {c:7d} ({p:.3f}%)")
            
        print(f"\n[{name}] Link Source Tier Distribution (Split 6-tier):")
        counts_sp = df_sub['link_source_tier_split'].value_counts()
        pcts_sp = df_sub['link_source_tier_split'].value_counts(normalize=True) * 100
        for cat in ['no_link', 'mainstream_reliable', 'mainstream_imperfect', 'alt_media', 'aggregator_or_platform', 'unmatched_link']:
            c = counts_sp.get(cat, 0)
            p = pcts_sp.get(cat, 0.0)
            print(f"  - {cat:25s}: {c:7d} ({p:.3f}%)")
            
    print("\n--- Running Regressions ---")
    results = []
    specs = [
        ("r/conspiracy", df_con),
        ("r/politics", df_pol),
    ]
    
    # Run Legacy 5-tier models
    print("\n=== RUNNING LEGACY 5-TIER LOGIT REGRESSIONS ===")
    formula_5 = "high_traction ~ pe_prob + ps_prob + C(link_source_tier, Treatment(reference='no_link')) + has_maverick + has_canonical_expert + has_consensus_expert + log_char_length"
    
    for name, df_sub in specs:
        n_consensus = int(df_sub["has_consensus_expert"].sum())
        use_formula = formula_5
        dropped_consensus = False
        
        if n_consensus < 20:
            use_formula = use_formula.replace(" + has_consensus_expert", "")
            dropped_consensus = True
        else:
            ct = pd.crosstab(df_sub["has_consensus_expert"], df_sub["high_traction"])
            if (ct.values == 0).any():
                use_formula = use_formula.replace(" + has_consensus_expert", "")
                dropped_consensus = True
                
        print(f"Running Legacy Logit Model for {name}...")
        try:
            m = smf.logit(use_formula, data=df_sub).fit(disp=0, maxiter=100)
            print(m.summary().tables[1])
            
            # Extract standard parameters
            for c in ["pe_prob", "ps_prob", "has_maverick", "has_canonical_expert", "has_consensus_expert", "log_char_length"]:
                if c in m.params:
                    results.append({
                        "model": "legacy_5_tier", "subreddit": name, "variable": c,
                        "coef": m.params[c], "se": m.bse[c], "pvalue": m.pvalues[c], "n_obs": int(m.nobs)
                    })
            # Extract link_source_tier categories
            for cat in ['mainstream_reliable', 'mixed_or_low_reliability', 'aggregator_or_platform', 'unmatched_link']:
                var_name = f"C(link_source_tier, Treatment(reference='no_link'))[T.{cat}]"
                if var_name in m.params:
                    results.append({
                        "model": "legacy_5_tier", "subreddit": name, "variable": f"link_{cat}",
                        "coef": m.params[var_name], "se": m.bse[var_name], "pvalue": m.pvalues[var_name], "n_obs": int(m.nobs)
                    })
        except Exception as e:
            print(f"Legacy model failed for {name}: {e}")

    # Run Split 6-tier models
    print("\n=== RUNNING SPLIT 6-TIER LOGIT REGRESSIONS (Mainstream Imperfect vs Alt Media) ===")
    formula_6 = "high_traction ~ pe_prob + ps_prob + C(link_source_tier_split, Treatment(reference='no_link')) + has_maverick + has_canonical_expert + has_consensus_expert + log_char_length"
    
    for name, df_sub in specs:
        n_consensus = int(df_sub["has_consensus_expert"].sum())
        use_formula = formula_6
        dropped_consensus = False
        
        if n_consensus < 20:
            use_formula = use_formula.replace(" + has_consensus_expert", "")
            dropped_consensus = True
        else:
            ct = pd.crosstab(df_sub["has_consensus_expert"], df_sub["high_traction"])
            if (ct.values == 0).any():
                use_formula = use_formula.replace(" + has_consensus_expert", "")
                dropped_consensus = True
                
        print(f"Running Split 6-tier Logit Model for {name}...")
        try:
            m = smf.logit(use_formula, data=df_sub).fit(disp=0, maxiter=100)
            print(m.summary().tables[1])
            
            # Extract standard parameters
            for c in ["pe_prob", "ps_prob", "has_maverick", "has_canonical_expert", "has_consensus_expert", "log_char_length"]:
                if c in m.params:
                    results.append({
                        "model": "split_6_tier", "subreddit": name, "variable": c,
                        "coef": m.params[c], "se": m.bse[c], "pvalue": m.pvalues[c], "n_obs": int(m.nobs)
                    })
            # Extract link_source_tier categories
            for cat in ['mainstream_reliable', 'mainstream_imperfect', 'alt_media', 'aggregator_or_platform', 'unmatched_link']:
                var_name = f"C(link_source_tier_split, Treatment(reference='no_link'))[T.{cat}]"
                if var_name in m.params:
                    results.append({
                        "model": "split_6_tier", "subreddit": name, "variable": f"link_{cat}",
                        "coef": m.params[var_name], "se": m.bse[var_name], "pvalue": m.pvalues[var_name], "n_obs": int(m.nobs)
                    })
        except Exception as e:
            print(f"Split model failed for {name}: {e}")
            
    pd.DataFrame(results).to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved combined regression results to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
