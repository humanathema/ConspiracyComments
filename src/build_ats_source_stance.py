"""build_ats_source_stance.py

ATS port of build_source_stance.py -- extends the SAME already-trained,
already-validated two-stage cascade stance classifier (the entity-stance
model, reused verbatim, no new labeling) to cited domains/URLs in the ATS
corpus, mirroring the reddit-side source-stance analysis.

Reuses build_source_stance.py's own window-extraction/scoring functions
directly (find_url_spans, score_windows_cascade, summarize) rather than
reimplementing them -- only the input schema (post_id/body instead of
comment_id/text) and target-list construction differ.

Simplified vs the reddit pipeline in one deliberate way, called out here
rather than silently: reddit's domain/URL target lists come from a
hand-curated quality rollup (domain_source_quality_rollup.csv) and an
author-distinct URL ranking (cited_urls_ranked.csv) -- building ATS
equivalents of those would need real analyst review time (see the 2026-07-28
audit: reddit's own curated layer covers well under 1% of citation volume).
This script instead uses the freshly-rebuilt ats_citations_cache.parquet's
raw mention counts directly as the target-selection criterion (domains with
>=20 mentions; top 2000 URLs by mention count, not distinct-author count,
since ATS's cache doesn't carry author per citation) -- a lower bar than
reddit's, appropriate for a first pass, not a substitute for real curation.

Outputs:
  data/processed/ats_source_mentions_cache.parquet
  data/processed/ats_domain_stance_breakdown.csv
  data/processed/ats_url_stance_breakdown.csv
"""
import os
import sys

import joblib
import pandas as pd
import duckdb

sys.path.insert(0, os.path.dirname(__file__))
from build_source_stance import score_windows_cascade, find_url_spans, summarize
from stance_window_utils import extract_entity_window, is_list_or_link_dump_window, filter_quoted_spans

STANCE_MODEL_PATH = 'data/processed/stance_classifier_2stage_pooled.joblib'
CITATIONS_PATH = 'data/processed/ats_citations_cache.parquet'
CORPUS_PATH = 'data/processed/ats_comments_final.parquet'

OUT_PARQUET = 'data/processed/ats_source_mentions_cache.parquet'
OUT_DOMAIN_BREAKDOWN = 'data/processed/ats_domain_stance_breakdown.csv'
OUT_URL_BREAKDOWN = 'data/processed/ats_url_stance_breakdown.csv'

MIN_DOMAIN_MENTIONS = 20
TOP_N_URLS = 2000
MIN_MENTIONS_TO_REPORT = 20


