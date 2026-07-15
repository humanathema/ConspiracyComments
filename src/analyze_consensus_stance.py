#!/usr/bin/env python3
"""Analyzes completed consensus stance labeling results.

Joins queue_consensus_stance.csv back to consensus_stance_queue_strata_map.csv
by id, prints a contingency table of human_stance x stratum with row percentages.
"""
import os
import sys
import pandas as pd

QUEUE_PATH = 'data/hitl/queue_consensus_stance.csv'
MAP_PATH = 'data/processed/consensus_stance_queue_strata_map.csv'

def main():
    if not os.path.exists(QUEUE_PATH):
        print(f"Error: {QUEUE_PATH} not found.")
        sys.exit(1)
    if not os.path.exists(MAP_PATH):
        print(f"Error: {MAP_PATH} not found.")
        sys.exit(1)

    df_queue = pd.read_csv(QUEUE_PATH)
    df_map = pd.read_csv(MAP_PATH)

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

    # Raw counts contingency table
    print("\n=== Contingency Table: Stance x Stratum (Raw Counts) ===")
    ct_counts = pd.crosstab(rated['human_stance'], rated['stratum'], margins=True)
    print(ct_counts)

    # Row percentages (normalize='index')
    print("\n=== Contingency Table: Stance x Stratum (Row Percentages) ===")
    ct_pct = pd.crosstab(rated['human_stance'], rated['stratum'], normalize='index') * 100
    print(ct_pct.round(2).astype(str) + '%')
    print("==========================================================")

if __name__ == "__main__":
    main()
