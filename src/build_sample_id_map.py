"""Recover real Reddit comment ids for the 2,000-row validation sample.

The labeled_2k / ensemble / cascade files identify comments only by row
index (0-1998), and their text columns are truncated, so they cannot be
joined to the raw archive directly. This script matches the untruncated
sample text (from the v2 batch jsonl) against the raw archive on a
normalized 200-char text key and writes the mapping to
data/processed/sample_2k_id_map.csv (row_idx, reddit_id).

Rows whose normalized key matches more than one distinct comment id
(duplicate/copypasta comments) are dropped as ambiguous: 1,968 of 2,000
resolve uniquely.
"""
import json
import re

import duckdb
import pandas as pd

V2_JSONL = 'data/llm_batches/credibility_signals_batch_v2_tightened.jsonl'
RAW_GLOB = 'data/raw/r_conspiracy_comments*.jsonl*'
OUT = 'data/processed/sample_2k_id_map.csv'


def norm(s):
    return re.sub(r'[^a-z0-9]', '', str(s).lower())[:200]


def main():
    rows = []
    with open(V2_JSONL) as fh:
        for line in fh:
            o = json.loads(line)
            rows.append((o['id'], norm(o['target_text'])))
    keys = pd.DataFrame(rows, columns=['row_idx', 'key'])

    con = duckdb.connect()
    con.register('keys', keys)
    res = con.execute(f"""
        SELECT k.row_idx, r.id
        FROM read_json_auto('{RAW_GLOB}',
                            maximum_object_size=50000000, union_by_name=True) r
        JOIN keys k
          ON substr(regexp_replace(lower(r.body), '[^a-z0-9]', '', 'g'), 1, 200) = k.key
        WHERE r.body IS NOT NULL
    """).df().drop_duplicates(['row_idx', 'id'])

    unambig = (res.groupby('row_idx')
                  .filter(lambda g: g['id'].nunique() == 1)
                  .drop_duplicates('row_idx'))
    print(f'matched {res["row_idx"].nunique()} of {len(keys)}; '
          f'{len(unambig)} unambiguous')
    unambig[['row_idx', 'id']].rename(columns={'id': 'reddit_id'}).to_csv(OUT, index=False)
    print(f'written to {OUT}')


if __name__ == '__main__':
    main()
