#!/usr/bin/env python3
"""build_stance_active_learning_queue.py

Uncertainty-sampling round 2 for the stance classifier's weakest spot.
train_stance_classifier.py's 5-fold CV showed accuracy varying sharply by
source queue -- consensus_stance (r/conspiracy) held out at 77%, but
maverick_stance (r/conspiracy) only 56%, barely above a naive baseline.
That queue is also the largest underlying population (~20k has_maverick
positives in r/conspiracy), so improving it matters more than the other
three.

Method: score every has_maverick==1 r/conspiracy comment NOT already in
the rated queue_maverick_stance.csv with the current classifier, rank by
|P(endorsement) - 0.5| (closest to 0.5 = most uncertain -- classic
uncertainty sampling), take the most uncertain N, build a new blinded
queue with the same schema/codebook as the original stance queues so it
drops straight into hitl_rater.py. Rating these and retraining should
improve the classifier more per-labeled-example than random additional
sampling would, since they're exactly the cases the current model can't
tell apart.

Usage:
    python3.12 src/build_stance_active_learning_queue.py
        # defaults to maverick_stance, N=120
    python3.12 src/build_stance_active_learning_queue.py --queue consensus_stance --n 60
"""
import os
import sys
import json
import argparse
import numpy as np
import pandas as pd
import duckdb
import joblib

sys.path.insert(0, os.path.dirname(__file__))
from refine_thesis_models import build_regex
from rerun_refined_regressions_v2 import (
    load_entities_split_corrected, compute_has_maverick, compute_has_consensus_expert,
    STAGED_PATH, EMPATH_PATH, THREAD_PATH, PRESENCE_PATH, BRIGADE_PATH, POLITICS_SCORED_PATH,
)
import re
from combined_maverick_detector import load_maverick_disambiguation_lookup, CANDIDATE_TO_BARES as MAVERICK_CANDIDATE_TO_BARES
from consensus_disambiguation_lookup import load_consensus_disambiguation_lookup, CANDIDATE_TO_BARES as CONSENSUS_CANDIDATE_TO_BARES
from stance_window_utils import extract_entity_window, compute_spans_for_row

STANCE_MODEL_PATH = 'data/processed/stance_classifier.joblib'

QUEUE_SPECS = {
    'maverick_stance': {
        'existing_queue': 'data/hitl/queue_maverick_stance.csv',
        'subreddit': 'r/conspiracy',
        'construct': 'maverick',
    },
    'consensus_stance': {
        'existing_queue': 'data/hitl/queue_consensus_stance.csv',
        'subreddit': 'r/conspiracy',
        'construct': 'consensus',
    },
    'maverick_stance_politics': {
        'existing_queue': 'data/hitl/queue_maverick_stance_politics.csv',
        'subreddit': 'r/politics',
        'construct': 'maverick',
    },
    'consensus_stance_politics': {
        'existing_queue': 'data/hitl/queue_consensus_stance_politics.csv',
        'subreddit': 'r/politics',
        'construct': 'consensus',
    },
}


