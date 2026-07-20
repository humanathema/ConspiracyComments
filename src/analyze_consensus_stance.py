#!/usr/bin/env python3
"""Analyzes completed stance-labeling HITL queue results.

Joins a blinded stance queue back to its unblinded strata map by id, prints
a contingency table of human_stance x stratum with row percentages, and runs
the chi-square test of whether stance distribution differs by traction
stratum.

Generalized 2026-07-20 (was hardcoded to queue_consensus_stance.csv) so the
same analysis works for any of the stance queues (consensus, maverick, and
the future r/politics ones) without duplicating this script -- see
handoff/task_stance_queues_expansion.md.

Usage:
    python3.12 src/analyze_consensus_stance.py
        # defaults to the consensus-stance queue, unchanged behavior
    python3.12 src/analyze_consensus_stance.py --queue maverick
        # data/hitl/queue_maverick_stance.csv + maverick_stance_queue_strata_map.csv
    python3.12 src/analyze_consensus_stance.py \\
        --queue-path data/hitl/queue_whatever.csv --map-path data/processed/whatever_strata_map.csv
        # fully explicit paths, for anything not following the queue_<name>_stance.csv convention
"""
import argparse
import os
import sys
import pandas as pd
from scipy import stats

QUEUE_PATH_TEMPLATE = 'data/hitl/queue_{name}_stance.csv'
MAP_PATH_TEMPLATE = 'data/processed/{name}_stance_queue_strata_map.csv'


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--queue', default='consensus',
                    help="Short name (e.g. 'consensus', 'maverick') -- resolves to the "
                         "standard queue_<name>_stance.csv / <name>_stance_queue_strata_map.csv paths. "
                         "Ignored if --queue-path/--map-path are given.")
    p.add_argument('--queue-path', default=None, help="Explicit override for the queue CSV path.")
    p.add_argument('--map-path', default=None, help="Explicit override for the strata-map CSV path.")
    return p.parse_args()


def main():
    args = parse_args()
    QUEUE_PATH = args.queue_path or QUEUE_PATH_TEMPLATE.format(name=args.queue)
    MAP_PATH = args.map_path or MAP_PATH_TEMPLATE.format(name=args.queue)

    if not os.path.exists(QUEUE_PATH):
        print(f"Error: {QUEUE_PATH} not found.")
        sys.exit(1)
    if not os.path.exists(MAP_PATH):
        print(f"Error: {MAP_PATH} not found.")
        sys.exit(1)

    df_queue = pd.read_csv(QUEUE_PATH)
    df_map = pd.read_csv(MAP_PATH)

    # Both files contain a triplicated comment (id fn340rs) from the
    # no-dedup queue builder; without this the inner join counts it 9x.
    n_dupes = df_queue['id'].duplicated().sum()
    if n_dupes:
        print(f"Note: dropping {n_dupes} duplicate queue row(s) (keeping first rating).")
    df_queue = df_queue.drop_duplicates(subset='id', keep='first')
    df_map = df_map.drop_duplicates(subset='id', keep='first')

    # Check progress
    labeled = df_queue[df_queue['human_stance'].notna() & (df_queue['human_stance'].str.strip() != "")]
    print(f"Total rows in queue: {len(df_queue)}")
    print(f"Labeled rows: {len(labeled)}")

    if len(labeled) == 0:
        print("No ratings have been submitted yet. Please use http://localhost:8420 to rate the queue.")
        sys.exit(0)

    # Convert ID to string to join cleanly
    df_queue['id'] = df_queue['id'].astype(str)
    df_map['id'] = df_map['id'].astype(str)

    # Join
    merged = df_queue.merge(df_map, on='id', how='inner')

    # Filter to rated items
    rated = merged[merged['human_stance'].notna() & (merged['human_stance'].str.strip() != "")].copy()

    # wrong_match rows are cases where the entity regex misidentified the
    # match (e.g. bare "Brand"/"Hawking" matching the common word, not the
    # person) -- these aren't a real stance instance at all and would
    # otherwise inflate/distort the stance x traction contingency table
    # with rows that have nothing to do with the construct being tested.
    n_wrong = (rated['human_stance'] == 'wrong_match').sum()
    if n_wrong:
        print(f"Excluding {n_wrong} row(s) rated 'wrong_match' (entity misidentified, not a real stance instance).")
        rated = rated[rated['human_stance'] != 'wrong_match'].copy()

    # Raw counts contingency table
    print("\n=== Contingency Table: Stance x Stratum (Raw Counts) ===")
    ct_counts = pd.crosstab(rated['human_stance'], rated['stratum'], margins=True)
    print(ct_counts)

    # Row percentages (normalize='index')
    print("\n=== Contingency Table: Stance x Stratum (Row Percentages) ===")
    ct_pct = pd.crosstab(rated['human_stance'], rated['stratum'], normalize='index') * 100
    print(ct_pct.round(2).astype(str) + '%')

    # Formal test of the question the queue was built to answer:
    # does stance distribution differ between high- and low-traction comments?
    ct = pd.crosstab(rated['human_stance'], rated['stratum'])
    chi2, p, dof, _ = stats.chi2_contingency(ct)
    print(f"\nChi-square (all stances x stratum): chi2={chi2:.2f}, dof={dof}, p={p:.4f}")
    if {'hostile', 'endorsement'}.issubset(ct.index):
        ct2 = ct.loc[['hostile', 'endorsement']]
        chi2b, pb, dofb, _ = stats.chi2_contingency(ct2)
        print(f"Chi-square (hostile vs endorsement only): chi2={chi2b:.2f}, dof={dofb}, p={pb:.4f}")
    print("==========================================================")

if __name__ == "__main__":
    main()
