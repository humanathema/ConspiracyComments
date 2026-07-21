"""build_citations_cache.py

Centralizes URL extraction, normalization, and classification across the entire project
(r/conspiracy enriched corpus, r/politics staged scores, and r/AskReddit staged scores).

Produces a central Parquet cache:
  - data/processed/citations_cache.parquet
  - data/processed/citations_cache.csv
"""
import os
import re
import sys
import pandas as pd
import duckdb

# Add src to path for relative imports if needed
sys.path.insert(0, os.path.dirname(__file__))

CURATION_PATH = 'handoff/cited_content_curation_step2.md'
DOMAIN_LOOKUP_PATH = 'data/processed/domain_classification_lookup.csv'
STAGED_PATH = 'data/processed/research_corpus_staged_scores_full21m.parquet'
EMPATH_PATH = 'data/processed/empath_scores_full.parquet'
POLITICS_PATH = 'data/processed/comparison_politics_staged_scored.parquet'
ASKREDDIT_PATH = 'data/processed/comparison_askreddit_staged_scored.parquet'

OUT_PARQUET = 'data/processed/citations_cache.parquet'
OUT_CSV = 'data/processed/citations_cache.csv'

URL_PATTERN = r'https?://[^\s\]\>"\']+'
TRAILING_PUNCT = re.compile(r'[.,;:!?\'"\]]+$')

DOMAIN_FALLBACK_EXCLUDED = {
    'reddit.com', 'np.reddit.com', 'old.reddit.com', 'redd.it', 'i.redd.it', 'v.redd.it',
    'businessinsider.com', 'usatoday.com', 'documentcloud.org', 'scribd.com',
    'cia.gov', 'assets.documentcloud.org'
}


def strip_unbalanced_trailing_paren(u):
    while u.endswith(')') and u.count(')') > u.count('('):
        u = u[:-1]
    return u


def normalize_url(u):
    u = re.sub(r'^http://', 'https://', u)
    m = re.match(r'^(https://[^/]+)(/.*)?$', u)
    if m:
        domain, path = m.group(1).lower(), m.group(2) or ''
        if path == '/':
            path = ''
        u = domain + path
        
    # Standardize documentcloud.org URLs (extract ID and slug, strip subdomains/S3 paths)
    if 'documentcloud.org' in u.lower():
        u_clean = u.split('#')[0].split('?')[0]
        m_doc = re.search(r'/documents/(\d+)[-/]([^/]+)', u_clean, re.IGNORECASE)
        if m_doc:
            doc_id = m_doc.group(1)
            slug = m_doc.group(2)
            slug = re.sub(r'\.(html|pdf|txt)$', '', slug, flags=re.IGNORECASE)
            slug = slug.rstrip('/')
            u = f"https://www.documentcloud.org/documents/{doc_id}-{slug}"
            
    return u


def extract_urls(text):
    if not isinstance(text, str):
        return []
    raw = re.findall(URL_PATTERN, text)
    cleaned = []
    for u in raw:
        u = TRAILING_PUNCT.sub('', u)
        u = strip_unbalanced_trailing_paren(u)
        u = TRAILING_PUNCT.sub('', u)
        if len(u) > 15:
            cleaned.append(normalize_url(u))
    return list(set(cleaned))


def parse_curated_urls():
    if not os.path.exists(CURATION_PATH):
        print(f"Error: {CURATION_PATH} not found.")
        return []
        
    with open(CURATION_PATH, 'r') as f:
        content = f.read()
        
    rows = []
    lines = content.split('\n')
    in_table = False
    for line in lines:
        if line.startswith('|') and 'url' in line and 'authors' in line:
            in_table = True
            continue
        if in_table:
            if not line.strip() or not line.startswith('|'):
                in_table = False
                continue
            if '---|---|---|---|---' in line:
                continue
            parts = [p.strip() for p in line.split('|')[1:-1]]
            if len(parts) >= 4:
                rows.append({
                    'url': parts[0],
                    'type': parts[3]
                })
    return rows


