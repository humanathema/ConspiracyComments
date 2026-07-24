#!/usr/bin/env python3
"""compute_irr_agreement.py

Calculates Inter-Rater Reliability (IRR) metrics for the shared stance queue:
- Pairwise Cohen's Kappa (unweighted 4-class)
- Pairwise Collapsed Cohen's Kappa (3-class, collapsing ambiguous/neutral)
- Pairwise Weighted Cohen's Kappa (linear & quadratic weights over 3-class spectrum)
- Multi-rater Fleiss' Kappa (uncollapsed 4-class vs collapsed 3-class)
- Raw agreement percentages

Aligns ratings automatically across the shared 99 items, handling incomplete
or in-progress rating sessions gracefully.
"""
import os
import sys
import glob
import pandas as pd
import numpy as np
from sklearn.metrics import cohen_kappa_score

# Resolve root path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IRR_DIR = os.path.join(REPO_ROOT, "data/hitl/irr_responses")
MASTER_QUEUE = os.path.join(REPO_ROOT, "data/hitl/queue_irr_stance_shared.csv")


def load_irr_responses():
    pattern = os.path.join(IRR_DIR, "irr_stance_shared__*.csv")
    files = glob.glob(pattern)
    if not files:
        return {}
        
    responses = {}
    for f in files:
        # Extract rater name from file pattern: irr_stance_shared__<rater>.csv
        base = os.path.basename(f)
        rater = base.replace("irr_stance_shared__", "").replace(".csv", "")
        
        # Skip user manual work copy files
        if "copy" in rater.lower() or "temp" in rater.lower():
            continue
            
        try:
            df = pd.read_csv(f)
            # Find the stance column (human_stance or human_label)
            col = "human_stance" if "human_stance" in df.columns else "human_label"
            if col in df.columns:
                # Store as dict: id -> clean label
                df_clean = df.dropna(subset=[col]).copy()
                responses[rater] = dict(zip(df_clean["id"].astype(str), df_clean[col].astype(str).str.strip()))
        except Exception as e:
            print(f"Warning: Failed to load response file for {rater}: {e}")
            
    return responses


def map_label(lbl):
    """Maps nominal labels to a linear stance scale.
    hostile (-1) <--- neutral/ambiguous (0) ---> endorsement (+1)
    """
    if lbl in ["ambiguous", "neutral", "other", "unclear"]:
        return 0
    elif lbl == "endorsement":
        return 1
    elif lbl == "hostile":
        return -1
    return np.nan


def calculate_pairwise_stats(y1, y2):
    """Computes original, collapsed, and weighted kappa statistics."""
    # 4-class nominal agreement (Standard)
    raw_4 = sum(1 for a, b in zip(y1, y2) if a == b) / len(y1)
    kappa_4 = cohen_kappa_score(y1, y2)
    
    # Map to ordinal stance scale
    y1_num = [map_label(lbl) for lbl in y1]
    y2_num = [map_label(lbl) for lbl in y2]
    
    # Collapsed 3-class nominal agreement (collapsing neutral/ambiguous to 0)
    raw_3 = sum(1 for a, b in zip(y1_num, y2_num) if a == b) / len(y1)
    
    # Compute Weighted Kappas manually over [-1, 0, 1] ordinal spectrum
    categories = [-1, 0, 1]
    n_cats = len(categories)
    
    # Confusion matrix
    O = np.zeros((n_cats, n_cats))
    for t, j in zip(y1_num, y2_num):
        if not np.isnan(t) and not np.isnan(j):
            O[categories.index(t), categories.index(j)] += 1
            
    t_marg = O.sum(axis=1)
    j_marg = O.sum(axis=0)
    N = O.sum()
    
    if N == 0:
        return raw_4, kappa_4, raw_3, 0.0, 0.0
        
    E = np.outer(t_marg, j_marg) / N
    
    # Linear and Quadratic Weight matrices
    W_linear = np.zeros((n_cats, n_cats))
    W_quad = np.zeros((n_cats, n_cats))
    for i in range(n_cats):
        for j in range(n_cats):
            W_linear[i, j] = abs(categories[i] - categories[j])
            W_quad[i, j] = (categories[i] - categories[j])**2
            
    num_linear = np.sum(W_linear * O)
    den_linear = np.sum(W_linear * E)
    kappa_linear = 1.0 - (num_linear / den_linear) if den_linear > 0 else 0.0
    
    num_quad = np.sum(W_quad * O)
    den_quad = np.sum(W_quad * E)
    kappa_quad = 1.0 - (num_quad / den_quad) if den_quad > 0 else 0.0
    
    return raw_4, kappa_4, raw_3, kappa_linear, kappa_quad


