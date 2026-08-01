# ATS threaded forum view (local-only, in progress 2026-07-26)

Started per Nash's request: the AboveTopSecret comment viewer was a flat
list you had to open/close one comment at a time. Replacing it with a
scrollable, sequential forum view (chronological, replies indented where
detected) instead.

**Note for whichever session is doing the Cloud Run + GCS migration**:
this work is currently local-disk only (new parquet file, server reads it
by relative path off `DB_PATH`'s directory same as the existing
`ats_comments_browse.parquet`). It'll need the same treatment as that file
when data moves to a GCS bucket. Flagging so it gets folded into the
migration rather than done twice.

## What changed

1. `src/build_ats_thread_view_export.py` (new) — builds
   `data/processed/ats_comments_thread_view.parquet` by joining the
   existing `ats_comments_browse.parquet` (has `hs_prob`, scored) with
   `ats_comments_final.parquet` (has `page_num`, `reply_to_post_ids`, both
   dropped somewhere upstream of the browse export — never tracked in any
   script, so this had to be rebuilt rather than found). Adds a
   `thread_seq` column (row number within thread, ordered by page_num then
   comment_id) so the API can do windowed/offset pagination without
   re-deriving order each call. 1.75GB, 7,147,196 rows, 339,196 threads.
   Already run once locally — the parquet exists in `data/processed/`.

2. `src/serve_drilldown_api.py` — new `query_ats_thread_posts()` +
   `/api/ats_thread_posts` route. Params: `thread_id` (required),
   `center_post_id` (first load — server finds that post's `thread_seq`
   and returns a window centered on it) or `offset`/`limit` (scroll-more
   calls in either direction, existing generic offset/limit query params).

3. `src/templates/explorer/app_logic.js` — replaced `openAtsSingleDrill`
   (single comment in isolation) with `openAtsThreadView` +
   `renderAtsThreadView` + scroll-triggered `loadMoreAtsThreadPosts`.
   Loads ~70 posts centered on the clicked comment, infinite-scrolls
   further posts in both directions as you near the top/bottom of the
   loaded window, preserving scroll position across loads. Posts with a
   detected `reply_to_post_ids` (only ~7% of posts — parsed from "reply to
   post by X" / quoted-author text upstream in `ingest_ats_archive.py`)
   are visually indented under their parent *if the parent is currently
   loaded*; everything else renders flat in chronological order, which is
   how the archived thread actually reads day to day.

4. `src/templates/explorer/part1_head_body.html` — CSS for `.thread-view`,
   `.thread-post` (incl. `.thread-post-reply` indent, `.thread-post-anchor`
   highlight for the entry post), `.thread-scroll`, load sentinels.

## Design decisions (confirmed with Nash before building)

- Flat chronological + indent detected replies, not a strict reply tree —
  most posts (~93%) have no detected parent, so a strict tree would mostly
  collapse to flat anyway and reads worse.
- Lazy-load in chunks around the entry point, not full-thread or
  page-based pagination — largest threads run ~10k posts.
- Replaces the single-comment modal outright rather than living alongside
  it as a separate "view full thread" link.

## Update 2026-07-26: browse-first pivot

Nash reviewed the first pass and pushed back twice: (1) clicking a "Top
thread" was still just dumping every matching post from that thread into
the flat search-results table as separate rows, and (2) more fundamentally
the whole tab was still centered on a search table as the primary way in,
when it should read as a forum you browse, with keyword search as an
adjunct. Confirmed via AskUserQuestion: build a real browsable thread
index, not just the existing top-50-by-engagement table, and make search
secondary (empty by default, no auto-loaded unfiltered dump).

Added:

5. `src/build_ats_thread_index.py` (new) + `ats_thread_index` table in
   `drilldown.sqlite` (339,196 rows, one per thread: thread_id,
   thread_title, total_comments, starred_comments, first_post_ts).
   Aggregated once from `ats_comments_thread_view.parquet` so the API can
   sort/paginate/filter cheaply rather than re-aggregating 7.1M parquet
   rows per request. Already run locally.

6. `serve_drilldown_api.py` — `query_ats_thread_index()` +
   `/api/ats_thread_index` route. Params: `q` (thread-title filter),
   `sort` (`total_comments` or `thread_title`), `dir`, `offset`/`limit`.

7. Rewired the ATS tab UI (`part1_head_body.html` + `app_logic.js`):
   - "Browse threads" panel is now the primary, top-of-tab element —
     filterable/sortable/paginated ("Load more") full thread index. Every
     row opens straight into `openAtsThreadView` from the start of the
     thread (`center_post_id` omitted, `offset:0`).
   - The old static "Top threads by engagement" panel (top-50-only,
     backed by `ats_top_threads`) is gone from the UI — superseded by the
     new index defaulting to the same sort. The `ats_top_threads`
     table/endpoint still exist server-side, just unused by the frontend
     now; fine to drop later if nothing else references them.
   - "Search comments" renamed "Find a specific comment", pushed to the
     bottom, explicitly labeled secondary, and no longer auto-fetches on
     tab load — starts empty, only queries once you type.
   - Search results table gained a Date column (raw_timestamp) per
     Nash's request.

Verified end-to-end in the in-app browser against a local
`serve_drilldown_api.py` + a locally-served copy of the reassembled
explorer HTML (temporarily pointed `API_BASE` at localhost — the real
`index.html`/`app_logic.js` still point at the production API and were
not repointed). Confirmed: browse list loads/filters/sorts, clicking a
thread opens the reader at the top, infinite-scroll-down loads further
chunks (verified rows 70 -> 140 after scrolling to the bottom sentinel),
reply indentation renders correctly, and the search panel stays empty
until used.

## Update 2026-07-26 (cont.): scroll-up verified

Opened the reader centered mid-thread (offset ~5000 of 9869), scrolled to
top, confirmed `minOffset` dropped (4965 -> 4895), row count grew
(70 -> 140), and scroll position was preserved (jumped to a proportional
offset rather than snapping to 0) so the reader doesn't lose your place
when older posts load in above. Also confirmed the start-of-thread
boundary: opening from `offset:0` shows "— start of thread —" immediately
rather than attempting a fetch past the beginning.

## Not yet done

- `index.html` at the repo root (the one actually served/committed) was
  not regenerated from these template changes — testing used a throwaway
  copy of `scratch/index_reassembled.html`. Needs `python3
  src/reassemble_explorer.py` run for real and the output copied over
  `index.html` before this ships, same as any other template change.
- `openAtsSingleDrill` is fully removed; nothing else in the codebase
  referenced it directly (checked).
