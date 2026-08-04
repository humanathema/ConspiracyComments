import pandas as pd
import numpy as np
from sklearn.metrics import cohen_kappa_score

# Winning ensemble subset
ensemble_files = [
    'preds_r7v3_baseline.csv', 'preds_r5v2_baseline.csv', 
    'preds_r5v2_split.csv', 'preds_r7v2_split.csv', 'preds_r7v1_baseline.csv'
]
dfs = [pd.read_csv(f) for f in ensemble_files]
df_ens = dfs[0].copy()

# Average probabilities across models
p_neutral = np.mean([df['p_neutral'].values for df in dfs], axis=0)
p_hostile = np.mean([df['p_hostile'].values for df in dfs], axis=0)
p_endorsement = np.mean([df['p_endorsement'].values for df in dfs], axis=0)
p_ambiguous = np.mean([df['p_ambiguous'].values for df in dfs], axis=0)

tier2_pred = []
tier2_margin = []

for pn, ph, pe, pa in zip(p_neutral, p_hostile, p_endorsement, p_ambiguous):
    if pn >= 0.5:
        tier2_pred.append("other")
        tier2_margin.append(np.nan)
    else:
        top = np.argmax([ph, pe, pa])
        if top == 2:
            tier2_pred.append("other")
            tier2_margin.append(np.nan)
        else:
            denom = ph + pe
            p_hostile_norm = ph / denom if denom > 0 else 0.5
            tier2_pred.append("hostile" if top == 0 else "endorsement")
            tier2_margin.append(abs(p_hostile_norm - 0.5))

df_ens['tier2_pred'] = tier2_pred
df_ens['tier2_margin'] = tier2_margin

# Assuming frontier_score_label is pre-mapped in the dataset
# threshold = 0.45 optimally escalates ~17% of rows based on prior sweeps
escalate = df_ens["tier2_margin"] < 0.45
final_pred = df_ens["tier2_pred"].where(~escalate | df_ens["frontier_score_label"].isna(), df_ens["frontier_score_label"])

kappa = cohen_kappa_score(df_ens['true'], final_pred)
print(f"Final Cascade Kappa (Threshold 0.45): {kappa:.4f}")