def main():
    print("=== HITL Stance Inter-Rater Reliability (IRR) Calculator ===")
    
    if not os.path.exists(MASTER_QUEUE):
        print(f"Error: Master queue not found at {MASTER_QUEUE}. Please build it first.")
        sys.exit(1)
        
    master_df = pd.read_csv(MASTER_QUEUE)
    master_ids = set(master_df["id"].astype(str))
    print(f"Loaded master shared queue with {len(master_ids)} items.")
    
    responses = load_irr_responses()
    if not responses:
        print(f"\nNo rater responses found under {IRR_DIR} yet.")
        sys.exit(0)
        
    print(f"Found ratings from {len(responses)} rater(s): {', '.join(responses.keys())}")
    
    # Progress Summary
    print("\n--- Rating Progress Summary ---")
    progress_rows = []
    for rater, label_map in responses.items():
        count = sum(1 for cid in master_ids if cid in label_map)
        pct = (count / len(master_ids)) * 100
        print(f"  * {rater:<15}: {count}/{len(master_ids)} rated ({pct:.1f}%)")
        progress_rows.append({"Rater": rater, "Count": count, "Percent": f"{pct:.1f}%"})
        
    if len(responses) < 2:
        print("\nNeed at least 2 raters to compute agreement and Kappa. Exiting.")
        sys.exit(0)
        
    # Build aligned matrix
    aligned_data = []
    for cid in sorted(master_ids):
        row = {"id": cid}
        for rater, label_map in responses.items():
            row[rater] = label_map.get(cid, None)
        aligned_data.append(row)
    aligned_df = pd.DataFrame(aligned_data)
    
    # Pairwise Analysis
    print("\n--- Pairwise Agreement Matrix & Advanced Kappa Stats ---")
    raters = sorted(list(responses.keys()))
    pairwise_results = []
    
    for i in range(len(raters)):
        for j in range(i + 1, len(raters)):
            r1, r2 = raters[i], raters[j]
            # Get overlapping subset
            overlap = aligned_df[aligned_df[r1].notna() & aligned_df[r2].notna()]
            n_overlap = len(overlap)
            
            if n_overlap < 5:
                print(f"  * {r1} vs {r2}: Insufficient overlap ({n_overlap} items) to compute Kappa.")
                continue
                
            y1 = overlap[r1].tolist()
            y2 = overlap[r2].tolist()
            
            raw_4, kappa_4, raw_3, kappa_lin, kappa_qd = calculate_pairwise_stats(y1, y2)
            
            print(f"  * {r1} vs {r2}:")
            print(f"    - Overlapping items          : {n_overlap}")
            print(f"    - Raw uncollapsed (4 classes): {raw_4:.1%}")
            print(f"    - Standard Cohen's Kappa     : {kappa_4:.3f}")
            print(f"    - Raw collapsed (3 classes)  : {raw_3:.1%}")
            print(f"    - Linear-Weighted Kappa      : {kappa_lin:.3f}")
            print(f"    - Quadratic-Weighted Kappa   : {kappa_qd:.3f}\n")
            
            pairwise_results.append({
                "Rater 1": r1,
                "Rater 2": r2,
                "Overlap": n_overlap,
                "Raw 4Class": f"{raw_4:.1%}",
                "Kappa 4Class": f"{kappa_4:.3f}",
                "Raw 3Class": f"{raw_3:.1%}",
                "Kappa Linear": f"{kappa_lin:.3f}",
                "Kappa Quadratic": f"{kappa_qd:.3f}"
            })
            
    # Fleiss' Kappa (multi-rater agreement)
    print("--- Group-Wide Agreement (Fleiss' Kappa) ---")
    full_overlap = aligned_df.dropna(subset=raters)
    n_full_overlap = len(full_overlap)
    
    fleiss_summary = ""
    if n_full_overlap >= 10:
        try:
            from statsmodels.stats.inter_rater import fleiss_kappa
            
            # Uncollapsed (4-class)
            categories_4 = sorted(list({full_overlap[r].iloc[idx] for r in raters for idx in range(len(full_overlap)) if pd.notna(full_overlap[r].iloc[idx])}))
            cat_to_idx_4 = {cat: idx for idx, cat in enumerate(categories_4)}
            counts_4 = np.zeros((n_full_overlap, len(categories_4)), dtype=int)
            for idx_subject, (_, row) in enumerate(full_overlap.iterrows()):
                for r in raters:
                    lbl = row[r]
                    if lbl in cat_to_idx_4:
                        counts_4[idx_subject, cat_to_idx_4[lbl]] += 1
            f_kappa_4 = fleiss_kappa(counts_4)
            
            # Collapsed (3-class)
            categories_3 = [-1, 0, 1]
            counts_3 = np.zeros((n_full_overlap, len(categories_3)), dtype=int)
            for idx_subject, (_, row) in enumerate(full_overlap.iterrows()):
                for r in raters:
                    num_lbl = map_label(row[r])
                    if not np.isnan(num_lbl):
                        counts_3[idx_subject, categories_3.index(num_lbl)] += 1
            f_kappa_3 = fleiss_kappa(counts_3)
            
            print(f"  * Overlapping items rated by ALL: {n_full_overlap}")
            print(f"  * Fleiss' Kappa (uncollapsed 4-class): {f_kappa_4:.3f}")
            print(f"  * Fleiss' Kappa (collapsed 3-class)  : {f_kappa_3:.3f}")
            
            fleiss_summary = (
                f"* **Uncollapsed 4-Class Fleiss' Kappa**: {f_kappa_4:.3f}\n"
                f"* **Collapsed 3-Class Fleiss' Kappa**: {f_kappa_3:.3f} *(collapsing neutral and ambiguous)*"
            )
        except Exception as e:
            print(f"  * Warning: Failed to compute Fleiss' Kappa: {e}")
            fleiss_summary = "Failed to compute Fleiss' Kappa."
    else:
        print(f"  * Skipping Fleiss' Kappa: only {n_full_overlap} items rated in common by ALL raters (need >= 10).")
        fleiss_summary = f"Skipped (only {n_full_overlap} items rated in common by ALL raters, need >= 10)."
        
    # Write beautiful Markdown summary
    summary_path = os.path.join(IRR_DIR, "irr_summary.md")
    os.makedirs(IRR_DIR, exist_ok=True)
    
    with open(summary_path, "w") as f:
        f.write("# Stance Labeling Inter-Rater Reliability (IRR) Summary\n\n")
        f.write("This file is dynamically updated by `compute_irr_agreement.py` to trace labeling convergence and advanced Kappa metrics.\n\n")
        
        f.write("## Progress Summary\n\n")
        f.write("| Rater | Items Rated | Progress |\n")
        f.write("|---|---|---|\n")
        for row in progress_rows:
            f.write(f"| {row['Rater']} | {row['Count']} | {row['Percent']} |\n")
            
        f.write("\n## Pairwise Agreement & Kappa Statistics\n\n")
        if pairwise_results:
            f.write("| Rater 1 | Rater 2 | Overlap | Raw 4-Class | Unweighted Kappa | Raw 3-Class (Collapsed) | Linear-Weighted Kappa | Quadratic-Weighted Kappa |\n")
            f.write("|---|---|---|---|---|---|---|---|\n")
            for row in pairwise_results:
                f.write(f"| {row['Rater 1']} | {row['Rater 2']} | {row['Overlap']} | {row['Raw 4Class']} | {row['Kappa 4Class']} | {row['Raw 3Class']} | {row['Kappa Linear']} | {row['Kappa Quadratic']} |\n")
        else:
            f.write("Insufficient overlapping ratings to calculate Cohen's Kappa yet.\n")
            
        f.write("\n## Group-Wide Multi-Rater Agreement (Fleiss' Kappa)\n\n")
        f.write(f"{fleiss_summary}\n")
        
    print(f"\nMarkdown summary report successfully saved to {summary_path}")


if __name__ == "__main__":
    main()
