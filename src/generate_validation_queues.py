"""Generate blind human-labeling queues for the week's validation plan.

Four queues, written to data/hitl/:

1. queue_procedural_skepticism.csv  (~100) — from the LLM ensemble output,
   stratified by inter-pass consensus (unanimous-positive / split / negative).
2. queue_personal_experience.csv    (~100) — same design.
3. queue_hedged_suspicion_extension.csv (~200) — extends the n=47 spot check
   of the dedicated ML pipeline; stratified across predicted-probability bands
   so the decision boundary is stressed; excludes already-labeled items.
4. queue_intra_rater_hedged_suspicion.csv (~100) — blind re-code of items
   already labeled in the deduped HITL queue, for intra-rater reliability.
   Do NOT consult prior labels while coding; originals stay keyed by id in
   hedged_suspicion_hitl_queue_deduped.csv for the comparison.

Queues deliberately contain NO model columns (labels, probabilities, hit
counts): the rater must be blind to the machine's opinion.
"""
import numpy as np
import pandas as pd

SEED = 42


def binz(s):
    s = s.astype(str).str.lower().str.strip()
    return s.isin(['positive', 'lean_positive', 'yes', 'true', '1', '1.0']).astype(int)


def write_queue(df, cols, path):
    out = df[cols].copy()
    out['human_label'] = ''
    out['notes'] = ''
    out = out.sample(frac=1, random_state=SEED).reset_index(drop=True)
    out.to_csv(path, index=False)
    print(f'{path}: {len(out)} items')


def ensemble_queue(dim, n_total=100):
    d = pd.read_csv(f'data/processed/ensemble_{dim}.csv')
    labcols = [c for c in d.columns if c.startswith('label_')]
    votes = sum(binz(d[c]) for c in labcols)
    unanimous = d[votes == len(labcols)]
    split = d[(votes > 0) & (votes < len(labcols))]
    negative = d[votes == 0]
    # oversample positives/splits: they carry the validation information
    parts = []
    for pool, n in [(unanimous, int(n_total * 0.4)),
                    (split, int(n_total * 0.3)),
                    (negative, n_total - int(n_total * 0.4) - int(n_total * 0.3))]:
        n = min(n, len(pool))
        if n:
            parts.append(pool.sample(n, random_state=SEED))
    q = pd.concat(parts, ignore_index=True)
    write_queue(q, ['id', 'target_text'], f'data/hitl/queue_{dim}.csv')


def hedged_extension_queue(n_total=200):
    # ml_predictions only covers the borderline 0.2-0.8 range; the full-corpus
    # scores file has all bands but no text, so sample ids there and pull
    # bodies from the raw archive in one DuckDB scan.
    import duckdb
    scores = pd.read_parquet('data/processed/full_corpus_suspicion_scores.parquet')
    labeled = set(pd.read_csv(
        'data/processed/hedged_suspicion_hitl_queue_deduped.csv')['id'])
    scores = scores[~scores['id'].isin(labeled)]
    # The wild probability distribution is compressed into ~[0.2, 0.8], so
    # stratify by rank, not by nominal probability: top of the ranking, the
    # region above threshold, the threshold boundary, and the bottom mass.
    per = n_total // 4
    top = scores.nlargest(per * 3, 'ml_suspicion_prob').sample(per, random_state=SEED)
    mid_hi = scores[(scores['ml_suspicion_prob'] >= 0.5)
                    & (scores['ml_suspicion_prob'] < 0.7)].sample(per, random_state=SEED)
    boundary = scores[(scores['ml_suspicion_prob'] >= 0.45)
                      & (scores['ml_suspicion_prob'] < 0.5)].sample(per, random_state=SEED)
    low = scores[scores['ml_suspicion_prob'] < 0.35].sample(per, random_state=SEED)
    q = pd.concat([top, mid_hi, boundary, low], ignore_index=True)

    raw_glob = 'data/raw/r_conspiracy_comments*.jsonl*'
    id_list = ",".join(f"'{i}'" for i in q['id'])
    texts = duckdb.connect().execute(f"""
        SELECT id, body FROM read_json_auto('{raw_glob}',
            maximum_object_size=50000000, union_by_name=True)
        WHERE id IN ({id_list})
    """).df()
    q = q.merge(texts, on='id', how='inner')
    write_queue(q, ['id', 'body'],
                'data/hitl/queue_hedged_suspicion_extension.csv')


def intra_rater_queue(n_total=100):
    q = pd.read_csv('data/processed/hedged_suspicion_hitl_queue_deduped.csv')
    q = q.dropna(subset=['hitl_label']).sample(n_total, random_state=SEED)
    write_queue(q, ['id', 'extracted_span', 'body'],
                'data/hitl/queue_intra_rater_hedged_suspicion.csv')


if __name__ == '__main__':
    ensemble_queue('procedural_skepticism')
    ensemble_queue('personal_experience')
    hedged_extension_queue()
    intra_rater_queue()
