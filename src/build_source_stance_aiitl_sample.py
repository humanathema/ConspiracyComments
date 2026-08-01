"""build_source_stance_aiitl_sample.py

Prepares a stratified sample of citation-context windows (both reddit and
ATS source-stance output) for an "AIITL" (AI-in-the-loop, not human-in-
-the-loop) sanity check: does the entity-trained stance classifier's
predicted label actually match what the window says, when the window is
built around a URL/domain citation rather than a named entity mention?

Raised 2026-07-28 after a manual spot-check found two likely distinct
failure modes on the ATS side within minutes of reading five real examples:
  1. Forum signature-block contamination -- a URL embedded in a user's
     static signature (e.g. credit-millionaire.com, unrelated Sun Tzu
     quote, repeated verbatim after every post) gets swept into the
     citation window and scored as if it were live commentary.
  2. Systematic default-to-endorsement bias on neutral reference citations
     (en.wikipedia.org windows were mostly plain, sentiment-free citation
     dumps, not endorsement, but still landed >90% "endorsement").

Both need quantifying at scale, not just eyeballed on 5 rows. Rather than
guessing at prevalence, this samples real windows (regenerated from the
underlying corpus + citations cache, same window-extraction code the
scoring pipeline itself used) for an open-weight LLM (no paid API, no
sign-off needed) to independently judge on a Kaggle GPU kernel.

Also computes a free, deterministic duplicate-window flag per row
(exact match on the window text within the same domain) as a first-pass,
zero-cost signal for likely signature/copypasta contamination -- the LLM
judge is the second layer, for cases duplicate-detection can't catch
(e.g. near-duplicate signatures with minor variation, or genuinely novel
text that's still off-topic).

Outputs:
  data/processed/source_stance_aiitl_sample.parquet
    platform | comment_id | source_key | level | window_text |
    predicted_label | p_hostile | p_endorsement | p_other |
    is_duplicate_window | mention_count (of source_key)
"""
import os
import sys

import duckdb
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from build_source_stance import find_url_spans
from stance_window_utils import extract_entity_window, filter_quoted_spans

N_PER_PLATFORM = 1500
RNG_SEED = 42

OUT_PATH = 'data/processed/source_stance_aiitl_sample.parquet'


