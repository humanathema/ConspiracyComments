"""run_stance_submodels_only.py

Runs ONLY the mention-only stance sub-models from run_integrated_regressions.py,
without redoing the 216-fit main grid or the formal interaction-term test --
both of those already completed and saved successfully in a prior run
(data/processed/synthesis_regression_results_corrected.csv,
synthesis_regression_results_filtered_clustered.csv,
synthesis_interaction_results_corrected.csv), which is why a full rerun would
have wasted ~90 minutes re-deriving results that already exist on disk. Only
the stance sub-models (the last stage) failed, from an OOM that's since been
fixed (text_df memory footprint). This script reuses
run_integrated_regressions.py's own functions (build_expert_regexes,
load_integrated_dataset, run_stance_submodels) so there's no duplicated logic
-- it just skips straight to the one missing piece.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from run_integrated_regressions import build_expert_regexes, load_integrated_dataset, run_stance_submodels


def main():
    print("=== Stance sub-models only (main grid + interaction test already saved) ===")

    rx_mav, rx_can, rx_con, maverick_lookup, consensus_lookup = build_expert_regexes()
    df, text_df = load_integrated_dataset(rx_mav, rx_can, rx_con, maverick_lookup, consensus_lookup)

    print("Preprocessing variables (same as main())...")
    min_upvotes = df['upvotes'].min()
    df['log_upvotes'] = np.log(df['upvotes'] - min_upvotes + 1)
    df['high_traction'] = (df['upvotes'] >= 5).astype(int)
    df['elasticity_bin'] = pd.qcut(df['elasticity_ratio'], 3, labels=['Low', 'Medium', 'High'])

    run_stance_submodels(df, text_df, rx_mav, rx_con, maverick_lookup, consensus_lookup)
    print("\nDone.")


if __name__ == "__main__":
    main()
