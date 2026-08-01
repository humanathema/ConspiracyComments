# Move the seed-claim probe tool's embeddings off Nash's local machine, onto Cloud Run (not started, 2026-07-26)

Raised by Nash during the Cloud Run + GCS migration (see
`ANTIGRAVITY_HANDOFF.md`'s task index / the migration's own handoff doc):
the interactive seed-claim probing tool
(`src/serve_seed_claim_probe.py`, see
`handoff/task_topic_quality_explorer_integration.md`'s "Piece 3" section
for the original design) currently requires Nash to run a local Python
server on his own machine, reached by the explorer's JS via
`http://localhost:<port>`. That was a deliberate 2026-07-26 decision at
the time — worth reading the original reasoning before assuming Cloud Run
just obviously fixes it.

## Why it was local-only in the first place

Quoting the original decision (`task_topic_quality_explorer_integration.md`
line ~104): "stage-2 (embedding) compute runs on Nash's local machine, on
demand — not live on the GCE VM. The VM is an e2-micro (1GB RAM),
`drilldown-api.service` is deliberately stdlib-only and currently peaks at
~14MB RAM; adding `sentence-transformers` there is a real OOM risk against
Caddy/hitl_rater/drilldown-api all sharing that 1GB." A live-batched
alternative was also rejected because it "loses the interactive feel Nash
wants — type and immediately see."

**That constraint is exactly what the Cloud Run migration removes** — a
dedicated Cloud Run instance can get real memory (1-2GB+) instead of
fighting for scraps of a shared 1GB VM. Worth doing now that the
constraint that motivated the local-only design is gone.

## Why this is a good fit, not just "more RAM available"

The heavy one-time cost was already designed around in the original piece:
bulk embeddings are precomputed and cached on disk, not computed live:
- `data/processed/topic_centroids.npz` — (97, 384) float32, tiny.
- `data/processed/_audit_topic_quality_embeddings_cache.npy` — (100000,
  384) float32, ~150MB, row-aligned with
  `data/processed/train_topic_assignments.parquet`.

The only *live* compute per request is embedding the short seed-claim
text(s) a user types with the already-vendored `all-MiniLM-L6-v2` (~90MB
model) and comparing against those cached vectors — cheap numpy
dot-products once the model and cache are loaded. That's a small,
well-bounded workload, not "run ML inference over the whole corpus live."

## Two tradeoffs, resolved with Nash 2026-07-26

1. **Cold starts on this specific feature are accepted, not fixed.**
   Nash's call: the main explorer (navigation, drill-downs, ATS search)
   must stay fast and doesn't touch this service at all; the seed-claim
   probe is used occasionally and it's fine if opening it pays a real
   cold-start cost, since it's isolated to that one feature rather than
   blocking core navigation. **Explicitly no `min-instances=1`** — no
   always-on cost for this, full stop.
2. **No torch.** `sentence-transformers`' default backend is PyTorch, but
   that's not required for a single small model like MiniLM — use
   **`fastembed`** (ONNX Runtime-based, built specifically for lightweight
   embedding inference, ships ONNX exports of common models including
   `all-MiniLM-L6-v2`) instead. Same model, much smaller container image,
   meaningfully faster cold start than pulling in all of PyTorch — matters
   more here, not less, given every use of this feature pays the cold
   start (point 1).
3. **Needs to be its own separate Cloud Run service**, not bundled into
   the lightweight DuckDB-on-parquet read API built for the rest of the
   explorer — otherwise every simple drill-down request pays the cost of
   the embedding dependency being importable in that container too.

## Side benefit worth naming

This tool currently cannot work for anyone but Nash, since it depends on
his own laptop running a local server reachable at `localhost` from the
browser. Moving it to Cloud Run makes it usable by anyone visiting the
explorer — relevant given Nash's stated intent to eventually make the
tool public and invite outside contribution.

## Scope, once picked up

- New Cloud Run service (separate from `cloudrun_api/`, e.g.
  `cloudrun_seed_probe/`), `fastembed` (ONNX Runtime-based, no torch) as
  the embedding dependency instead of `sentence-transformers`.
  No `min-instances` — cold starts on this feature are accepted (see
  above).
- Upload `topic_centroids.npz` and
  `_audit_topic_quality_embeddings_cache.npy` (plus
  `train_topic_assignments.parquet` for the row alignment) to the GCS
  bucket alongside the rest of the migrated data.
- Load model + both cached arrays once at container startup, held in
  memory for the container's lifetime (same one-connection-per-instance
  pattern as the main read API's DuckDB connection).
- Port the Stage 1 (TF-IDF prefilter) + Stage 2 (embedding comparison,
  macro/micro/nearest-seed-assignment) logic from
  `src/serve_seed_claim_probe.py` largely as-is — the algorithm doesn't
  change, only where it runs and how it's reached.
- Update `app_logic.js`'s seed-claim probe UI to call the new Cloud Run
  URL instead of `http://localhost:8421` (see the two local-only calls
  noted in the endpoint inventory during the main migration's planning —
  `/api/health` and `/api/probe_local` at that port).
- Resolve the `min-instances` cost decision with Nash before deploying.
