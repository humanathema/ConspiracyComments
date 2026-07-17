# Task: Finish rating the consensus-stance queue, then run the formal analysis

## Status: in progress, human ratings ongoing

`data/hitl/queue_consensus_stance.csv` — 240 comments where
`has_consensus_expert == 1` in the pure r/conspiracy population,
stratified by traction (120 high, 120 low), blinded (no upvote data
shown to the rater, rows shuffled). As of 2026-07-17: 152/240 rated.

**This is Nash's rating work, not something to automate or have
Antigravity rate.** The tool is `src/hitl_rater.py`
(`python3.12 src/hitl_rater.py`, open `http://localhost:8420`). If
picking this up as an Antigravity task, your job is limited to:

1. **Check whether rating is complete** — `python3.12 -c "import pandas as pd; df=pd.read_csv('data/hitl/queue_consensus_stance.csv'); print(df['human_stance'].notna().sum(), '/', len(df))"`.
2. **If complete (240/240)**, run `src/analyze_consensus_stance.py` and
   report the full stance × stratum contingency table (not just a
   summary — the actual numbers).
3. **Preliminary read as of 152/240** (do not treat as final, re-check
   once complete): hostile framing outnumbers endorsement roughly 3-to-1
   overall (99 vs. 30, plus 12 ambiguous, 11 neutral). If this holds,
   it's a significant reframing of the `has_consensus_expert` +0.533
   regression coefficient — it may mean "attacking consensus figures
   predicts engagement" rather than "citing them approvingly does."
   Don't write this into any thesis-facing document as settled until the
   full 240 are rated and the stratum breakdown is checked (does stance
   actually differ between high-traction and low-traction comments? —
   that's the real question this queue was built to answer, not just
   the overall stance distribution).

## Do not

- Rate any of the comments yourself (Antigravity or otherwise) — this
  needs to be genuine human judgment from Nash.
- Modify `data/hitl/queue_consensus_stance.csv`'s existing ratings for
  any reason without backing the file up first (see main handoff
  guardrail 4).
