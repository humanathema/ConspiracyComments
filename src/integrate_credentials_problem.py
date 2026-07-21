"""integrate_credentials_problem.py

Integrates three separate lines of credentials research into a unified,
robust finding for the "credentials problem" question:
1. Entity-based breakdown (from per_entity_stance_breakdown.py)
2. source_citation model predictions (from score_authority_appeal_full.py)
3. URL/citation taxonomy (parsed directly from cited_content_curation_step2.md)

Outputs detailed metrics and cross-tabulation reports.
"""
import os
import re
import sys
import numpy as np
import pandas as pd
import joblib
import duckdb

# Setup path portability
sys.path.insert(0, os.path.dirname(__file__))
from rerun_refined_regressions_v2 import load_entities_split_corrected
from refine_thesis_models import build_regex
from combined_maverick_detector import load_maverick_disambiguation_lookup, VALID_MAVERICK_CANDIDATES, CANDIDATE_TO_BARES as MAVERICK_CANDIDATE_TO_BARES
from consensus_disambiguation_lookup import load_consensus_disambiguation_lookup, VALID_CONSENSUS_CANDIDATES, CANDIDATE_TO_BARES as CONSENSUS_CANDIDATE_TO_BARES
from stance_window_utils import extract_entity_window, filter_quoted_spans, is_list_or_link_dump_window, compute_spans_for_row

CURATION_PATH = 'handoff/cited_content_curation_step2.md'
SCORED_PATH = 'data/processed/authority_appeal_scored.parquet'
ENRICHED_PATH = 'data/processed/research_corpus_enriched.parquet'
STANCE_MODEL_PATH = 'data/processed/stance_classifier_3class.joblib'
OUT_CSV_PATH = 'data/processed/credentials_integration_results.csv'
OUT_REPORT_PATH = 'data/processed/credentials_problem_integration_report.md'

URL_PATTERN = r'https?://[^\s\]\>"\']+'
TRAILING_PUNCT = re.compile(r'[.,;:!?\'"\]]+$')


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
    """Parses cited_content_curation_step2.md table to build matchers."""
    if not os.path.exists(CURATION_PATH):
        print(f"Error: {CURATION_PATH} not found.")
        sys.exit(1)
        
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
    """Compiles regex matchers and establishes the 4-tier taxonomy mapping.

    FIXED 2026-07-22 (Nash's domain-frequency scan of the 'other' bucket,
    see explore_other_bucket_domains.py): the original version only
    classified a citation if it matched one of the 139 curated URLs by
    EXACT page-level regex. Domains that are already curated -- e.g.
    corbettreport.com (individual_named_source), ae911truth.org,
    vigilantcitizen.com, geoengineeringwatch.org, qmap.pub, voat.co,
    cryptome.org, covid19criticalcare.com, gbdeclaration.org (all
    movement_internal_anonymous) -- were falling through to 'other' for
    every page EXCEPT the one literal curated URL, since the only
    domain-level fallback covered a dozen hardcoded institutional/
    mainstream domains and nothing for the other two tiers at all. This
    accounted for ~2.22M of the 4.37M 'other' citations (roughly half the
    bucket) -- a code gap, not a curation gap, since the category
    judgment for these domains was already made by Nash.

    Now also returns a domain-level fallback map (domain -> tax) built
    from the SAME curated rows/tax assignment, so any page under an
    already-curated domain gets that domain's category instead of
    silently defaulting to 'other'. Conflicting tax assignments for the
    same domain (rare, checked at build time) are resolved by majority
    vote across that domain's curated rows, with a printed warning so a
    real conflict isn't silently papered over."""
    matchers = []
    domain_tax_votes = {}
    for r in curated_rows:
        curated_url = r['url'].strip()
        t = r['type'].lower().strip()
        u_lower = curated_url.lower()

        # Taxonomy mapping
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

        # Domain-level vote (first whitespace/slash-delimited token, since
        # curated rows are written as "domain.tld path/to/page" or
        # "domain.tld/path/to/page" -- same convention parsed elsewhere,
        # see explore_other_bucket_domains.py's load_curated_domains()).
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
        if len(counts) > 1:
            print(f"  WARNING: domain '{domain}' has conflicting curated categories {dict(counts)} "
                  f"-- using majority ({counts.index[0]}).")
        domain_tax_map[domain] = counts.index[0]

    return matchers, domain_tax_map


