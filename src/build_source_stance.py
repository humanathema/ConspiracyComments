"""build_source_stance.py

Extends stance detection to CITED SOURCES: domains (which is also
subdomain-granular already -- citations_cache.parquet's `domain` column is
the full hostname, e.g. 'en.wikipedia.org' and 'en.m.wikipedia.org' are
already distinct rows, not collapsed to a registered-domain level) and
individual frequently-linked URLs.

Conceptually the same construct as entity stance (is the commenter's
own language around this citation hostile toward the source or endorsing
it -- "of course CNN would say that" vs "per this CNN piece"), NOT the
same construct as topic stance (is the commenter for/against a topic's
underlying claim) -- that one needs its own labeled training data and is
deliberately NOT touched here, see build_topic_stance_queue.py /
data/hitl/queue_topic_stance.csv (13% labeled, not enough to train on).

Reuses the SAME trained two-stage cascade classifier and window
convention (stance_window_utils.py) as the entity pipeline -- no new
labeling, no new judgment calls about which domains/URLs matter (target
lists are the project's already-curated, already-reviewed domain/URL
lists, the same ones backing the drilldown's domain_examples/url_examples
tables):
  - domains: data/processed/domain_source_quality_rollup.csv (8,096
    domains with >=20 citations)
  - URLs: data/processed/cited_urls_ranked.csv, top 2000 by distinct
    authors (matches TOP_N_URLS in build_drilldown_backend_db.py)

Unlike entity mentions, citations_cache.parquet doesn't store the
citation's character span within the comment -- only comment_id/url/domain.
Spans are relocated deterministically by re-running the same URL-matching
regex build_citations_cache.py used to build the cache in the first place
(URL_PATTERN + normalize_url), so the window is anchored on the actual
citation, not the whole comment. A citation whose exact normalized URL
can't be relocated in its own comment's text (rare -- e.g. markdown link
display text diverging from the href) is dropped rather than falling back
to whole-comment text, since an unanchored window would silently mix in
whatever else the comment says.

Outputs:
  data/processed/source_mentions_cache.parquet
    comment_id | source_key | level (domain|url) | p_hostile |
    p_endorsement | p_other | predicted_label | is_list_dump
  data/processed/domain_stance_breakdown.csv
  data/processed/url_stance_breakdown.csv
"""
import os
import re
import sys

import numpy as np
import pandas as pd
import joblib
import duckdb

sys.path.insert(0, os.path.dirname(__file__))
from build_citations_cache import URL_PATTERN, TRAILING_PUNCT, strip_unbalanced_trailing_paren, normalize_url
from stance_window_utils import extract_entity_window, is_list_or_link_dump_window, filter_quoted_spans

STANCE_MODEL_PATH = 'data/processed/stance_classifier_2stage_pooled.joblib'
CITATIONS_PATH = 'data/processed/citations_cache.parquet'
TOPIC_CORPUS = 'data/processed/empath_scores_full_mapped.parquet'
DOMAIN_ROLLUP = 'data/processed/domain_source_quality_rollup.csv'
CITED_URLS = 'data/processed/cited_urls_ranked.csv'
TOP_N_URLS = 2000

OUT_PARQUET = 'data/processed/source_mentions_cache.parquet'
OUT_DOMAIN_BREAKDOWN = 'data/processed/domain_stance_breakdown.csv'
OUT_URL_BREAKDOWN = 'data/processed/url_stance_breakdown.csv'
MIN_MENTIONS_TO_REPORT = 20


def score_windows_cascade(windows, vec, clf_stage1, clf_stage2):
    X = vec.transform(windows)
    s1_classes = list(clf_stage1.classes_)
    p_stage1 = clf_stage1.predict_proba(X)
    p_other = p_stage1[:, s1_classes.index('other')]
    p_clear = 1.0 - p_other
    pred_stage1 = clf_stage1.predict(X)

    s2_classes = list(clf_stage2.classes_)
    p_stage2 = clf_stage2.predict_proba(X)
    p_hostile_given_clear = p_stage2[:, s2_classes.index('hostile')]
    p_endorsement_given_clear = p_stage2[:, s2_classes.index('endorsement')]

    p_hostile = p_clear * p_hostile_given_clear
    p_endorsement = p_clear * p_endorsement_given_clear

    predicted_label = np.where(
        pred_stage1 == 'other', 'other',
        np.where(p_hostile_given_clear >= p_endorsement_given_clear, 'hostile', 'endorsement'),
    )
    return predicted_label, {'hostile': p_hostile, 'endorsement': p_endorsement, 'other': p_other}


def find_url_spans(text, target_url):
    """Re-locates target_url's raw occurrence(s) in text by re-running the
    same extraction regex citations_cache was built with, normalizing each
    raw match individually (not deduped, unlike build_citations_cache.py's
    extract_urls) so we keep the character span."""
    text = str(text)
    spans = []
    for m in re.finditer(URL_PATTERN, text):
        raw = m.group(0)
        cleaned = TRAILING_PUNCT.sub('', raw)
        cleaned = strip_unbalanced_trailing_paren(cleaned)
        cleaned = TRAILING_PUNCT.sub('', cleaned)
        if len(cleaned) <= 15:
            continue
        if normalize_url(cleaned) != target_url:
            continue
        # end excludes any trailing punctuation stripped above
        end = m.start() + len(cleaned)
        spans.append({"start": m.start(), "end": end, "text": text[m.start():end]})
    return spans


