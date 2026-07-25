# Corpus explorer: live backend + rich comment view

**Status as of 2026-07-26: done.** Everything scoped in this doc as of
2026-07-25 (multi-rater identity, unreviewed-entity examples, rich
comment context, Outlier assignment + suggestion) was built and deployed
by a follow-on Antigravity session (`75255a6a`, see its
`walkthrough.md`/`task.md` in `~/.gemini/antigravity/brain/` if you want
the blow-by-blow). Verified 2026-07-26: local `index.html` byte-matches
what's actually served at the live URL, and the API responds. This doc
is now a reference for how the thing is built/deployed, not a to-do list.

## What's live and verified

**The real tool**: **https://api.kahatahi.co.nz/explorer/** -- the
actual working corpus explorer. A synced snapshot is also republished at
the Artifact URL
(`https://claude.ai/code/artifact/34fad515-1d21-40d0-9e68-9aea007b3d89`)
for convenience, but the VM-hosted copy is source of truth (see "Why not
the Artifact" below).

**Infrastructure** (GCP project `sapient-zodiac-502400-k2`, account
`contact@kaha-tahi.com`):
- VM: `instance-20260722-010225`, zone `us-central1-a`, e2-micro (1GB RAM,
  30GB disk), external IP `34.44.51.4`. SSH via
  `gcloud compute ssh instance-20260722-010225 --zone=us-central1-a`.
- DNS: `api.kahatahi.co.nz` -> `34.44.51.4`, Cloudflare A record, **"DNS
  only" (grey cloud), not proxied** -- required for Caddy's ACME
  HTTP-01 challenge to work.
- Caddy (auto-HTTPS via Let's Encrypt) terminates TLS and reverse-proxies
  to the API on `localhost:8420`; serves the static explorer HTML at
  `/explorer/*` from `/home/nash/www/explorer/index.html`. Config:
  `/etc/caddy/Caddyfile` on the VM.
- API: `src/serve_drilldown_api.py` (stdlib only), systemd service
  `drilldown-api.service`, listening on `8420` (peak ~14MB RAM observed
  -- comfortably inside the e2-micro's limits). WAL mode + 5s busy
  timeout on every connection for concurrency safety (load-tested: 10
  local threads x 50 writes, plus a live GCE concurrency test under a
  throwaway `_concurrency_test_bot` rater, no lock errors).
  Token: `wCcvTs2IfGhWn64xDhZ8CQxS8Fa5uMzS` (embedded client-side as
  `API_TOKEN` -- deters casual access, not real security, by design).
- Data: `/home/nash/data/processed/drilldown.sqlite` (~950MB after the
  latest rebuild), built locally by `src/build_drilldown_backend_db.py`
  and pushed via `rsync` (delta-transfer + SHA256 checksum match on both
  ends -- see gotcha below for why not `scp | tail`).
- `hitl_rater.py` runs on port 8080 (moved off 80 to free it for Caddy).

### Gotcha already hit and fixed: `gcloud compute scp | tail` silently truncates

`command | tail -N` reports **`tail`'s** exit code, not the piped
command's -- a truncated ~1.2GB sqlite transfer looked like a successful
"exit code 0". Always verify large transfers by checksum. Fixed by using
`rsync` instead.

### Gotcha already hit and fixed: `/home/nash` permissions

Caddy runs as user `caddy`; `/home/nash` was `700`, blocking traversal
even though the target files were readable. Fixed with
`chmod o+x /home/nash`.

## Why not the Artifact (published Claude Artifacts can't do this)

Published Artifacts run in a sandboxed iframe with **no capability for
arbitrary outbound `fetch()`** to a custom server (confirmed against the
runtime contract via the `artifact-capabilities` skill -- only
`downloads` and `mcp` exist, neither of which is "talk to my own API").
That's why the interactive tool is self-hosted rather than delivered as
a Claude Artifact; the Artifact copy is a synced snapshot for
convenience only.

## What's built into the live tool

- **Live drill-down** for topics/entities/domains/URLs -- full text,
  real pagination, sortable columns, column-picker.
- **Topic-fit rating**: 5-point fuzzy scale, staged in `topic_fit_ratings`
  (never mutates the actual topic assignment), now **rater-scoped** (see
  below).
- **Any-entity time series**, fetched live per entity, cached client-side.
- **Unreviewed entities** (Trump, DNC, CIA, etc. -- the 178-row
  `missing_entity_candidates.csv` list) now have real monthly timelines:
  a full-corpus case-insensitive DuckDB regex extraction (not the old
  example-capped query) replaced the flatlined placeholder data,
  expanding `entity_monthly` to 77,785 rows / ~9.67M mentions. They still
  correctly show `construct='unreviewed'`, `predicted_label` blank,
  weight `0.0` -- no stance was invented for them, matching the original
  guardrail (they were mined by frequency only, never run through the
  classifier).
- **Rich single-comment detail view** (split-panel, list left / detail
  right): entity-name highlighting (gold), full epistemic-lexicon term
  highlighting (`utils/epistemic_lexicon.py`, 11 categories, color-coded
  `<mark>`, legend chip strip, light/dark variants), zoom control,
  context strip. The `.detail-zoom`/`.detail-rating-row` CSS collision
  (rating buttons overlapping text, reported via screenshot 2026-07-25)
  is fixed -- separate class now, see `src/templates/explorer/part1_head_body.html:115-126`.
  Comment context (post title/domain/upvotes) is now included via
  `GET /api/comment_context`.
- **Outliers included** in `topic_examples` (not hidden).
- **Outlier topic assignment + suggestion, built**: `GET
  /api/outlier_suggestions` (TF-IDF similarity against
  `topics_summary.json` + live kNN against prior manual assignments) and
  `POST /api/assign_outlier_topic`, staged in `outlier_topic_assignments`
  -- chips/dropdown/assign-button UI in the comment reader. Note: this
  shipped as TF-IDF + kNN, not the embedding/centroid approach I'd
  proposed as v1 -- zero-dependency and no SentenceTransformer call
  needed at request time, a simpler design than what I'd sketched.
- **Multi-rater identity, built**: instead of a plain name-entry field
  (the `hitl_rater.py` pattern I'd pointed at), unnamed raters get a
  randomly generated pseudonym (`generateRandomRaterName()`, e.g.
  "Cloaked Reptilian") persisted in `localStorage`, editable any time.
  `rater` now threads through `topic_fit_ratings` (composite key
  includes rater) and `entity_merges` (`PRIMARY KEY (source_key,
  rater)` -- merges are per-rater, not global) via a self-healing schema
  migration that runs on API startup.
- Extended entity stance data
  (`entity_mentions_cache_extended.parquet` -- villain/
  mainstream_source/mainstream_figure_not_source/alternative_source/
  other/canonical) wired into `entity_examples` and `entity_monthly`.

## Still not done (lower priority, not raised again since scoping)

- **Static "Named entities" table aggregate rollup**
  (`DATA.entities`, the %hostile/%endorsement/mean_p_hostile summary in
  the Named Entities tab) still reflects the pre-extended-stance data for
  `canonical`/`other`/`unreviewed` constructs -- the live drill-down has
  real data for these now, but the embedded static summary table wasn't
  regenerated against it. Low-impact since anyone who clicks through gets
  the real numbers; only the tab's summary row is stale.

## How to redeploy (current recipe -- supersedes the old scratchpad-based one)

The explorer is now assembled from tracked files in
`src/templates/explorer/` (not a session-scratchpad -- this survives
across sessions):
- `part1_head_body.html` -- page HTML/CSS.
- `part2_chartjs.html` -- Chart.js v4.4.1, verbatim.
- `app_logic.js` -- all page JS.

Build script: `src/reassemble_explorer.py` assembles these (+ a `DATA`
JSON blob built from `data/processed/*.csv`/`.json`) into `index.html`
at the repo root. Deploy via `rsync` to
`instance-20260722-010225:/home/nash/www/explorer/index.html` -- verify
with a checksum, not exit code (see gotcha above).

Backend rebuild (`src/build_drilldown_backend_db.py`): full rebuild is
slow (multiple full-corpus DuckDB queries, ~950MB output). For small
schema tweaks, rebuild just the affected table locally, dump to CSV,
patch the remote sqlite via a short script over SSH rather than
re-uploading the whole file. `src/migrate_drilldown_db.py` exists now
for the self-healing-schema-migration pattern (used for the
`entity_merges` rater-column migration) -- reuse that shape for future
schema changes rather than one-off manual patches.

## Raised but intentionally parked (2026-07-26)

Nash floated using git to sync what's on the VM with the repo here,
instead of the current manual rsync/scp-per-change flow. Not pursued --
explicitly left for later. If picked up, worth thinking through: the
sqlite file is too large/binary-diffy for git to be a good fit for *that*
part (rsync is doing real work there, keep it), but the explorer
HTML/JS/API script could reasonably become a real deploy-on-push instead
of manual rsync.
