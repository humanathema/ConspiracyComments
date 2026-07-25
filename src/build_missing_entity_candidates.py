"""build_missing_entity_candidates.py

Finds real, high-volume named entities that were mined by the bottom-up
NER frequency pass (src/mine_corpus_entity_frequency.py ->
corpus_entity_frequency.csv) but never promoted to human review
(entity_final_review.csv) -- confirmed gap, e.g. "Trump" (158K+ combined
mentions) has in_candidate_list=False on every variant. Same class of
problem as the earlier "Brand"/"Hawking" bare-form gaps on the maverick
side, but much larger in scope and on the mainstream/political-figure
side.

Does NOT classify anything -- entity-list judgment calls are Nash's,
not this script's (see project guardrails). Produces a reviewable
candidate list with a blank decision column, same convention as the
original maverick_candidate_entities_scored.csv.

Output: data/processed/missing_entity_candidates.csv
  entity, corpus_mentions, example_1, example_2, decision
"""
import csv
from collections import defaultdict

FREQ_PATH = 'data/processed/corpus_entity_frequency.csv'
REVIEW_PATH = 'data/processed/entity_final_review.csv'
OUT_PATH = 'data/processed/missing_entity_candidates.csv'

MIN_MENTIONS = 500

# NORP (nationality/religious/political-group) label leaks in a lot of bare
# demonyms and generic group nouns that aren't specific named entities --
# exclude those explicitly rather than trying to auto-detect "is this a
# real entity", which is exactly the kind of judgment call this script
# should not be making.
STOPLIST = {
    'american', 'americans', 'russian', 'russians', 'chinese', 'german',
    'germans', 'british', 'european', 'europeans', 'jewish', 'jews', 'jew',
    'christian', 'christians', 'nazi', 'nazis', 'republicans', 'republican',
    'democrats', 'democrat', 'israeli', 'israelis', 'muslim', 'muslims',
    'canadian', 'canadians', 'french', 'english', 'irish', 'african',
    'asian', 'arab', 'arabs', 'catholic', 'catholics', 'gop', 'lol',
    'covid', 'covid-19', 'msm', 'mueller report',
}

already_reviewed = set()
with open(REVIEW_PATH, newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        already_reviewed.add(row['entity'].strip().lower())

totals = defaultdict(int)
best_examples = {}  # lower_name -> (count_of_best_row, display_name, ex1, ex2)
with open(FREQ_PATH, newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        name = row['entity'].strip()
        if len(name) < 3:
            continue
        key = name.lower()
        if key in STOPLIST or key in already_reviewed:
            continue
        try:
            dc = int(row['doc_count'])
        except ValueError:
            continue
        totals[key] += dc
        cur = best_examples.get(key)
        if cur is None or dc > cur[0]:
            best_examples[key] = (dc, name, row.get('example_1', ''), row.get('example_2', ''))

rows = [(n, key) for key, n in totals.items() if n >= MIN_MENTIONS and key not in already_reviewed]
rows.sort(reverse=True)

with open(OUT_PATH, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['entity', 'corpus_mentions', 'example_1', 'example_2', 'decision'])
    for n, key in rows:
        _, display_name, ex1, ex2 = best_examples[key]
        w.writerow([display_name, n, ex1, ex2, ''])

print(f"Saved {len(rows):,} candidate rows to {OUT_PATH} (threshold: {MIN_MENTIONS} mentions, already-reviewed and stoplisted entries excluded)")
