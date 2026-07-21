"""build_jones_stance_quality_queue.py

Quality-check queue for the stance classifier's headline Alex Jones number
(85.8% hostile pooled, stable 2008-2026 per per_entity_stance_over_time.py).
That number rests entirely on the classifier being right -- it's never been
checked against fresh human labels specific to Jones (the existing HITL
queues cover mavericks broadly, not any one entity in depth). This script
draws a stratified random sample of Jones mentions across the classifier's
predicted-probability range (post quote-stripping fix, current
stance_classifier.joblib) for blind hand-labeling in the same format/
convention as the existing queue_*.csv files (queue_consensus_stance_CODEBOOK.md:
hostile / endorsement / neutral / ambiguous).

Stratification: hostile (<0.35) / borderline (0.35-0.65) / endorsing (>0.65)
predicted buckets, ~33 each for a ~100-row sample -- enough to get a rough
per-bucket accuracy read without pretending to more precision than 892
training rows and a kappa=0.352 classifier can support.

Predicted probabilities are saved separately (not in the labeling CSV) so
labeling stays blind -- join back on `id` after labeling to score agreement.

Output:
  data/hitl/queue_jones_stance_quality_check.csv          -- for hand labeling
  data/processed/jones_stance_quality_check_predictions.csv -- model's
    stance_prob/bucket per id, for scoring after labeling (see
    score_jones_stance_quality_check.py)
"""
import os
import sys
import numpy as np
import pandas as pd
import duckdb
import joblib

sys.path.insert(0, os.path.dirname(__file__))
from refine_thesis_models import build_regex
from rerun_refined_regressions_v2 import load_entities_split_corrected, STAGED_PATH, EMPATH_PATH, THREAD_PATH, BRIGADE_PATH
from combined_maverick_detector import load_maverick_disambiguation_lookup, VALID_MAVERICK_CANDIDATES, CANDIDATE_TO_BARES
from stance_window_utils import extract_entity_window
from per_entity_stance_breakdown import entity_groups_for_row

STANCE_MODEL_PATH = 'data/processed/stance_classifier.joblib'
QUEUE_OUT_PATH = 'data/hitl/queue_jones_stance_quality_check.csv'
PRED_OUT_PATH = 'data/processed/jones_stance_quality_check_predictions.csv'
TARGET_ENTITY = 'alex jones'
N_PER_BUCKET = 33
RANDOM_SEED = 42