def sample_platform(platform, cache_path, corpus_path, id_col, text_col, breakdown_domain_path, breakdown_url_path):
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='4GB'")

    dom_bd = pd.read_csv(breakdown_domain_path)
    url_bd = pd.read_csv(breakdown_url_path)

    # Stratify: half from domain-level mentions, half from url-level,
    # weighted toward high-mention_count sources (where a systematic bias
    # would do the most damage to the aggregate numbers) but with a floor
    # of low-mention sources included too, so the sample isn't blind to
    # long-tail behavior.
    dom_bd = dom_bd.sort_values('mention_count', ascending=False)
    url_bd = url_bd.sort_values('mention_count', ascending=False)

    n_half = N_PER_PLATFORM // 2
    top_domains = dom_bd.head(30)['domain'].tolist()
    rest_domains = dom_bd.iloc[30:]['domain'].sample(
        n=min(20, max(0, len(dom_bd) - 30)), random_state=RNG_SEED
    ).tolist() if len(dom_bd) > 30 else []
    target_domains = top_domains + rest_domains

    top_urls = url_bd.head(30)['url'].tolist()
    rest_urls = url_bd.iloc[30:]['url'].sample(
        n=min(20, max(0, len(url_bd) - 30)), random_state=RNG_SEED
    ).tolist() if len(url_bd) > 30 else []
    target_urls = top_urls + rest_urls

    print(f"[{platform}] Sampling from {len(target_domains)} domains + {len(target_urls)} URLs...")

    cache_df = con.execute(f"SELECT * FROM '{cache_path}'").df()

    dom_rows = cache_df[(cache_df['level'] == 'domain') & (cache_df['source_key'].isin(target_domains))]
    url_rows = cache_df[(cache_df['level'] == 'url') & (cache_df['source_key'].isin(target_urls))]

    dom_sample = dom_rows.groupby('source_key', group_keys=False).apply(
        lambda g: g.sample(n=min(len(g), max(1, n_half // max(1, len(target_domains)))), random_state=RNG_SEED)
    )
    url_sample = url_rows.groupby('source_key', group_keys=False).apply(
        lambda g: g.sample(n=min(len(g), max(1, n_half // max(1, len(target_urls)))), random_state=RNG_SEED)
    )

    sample = pd.concat([dom_sample, url_sample], ignore_index=True)
    print(f"[{platform}] {len(sample):,} rows sampled (before window regeneration).")

    con.register('sample_df', sample)
    joined = con.execute(f"""
        SELECT s.comment_id, s.source_key, s.level, s.predicted_label,
               s.p_hostile, s.p_endorsement, s.p_other, e.{text_col} AS text
        FROM sample_df s
        JOIN '{corpus_path}' e ON e.{id_col} = s.comment_id
    """).df()

    print(f"[{platform}] Regenerating windows for {len(joined):,} rows...")
    rows = []
    for row in joined.itertuples(index=False):
        # source_key is a URL only when level == 'url'; for domain-level rows
        # we need *a* URL from that domain in this comment to relocate a span,
        # so just re-run find_url_spans against the raw domain substring match
        # as a fallback anchor when level == 'domain'.
        if row.level == 'url':
            spans = find_url_spans(row.text, row.source_key)
        else:
            import re
            idx = row.text.lower().find(row.source_key.lower())
            spans = [{"start": idx, "end": idx + len(row.source_key), "text": row.source_key}] if idx >= 0 else []
        spans = filter_quoted_spans(row.text, spans)
        if not spans:
            continue
        win = extract_entity_window(row.text, spans)
        rows.append({
            'platform': platform, 'comment_id': row.comment_id, 'source_key': row.source_key,
            'level': row.level, 'window_text': win, 'predicted_label': row.predicted_label,
            'p_hostile': row.p_hostile, 'p_endorsement': row.p_endorsement, 'p_other': row.p_other,
        })

    df_out = pd.DataFrame(rows)
    # Deterministic duplicate-window flag: exact match within the same source_key.
    df_out['is_duplicate_window'] = df_out.duplicated(subset=['source_key', 'window_text'], keep=False)
    mention_map = pd.concat([
        dom_bd[['domain', 'mention_count']].rename(columns={'domain': 'source_key'}),
        url_bd[['url', 'mention_count']].rename(columns={'url': 'source_key'}),
    ])
    df_out = df_out.merge(mention_map, on='source_key', how='left')
    print(f"[{platform}] Final sample: {len(df_out):,} rows, "
          f"{df_out['is_duplicate_window'].mean()*100:.1f}% flagged as duplicate windows.")
    return df_out


def main():
    reddit_sample = sample_platform(
        'reddit',
        'data/processed/source_mentions_cache.parquet',
        'data/processed/empath_scores_full_mapped.parquet',
        'id', 'text',
        'data/processed/domain_stance_breakdown.csv',
        'data/processed/url_stance_breakdown.csv',
    )
    ats_sample = sample_platform(
        'ats',
        'data/processed/ats_source_mentions_cache.parquet',
        'data/processed/ats_comments_final.parquet',
        'post_id', 'body',
        'data/processed/ats_domain_stance_breakdown.csv',
        'data/processed/ats_url_stance_breakdown.csv',
    )

    combined = pd.concat([reddit_sample, ats_sample], ignore_index=True)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    combined.to_parquet(OUT_PATH, index=False)
    print(f"\nSaved {len(combined):,} total sample rows to {OUT_PATH}")
    print(combined.groupby('platform')['is_duplicate_window'].mean())


if __name__ == '__main__':
    main()
