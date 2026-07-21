"""Consensus-expert bare-form disambiguation lookup.

Mirrors combined_maverick_detector.load_maverick_disambiguation_lookup() --
same Stage B/C mechanism (stage_b_consolidated_corpus_pass.py harvests
context word-bags, stage_c_classify_ambiguous.py classifies each bare
instance against signature words built from unambiguous full-name
mentions), applied to the mainstream/consensus-expert side, which didn't
have any per-instance disambiguation before.

Added 2026-07-20: "Hawking" was a blind bare-form alias for Stephen
Hawking in VERIFIED_CONSENSUS_EXPERTS with no disambiguation -- caught
matching the common verb "hawking" (selling) as often as the physicist,
confirmed by hand-reviewing the r/politics consensus-stance HITL queue.
Bare "Hawking" was removed from the blind list (see
consensus_experts_verified.py); resolved matches now come through here
instead, same pattern as the maverick side's manning/jones/adams/etc.
clusters.
"""
import os
import pandas as pd

VALID_CONSENSUS_CANDIDATES = {
    "Stephen Hawking",
}

CANDIDATE_TO_BARES = {
    "Stephen Hawking": ["hawking"],
}


def load_consensus_disambiguation_lookup():
    path = "data/processed/entity_disambiguation_classified.csv"
    lookup = {}
    if not os.path.exists(path):
        return lookup
    df = pd.read_csv(path)
    df = df[df["cluster"] == "hawking"]
    for _, r in df.iterrows():
        cid = str(r["id"])
        resolved = r["classified_as"]
        if pd.notna(resolved) and str(resolved).strip() != "":
            lookup[cid] = str(resolved).strip()
    return lookup