def main():
    print("=== Building Alex Jones stance quality-check queue ===")

    print("Loading stance classifier (post quote-stripping fix)...")
    stance_model = joblib.load(STANCE_MODEL_PATH)
    vec, clf = stance_model['vec'], stance_model['clf']
    print(f"  cv_kappa={stance_model['cv_kappa']:.3f}, cv_auc={stance_model['cv_auc']:.3f}, n_train={stance_model['n_train']}")

    print("Loading verified entity lists...")
    mavericks, canon, consensus = load_entities_split_corrected()
    rx_mav = build_regex(mavericks)
    lookup = load_maverick_disambiguation_lookup()

    con = duckdb.connect()
    print("Loading r/conspiracy unfiltered population (has_maverick flag only)...")
    query = f"""
        SELECT
            s.id,
            e.parent_id,
            e.link_id,
            CAST(regexp_matches(e.text, $1) AS INTEGER) as has_maverick_regex
        FROM '{STAGED_PATH}' s
        JOIN '{EMPATH_PATH}' e ON s.id = e.id
        JOIN '{THREAD_PATH}' t ON SUBSTR(e.link_id, 4) = t.post_id
        LEFT JOIN '{BRIGADE_PATH}' b ON s.id = b.comment_id
        WHERE t.is_high_crosspost = 0
          AND COALESCE(b.brigade_upvote_flag, 0) = 0
          AND COALESCE(b.brigade_downvote_flag, 0) = 0
        QUALIFY ROW_NUMBER() OVER (PARTITION BY s.id) = 1
    """
    df = con.execute(query, ["(?i)" + rx_mav.pattern]).df()
    resolved_mav = df["id"].astype(str).map(lookup)
    df["has_maverick"] = (df["has_maverick_regex"].astype(bool) | resolved_mav.isin(VALID_MAVERICK_CANDIDATES)).astype(int)
    df = df[df["has_maverick"] == 1].drop(columns=["has_maverick_regex"])
    print(f"  {len(df):,} maverick-mention rows to scan for Jones.")

    ids = df['id'].astype(str)
    con.register("mention_ids_view", df[['id']])
    text_df = con.execute(f"""
        SELECT e.id, e.text FROM '{EMPATH_PATH}' e JOIN mention_ids_view n ON e.id = n.id
    """).df()
    text_lookup = dict(zip(text_df['id'], text_df['text']))
    meta_lookup = dict(zip(df['id'], zip(df['parent_id'], df['link_id'])))

    print(f"Scanning for '{TARGET_ENTITY}' mentions (quote-stripped windows)...")
    rows = []
    for cid in ids:
        text = text_lookup.get(cid)
        if text is None:
            continue
        groups = entity_groups_for_row(text, cid, rx_mav, lookup, CANDIDATE_TO_BARES)
        spans = groups.get(TARGET_ENTITY)
        if not spans:
            continue
        window = extract_entity_window(text, spans)
        parent_id, link_id = meta_lookup.get(cid, (None, None))
        rows.append({
            "id": cid, "full_text": text, "entity_spans": spans,
            "parent_id": parent_id, "link_id": link_id, "text_window": window,
        })
    print(f"  Found {len(rows):,} Jones mentions (post quote-stripping).")

    long_df = pd.DataFrame(rows)
    X = vec.transform(long_df['text_window'])
    long_df['stance_prob'] = clf.predict_proba(X)[:, 1]

    def bucket(p):
        if p < 0.35:
            return 'hostile'
        if p > 0.65:
            return 'endorsing'
        return 'borderline'
    long_df['predicted_bucket'] = long_df['stance_prob'].apply(bucket)

    print("\nPredicted bucket sizes (all Jones mentions):")
    print(long_df['predicted_bucket'].value_counts())

    rng = np.random.RandomState(RANDOM_SEED)
    sampled_parts = []
    for b in ['hostile', 'borderline', 'endorsing']:
        pool = long_df[long_df['predicted_bucket'] == b]
        n = min(N_PER_BUCKET, len(pool))
        if n < N_PER_BUCKET:
            print(f"  WARNING: only {len(pool)} available in '{b}' bucket, sampling all of them.")
        sampled_parts.append(pool.sample(n=n, random_state=rng))
    sample = pd.concat(sampled_parts, ignore_index=True).sample(frac=1, random_state=rng).reset_index(drop=True)

    import json as jsonlib
    queue = sample[['id', 'full_text', 'parent_id', 'link_id', 'entity_spans']].copy()
    queue['human_stance'] = ''
    queue['notes'] = ''
    queue['entity_spans'] = queue['entity_spans'].apply(jsonlib.dumps)
    queue = queue[['id', 'full_text', 'human_stance', 'notes', 'entity_spans', 'parent_id', 'link_id']]
    os.makedirs('data/hitl', exist_ok=True)
    queue.to_csv(QUEUE_OUT_PATH, index=False)
    print(f"\nSaved {len(queue)}-row labeling queue to {QUEUE_OUT_PATH}")
    print("Label the 'human_stance' column with: hostile / endorsement / neutral / ambiguous")
    print("(same convention as data/hitl/queue_consensus_stance_CODEBOOK.md)")

    preds = sample[['id', 'stance_prob', 'predicted_bucket']]
    preds.to_csv(PRED_OUT_PATH, index=False)
    print(f"Saved model predictions (kept separate for blind labeling) to {PRED_OUT_PATH}")


if __name__ == "__main__":
    main()
