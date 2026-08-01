# Client-side caching + predictive prefetch for the explorer (not started, 2026-07-26)

Raised by Nash during the Cloud Run + GCS migration (see
`handoff/task_cloud_run_gcs_migration.md` if that doc exists by the time
you read this, otherwise check `ANTIGRAVITY_HANDOFF.md`'s task index) as a
way to cut apparent latency from the transpacific round-trip (backend runs
in `us-central1`, Nash is in NZ — ~150-250ms baseline RTT). Two genuinely
separate techniques, both worth doing:

1. **Persistent client-side caching (IndexedDB)** — cache API responses
   keyed by request so repeat visits to the same drill-down/entity/ATS
   thread don't re-pay the round-trip. Partial version of this already
   exists: entity time series are cached client-side per-session in
   `app_logic.js` today, but not across page reloads. IndexedDB would
   extend that to survive reloads.
2. **Predictive prefetch** — fire the fetch on `mouseenter` instead of
   waiting for `click` (human click-through-on-hover latency is ~100-150ms,
   which masks more than half the round-trip before the click even
   registers), plus track recently-visited drill-down paths in
   `localStorage` to speculatively warm likely-next requests on page load.

## Why this wasn't started immediately when raised

`app_logic.js` already had two things landing on it in parallel at the
time: the other Claude session's ATS threaded-forum-view work (see
`task_ats_threaded_forum_view.md`) and the Cloud Run migration's own
`API_BASE` repoint (task 5 in the migration plan). Stacking a third
simultaneous edit onto the same file risked real merge conflicts. Deferred
until the migration's read-path cutover is verified working end-to-end and
the dust has settled on `app_logic.js`.

## Why it's more justified now than it would have been earlier

This session initially pushed back on prefetch/caching work (a similar
idea raised via a pasted Gemini conversation) on the grounds that the
explorer had ~2 users (Nash + supervisor) and no real traffic pattern to
predict. That's no longer the full picture: Nash wants to eventually make
the tool public and invite outside contribution, and Cloud Run's real
memory headroom (vs. the e2-micro's 1GB, which OOM-crashed under far
lighter load) means the backend can actually absorb some speculative/
prefetched requests without repeating that failure mode.

## Scope, once picked up

- Land after the Cloud Run read-path is live and verified (see the
  migration plan's verification steps) — don't touch `app_logic.js` for
  this until that's settled.
- IndexedDB layer: wrap the existing `drillApiUrl()`-based fetch calls,
  check cache before hitting the network, write through on response, with
  a TTL/staleness policy (exact TTL not yet decided — data changes
  relatively rarely outside of active rating sessions, so probably
  generous, e.g. hours not seconds).
- Hover-prefetch: add `mouseenter` listeners on drill-down row links/entity
  links that fire the same fetch the click handler would, deduped against
  in-flight/cached requests so a hover-then-click doesn't double-fetch.
- Path prediction: track the last N distinct drill-down views in
  `localStorage`, speculatively prefetch the most-recent or most-frequent
  on page load — keep this simple (no need for anything fancier than
  frequency counting at this data volume/user count).