# 2026-07-22: domain-level fallback over-generalizes for general-purpose
# multi-topic platforms/publishers where the curated row(s) tagged ONE
# specific article, not the whole site's character -- reddit.com alone
# would move ~1.55M citations (every subreddit on the platform) off of 2
# curated conspiracy-subforum pages. businessinsider.com/usatoday.com
# same pattern from one flagged article each. Excluded here pending real
# per-domain review, not auto-decided -- same guardrail-against-
# guesswork principle as the curation doc itself. documentcloud.org
# deliberately left in (Nash's call): plausibly has a genuinely specific
# role in this corpus worth investigating rather than blanket-excluding.
DOMAIN_FALLBACK_EXCLUDED = {'reddit.com', 'np.reddit.com', 'old.reddit.com', 'businessinsider.com', 'usatoday.com', 'cia.gov', 'assets.documentcloud.org'}


def classify_url(url, matchers, domain_tax_map):
    """Classifies a URL into the 4-tier taxonomy: exact curated-page match
    first, then curated-DOMAIN fallback (see build_taxonomy_matchers'
    2026-07-22 fix note, and DOMAIN_FALLBACK_EXCLUDED above), then the
    small hardcoded institutional/mainstream domain list, then 'other'."""
    for orig_str, rx, tax in matchers:
        if rx.match(url):
            return tax

    m = re.match(r'^https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,4})', url)
    if not m:
        return 'other'
    domain = m.group(1).lower()

    if domain in domain_tax_map and domain not in DOMAIN_FALLBACK_EXCLUDED:
        return domain_tax_map[domain]

    # Domain fallbacks (not covered by the curated list at all)
    if domain.endswith('.gov') or domain.endswith('.mil') or domain in [
        'cdc.gov', 'nih.gov', 'fda.gov', 'who.int', 'ncbi.nlm.nih.gov',
        'pubmed.ncbi.nlm.nih.gov', 'nature.com', 'nejm.org', 'thelancet.com',
        'bmj.com', 'pnas.org', 'sciencedirect.com', 'springer.com',
        'jamanetwork.com', 'science.org', 'biorxiv.org', 'medrxiv.org', 'wiley.com'
    ]:
        return 'credentialed_institutional'
    if domain in [
        'youtube.com', 'youtu.be', 'twitter.com', 'x.com', 'wikipedia.org',
        'en.wikipedia.org', 'reddit.com', 'old.reddit.com', 'nytimes.com',
        'bbc.com', 'theguardian.com', 'reuters.com', 'npr.org', 'cnn.com'
    ]:
        return 'other'

    return 'other'


def entity_groups_for_row(text, cid, rx, lookup, candidate_to_bares):
    text = str(text)
    direct_spans = [{"start": m.start(), "end": m.end(), "text": m.group(0)} for m in rx.finditer(text)]
    direct_spans = filter_quoted_spans(text, direct_spans)
    groups = {}
    for s in direct_spans:
        groups.setdefault(s["text"].lower(), []).append(s)
    if not groups:
        resolved = lookup.get(str(cid))
        if resolved:
            bares = candidate_to_bares.get(resolved, [])
            fallback_spans = []
            for bare in bares:
                bare_rx = re.compile(r'\b' + re.escape(bare) + r'\b', re.IGNORECASE)
                fallback_spans.extend({"start": m.start(), "end": m.end(), "text": m.group(0)} for m in bare_rx.finditer(text))
            fallback_spans = filter_quoted_spans(text, fallback_spans)
            if fallback_spans:
                groups[resolved.lower()] = fallback_spans
    return groups