def summarize(long_df, key_col, level_label):
    if long_df.empty:
        return pd.DataFrame()
    long_df = long_df.copy()
    long_df['is_hostile'] = (long_df['predicted_label'] == 'hostile').astype(float)
    long_df['is_endorsement'] = (long_df['predicted_label'] == 'endorsement').astype(float)
    long_df['is_other'] = (long_df['predicted_label'] == 'other').astype(float)

    g = long_df.groupby(key_col)
    summary = g.size().rename('mention_count').reset_index()
    summary['mean_p_hostile'] = g['p_hostile'].mean().values
    summary['mean_p_endorsement'] = g['p_endorsement'].mean().values
    summary['mean_p_other'] = g['p_other'].mean().values
    summary['pct_predicted_hostile'] = g['is_hostile'].mean().values
    summary['pct_predicted_endorsement'] = g['is_endorsement'].mean().values
    summary['pct_predicted_other'] = g['is_other'].mean().values
    summary['pct_list_dump'] = g['is_list_dump'].mean().values
    summary['level'] = level_label
    return summary.sort_values('mention_count', ascending=False)


def main():
    print("=== Source (domain/subdomain/URL) stance cache ===")

    if not os.path.exists(STANCE_MODEL_PATH):
        print(f"MISSING STANCE MODEL: {STANCE_MODEL_PATH}. Train it first.")
        sys.exit(1)

    print("Loading two-stage cascade model...")
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec = stance_model['vec']
    clf_stage1, clf_stage2 = stance_model['clf_stage1'], stance_model['clf_stage2']
    print(f"Loaded model successfully (CV kappa={stance_model['cv_kappa_end_to_end']:.3f})")

    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='4GB'")

    print("\nLoading target domain/URL lists (already-curated, matches drilldown's domain/url_examples)...")
    n_domains = con.execute(f"SELECT count(*) FROM read_csv_auto('{DOMAIN_ROLLUP}')").fetchone()[0]
    n_urls = min(TOP_N_URLS, con.execute(f"SELECT count(*) FROM read_csv_auto('{CITED_URLS}')").fetchone()[0])
    print(f"  {n_domains:,} curated domains, top {n_urls:,} URLs by distinct authors.")

    print("\nFiltering citations_cache to target domains/URLs and fetching matching comment text "
          "(only the matching subset, not the full corpus)...")
    citations = con.execute(f"""
        WITH top_urls AS (
            SELECT url FROM read_csv_auto('{CITED_URLS}') ORDER BY distinct_authors DESC LIMIT {n_urls}
        ),
        target_citations AS (
            SELECT DISTINCT c.comment_id, c.url, c.domain,
                   d.domain IS NOT NULL AS is_target_domain,
                   u.url IS NOT NULL AS is_target_url
            FROM '{CITATIONS_PATH}' c
            LEFT JOIN read_csv_auto('{DOMAIN_ROLLUP}') d ON c.domain = d.domain
            LEFT JOIN top_urls u ON c.url = u.url
            WHERE d.domain IS NOT NULL OR u.url IS NOT NULL
        )
        SELECT t.comment_id, t.url, t.domain, t.is_target_domain, t.is_target_url, e.text
        FROM target_citations t
        JOIN '{TOPIC_CORPUS}' e ON e.id = t.comment_id
    """).df()
    print(f"  {len(citations):,} (comment, url) citation rows to window/score.")

    print("\nRelocating citation spans and extracting +-15-word windows...")
    rows_to_score = []
    for row in citations.itertuples(index=False):
        text = row.text
        spans = find_url_spans(text, row.url)
        spans = filter_quoted_spans(text, spans)
        if not spans:
            continue
        win = extract_entity_window(text, spans)
        is_dump = is_list_or_link_dump_window(win)
        if row.is_target_domain:
            rows_to_score.append({
                'comment_id': row.comment_id, 'source_key': row.domain, 'level': 'domain',
                'window_text': win, 'is_list_dump': is_dump,
            })
        if row.is_target_url:
            rows_to_score.append({
                'comment_id': row.comment_id, 'source_key': row.url, 'level': 'url',
                'window_text': win, 'is_list_dump': is_dump,
            })
    del citations

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
    print(f"\nSaved source-mentions cache to {OUT_PARQUET} ({len(df_cache):,} rows).")

    print("\nBuilding domain/URL breakdowns...")
    dom_breakdown = summarize(df_cache[df_cache['level'] == 'domain'], 'source_key', 'domain')
    dom_breakdown = dom_breakdown.rename(columns={'source_key': 'domain'})
    dom_breakdown.to_csv(OUT_DOMAIN_BREAKDOWN, index=False)
    print(f"Saved {len(dom_breakdown):,} rows to {OUT_DOMAIN_BREAKDOWN}")

    url_breakdown = summarize(df_cache[df_cache['level'] == 'url'], 'source_key', 'url')
    url_breakdown = url_breakdown.rename(columns={'source_key': 'url'})
    url_breakdown.to_csv(OUT_URL_BREAKDOWN, index=False)
    print(f"Saved {len(url_breakdown):,} rows to {OUT_URL_BREAKDOWN}")

    print(f"\n=== Top 30 domains by mention count (min {MIN_MENTIONS_TO_REPORT}) ===")
    top_dom = dom_breakdown[dom_breakdown['mention_count'] >= MIN_MENTIONS_TO_REPORT].head(30)
    print(top_dom[['domain', 'mention_count', 'pct_predicted_hostile', 'pct_predicted_endorsement', 'pct_predicted_other']].to_string(index=False))

    print(f"\n=== Top 30 URLs by mention count (min {MIN_MENTIONS_TO_REPORT}) ===")
    top_url = url_breakdown[url_breakdown['mention_count'] >= MIN_MENTIONS_TO_REPORT].head(30)
    print(top_url[['url', 'mention_count', 'pct_predicted_hostile', 'pct_predicted_endorsement', 'pct_predicted_other']].to_string(index=False))

    print("\nDone.")


if __name__ == '__main__':
    main()
