"""build_domain_classification_lookup.py

Consolidates three domain classification databases:
1. Cell-61 Epistemic Domain Taxonomy (from run_link_type_regressions.py)
2. MBFC / SJR Source Authority Scores (from source_authority_scores.csv)
3. Curated Domains (from cited_content_curation_step2.md)

Outputs a canonical domain lookup table:
  - data/processed/domain_classification_lookup.csv

Applying DOMAIN_FALLBACK_EXCLUDED to reddit.com, businessinsider.com, usatoday.com,
documentcloud.org, and scribd.com to prevent platform over-generalization.
"""
import os
import re
import pandas as pd

SOURCE_AUTHORITY_PATH = 'data/processed/source_authority_scores.csv'
CURATION_PATH = 'handoff/cited_content_curation_step2.md'
OUT_PATH = 'data/processed/domain_classification_lookup.csv'

# First-class exclusion lists to prevent platform over-generalization
DOMAIN_FALLBACK_EXCLUDED = {
    'reddit.com', 'np.reddit.com', 'old.reddit.com', 'redd.it', 'i.redd.it', 'v.redd.it',
    'businessinsider.com', 'usatoday.com', 'documentcloud.org', 'scribd.com'
}

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

CELL61_TAXONOMY = {
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


def load_curated_domains():
    if not os.path.exists(CURATION_PATH):
        print(f"Warning: {CURATION_PATH} not found.")
        return set()
    with open(CURATION_PATH) as f:
        lines = f.readlines()
    domains = set()
    for line in lines:
        if not line.startswith('|') or line.startswith('|---') or line.strip().startswith('| url'):
            continue
        cell = line.split('|')[1].strip()
        if not cell:
            continue
        # Extract root domain / subdomain token (first token split by space or slash)
        token = re.split(r'[\s/]', cell, maxsplit=1)[0]
        token = token.lower().lstrip('www.')
        if token:
            domains.add(token)
    return domains


def main():
    print("=== BUILDING DOMAIN CLASSIFICATION LOOKUP ===")
    
    domain_records = {}

    # 1. Populate from Cell-61 Taxonomy
    print("1. Integrating Cell-61 Epistemic Domain Taxonomy...")
    for category, domains in CELL61_TAXONOMY.items():
        for d in domains:
            domain_records.setdefault(d, {
                'domain': d,
                'category': category,
                'mbfc_reliability_label': None,
                'sjr_quartile': None,
                'is_platform': d in PLATFORM_DOMAINS,
                'source': 'cell_61_taxonomy'
            })
            # Merge sources if already present
            if d in domain_records and domain_records[d]['category'] != category:
                # Handle explicit known conflicts (e.g. documentcloud.org being in leak_whistleblower and legal_documents)
                if d == 'documentcloud.org':
                    # We resolve documentcloud.org to legal_documents at domain fallback level
                    domain_records[d]['category'] = 'legal_documents'
                else:
                    domain_records[d]['category'] = category
                    domain_records[d]['source'] += f", cell_61_{category}"

    # 2. Populate from Source Authority Scores
    if os.path.exists(SOURCE_AUTHORITY_PATH):
        print("2. Integrating MBFC/SJR Source Authority Scores...")
        df_sa = pd.read_csv(SOURCE_AUTHORITY_PATH)
        for idx, row in df_sa.iterrows():
            matched_name = row['matched_name']
            if not isinstance(matched_name, str) or not matched_name or '.' not in matched_name:
                continue
            d = matched_name.lower().strip()
            
            reliability = row['reliability_label'] if isinstance(row['reliability_label'], str) else None
            category = row['category']
            
            # Map source category to Cell-61 Category
            mapped_category = None
            if category == 'news':
                mapped_category = 'mainstream_news'
            elif category == 'journal':
                mapped_category = 'academic_scientific'
            elif category == 'gov':
                mapped_category = 'government_official'
                
            mbfc_label = None
            sjr_quart = None
            
            if row['dataset'] == 'mbfc':
                mbfc_label = reliability
            elif row['dataset'] == 'sjr':
                sjr_quart = reliability
                
            if d in domain_records:
                # Merge existing record
                rec = domain_records[d]
                if mbfc_label:
                    rec['mbfc_reliability_label'] = mbfc_label
                if sjr_quart:
                    rec['sjr_quartile'] = sjr_quart
                rec['source'] += ", source_authority_scores"
            else:
                domain_records[d] = {
                    'domain': d,
                    'category': mapped_category or 'mainstream_news',
                    'mbfc_reliability_label': mbfc_label,
                    'sjr_quartile': sjr_quart,
                    'is_platform': d in PLATFORM_DOMAINS,
                    'source': 'source_authority_scores'
                }

    # 3. Populate from Curation File
    print("3. Integrating Curated Domains list...")
    curated_domains = load_curated_domains()
    print(f"  Parsed {len(curated_domains)} domain tokens from {CURATION_PATH}.")
    for d in curated_domains:
        if d in domain_records:
            domain_records[d]['source'] += ", curation_doc_fallback"
        else:
            # Determine base category
            mapped_cat = 'other'
            if d in PLATFORM_DOMAINS:
                mapped_cat = 'archive_preservation' if 'archive' in d else 'reference'
            domain_records[d] = {
                'domain': d,
                'category': mapped_cat,
                'mbfc_reliability_label': None,
                'sjr_quartile': None,
                'is_platform': d in PLATFORM_DOMAINS,
                'source': 'curated_doc_fallback'
            }

    # Build DataFrame
    lookup_df = pd.DataFrame(list(domain_records.values()))
    
    # Apply DOMAIN_FALLBACK_EXCLUDED explicitly as a first-class feature
    print("4. Applying first-class exclusion constraints (DOMAIN_FALLBACK_EXCLUDED)...")
    # For these domains, we reset categories or make sure they are treated as platforms or get no default category
    for d in DOMAIN_FALLBACK_EXCLUDED:
        if d in domain_records:
            # We enforce is_platform=True or category=other/platform for these
            lookup_df.loc[lookup_df['domain'] == d, 'is_platform'] = True
            lookup_df.loc[lookup_df['domain'] == d, 'source'] += ", fallback_exclusion_constraint"

    # Enforce platform flags wholesale
    for d in PLATFORM_DOMAINS:
        lookup_df.loc[lookup_df['domain'] == d, 'is_platform'] = True

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    lookup_df.to_csv(OUT_PATH, index=False)
    print(f"=== Saved {len(lookup_df):,} domain lookup records to {OUT_PATH} ===")


if __name__ == '__main__':
    main()
