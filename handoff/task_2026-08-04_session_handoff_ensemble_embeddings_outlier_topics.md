# Session handoff 2026-08-04 — stance ensemble, neutral/ambiguous ceiling, outlier embeddings, topic reassignment plan

Long overnight session (a32d297a), continuing directly from 6a4986c3 (the
session that designed the outlier-correction plan below — read that
session's transcript directly if you need more detail than this doc has,
`.jsonl` file still on disk at
`/Users/nash/.claude/projects/-Users-nash-Projects-ConspiracyComments/6a4986c3-6b38-4aee-9fe9-3167098bde4a.jsonl`).
This doc is intentionally terse — written under a token-budget warning —
prioritizing what's DONE, what's STAGED, and exact next steps over prose.

## 1. Stance classifier — what's actually done

**Best single model so far**: GCE ModernBERT-large, 1 epoch, round7-v2 data
— baseline(collapsed)=0.4840, split(bucket_redesign)=0.4588. Best
single-model numbers on the whole board.

**Ensemble validated as real** (not hoped-for): 4-way majority vote on
roberta-base v1-data predictions (round5-v1 both arms + round7-v1 both
arms) = kappa **0.4632** vs best single model 0.4477. Notably the WORST
individual model (r5v1_split, 0.3588) still added value to the vote —
real diversity payoff, not just picking the best model repeatedly.

**Currently running on GCE** (`stance-arch-smoke-test` instance, project
`conspiracycomments-gce`, account `tobiasnash@gmail.com`, zone
`us-central1-a`, 1x L4 GPU): 6-model ModernBERT ensemble batch,
`~/run_ensemble.sh`, 2 epochs each, predictions saved to
`~/preds_{TAG}_{arm}.csv` on the VM (TAG ∈ r7v2/r7v1/r5v2, arm ∈
baseline/split). A 7th+8th run (r7v3/r5v3, see §2) was appended to the
running script's file — **uncertain whether bash picked up the append
to an already-running script**. Check `~/ensemble_run.log` for "ALL
RECIPES DONE" — if r7v3/r5v3 didn't run automatically, launch
`~/run_v3.sh` manually (already staged on the VM).

**Once all 8 predictions exist**: pull all `preds_*.csv` down, run the
same majority-vote ensemble script pattern used for the 4-way roberta
test (brute-force `itertools.combinations` over subsets, pick best kappa)
on the full 8-model pool. Expect this to beat 0.4840.

**IMPORTANT COST NOTE**: this GCE instance is billing against project
`conspiracycomments-gce`, quota-boosted via `gcloud alpha quotas
preferences create` (approved instantly, 1x L4/T4/V100 available).
**Stop the instance when done** (`gcloud compute instances stop
stance-arch-smoke-test --project=conspiracycomments-gce
--account=tobiasnash@gmail.com --zone=us-central1-a`) — it's been running
several hours, on the trial billing account (`tobiasnashpncc`'s
`018899-4B2CA6-0C87CD`).

## 2. Neutral/ambiguous relabeling — v3 built, real ceiling found

**Root cause finally isolated**: 13 prompt variants tested tonight
against a 446-row human ground-truth set (`/tmp/neutral_ambiguous_corrected.csv`
— **NO BUILD SCRIPT, lives only in /tmp, reconstruct or document
provenance before it's lost** — best guess: selected from HITL queue
rows human-labeled neutral/ambiguous, then re-reviewed/corrected jointly
with Nash). Best config found: **v4, plain binary framing** ("does this
comment carry ANY evaluative trace toward the entity, yes/no" — no
category words, no few-shot, no explicit checklist), kappa **0.3202**.
Every embellishment (few-shot, explicit rules, confidence-gating,
entity-focus tightening, base-rate stats) made it WORSE, not better —
consistent, repeated pattern across all 13 variants.

