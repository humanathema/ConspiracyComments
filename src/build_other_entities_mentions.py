"""build_other_entities_mentions.py

Surfaces entities the project identified but never ran through the
maverick/consensus stance pipeline (villain, mainstream_figure_not_source,
mainstream_source, alternative_source, other buckets from
entity_final_review.csv -- e.g. Bill Gates, Hillary Clinton, Washington
Post). No stance classification here, just raw mention counts, tagged
construct="other" so the explorer can show them without pretending they've
been categorized as maverick or consensus-expert sources.

Output: data/processed/other_entities_mentions.csv
  entity, mention_count, bucket
"""
import csv

REVIEW_PATH = 'data/processed/entity_final_review.csv'
EXISTING_PATHS = [
    'data/processed/per_entity_stance_breakdown_pure.csv',
    'data/processed/per_entity_stance_breakdown_unfiltered.csv',
]
OUT_PATH = 'data/processed/other_entities_mentions.csv'

TARGET_BUCKETS = {'villain', 'mainstream_figure_not_source', 'other', 'mainstream_source', 'alternative_source'}
MIN_DOC_COUNT = 500

existing = set()
for path in EXISTING_PATHS:
    with open(path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            existing.add(row['entity'].lower())

out_rows = []
with open(REVIEW_PATH, newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        if row['final_bucket_guess'] not in TARGET_BUCKETS:
            continue
        if row['likely_pure_junk'] == 'True':
            continue
        if row['disambiguation_note']:
            continue  # ambiguous bare names (e.g. ungrouped "Clinton") -- skip, ambiguity needs the same disambiguation machinery the maverick/consensus lists already use
        try:
            doc_count = float(row['doc_count'] or 0)
        except ValueError:
            continue
        if doc_count < MIN_DOC_COUNT:
            continue
        if row['entity'].lower() in existing:
            continue
        out_rows.append((doc_count, row['entity'], row['final_bucket_guess']))

out_rows.sort(reverse=True)

with open(OUT_PATH, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['entity', 'mention_count', 'bucket'])
    for doc_count, entity, bucket in out_rows:
        w.writerow([entity, int(doc_count), bucket])

print(f"Saved {len(out_rows):,} rows to {OUT_PATH}")