def load_conspiracy_population():
    con = duckdb.connect()
    query = f"""
        SELECT s.id, e.text, e.upvotes, e.parent_id, e.link_id
        FROM '{STAGED_PATH}' s
        JOIN '{EMPATH_PATH}' e ON s.id = e.id
        JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
        LEFT JOIN '{PRESENCE_PATH}' p ON SUBSTR(e.link_id, 4) = p.post_id
        LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
        WHERE t.elasticity_ratio <= (SELECT quantile(elasticity_ratio, 0.33) FROM '{THREAD_PATH}')
          AND t.is_high_crosspost = 0
          AND p.insider_presence_ratio >= 0.75
          AND COALESCE(b.brigade_upvote_flag, 0) = 0
          AND COALESCE(b.brigade_downvote_flag, 0) = 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
    """
    return con.execute(query).df()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--queue', default='maverick_stance', choices=list(QUEUE_SPECS.keys()))
    parser.add_argument('--n', type=int, default=120)
    parser.add_argument('--round', type=int, default=2,
                         help="Round number -- each round gets its own output file "
                              "(queue_<name>_round<N>.csv) so earlier rounds' ratings are never overwritten.")
    args = parser.parse_args()

    spec = QUEUE_SPECS[args.queue]
    round_queue_path = f'data/hitl/queue_{args.queue}_round{args.round}.csv'
    round_map_path = f'data/processed/{args.queue}_round{args.round}_uncertainty_map.csv'
    # Exclude every PRIOR round's ids (round 2..args.round-1), not just the immediately
    # preceding one, so re-running at any round number never re-samples an already-rated row.
    prior_round_paths = [f'data/hitl/queue_{args.queue}_round{r}.csv' for r in range(2, args.round)]

    print(f"=== Active-learning round {args.round} for '{args.queue}' ({spec['subreddit']}, {spec['construct']}) ===")

    print("Loading stance classifier...")
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec, clf = stance_model['vec'], stance_model['clf']
    print(f"  cv_kappa={stance_model['cv_kappa']:.3f}, cv_auc={stance_model['cv_auc']:.3f}")

    print("Splitting entities...")
    mavericks, canon, consensus = load_entities_split_corrected()
    rx_mav = build_regex(mavericks)
    rx_con = build_regex(consensus)
    lookup = load_maverick_disambiguation_lookup()
    consensus_lookup = load_consensus_disambiguation_lookup()

    if spec['subreddit'] == 'r/conspiracy':
        df = load_conspiracy_population()
    else:
        df = pd.read_parquet(POLITICS_SCORED_PATH)

    print(f"Loaded {len(df):,} {spec['subreddit']} comments.")

    if spec['construct'] == 'maverick':
        df['has_construct'] = compute_has_maverick(df, rx_mav, lookup)
        rx = rx_mav
        active_lookup = lookup
        candidate_to_bares = MAVERICK_CANDIDATE_TO_BARES
    else:
        df['has_construct'] = compute_has_consensus_expert(df, rx_con, consensus_lookup)
        rx = rx_con
        active_lookup = consensus_lookup
        candidate_to_bares = CONSENSUS_CANDIDATE_TO_BARES

    pop = df[df['has_construct'] == 1].copy()
    print(f"Positive population: {len(pop):,}")

    def load_comment_ids(path):
        """Exclude at the COMMENT level, not the row level -- a queue built
        with the multi-entity split has a `comment_id` column distinct from
        `id` (which gets an __entity suffix per split row); older queues
        (pre-split) don't have that column and used `id` as the comment id
        directly, so fall back to `id` for those."""
        d = pd.read_csv(path)
        col = 'comment_id' if 'comment_id' in d.columns else 'id'
        return set(d[col].astype(str)), len(d)

    existing_ids = set()
    if os.path.exists(spec['existing_queue']):
        ids, _ = load_comment_ids(spec['existing_queue'])
        existing_ids |= ids
    for p in prior_round_paths:
        if os.path.exists(p):
            ids, _ = load_comment_ids(p)
            existing_ids |= ids
    print(f"Already-queued comment ids (original queue + rounds 2..{args.round - 1}) to exclude: {len(existing_ids)}")
    if os.path.exists(round_queue_path):
        ids, n_rows = load_comment_ids(round_queue_path)
        existing_ids |= ids
        print(f"  (this round's own output file already exists too -- also excluding its {n_rows} row(s)/{len(ids)} comment(s))")

    pop = pop[~pop['id'].astype(str).isin(existing_ids)].copy()
    print(f"Remaining unrated positive population: {len(pop):,}")

    if len(pop) == 0:
        print("Nothing left to sample -- entire population already queued.")
        return

    # FIX 2026-07-20 (Nash's round-3 feedback): dedupe by exact text before
    # sampling. Found via round 3 -- one author copy-pasted the same
    # comment across 5 different threads within a 3-minute span (genuine
    # repost spam, not a pipeline bug: same author, different link_id/id,
    # confirmed via corpus lookup). Identical text produces identical/
    # near-identical TF-IDF vectors, so all copies land at the same
    # uncertainty score and can dominate a small round's sample, burning
    # rating budget on what's functionally one data point rated N times.
    n_before_dedup = len(pop)
    pop = pop.drop_duplicates(subset='text', keep='first')
    n_dropped = n_before_dedup - len(pop)
    if n_dropped:
        print(f"Dropped {n_dropped} duplicate-text row(s) (kept first occurrence of each) before sampling.")

    # REDESIGNED 2026-07-20: the classifier is now trained on entity-focused
    # text windows (stance_window_utils), not whole-comment text -- score
    # the same way here, on the WHOLE remaining candidate population
    # (before sampling), so uncertainty is measured on the same kind of
    # input the classifier actually learned from. Uses the combined
    # direct-regex-else-lookup-fallback span helper; the finer per-entity
    # grouping used for the multi-entity row split further below is
    # recomputed separately, only for the much smaller final sample.
    print("Computing entity windows for scoring (whole remaining population)...")
    pop['text_window'] = [
        extract_entity_window(text, compute_spans_for_row(
            text, cid, rx, active_lookup, candidate_to_bares))
        for cid, text in zip(pop['id'].astype(str), pop['text'].fillna(''))
    ]

    print("Scoring stance probability...")
    X = vec.transform(pop['text_window'])
    pop['stance_prob'] = clf.predict_proba(X)[:, 1]
    pop['uncertainty'] = (pop['stance_prob'] - 0.5).abs()

    n = min(args.n, len(pop))
    sample = pop.nsmallest(n, 'uncertainty').copy()
    print(f"Selected {len(sample)} most-uncertain rows "
          f"(stance_prob range: {sample['stance_prob'].min():.3f}-{sample['stance_prob'].max():.3f})")

    shuffled = sample.sample(frac=1, random_state=42).reset_index(drop=True)

    os.makedirs(os.path.dirname(round_map_path), exist_ok=True)
    shuffled[['id', 'stance_prob', 'uncertainty']].to_csv(round_map_path, index=False)
    print(f"Saved unblinded uncertainty map to {round_map_path}")

    # FIX 2026-07-20 (Nash's round-3 feedback): rows resolved ONLY via the
    # disambiguation lookup (bare ambiguous forms like "Jones"/"Webb" that
    # are deliberately excluded from the direct verified-list regex, see
    # compute_has_maverick/compute_has_consensus_expert) previously got
    # zero entity_spans, showing no highlight at all even though they're
    # genuinely positive has_maverick/has_consensus_expert cases. Fixed by
    # falling back to highlighting the resolved candidate's bare form(s)
    # when the direct regex finds nothing. (active_lookup/candidate_to_bares
    # already set above, right after `rx` was picked.)

    # FIX 2026-07-20 (Nash's round-3 feedback, option b): comments
    # mentioning two+ DIFFERENT entities used to get one row with every
    # span highlighted at once, with no way to tell which mention the
    # stance rating was supposed to target. Fixed by grouping spans by
    # which entity they refer to (matched text, lowercased, for direct
    # regex hits; the resolved candidate name for lookup-fallback hits)
    # and emitting ONE ROW PER DISTINCT ENTITY when a comment mentions
    # more than one -- each split row shows only its own entity's
    # highlight(s) and a target_entity label so the rater knows what's
    # being asked. Split rows share the same full_text/parent_id/link_id
    # but get a unique `id` (comment_id + entity suffix) so ratings don't
    # collide in hitl_rater.py's id-keyed label lookup; `comment_id` is
    # kept as a separate column so future rounds' "already queued"
    # exclusion still operates at the comment level, not the row level.
    print("Computing entity spans and splitting multi-entity comments into separate rows...")
    n_fallback = 0
    n_split = 0
    queue_rows = []
    for _, row in shuffled.iterrows():
        cid = str(row['id'])
        text = str(row['text'])

        direct_spans = [{"start": m.start(), "end": m.end(), "text": m.group(0)} for m in rx.finditer(text)]
        entity_groups = {}  # entity_key -> list of spans
        for s in direct_spans:
            entity_groups.setdefault(s["text"].lower(), []).append(s)

        if not entity_groups:
            resolved = active_lookup.get(cid)
            bares = candidate_to_bares.get(resolved, [])
            fallback_spans = []
            for bare in bares:
                bare_rx = re.compile(r'\b' + re.escape(bare) + r'\b', re.IGNORECASE)
                fallback_spans.extend({"start": m.start(), "end": m.end(), "text": m.group(0)} for m in bare_rx.finditer(text))
            if fallback_spans:
                entity_groups[resolved] = fallback_spans
                n_fallback += 1

        if len(entity_groups) > 1:
            n_split += 1

        if not entity_groups:
            # No span found at all (shouldn't normally happen, but don't
            # silently drop the row -- keep it with an empty highlight
            # like before, better than losing a rated-worthy comment).
            entity_groups = {None: []}

        for entity_key, spans in entity_groups.items():
            suffix = "" if len(entity_groups) == 1 else f"__{re.sub(r'[^a-z0-9]+', '_', str(entity_key).lower())}"
            queue_rows.append({
                'id': cid + suffix,
                'comment_id': cid,
                'target_entity': entity_key if len(entity_groups) > 1 else "",
                'full_text': text,
                'human_stance': '',
                'notes': '',
                'entity_spans': json.dumps(spans),
                'parent_id': row['parent_id'],
                'link_id': row['link_id'],
            })

    print(f"  {n_fallback} row(s) highlighted via the bare-form disambiguation fallback.")
    print(f"  {n_split} comment(s) mentioned 2+ distinct entities and were split into separate rows.")

    os.makedirs(os.path.dirname(round_queue_path), exist_ok=True)
    df_queue = pd.DataFrame(queue_rows)
    df_queue.to_csv(round_queue_path, index=False)
    print(f"Saved blinded round-{args.round} queue to {round_queue_path}")
    print(f"Total rating rows: {len(df_queue)} (from {len(shuffled)} sampled comments)")
    print(f"Rows with a matched entity span: {(df_queue['entity_spans'] != '[]').sum()} / {len(df_queue)}")


if __name__ == "__main__":
    main()
