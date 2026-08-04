"""build_bigval_split_v3.py

Merges silver_other_neutral_ambiguous_scored_v3_final.parquet (v4-binary
stage1 + direction-check stage2, kappa 0.3202 against 446-row human ground
truth, vs v2's ~0.16) into the base round5/round7 bigval files, the same
way _split_v2 was built from v2's verdicts.
"""
import pandas as pd

v3 = pd.read_parquet("data/processed/silver_other_neutral_ambiguous_scored_v3_final.parquet")
v3 = v3.drop_duplicates(subset=["text", "target_entity"])

for round_name in ("round5", "round7"):
    base = pd.read_parquet(f"data/processed/stance_classifier_training_data_{round_name}_bigval.parquet")
    m = base.merge(v3[["text", "target_entity", "verdict"]], on=["text", "target_entity"], how="left")
    assert len(m) == len(base), f"{round_name}: row count changed during merge"

    is_ai_other = (m["is_human"] == False) & (m["label"] == "other")
    matched = is_ai_other & m["verdict"].notna()
    print(f"{round_name}: {is_ai_other.sum()} AI-silver 'other' rows, {matched.sum()} matched to v3", flush=True)

    m.loc[matched, "raw_label"] = m.loc[matched, "verdict"]
    became_directional = matched & m["verdict"].isin(["hostile", "endorsement"])
    print(f"{round_name}: {became_directional.sum()} rows corrected label -> hostile/endorsement", flush=True)
    m.loc[became_directional, "label"] = m.loc[became_directional, "verdict"]

    m = m.drop(columns=["verdict"])
    out_path = f"data/processed/stance_classifier_training_data_{round_name}_bigval_split_v3.parquet"
    m.to_parquet(out_path, index=False)
    print(f"{round_name}: saved {out_path} ({len(m)} rows)\n", flush=True)