def build_taxonomy_matchers(curated_rows):
    matchers = []
    domain_tax_votes = {}
    for r in curated_rows:
        curated_url = r['url'].strip()
        t = r['type'].lower().strip()
        u_lower = curated_url.lower()

        # Taxonomy mapping for credentials
        if 'institutional' in t or 'official' in t or 'scientific paper' in t or 'academic study' in t or 'preprint' in t or 'legal document' in t or t in ['scientific paper (methodological critique)']:
            tax = 'credentialed_institutional'
        elif 'individual' in t or 'whistleblower' in t:
            tax = 'individual_named_source'
        elif 'alternative' in t or 'conspiracy' in t or 'leak' in t or 'movement' in t or 'community meta' in t or 'esoteric' in t or 'spiritual' in t:
            if 'foreignpolicy.com' in u_lower:
                tax = 'other'
            else:
                tax = 'movement_internal_anonymous'
        else:
            tax = 'other'

        domain_token = re.split(r'[\s/]', curated_url, maxsplit=1)[0].lower()
        domain_token = re.sub(r'^www\.', '', domain_token)
        if domain_token:
            domain_tax_votes.setdefault(domain_token, []).append(tax)

        # Compile regex
        curated_url_clean = re.sub(r'\s*\.\.\.\s*', '...', curated_url)
        pattern = re.escape(curated_url_clean)
        pattern = pattern.replace(r'\.\.\.', r'.*')
        if not pattern.startswith('http'):
            pattern = r'https?://(?:www\.)?' + pattern
        if pattern.endswith('/'):
            pattern = pattern + '?'
        else:
            pattern = pattern + '/?'

        try:
            rx = re.compile('^' + pattern + '$', re.IGNORECASE)
            matchers.append((curated_url, rx, tax))
        except Exception as e:
            print(f"Error compiling regex for {curated_url}: {e}")

    domain_tax_map = {}
    for domain, votes in domain_tax_votes.items():
        counts = pd.Series(votes).value_counts()
        domain_tax_map[domain] = counts.index[0]

    return matchers, domain_tax_map


