"""rank_cited_urls_by_author.py

Step 1 of the "credentials problem" content/authorship investigation
(Nash's redirect from domain-level analysis to specific pieces of
content and their authors -- articles, papers, lectures that get cited
repeatedly, sometimes via different URLs). Bottom-up, frequency-first,
mirroring how the maverick/consensus entity lists themselves were
actually built (corpus-frequency ranking, then hand-curated) rather than
trying to automate content-identity resolution or author attribution
from scratch.

Key design choice: rank by DISTINCT AUTHOR COUNT, not raw mention count.
This structurally solves the despam problem Nash raised -- one person
posting the same link 50 times across threads (see the Ok_Cartographer_6947
copypasta case found earlier this session, confirmed via corpus lookup:
same text, 5 different threads, 3-minute window) counts once toward
"distinct authors," while genuine independent citation by many different
people accumulates. Raw mention count and total/mean upvotes are reported
alongside so a spam-heavy-but-still-upvoted link (which Nash noted could
still be real signal) is visible, not silently discarded -- this script
doesn't decide what's signal vs noise, it surfaces both angles for
human review.

Source population: research_corpus_enriched.parquet (4.78M rows) -- safe
to use here despite being built for source_citation/appeal_to_authority
originally, since its filter (evidence_count>0 OR has_link=1 OR
alt_authority_count>0 OR quantitative_count>0) is an OR that already
includes every has_link=1 row, so no linked comment is excluded.

Output: data/processed/cited_urls_ranked.csv -- every URL that appears,
ranked by distinct author count, for manual review/curation (Step 2:
hand-identify what the top items actually are and who authored them,
same pattern as the entity-list curation).
"""
import os
import re
import sys
import pandas as pd
import duckdb

ENRICHED_PATH = 'data/processed/research_corpus_enriched.parquet'
EMPATH_PATH = 'data/processed/empath_scores_full.parquet'
OUT_PATH = 'data/processed/cited_urls_ranked.csv'

URL_PATTERN = r'https?://[^\s\]\>"\']+'
TRAILING_PUNCT = re.compile(r'[.,;:!?\'"\]]+$')


def strip_unbalanced_trailing_paren(u):
    """FIX: the first version excluded ')' entirely from the URL character
    class to avoid grabbing markdown-link closing parens, e.g.
    "[text](https://example.com)" -- but that truncated URLs that
    legitimately CONTAIN parens in their own path, like Lancet PII codes
    (PIIS0140-6736(20)32656-8) and some Wikipedia disambiguation pages,
    silently merging genuinely different articles under one truncated,
    wrong identity. Fixed by allowing ')' in the match, then only
    stripping trailing ')' characters that are genuinely unbalanced
    (more closes than opens) -- a real markdown-artifact close, not part
    of the URL's own content."""
    while u.endswith(')') and u.count(')') > u.count('('):
        u = u[:-1]
    return u


def normalize_url(u):
    """FIX (Nash's feedback): the first version ranked http:// and https://
    variants of the same URL as separate rows (ae911truth.org split
    139/116 authors instead of combining to its true reach), same for a
    trailing slash on an otherwise-identical URL. Normalizes: force
    https, strip a bare trailing slash (but not slashes that are part of
    a real path), lowercase the domain only (not the path -- paths can be
    legitimately case-sensitive)."""
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
        u = TRAILING_PUNCT.sub('', u)  # a stripped paren can expose more trailing punctuation
        if len(u) > 15:  # drop degenerate matches
            cleaned.append(normalize_url(u))
    return cleaned


def main():
    print("=== Ranking cited URLs by distinct-author count (despam-by-construction) ===")

    print(f"Loading {ENRICHED_PATH}...")
    df = pd.read_parquet(ENRICHED_PATH, columns=['id', 'author', 'text'])
    print(f"  Loaded {len(df):,} rows.")

    print("Fetching upvotes for these ids (not in the enriched parquet)...")
    con = duckdb.connect()
    con.register("ids_view", df[['id']])
    upvotes_df = con.execute(f"""
        SELECT e.id, e.upvotes
        FROM '{EMPATH_PATH}' e
        JOIN ids_view n ON e.id = n.id
    """).df()
    upvotes_lookup = dict(zip(upvotes_df['id'], upvotes_df['upvotes']))
    df['upvotes'] = df['id'].map(upvotes_lookup).fillna(0)

    print("Extracting URLs from text...")
    records = []
    for row_id, author, text, upvotes in zip(df['id'], df['author'], df['text'], df['upvotes']):
        urls = extract_urls(text)
        for u in set(urls):  # dedupe within a single comment (e.g. same link posted twice in one comment)
            records.append({'url': u, 'id': row_id, 'author': author, 'upvotes': upvotes})

    print(f"  Extracted {len(records):,} (comment, url) pairs, "
          f"{len(set(r['url'] for r in records)):,} distinct URLs.")

    long_df = pd.DataFrame(records)

    print("Aggregating per URL...")
    agg = long_df.groupby('url').agg(
        distinct_authors=('author', 'nunique'),
        mention_count=('id', 'count'),
        total_upvotes=('upvotes', 'sum'),
        mean_upvotes=('upvotes', 'mean'),
        max_upvotes=('upvotes', 'max'),
    ).reset_index()
    agg['mentions_per_author'] = agg['mention_count'] / agg['distinct_authors']
    agg = agg.sort_values('distinct_authors', ascending=False)

    agg.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(agg):,} ranked URLs to {OUT_PATH}")

    print("\n=== Top 50 URLs by distinct author count ===")
    pd.set_option('display.max_colwidth', 80)
    print(agg.head(50).to_string(index=False))

    print("\n=== Sanity check: high mention_count but LOW distinct_authors (likely spam) ===")
    likely_spam = agg[(agg['mention_count'] >= 10) & (agg['mentions_per_author'] >= 5)].sort_values('mention_count', ascending=False)
    print(f"{len(likely_spam):,} URLs match this pattern (mention_count>=10, avg >=5 mentions/author)")
    print(likely_spam.head(20).to_string(index=False))

    print("\nDone.")


if __name__ == "__main__":
    main()
