"""reclassify_credentials_citations.py

Cheap fix-application pass over the ALREADY-EXTRACTED citations from
integrate_credentials_problem.py's original run (data/processed/
credentials_integration_results.csv, 4,568,747 rows) -- reapplies the
2026-07-22 classify_url()/build_taxonomy_matchers() domain-fallback fix
(see integrate_credentials_problem.py's module docstring) WITHOUT
re-scanning the corpus or re-running entity-stance model scoring.

Why this exists rather than just rerunning integrate_credentials_problem.py
end to end: that script's per-comment Anti-Consensus/Consensus-Aligned
stance labeling (`comment_stance`) is a SEPARATE, independent computation
from URL categorization -- it re-scores every entity-mentioning comment
from scratch with the stance classifier, and is completely unaffected by
the classify_url() bug fix. Rerunning the whole script would have redone
that expensive, unrelated step for no reason (caught mid-run and killed
2026-07-22 -- see conversation). `comment_stance` is reused as-is from
the original output; only `category` (and the `precedence` derived from
it) gets recomputed here.

Speed: classify_url() tries up to 139 exact-URL regexes before falling
back to the domain map. Naively running that for all 4.57M citations
would mean ~4.57M x up to 139 regex attempts. Since only a citation whose
DOMAIN appears among the 139 curated URLs' domains could possibly match
one of those regexes, this groups matchers by domain up front and only
runs the (usually 1-3) regexes relevant to a citation's own domain --
skipping the other ~136+ irrelevant regexes entirely for the other
~99.9% of domains.

Output: overwrites data/processed/credentials_integration_results.csv
and data/processed/credentials_problem_integration_report.md in place
(same filenames as the original run, this IS the corrected version).
"""
import os
import re
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from integrate_credentials_problem import parse_curated_urls, build_taxonomy_matchers

RESULTS_PATH = 'data/processed/credentials_integration_results.csv'
OUT_CSV_PATH = RESULTS_PATH
OUT_REPORT_PATH = 'data/processed/credentials_problem_integration_report.md'

PRECEDENCE_MAP = {
    'credentialed_institutional': 4,
    'individual_named_source': 3,
    'movement_internal_anonymous': 2,
    'other': 1,
}


def build_domain_indexed_matchers(matchers):
    """Groups the 139 exact-URL regex matchers by the domain they belong
    to, so classify_fast() only needs to try the handful relevant to a
    given citation's own domain instead of all 139 every time."""
    by_domain = {}
    for orig_str, rx, tax in matchers:
        domain_token = re.split(r'[\s/]', orig_str.strip(), maxsplit=1)[0].lower()
        domain_token = re.sub(r'^www\.', '', domain_token)
        by_domain.setdefault(domain_token, []).append((rx, tax))
    return by_domain


DOMAIN_RE = re.compile(r'^https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,4})')

HARDCODED_INSTITUTIONAL = {
    'cdc.gov', 'nih.gov', 'fda.gov', 'who.int', 'ncbi.nlm.nih.gov',
    'pubmed.ncbi.nlm.nih.gov', 'nature.com', 'nejm.org', 'thelancet.com',
    'bmj.com', 'pnas.org', 'sciencedirect.com', 'springer.com',
    'jamanetwork.com', 'science.org', 'biorxiv.org', 'medrxiv.org', 'wiley.com',
}
HARDCODED_OTHER = {
    'youtube.com', 'youtu.be', 'twitter.com', 'x.com', 'wikipedia.org',
    'en.wikipedia.org', 'reddit.com', 'old.reddit.com', 'nytimes.com',
    'bbc.com', 'theguardian.com', 'reuters.com', 'npr.org', 'cnn.com',
}