def main():
    print("=== ATS source (domain/URL) stance cache ===")

    if not os.path.exists(STANCE_MODEL_PATH):
        print(f"MISSING STANCE MODEL: {STANCE_MODEL_PATH}. Train it first.")
        sys.exit(1)

    print("Loading two-stage cascade model (same model used for reddit + ATS entity stance)...")
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec = stance_model['vec']
    clf_stage1, clf_stage2 = stance_model['clf_stage1'], stance_model['clf_stage2']
    print(f"Loaded model successfully (CV kappa={stance_model['cv_kappa_end_to_end']:.3f})")

    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='4GB'")

    print("\nBuilding target domain/URL lists from ats_citations_cache.parquet mention counts...")
    domain_counts = con.execute(f"""
        SELECT domain, count(*) as n FROM '{CITATIONS_PATH}' GROUP BY domain HAVING count(*) >= {MIN_DOMAIN_MENTIONS}
    """).df()
    url_counts = con.execute(f"""
        SELECT url, count(*) as n FROM '{CITATIONS_PATH}' GROUP BY url ORDER BY n DESC LIMIT {TOP_N_URLS}
    """).df()
    print(f"  {len(domain_counts):,} domains with >={MIN_DOMAIN_MENTIONS} mentions, "
          f"top {len(url_counts):,} URLs by mention count.")

    target_domains = set(domain_counts['domain'])
    target_urls = set(url_counts['url'])

    print("\nFetching matching comment text for target citations...")
    citations = con.execute(f"""
        SELECT DISTINCT c.comment_id, c.url, c.domain
        FROM '{CITATIONS_PATH}' c
    """).df()
    citations = citations[citations['domain'].isin(target_domains) | citations['url'].isin(target_urls)]
    print(f"  {len(citations):,} (comment, url) citation rows to window/score.")

    body_lookup = con.execute(f"""
        SELECT post_id AS comment_id, body AS text FROM '{CORPUS_PATH}'
        WHERE post_id IN (SELECT DISTINCT comment_id FROM citations)
    """).df() if False else None
    # DuckDB can't see the python-local `citations` df via SQL scan without registering it;
    # register explicitly instead.
    con.register('citations_df', citations)
    body_lookup = con.execute(f"""
        SELECT c.comment_id, c.url, c.domain, e.body AS text
        FROM citations_df c
        JOIN '{CORPUS_PATH}' e ON e.post_id = c.comment_id
    """).df()
    print(f"  Resolved text for {len(body_lookup):,} citation rows.")

    print("\nRelocating citation spans and extracting +-15-word windows...")
    rows_to_score = []
    for row in body_lookup.itertuples(index=False):
        text = row.text
        spans = find_url_spans(text, row.url)
        spans = filter_quoted_spans(text, spans)
        if not spans:
            continue
        win = extract_entity_window(text, spans)
        is_dump = is_list_or_link_dump_window(win)
        if row.domain in target_domains:
            rows_to_score.append({
                'comment_id': row.comment_id, 'source_key': row.domain, 'level': 'domain',
                'window_text': win, 'is_list_dump': is_dump,
            })
        if row.url in target_urls:
            rows_to_score.append({
                'comment_id': row.comment_id, 'source_key': row.url, 'level': 'url',
                'window_text': win, 'is_list_dump': is_dump,
            })

    df_scored = pd.DataFrame(rows_to_score)
    print(f"Extracted {len(df_scored):,} total citation windows "
          f"(domain: {(df_scored['level'] == 'domain').sum():,}, url: {(df_scored['level'] == 'url').sum():,}).")
    if df_scored.empty:
        print("No windows found. Exiting.")
        return

    print("\nScoring all windows using the two-stage cascade classifier...")
    windows = df_scored['window_text'].fillna('').tolist()
    predicted_label, p_by_class = score_windows_cascade(windows, vec, clf_stage1, clf_stage2)
    df_scored['p_hostile'] = p_by_class['hostile']
    df_scored['p_endorsement'] = p_by_class['endorsement']
    df_scored['p_other'] = p_by_class['other']
    df_scored['predicted_label'] = predicted_label
    df_scored['is_list_dump'] = df_scored['is_list_dump'].astype(int)

    df_cache = df_scored.drop(columns=['window_text'])
    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    df_cache.to_parquet(OUT_PARQUET, index=False)
    print(f"\nSaved ATS source-mentions cache to {OUT_PARQUET} ({len(df_cache):,} rows).")

    print("\nBuilding domain/URL breakdowns...")
    dom_breakdown = summarize(df_cache[df_cache['level'] == 'domain'], 'source_key', 'domain')
    dom_breakdown = dom_breakdown.rename(columns={'source_key': 'domain'})
    dom_breakdown.to_csv(OUT_DOMAIN_BREAKDOWN, index=False)
    print(f"Saved {len(dom_breakdown):,} rows to {OUT_DOMAIN_BREAKDOWN}")

    url_breakdown = summarize(df_cache[df_cache['level'] == 'url'], 'source_key', 'url')
    url_breakdown = url_breakdown.rename(columns={'source_key': 'url'})
    url_breakdown.to_csv(OUT_URL_BREAKDOWN, index=False)
    print(f"Saved {len(url_breakdown):,} rows to {OUT_URL_BREAKDOWN}")

    print(f"\n=== Top 30 ATS domains by mention count (min {MIN_MENTIONS_TO_REPORT}) ===")
    top_dom = dom_breakdown[dom_breakdown['mention_count'] >= MIN_MENTIONS_TO_REPORT].head(30)
    print(top_dom[['domain', 'mention_count', 'pct_predicted_hostile', 'pct_predicted_endorsement', 'pct_predicted_other']].to_string(index=False))

    print("\nDone.")


if __name__ == '__main__':
    main()