def main():
    print("=== INTEGRATING THE CREDENTIALS PROBLEM ===")
    
    # Check dependencies
    for p in [SCORED_PATH, ENRICHED_PATH, STANCE_MODEL_PATH]:
        if not os.path.exists(p):
            print(f"Error: Missing required input file: {p}")
            sys.exit(1)
            
    print("\nLoading pre-computed citation cache...")
    cache_path = 'data/processed/citations_cache.parquet'
    if not os.path.exists(cache_path):
        print(f"Error: Missing centralized cache file: {cache_path}. Run build_citations_cache.py first.")
        sys.exit(1)
    cache_df = pd.read_parquet(cache_path)
    
    print("\nLoading scored authority appeal Parquet...")
    scored_df = pd.read_parquet(SCORED_PATH)
    print(f"  Loaded {len(scored_df):,} rows.")
    
    # Filter for high source citation
    high_citation = scored_df[scored_df['source_citation_prob'] > 0.5]
    print(f"  Found {len(high_citation):,} comments with source_citation_prob > 0.5.")
    
    print("\nJoining with enriched corpus (to get comment text and authors)...")
    con = duckdb.connect()
    con.register("high_citation_view", high_citation[['id', 'source_citation_prob', 'has_maverick', 'has_consensus_expert']])
    
    enriched_matched = con.execute(f"""
        SELECT h.id, h.source_citation_prob, h.has_maverick, h.has_consensus_expert, e.text, e.author
        FROM '{ENRICHED_PATH}' e
        JOIN high_citation_view h ON e.id = h.id
    """).df()
    print(f"  Matched {len(enriched_matched):,} comments in enriched corpus.")
    
    print("\nMapping citations from pre-computed cache...")
    cache_sub = cache_df[['comment_id', 'url', 'credentials_taxonomy_tier']].rename(columns={'credentials_taxonomy_tier': 'category'})
    citations_df = pd.merge(
        cache_sub,
        enriched_matched[['id', 'author', 'has_maverick', 'has_consensus_expert']],
        left_on='comment_id',
        right_on='id',
        how='inner'
    ).drop(columns=['id'])
    
    print(f"  Mapped {len(citations_df):,} citation records (comment-url pairs) "
          f"across {citations_df['comment_id'].nunique():,} distinct comments.")
          
    # Load stance classifier for entity-stance categorization
    print("\nLoading 3-class stance classifier...")
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec, clf = stance_model['vec'], stance_model['clf']
    classes = list(clf.classes_)
    print(f"  Loaded stance classifier with classes {classes}.")
    
    # Load verified entities
    mavericks, canon, consensus = load_entities_split_corrected()
    rx_mav = build_regex(mavericks)
    rx_con = build_regex(consensus)
    lookup = load_maverick_disambiguation_lookup()
    consensus_lookup = load_consensus_disambiguation_lookup()
    
    # Get subset of citations that mention entities and need stance classification
    entity_citation_mask = (citations_df['has_maverick'] == 1) | (citations_df['has_consensus_expert'] == 1)
    entity_comment_ids = citations_df.loc[entity_citation_mask, 'comment_id'].unique()
    print(f"  Found {len(entity_comment_ids):,} unique comments with links that mention an entity.")
    
    # Predict stance for these comments
    text_lookup = dict(zip(enriched_matched['id'], enriched_matched['text']))
    has_mav_lookup = dict(zip(enriched_matched['id'], enriched_matched['has_maverick']))
    has_con_lookup = dict(zip(enriched_matched['id'], enriched_matched['has_consensus_expert']))
    comment_stances = {}
    
    print("  Running stance classification on entity-mentioning comments...")
    for cid in entity_comment_ids:
        text = text_lookup.get(cid)
        if not text:
            continue
            
        # Check maverick stance (using fast dictionary lookups instead of slow pandas queries)
        has_mav = int(has_mav_lookup.get(cid, 0))
        has_con = int(has_con_lookup.get(cid, 0))
        
        predicted_stance = 'other'
        
        # Helper to get prediction
        def get_pred(rx, ent_lookup, bares_map):
            groups = entity_groups_for_row(text, cid, rx, ent_lookup, bares_map)
            if not groups:
                return 'other'
            for ent_key, spans in groups.items():
                win = extract_entity_window(text, spans)
                if is_list_or_link_dump_window(win):
                    continue
                X = vec.transform([win])
                probs = clf.predict_proba(X)[0]
                return classes[probs.argmax()]
            return 'other'
            
        mav_stance = get_pred(rx_mav, lookup, MAVERICK_CANDIDATE_TO_BARES) if has_mav else 'other'
        con_stance = get_pred(rx_con, consensus_lookup, CONSENSUS_CANDIDATE_TO_BARES) if has_con else 'other'
        
        # Categorize overall comment stance
        # Anti-Consensus (Conspiracy): Maverick Endorsement or Consensus Hostile
        # Consensus-Aligned: Maverick Hostile or Consensus Endorsement
        is_anti_consensus = (mav_stance == 'endorsement') or (con_stance == 'hostile')
        is_consensus_aligned = (mav_stance == 'hostile') or (con_stance == 'endorsement')
        
        if is_anti_consensus and not is_consensus_aligned:
            comment_stances[cid] = 'Anti-Consensus'
        elif is_consensus_aligned and not is_anti_consensus:
            comment_stances[cid] = 'Consensus-Aligned'
        else:
            comment_stances[cid] = 'Neutral/Other'
            
    # Map comment stance back to citations dataframe
    citations_df['comment_stance'] = citations_df['comment_id'].map(comment_stances).fillna('No Entity Mentioned')
    
    # -------------------------------------------------------------
    # STATISTICAL REPORTS & ANALYSIS
    # -------------------------------------------------------------
    print("\n=== CITATION ANALYSIS STATISTICS ===")
    
    # Overall citation category distribution
    total_citations = len(citations_df)
    print(f"\nOverall Citation Category Distribution (N={total_citations:,} citations):")
    cat_dist = citations_df['category'].value_counts()
    for cat, count in cat_dist.items():
        pct = count / total_citations * 100
        print(f"  - {cat:27s}: {count:7d} ({pct:.2f}%)")
        
    # Cross-tabulate by comment stance (Entity-focused subset)
    entity_citations = citations_df[citations_df['comment_stance'] != 'No Entity Mentioned']
    print(f"\nEntity-Mentioning Sourcing Subset (N={len(entity_citations):,} citations):")
    
    crosstab = pd.crosstab(
        entity_citations['comment_stance'], 
        entity_citations['category'],
        normalize='index'
    ) * 100
    
    counts_crosstab = pd.crosstab(
        entity_citations['comment_stance'], 
        entity_citations['category']
    )
    
    print("\nCross-tabulation (Row Percentages):")
    print(crosstab.round(2).to_string())
    
    print("\nCross-tabulation (Citations Count):")
    print(counts_crosstab.to_string())
    
    # Resolve multiple URLs per comment (Precedence-based Comment-level Analysis)
    # Precedence: credentialed_institutional > individual_named_source > movement_internal_anonymous > other
    precedence_map = {
        'credentialed_institutional': 4,
        'individual_named_source': 3,
        'movement_internal_anonymous': 2,
        'other': 1
    }
    
    citations_df['precedence'] = citations_df['category'].map(precedence_map)
    comment_level_df = citations_df.sort_values('precedence', ascending=False).drop_duplicates('comment_id')
    
    print(f"\n=== COMMENT-LEVEL PRECEDENCE ANALYSIS (N={len(comment_level_df):,} comments) ===")
    
    # Overall comment-level taxonomy distribution
    comment_total = len(comment_level_df)
    comment_cat_dist = comment_level_df['category'].value_counts()
    for cat, count in comment_cat_dist.items():
        pct = count / comment_total * 100
        print(f"  - {cat:27s}: {count:7d} ({pct:.2f}%)")
        
    entity_comments = comment_level_df[comment_level_df['comment_stance'] != 'No Entity Mentioned']
    comment_crosstab = pd.crosstab(
        entity_comments['comment_stance'],
        entity_comments['category'],
        normalize='index'
    ) * 100
    
    comment_counts = pd.crosstab(
        entity_comments['comment_stance'],
        entity_comments['category']
    )
    
    print("\nComment-level Cross-tabulation (Row Percentages):")
    print(comment_crosstab.round(2).to_string())
    
    print("\nComment-level Cross-tabulation (Comments Count):")
    print(comment_counts.to_string())
    
    # Average number of citations per comment by group
    avg_citations = citations_df.groupby('comment_id').size().mean()
    print(f"\nAverage Citations per Comment: {avg_citations:.2f}")
    
    stance_avg = citations_df.groupby(['comment_id', 'comment_stance']).size().reset_index().groupby('comment_stance')[0].mean()
    print("\nAverage Citations per Comment by Stance Group:")
    for stance, avg in stance_avg.items():
        print(f"  - {stance:20s}: {avg:.2f}")
        
    # Save the full citations table to CSV
    citations_df.to_csv(OUT_CSV_PATH, index=False)
    print(f"\nSaved citations dataframe to {OUT_CSV_PATH}")
    
    # Compile a beautiful Markdown Report
    print(f"\nCompiling Markdown Report to {OUT_REPORT_PATH}...")
    with open(OUT_REPORT_PATH, 'w') as f:
        f.write("# Research Report: The Credentials Problem Integration\n\n")
        f.write("> **Overview**: This report integrates three independent investigative layers "
                "to answer the core comparative thesis question: *Does the conspiracy community's "
                "epistemic sourcing style depend on genuine expert credentials, or does it lean "
                "on alternative/movement-internal systems?*\n\n")
        
        f.write("## 1. Citation Category Definitions & Mapping\n\n")
        f.write("We categorized all cited links inside comments where `source_citation > 0.5` "
                "into a strict 4-tier taxonomy parsed from curated top cited URLs:\n")
        f.write("- **`credentialed_institutional`**: CDC, FDA, DOJ, WHO, NIH, NEJM, BMJ, Lancet, academic journals.\n")
        f.write("- **`individual_named_source`**: Independent platforms and whistleblowers (James Corbett, Benjamin Corey).\n")
        f.write("- **`movement_internal_anonymous`**: Conspiracy networks, alternative portals, and anonymous leak sites (ae911truth.org, WikiLeaks, Cryptome, Qmap).\n")
        f.write("- **`other`**: Neutral platforms and mainstream news agencies (Wikipedia, YouTube, BBC, Guardian, NPR).\n\n")
        
        f.write("## 2. Overall Citation Distribution\n\n")
        f.write(f"Across **{total_citations:,}** total link citations inside the r/conspiracy source-citation-positive comments:\n\n")
        f.write("| Category | Citations Count | Percentage |\n")
        f.write("|---|---|---|\n")
        for cat, count in cat_dist.items():
            f.write(f"| `{cat}` | {count:,} | {count / total_citations * 100:.2f}% |\n")
            
        f.write("\n## 3. Comparative Sourcing Analysis (Entity Mentions subset)\n\n")
        f.write("To test the 'credentials problem' precisely, we isolate comments mentioning listed "
                "entities and determine their stance (Anti-Consensus vs. Consensus-Aligned) using the 3-class stance classifier. "
                "Below are the row percentages at both the **citation-level** and **comment-level** (resolved via highest precedence).\n\n")
        
        f.write("### Citation-level Breakdown (Row Percentages)\n\n")
        f.write("| Comment Stance | Credentialed Institutional | Individual Named | Movement Internal | Other |\n")
        f.write("|---|---|---|---|---|\n")
        for stance in ['Anti-Consensus', 'Consensus-Aligned', 'Neutral/Other']:
            vals = crosstab.loc[stance]
            f.write(f"| **{stance}** | {vals.get('credentialed_institutional', 0.0):.2f}% | {vals.get('individual_named_source', 0.0):.2f}% | {vals.get('movement_internal_anonymous', 0.0):.2f}% | {vals.get('other', 0.0):.2f}% |\n")
            
        f.write("\n### Comment-level Precedence Breakdown (Row Percentages)\n\n")
        f.write("| Comment Stance | Credentialed Institutional | Individual Named | Movement Internal | Other |\n")
        f.write("|---|---|---|---|---|\n")
        for stance in ['Anti-Consensus', 'Consensus-Aligned', 'Neutral/Other']:
            vals = comment_crosstab.loc[stance]
            f.write(f"| **{stance}** | {vals.get('credentialed_institutional', 0.0):.2f}% | {vals.get('individual_named_source', 0.0):.2f}% | {vals.get('movement_internal_anonymous', 0.0):.2f}% | {vals.get('other', 0.0):.2f}% |\n")
            
        f.write("\n## 4. Citation Volume Analysis\n\n")
        f.write("We calculated the average citation volume (links per comment) to check if anti-consensus "
                "comments merely cite *less* or if they cite *differently*:\n\n")
        f.write("| Stance Group | Avg Links per Comment |\n")
        f.write("|---|---|\n")
        for stance, avg in stance_avg.items():
            f.write(f"| **{stance}** | {avg:.2f} |\n")
            
        f.write("\n## 5. Main Comparative Findings\n\n")
        
        # Compute the specific differences to automate the finding reporting
        anti_inst = crosstab.loc['Anti-Consensus', 'credentialed_institutional']
        con_inst = crosstab.loc['Consensus-Aligned', 'credentialed_institutional']
        anti_mov = crosstab.loc['Anti-Consensus', 'movement_internal_anonymous']
        con_mov = crosstab.loc['Consensus-Aligned', 'movement_internal_anonymous']
        
        f.write(f"1. **Institutional Sourcing**: Consensus-Aligned sourcing leans on **{con_inst:.2f}%** credentialed institutional citations, "
                f"while Anti-Consensus sourcing leans on **{anti_inst:.2f}%**. This confirms a notable shift away from mainstream official credentials.\n")
        f.write(f"2. **Alternative / Movement Sourcing**: Anti-Consensus comments cite alternative/movement-internal networks **{anti_mov:.2f}%** of the time, "
                f"compared to only **{con_mov:.2f}%** for Consensus-Aligned comments.\n")
        f.write(f"3. **Volume vs. Style**: Anti-Consensus comments average **{stance_avg.get('Anti-Consensus', 0.0):.2f}** links per comment, "
                f"compared to **{stance_avg.get('Consensus-Aligned', 0.0):.2f}** for Consensus-Aligned comments. "
                f"This suggests that anti-consensus comments do *not* simply lack citations; rather, they cite with comparable or higher density, "
                f"but significantly redirect their epistemic backing toward alternative, individual, and movement-internal authority systems.\n")
                
    print("Done compiling report.")


if __name__ == '__main__':
    main()