def main():
    print("=== MATERIALIZING CENTRALIZED CITATION CACHE ===")
    
    if not os.path.exists(DOMAIN_LOOKUP_PATH):
        print(f"Error: missing domain lookup file {DOMAIN_LOOKUP_PATH}. Build it first.")
        sys.exit(1)
        
    print("Loading domain classification lookup table...")
    df_domain_lookup = pd.read_csv(DOMAIN_LOOKUP_PATH)
    domain_to_rec = df_domain_lookup.set_index('domain').to_dict(orient='index')
    
    print("Parsing curated exact URLs...")
    curated_rows = parse_curated_urls()
    matchers, domain_tax_map = build_taxonomy_matchers(curated_rows)
    print(f"  Parsed {len(curated_rows)} curated exact URLs.")

    con = duckdb.connect()

    # Step 1. Gather all comments that may contain links
    print("\n[Population 1/3] Streaming r/conspiracy pure comments with links...")
    # Empath staged score has has_link
    query_con = f"""
        SELECT s.id, e.text
        FROM '{STAGED_PATH}' s
        JOIN '{EMPATH_PATH}' e ON s.id = e.id
        WHERE e.has_link = 1
    """
    df_con = con.execute(query_con).df()
    print(f"  Found {len(df_con):,} r/conspiracy comments with links.")

    print("\n[Population 2/3] Streaming r/politics staged comments with links...")
    # Politics scored sample has has_link
    query_pol = f"""
        SELECT id, text
        FROM '{POLITICS_PATH}'
        WHERE has_link = 1
    """
    df_pol = con.execute(query_pol).df()
    print(f"  Found {len(df_pol):,} r/politics comments with links.")

    print("\n[Population 3/3] Streaming r/AskReddit control comments with links...")
    query_ar = f"""
        SELECT id, text
        FROM '{ASKREDDIT_PATH}'
        WHERE has_link = 1
    """
    df_ar = con.execute(query_ar).df()
    print(f"  Found {len(df_ar):,} r/AskReddit comments with links.")

    # Combine into a single unique set of comment texts to extract links
    print("\nCombining populations...")
    df_con['population'] = 'conspiracy'
    df_pol['population'] = 'politics'
    df_ar['population'] = 'askreddit'
    
    combined_df = pd.concat([df_con, df_pol, df_ar], ignore_index=True)
    combined_df = combined_df.drop_duplicates(subset=['id'])
    print(f"  Total unique comments with links to extract: {len(combined_df):,}")

    print("\nExtracting and normalizing URLs from texts...")
    records = []
    for idx, row in combined_df.iterrows():
        cid = row['id']
        urls = extract_urls(row['text'])
        for url in urls:
            m = re.match(r'^https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,4})', url)
            if not m:
                continue
            domain = m.group(1).lower()
            records.append({
                'comment_id': cid,
                'url': url,
                'domain': domain
            })

    citations_df = pd.DataFrame(records)
    print(f"  Extracted {len(citations_df):,} citation records across populations.")

    print("\nApplying taxonomy classification mapping rules...")
    
    # Pre-cache classification logic for performance
    classification_cache = {}

    def classify_single_citation(url, domain):
        cache_key = (url, domain)
        if cache_key in classification_cache:
            return classification_cache[cache_key]
            
        # 1. Exact curated match check
        exact_tax = None
        for orig_str, rx, tax in matchers:
            if rx.match(url):
                exact_tax = tax
                break
                
        # 2. Get domain record
        domain_rec = domain_to_rec.get(domain)
        is_platform = False
        mbfc_rel = None
        sjr_quart = None
        category = 'other'
        
        if domain_rec:
            is_platform = bool(domain_rec['is_platform'])
            mbfc_rel = domain_rec['mbfc_reliability_label'] if pd.notna(domain_rec['mbfc_reliability_label']) else None
            sjr_quart = domain_rec['sjr_quartile'] if pd.notna(domain_rec['sjr_quartile']) else None
            category = domain_rec['category']
            
        # Enforce hard fallback exclusion list constraints (e.g. documentcloud.org, scribd.com, etc.)
        if domain in DOMAIN_FALLBACK_EXCLUDED:
            is_platform = True

        # Determine Credentials Taxonomy Tier (4-tier)
        cred_tier = 'other'
        conf = 'unreviewed'
        
        if exact_tax:
            cred_tier = exact_tax
            conf = 'curated'
        elif domain in DOMAIN_FALLBACK_EXCLUDED:
            # First-class fallback exclusions default strictly to other (unreviewed)
            cred_tier = 'other'
            conf = 'unreviewed'
        elif domain in domain_tax_map:
            # Curated domain-level fallback
            cred_tier = domain_tax_map[domain]
            conf = 'provisional_heuristic'
        elif domain == 'cia.gov':
            # Hand-review tiebreak: cia.gov default is credentialed_institutional
            cred_tier = 'credentialed_institutional'
            conf = 'provisional_heuristic'
        elif domain == 'pfizer.com':
            # Hand-review tiebreak: pfizer.com default is other (private commercial company)
            cred_tier = 'other'
            conf = 'provisional_heuristic'
        elif domain.endswith('.gov') or domain.endswith('.mil') or domain in [
            'cdc.gov', 'nih.gov', 'fda.gov', 'who.int', 'ncbi.nlm.nih.gov',
            'pubmed.ncbi.nlm.nih.gov', 'nature.com', 'nejm.org', 'thelancet.com',
            'bmj.com', 'pnas.org', 'sciencedirect.com', 'springer.com',
            'jamanetwork.com', 'science.org', 'biorxiv.org', 'medrxiv.org', 'wiley.com'
        ]:
            cred_tier = 'credentialed_institutional'
            conf = 'provisional_heuristic'
        elif domain in [
            'youtube.com', 'youtu.be', 'twitter.com', 'x.com', 'wikipedia.org',
            'en.wikipedia.org', 'reddit.com', 'old.reddit.com', 'nytimes.com',
            'bbc.com', 'theguardian.com', 'reuters.com', 'npr.org', 'cnn.com'
        ]:
            cred_tier = 'other'
            conf = 'provisional_heuristic'
        else:
            # Map based on domain lookup's base category
            if category in ['government_official', 'academic_scientific']:
                cred_tier = 'credentialed_institutional'
                conf = 'provisional_heuristic'
            elif category == 'alt_media':
                cred_tier = 'movement_internal_anonymous'
                conf = 'provisional_heuristic'
            elif category == 'leak_whistleblower':
                # Operational mapping rule for leak_whistleblower:
                # - Official government FOIA reading rooms map to credentialed_institutional
                if 'gov' in domain or domain.endswith('.gov') or domain in ['foia.state.gov', 'vault.fbi.gov']:
                    cred_tier = 'credentialed_institutional'
                else:
                    # Alternativ/unaffiliated leak archives map to movement_internal_anonymous
                    cred_tier = 'movement_internal_anonymous'
                conf = 'provisional_heuristic'
            else:
                cred_tier = 'other'
                conf = 'unreviewed'

        # Determine Link Source Tier (pre-computes 5-tier & 6-tier regressions categories)
        # Tiers: 'mainstream_reliable', 'mainstream_imperfect', 'alt_media', 'aggregator_or_platform', 'unmatched_link'
        source_tier = 'unmatched_link'
        
        if is_platform:
            source_tier = 'aggregator_or_platform'
        elif domain.endswith('.gov') or domain.endswith('.mil') or category in ['government_official', 'academic_scientific']:
            source_tier = 'mainstream_reliable'
        elif mbfc_rel:
            m_lower = mbfc_rel.lower()
            if m_lower in ['high', 'very high', 'mostly factual', 'unclassified news']:
                source_tier = 'mainstream_reliable'
            elif m_lower in ['mixed', 'low', 'very low']:
                # Operational Split: mainstream imperfect vs alternative media
                if category == 'alt_media' or domain in ['zerohedge.com', 'infowars.com', 'breitbart.com', 'rt.com']:
                    source_tier = 'alt_media'
                else:
                    source_tier = 'mainstream_imperfect'
        elif sjr_quart:
            s_lower = sjr_quart.lower()
            if s_lower in ['q1', 'q2']:
                source_tier = 'mainstream_reliable'
            elif s_lower in ['q3', 'q4']:
                source_tier = 'mainstream_imperfect'
        elif category == 'mainstream_news':
            if domain in ['dailymail.co.uk', 'nypost.com']:
                source_tier = 'mainstream_imperfect'
            else:
                source_tier = 'mainstream_reliable'
        elif category == 'alt_media':
            source_tier = 'alt_media'
        else:
            source_tier = 'unmatched_link'

        res = (category, is_platform, cred_tier, source_tier, conf, mbfc_rel, sjr_quart)
        classification_cache[cache_key] = res
        return res

    # Vectorized / fast mapped assignment
    categories = []
    platforms = []
    cred_tiers = []
    source_tiers = []
    confidences = []
    mbfc_reliability = []
    sjr_quartiles = []

    for idx, row in citations_df.iterrows():
        cat, is_plat, cred, src_tier, conf, mbfc, sjr = classify_single_citation(row['url'], row['domain'])
        categories.append(cat)
        platforms.append(is_plat)
        cred_tiers.append(cred)
        source_tiers.append(src_tier)
        confidences.append(conf)
        mbfc_reliability.append(mbfc)
        sjr_quartiles.append(sjr)

    citations_df['category'] = categories
    citations_df['is_platform'] = platforms
    citations_df['credentials_taxonomy_tier'] = cred_tiers
    citations_df['link_source_tier'] = source_tiers
    citations_df['confidence'] = confidences
    citations_df['mbfc_reliability_label'] = mbfc_reliability
    citations_df['sjr_quartile'] = sjr_quartiles

    print(f"\nCentralized Cache Mapping Stats:")
    print(f"  Total records: {len(citations_df):,}")
    print(f"  Curated exact URLs: {sum(citations_df['confidence'] == 'curated'):,}")
    print(f"  Fallback/Heuristic matches: {sum(citations_df['confidence'] == 'provisional_heuristic'):,}")
    print(f"  Unreviewed (strictly unassigned): {sum(citations_df['confidence'] == 'unreviewed'):,}")

    print("\nCredentials 4-tier Taxonomy Distribution:")
    for tier, count in citations_df['credentials_taxonomy_tier'].value_counts().items():
        print(f"  - {tier:27s}: {count:7d}")

    print("\nLink Source Tier Distribution (including split mainstream_imperfect/alt_media):")
    for tier, count in citations_df['link_source_tier'].value_counts().items():
        print(f"  - {tier:27s}: {count:7d}")

    # Output Parquet & CSV
    print(f"\nSaving cache files...")
    citations_df.to_parquet(OUT_PARQUET, index=False)
    citations_df.to_csv(OUT_CSV, index=False)
    print(f"=== Saved central Parquet cache to {OUT_PARQUET} ===")
    print(f"=== Saved central CSV cache audit to {OUT_CSV} ===")


if __name__ == '__main__':
    main()