**Why**: found real human inter-rater-reliability data
(`data/hitl/irr_responses/irr_summary.md` + raw CSVs) — 3 human raters
(Jono/Lw/tobias), neutral-vs-ambiguous-ONLY kappa between pairs: Jono-Lw
0.038, Jono-tobias **-0.055** (worse than chance), Lw-tobias 0.421. Jono's
base rate is 86% ambiguous, Lw/tobias's is ~78-80% neutral — genuinely
opposite defaults, not measurement noise. **This is very likely a real
ceiling, not a solvable prompt-engineering problem** — "ambiguous" is
defined by the rater's own epistemic uncertainty, and raters disagree on
where that threshold sits. v4's 0.32 may be close to the practical
ceiling given this.

**v3 training data built and staged** (v4-binary stage1 + a stage2
direction-check on rows stage1 flagged as "has trace", mirroring the
classifier's own two-stage architecture — recovers hostile/endorsement
correction capability that pure-binary v4 structurally can't provide):
- `data/processed/silver_other_neutral_ambiguous_scored_v3_final.parquet`
  — neutral 2194 (64.2%), ambiguous 1183 (34.6%), endorsement 23, hostile
  16. (v2 was neutral 85.1%/ambiguous 14.1% — big correction toward the
  true ~75%-ambiguous rate the ground truth set showed.)
- `data/processed/stance_classifier_training_data_{round5,round7}_bigval_split_v3.parquet`
  — merged, ready to train. round5: 1085 AI-silver rows in pool, 20
  corrected to hostile/endorsement. round7: 3416 rows, 39 corrected.
- Scripts: `src/score_silver_other_v4binary_api.py` (stage1),
  `src/score_silver_other_v3_stage2_direction.py` (stage2),
  `src/build_bigval_split_v3.py` (merge into training data).

**Recommendation**: v3 data is queued into the GCE ensemble run (§1).
Don't do more prompt-engineering on neutral/ambiguous — diminishing
returns against a real ceiling. If the thesis needs this distinction to
be better, the fix is more human labels (round8 already added 19), not
more prompts.

**TODO, not done**: document/reconstruct the 446-row ground truth set's
real provenance and write a build script for it — currently unreproducible.

## 3. Outlier topic reassignment — real plan recovered, partially staged

**Course correction**: earlier in this session I (wrongly) simplified to
"treat the whole 6.08M outlier population uniformly, no A/B split" — this
was a regression from an already-validated design in the predecessor
session (6a4986c3). Reverted back to the real plan below.

**Population split** (real counts, from Kaggle kernel
`tobiasnashws/outlier-ab-split`, output saved to
`data/processed/outlier_ab_split_{long,short}.parquet`):
- **Population A** (title-fallback-rescued, has a placeholder topic from
  its POST's title, not its own content) = **2,410,261** rows
  (long 625,768 + short 1,784,493)
- **Population B** (still `assigned_topic == -1` even after fallback —
  BERTopic genuinely gave up) = **3,691,484** rows (long 1,171,305 +
  short 2,520,179) — matches the predecessor session's "~3.7M" estimate
  almost exactly.

**Embeddings**: DONE for the combined A+B population.
`conspiracycomments-gce.embeddings.outlier_embeddings_final` (BigQuery
table, project `conspiracycomments-gce`) — 6,066,135 rows, 100% coverage,
`gemini-embedding-001` via `ML.GENERATE_EMBEDDING`, 3072-dim. Built via
`bq` CLI directly (no saved script — reconstruct from this doc if
needed): `CREATE TABLE ... AS SELECT id, ml_generate_embedding_result AS
embedding FROM ML.GENERATE_EMBEDDING(MODEL
conspiracycomments-gce.embeddings.gemini_embed_001, (SELECT id, text AS
content FROM conspiracycomments-gce.embeddings.outlier_text), STRUCT(TRUE
AS flatten_json_output))`. Cost: real, paid (Gemini embedding pricing
$0.15/M tokens), already spent, not re-billable.

**Population A method — divergence-flagging** (validated on 100k pilot,
found real corrections from a keyword-substring-collision mechanism, e.g.
"ICE"/"anon"/"gate" as substrings of unrelated words): embed (done, see
above), compare similarity to the fallback-assigned topic's centroid vs.
best alternative topic centroid, flag+reassign if a different topic fits
meaningfully better. **NOT YET RUN.** Staged skeleton at
`/Users/nash/Projects/surge-compute/kaggle_outlier_population_a_divergence/train.py`
— has explicit TODOs, most importantly: **topic centroids must be
rebuilt in Gemini's embedding space**, `topic_centroids.npz` is
MiniLM-space and not comparable. Build by sampling each topic's
high-`own_sim` (confidently-assigned) rows and embedding them the same
way (BigQuery `ML.GENERATE_EMBEDDING`).

**Population B method — outlier-coherence discovery via graph community
detection** (validated on 100k pilot — found real, named coherent
clusters MiniLM/BERTopic missed entirely: Trump body-double theories,
Vegas trutherism, Hunter Biden laptop). Pilot used real HLC
(`cdlib.hierarchical_link_community`) but that's capped at ~700 nodes
(OOM'd at the pilot's own 90k-node full scale). Clique percolation
(`nx.algorithms.community.k_clique_communities`) ran successfully at 90k
nodes but needed real tuning to avoid giant-mega-community collapse (k=4/
threshold=0.5 → 63% of the graph in one blob; k=5/threshold=0.75 fixed
it) — **that threshold is very unlikely to transfer to a 67x-larger
(3.69M-node) graph untuned.**

**NOT YET STAGED, real engineering needed, not just a parameter change**:
1. k-NN graph construction at 3.69M nodes needs an approximate-NN
   library (FAISS or ScaNN) — the pilot's `sklearn.neighbors.NearestNeighbors`
   brute-force approach does not scale to this size.
2. Community detection needs to be Louvain-based (near-linear, the only
   demonstrably-scalable method used anywhere in this project's graph
   work — see `src/graph_pilot_chain_clustering.py` for the pattern,
   though it was applied to a coarser chain-level graph, not raw
   comments) rather than clique percolation or true HLC.
3. The predecessor session's own risk flag: **chunk by super-topic or
   time period** rather than one monolithic 3.69M-node graph — not yet
   designed, no chunking scheme decided.
4. Reply-structure and author-connectivity edge layers (used in the
   pilot's combined graph) need a full-corpus equivalent — check whether
   `thread_topic_map.parquet` / `author_topic_engagement.csv` type files
   already have what's needed, or need rebuilding.

**Realistic next step**: this is a real multi-day build, not a
same-session task. Suggest starting with Population A (smaller, method
more directly reusable, no new graph infra needed) as the next concrete
piece of work, and treating Population B's graph pipeline as its own
scoped task once A is working.

## 4. Cross-cutting notes

- **GCE project `conspiracycomments-gce`**: created this session under
  `tobiasnash@gmail.com` specifically because `tobiasnash-vertex-frontier`
  (under `contact@tobiasnash.co.nz`) has an org policy blocking both
  service-account-key creation AND some IAM bindings — a personal Gmail
  project sidesteps both. Billing linked to `tobiasnashpncc`'s trial
  account (`018899-4B2CA6-0C87CD`, capped at 3 linked projects — deleted
  the unused `nashpncc-vertex-frontier` to make room).
- **BigQuery embedding jobs run under `conspiracycomments-gce` too** (not
  `tobiasnash-vertex-frontier`) for the same org-policy reason — the
  `bqcx-...@gcp-sa-bigquery-condel.iam.gserviceaccount.com` service
  agent needs an IAM grant (`roles/aiplatform.user`) that the org policy
  blocks on the other project.
- Remember to check GPU quota via `gcloud alpha quotas preferences
  create` if spinning up more GCE compute — worked instantly last time,
  not guaranteed.