# 2026-07-22: domain-level fallback over-generalized for general-purpose
# multi-topic platforms/publishers where the curated row(s) happened to
# tag ONE specific article, not the whole site's character -- confirmed
# via credentials_integration_results.csv reclassification: reddit.com
# alone accounted for 1,551,155 of the ~1.6M citations moved out of
# 'other' (from 2 curated conspiracy-subforum pages generalizing to
# EVERY subreddit on the platform), businessinsider.com (11,120) and
# usatoday.com (7,957) similarly generalized from one flagged article
# each. These fall back to exact-page-match only (their original
# behavior), pending real per-domain review -- not auto-decided here,
# same guardrail-against-guesswork principle as the original curation.
# documentcloud.org deliberately NOT excluded (Nash's call, 2026-07-22):
# plausibly has a genuinely specific, non-generic role in this corpus
# (a document-hosting platform specific documents get repeatedly cited
# from) -- worth a targeted look at which documents dominate rather than
# a blanket revert either way. See explore_documentcloud_citations.py.
DOMAIN_FALLBACK_EXCLUDED = {'reddit.com', 'np.reddit.com', 'old.reddit.com', 'businessinsider.com', 'usatoday.com', 'cia.gov', 'assets.documentcloud.org'}


def classify_fast(url, matchers_by_domain, domain_tax_map):
    m = DOMAIN_RE.match(url)
    if not m:
        return 'other'
    domain = m.group(1).lower()

    for rx, tax in matchers_by_domain.get(domain, []):
        if rx.match(url):
            return tax

    if domain in domain_tax_map and domain not in DOMAIN_FALLBACK_EXCLUDED:
        return domain_tax_map[domain]
    if domain.endswith('.gov') or domain.endswith('.mil') or domain in HARDCODED_INSTITUTIONAL:
        return 'credentialed_institutional'
    if domain in HARDCODED_OTHER:
        return 'other'
    return 'other'


def main():
    print("=== Reclassifying existing citations with the fixed domain-fallback taxonomy ===")

    curated_rows = parse_curated_urls()
    matchers, domain_tax_map = build_taxonomy_matchers(curated_rows)
    matchers_by_domain = build_domain_indexed_matchers(matchers)
    print(f"  {len(curated_rows)} curated rows, {len(domain_tax_map)} curated domains, "
          f"{len(matchers_by_domain)} domains with page-level regexes.")

    print(f"\nLoading existing citations from {RESULTS_PATH} (this is the expensive-to-rebuild part, reused as-is)...")
    citations_df = pd.read_csv(RESULTS_PATH)
    print(f"  Loaded {len(citations_df):,} citation rows.")

    old_cat_dist = citations_df['category'].value_counts()
    print("\nOld category distribution (buggy exact-match-only classifier):")
    print(old_cat_dist.to_string())

    print("\nReclassifying URLs (domain-indexed, no model scoring)...")
    citations_df['category'] = citations_df['url'].map(
        lambda u: classify_fast(u, matchers_by_domain, domain_tax_map)
    )

    new_cat_dist = citations_df['category'].value_counts()
    print("\nNew category distribution (fixed domain-fallback classifier):")
    print(new_cat_dist.to_string())

    moved = (old_cat_dist.get('other', 0) - new_cat_dist.get('other', 0))
    print(f"\nCitations moved OUT of 'other': {moved:,}")

    citations_df['precedence'] = citations_df['category'].map(PRECEDENCE_MAP)

    total_citations = len(citations_df)
    cat_dist = citations_df['category'].value_counts()

    entity_citations = citations_df[citations_df['comment_stance'] != 'No Entity Mentioned']
    crosstab = pd.crosstab(entity_citations['comment_stance'], entity_citations['category'], normalize='index') * 100

    comment_level_df = citations_df.sort_values('precedence', ascending=False).drop_duplicates('comment_id')
    entity_comments = comment_level_df[comment_level_df['comment_stance'] != 'No Entity Mentioned']
    comment_crosstab = pd.crosstab(entity_comments['comment_stance'], entity_comments['category'], normalize='index') * 100

    stance_avg = citations_df.groupby(['comment_id', 'comment_stance']).size().reset_index().groupby('comment_stance')[0].mean()

    print(f"\nSaving corrected citations to {OUT_CSV_PATH}...")
    citations_df.to_csv(OUT_CSV_PATH, index=False)

    print(f"Compiling corrected Markdown Report to {OUT_REPORT_PATH}...")
    with open(OUT_REPORT_PATH, 'w') as f:
        f.write("# Research Report: The Credentials Problem Integration\n\n")
        f.write("> **Overview**: This report integrates three independent investigative layers "
                "to answer the core comparative thesis question: *Does the conspiracy community's "
                "epistemic sourcing style depend on genuine expert credentials, or does it lean "
                "on alternative/movement-internal systems?*\n\n")
        f.write("> **2026-07-22 fix**: `classify_url()` now falls back to a curated-DOMAIN map "
                "(not just the 139 exact curated pages) before defaulting to `other` -- this moved "
                f"**{moved:,}** citations out of `other` into their already-curated domain's category "
                "(e.g. any corbettreport.com page, not just the one literal curated URL). "
                "`comment_stance` (Anti-Consensus/Consensus-Aligned) is unchanged from the original "
                "run -- that labeling doesn't depend on URL categorization. See `reclassify_credentials_citations.py`.\n\n")

        f.write("## 1. Citation Category Definitions & Mapping\n\n")
        f.write("We categorized all cited links inside comments where `source_citation > 0.5` "
                "into a strict 4-tier taxonomy parsed from curated top cited URLs (page-level "
                "matches, then curated-domain fallback, then a small hardcoded institutional/mainstream "
                "domain list, then `other`):\n")
        f.write("- **`credentialed_institutional`**: CDC, FDA, DOJ, WHO, NIH, NEJM, BMJ, Lancet, academic journals.\n")
        f.write("- **`individual_named_source`**: Independent platforms and whistleblowers (James Corbett, Benjamin Corey).\n")
        f.write("- **`movement_internal_anonymous`**: Conspiracy networks, alternative portals, and anonymous leak sites (ae911truth.org, WikiLeaks, Cryptome, Qmap).\n")
        f.write("- **`other`**: mainstream news agencies / generic platforms (Wikipedia, YouTube, BBC, Guardian, NPR), "
                "**and any domain not yet reviewed at all** -- this bucket is NOT verified-neutral, "
                "it is the default for anything outside the curated list (see `explore_other_bucket_domains.py`).\n\n")

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
        f.write("| Stance Group | Avg Links per Comment |\n")
        f.write("|---|---|\n")
        for stance, avg in stance_avg.items():
            f.write(f"| **{stance}** | {avg:.2f} |\n")

        f.write("\n## 5. Main Comparative Findings\n\n")
        anti_inst = crosstab.loc['Anti-Consensus', 'credentialed_institutional']
        con_inst = crosstab.loc['Consensus-Aligned', 'credentialed_institutional']
        anti_mov = crosstab.loc['Anti-Consensus', 'movement_internal_anonymous']
        con_mov = crosstab.loc['Consensus-Aligned', 'movement_internal_anonymous']
        f.write(f"1. **Institutional Sourcing**: Consensus-Aligned sourcing leans on **{con_inst:.2f}%** credentialed institutional citations, "
                f"while Anti-Consensus sourcing leans on **{anti_inst:.2f}%**. (No significance test run yet -- treat as descriptive.)\n")
        f.write(f"2. **Alternative / Movement Sourcing**: Anti-Consensus comments cite alternative/movement-internal networks **{anti_mov:.2f}%** of the time, "
                f"compared to **{con_mov:.2f}%** for Consensus-Aligned comments.\n")
        f.write(f"3. **Volume vs. Style**: Anti-Consensus comments average **{stance_avg.get('Anti-Consensus', 0.0):.2f}** links per comment, "
                f"compared to **{stance_avg.get('Consensus-Aligned', 0.0):.2f}** for Consensus-Aligned comments.\n")

    print("Done.")


if __name__ == "__main__":
    main()
