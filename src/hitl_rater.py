"""Minimal local HITL rating tool — no external deps beyond pandas/stdlib/duckdb.

Serves each queue's rows, writes `human_label`/`human_stance` and `notes`
straight back to the source CSV after every submission (so nothing is
lost if the browser or server dies mid-session).

Usage:
    python src/hitl_rater.py
    # then open http://localhost:8420 in a browser

Queues are hardcoded below — edit QUEUES to add/remove files.
"""
import json
import os
import duckdb
import pandas as pd
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# Global configuration defaults (overridden by command-line args)
HOST = "0.0.0.0"
PORT = 8420
TOKEN = ""

# Anchored to the repo root via this file's own location, not the
# process's CWD
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _abs(rel_path):
    return os.path.join(REPO_ROOT, rel_path)

QUEUES = {
    "personal_experience": _abs("data/hitl/queue_personal_experience.csv"),
    "procedural_skepticism": _abs("data/hitl/queue_procedural_skepticism.csv"),
    "maverick_authority": _abs("data/hitl/queue_maverick_authority.csv"),
    "consensus_stance": _abs("data/hitl/queue_consensus_stance.csv"),
    "maverick_stance": _abs("data/hitl/queue_maverick_stance.csv"),
    "consensus_stance_politics": _abs("data/hitl/queue_consensus_stance_politics.csv"),
    "maverick_stance_politics": _abs("data/hitl/queue_maverick_stance_politics.csv"),
    "maverick_stance_round2": _abs("data/hitl/queue_maverick_stance_round2.csv"),
    "maverick_stance_round3": _abs("data/hitl/queue_maverick_stance_round3.csv"),
    "maverick_stance_round4": _abs("data/hitl/queue_maverick_stance_round4.csv"),
    "maverick_stance_round5": _abs("data/hitl/queue_maverick_stance_round5.csv"),
    "maverick_stance_round6": _abs("data/hitl/queue_maverick_stance_round6.csv"),
    "maverick_stance_round7": _abs("data/hitl/queue_maverick_stance_round7.csv"),
    "maverick_stance_round8": _abs("data/hitl/queue_maverick_stance_round8.csv"),
    "consensus_stance_round8": _abs("data/hitl/queue_consensus_stance_round8.csv"),
    "wikileaks_quality_check": _abs("data/hitl/queue_wikileaks_stance_quality_check.csv"),
    "assange_quality_check": _abs("data/hitl/queue_assange_stance_quality_check.csv"),
    "snowden_quality_check": _abs("data/hitl/queue_snowden_stance_quality_check.csv"),
    "greenwald_quality_check": _abs("data/hitl/queue_greenwald_stance_quality_check.csv"),
    "jones_short_quality_check": _abs("data/hitl/queue_jones_short_stance_quality_check.csv"),
    "wikileaks_short_quality_check": _abs("data/hitl/queue_short_wikileaks_stance_quality_check.csv"),
    "assange_short_quality_check": _abs("data/hitl/queue_short_assange_stance_quality_check.csv"),
    "snowden_short_quality_check": _abs("data/hitl/queue_short_snowden_stance_quality_check.csv"),
    "greenwald_short_quality_check": _abs("data/hitl/queue_short_greenwald_stance_quality_check.csv"),
    "irr_stance_shared": _abs("data/hitl/queue_irr_stance_shared.csv"),
    "domain_citation_tier": _abs("data/hitl/queue_domain_citation_tier.csv"),
    "active_learning_requeue": _abs("data/hitl/queue_active_learning_requeue.csv"),
    "escalation_human_review": _abs("data/hitl/queue_escalation_human_review.csv"),
    "frontier_disagreement_qc": _abs("data/hitl/queue_frontier_disagreement_qc.csv"),
    "qwen_escalation_review": _abs("data/hitl/queue_qwen_escalation_review.csv"),
    # Added 2026-08-03: confidently-wrong stage1 requeue (rerun of
    # build_active_learning_requeue.py against round5-bigval's actual
    # trained model -- tiers 1/2 specifically target the "confidently
    # wrong other/stance" failure mode found via the threshold-sweep
    # diagnostics tonight, not generic boundary uncertainty), plus the
    # escalation ladder's aleatoric+no-context rows (39+29=68) that were
    # flagged since 2026-08-01 to go to direct review, never actually
    # queued until now.
    "active_learning_requeue_v2": _abs("data/hitl/queue_active_learning_requeue_v2.csv"),
    "escalation_aleatoric_review": _abs("data/hitl/queue_escalation_aleatoric_review.csv"),
    "escalation_round8_aleatoric": _abs("data/hitl/queue_escalation_round8_aleatoric.csv"),
    "expanded_entity_val_r1": _abs("data/hitl/queue_expanded_entity_val_r1.csv"),
    # Added 2026-08-13: round9 escalation candidates that made it through
    # the epistemic/aleatoric context test + frontier judge (with unsure
    # option) still unresolved. doubly_unresolved = neither the local
    # ensemble chain-walk nor the frontier judge could resolve them.
    # ensemble_judge_disagreement = local ensemble was confident but the
    # frontier judge said unsure -- real disagreement, cause not fully
    # diagnosed, entity round-robin + margin-ascending order for coverage.
    "round9_doubly_unresolved": _abs("data/hitl/queue_round9_doubly_unresolved_REVIEW.csv"),
    "round9_ensemble_judge_disagreement": _abs("data/hitl/queue_round9_ensemble_judge_disagreement_REVIEW.csv"),
}

# Auto-discovery, added 2026-08-13: any NEW queue_*.csv dropped into
# data/hitl/ gets picked up automatically (Nash's request, so future
# queues don't need a manual code edit + restart to appear). Existing
# hardcoded entries above are left untouched on purpose -- their key
# names are load-bearing (referenced by ?queue= URLs, scripts, bookmarks)
# and a filename-derived key wouldn't always match them anyway (e.g.
# "wikileaks_quality_check" -> queue_wikileaks_stance_quality_check.csv).
# Auto-discovery only fills in files NOT already covered by the dict
# above, and only if they look like an actual rating queue: has both
# 'id' and 'full_text' columns (the two the server code assumes exist
# everywhere -- queue_topic_stance.csv, e.g., uses 'text'/'label' instead
# and would break the UI if served). Filenames containing "BACKUP" are
# skipped on purpose (snapshots, not live queues).
def _discover_queues():
    import glob
    known_paths = set(QUEUES.values())
    hitl_dir = _abs("data/hitl")
    for path in sorted(glob.glob(os.path.join(hitl_dir, "queue_*.csv"))):
        if path in known_paths:
            continue
        base = os.path.basename(path)
        if "BACKUP" in base:
            continue
        try:
            header = pd.read_csv(path, nrows=0).columns
        except Exception:
            continue
        if "id" not in header or "full_text" not in header:
            continue
        key = base[len("queue_"):-len(".csv")]
        if key.endswith("_REVIEW"):
            key = key[:-len("_REVIEW")]
        if key in QUEUES:
            key = base[len("queue_"):-len(".csv")]  # fall back to the un-stripped form on collision
        QUEUES[key] = path
        print(f"Auto-discovered queue '{key}' -> {base}", flush=True)

_discover_queues()

EMPATH_PATH = _abs("data/processed/empath_scores_full_mapped.parquet")
# LOCAL_CONTEXT_DB (built by build_local_context_db.py from the raw
# comment shards Nash confirmed are available locally, data/raw/
# r_conspiracy_comments*.jsonl.gz) is the preferred context source.
# LEXICAL_FULL_PATH is the fallback: the full corpus with parent_id/link_id,
# used when LOCAL_CONTEXT_DB doesn't exist.
LOCAL_CONTEXT_DB = _abs("local_context.duckdb")  # local disk — thumb drive lacks space
LEXICAL_FULL_PATH = _abs("data/processed/lexical_scores_full.parquet")
# Post title/selftext for the "chain reached the submission" case (the
# comments table has no posts data at all). Both files are needed --
# they cover complementary date ranges, confirmed 2026-08-13 building the
# round9 chain-walk (build_round9_thread_chains.py): 9 submissions that
# round9 needed were only in the *2 file, not the main one.
RAW_POSTS_PATHS = [_abs("data/raw/r_conspiracy_posts.jsonl"), _abs("data/raw/r_conspiracy_posts2.jsonl.gz")]
# Local, indexed posts table (build_posts_index.py) -- added 2026-08-14 after
# finding the REAL cause of "sometimes says no context" / general slowness:
# any row whose immediate parent is the submission itself (parent_id starts
# "t3_") fell into _lookup_post()'s raw-file scan below, which reads
# data/raw/*.jsonl(.gz) -- i.e. the USB thumb drive, unindexed. A plain
# COUNT(*) over those two files took over 2 minutes and didn't finish. This
# isn't a rare "reached the top of a long thread" case either -- plenty of
# rows are direct top-level replies to a post, so this was hit constantly,
# not occasionally. LOCAL_POSTS_DB is a one-time local copy (same pattern as
# LOCAL_CONTEXT_DB for comments) -- falls back to the slow raw scan below if
# it hasn't been built yet.
LOCAL_POSTS_DB = _abs("local_posts_index.duckdb")

_LOCAL_CONTEXT_CON = None
_LOCAL_POSTS_CON = None


def _get_context_con():
    """One persistent read-only connection to the 19.5GB local_context.duckdb,
    opened once and reused via cheap per-request cursors -- was previously
    re-opened (duckdb.connect(...)) on every single /api/context call. DuckDB
    connections aren't safe to share directly across concurrent threads
    (ThreadingHTTPServer spins up one per request), but .cursor() gives a
    lightweight, thread-safe view into the same already-open connection, so
    this keeps concurrency-safety while cutting the repeated file-open cost."""
    global _LOCAL_CONTEXT_CON
    if _LOCAL_CONTEXT_CON is None and os.path.exists(LOCAL_CONTEXT_DB):
        _LOCAL_CONTEXT_CON = duckdb.connect(LOCAL_CONTEXT_DB, read_only=True)
        # This machine has 8GB RAM total (see machine_constraints memory) --
        # DuckDB's default memory_limit is a large fraction of detected
        # system RAM, and its buffer pool grows as it caches pages touched
        # by queries with no cap otherwise. Point lookups (WHERE id = ?)
        # against a 19.5GB file don't need much cache to be fast; capping
        # this explicitly avoids DuckDB's own buffer pool being a second,
        # independent source of memory pressure on top of everything else.
        _LOCAL_CONTEXT_CON.execute("PRAGMA memory_limit='1GB'")
    return _LOCAL_CONTEXT_CON


def _get_posts_con():
    global _LOCAL_POSTS_CON
    if _LOCAL_POSTS_CON is None and os.path.exists(LOCAL_POSTS_DB):
        _LOCAL_POSTS_CON = duckdb.connect(LOCAL_POSTS_DB, read_only=True)
        _LOCAL_POSTS_CON.execute("PRAGMA memory_limit='512MB'")
    return _LOCAL_POSTS_CON


def _lookup_post(submission_id):
    """Fast path: the local indexed posts table (see LOCAL_POSTS_DB comment
    above). Falls back to a raw scan of data/raw/*.jsonl(.gz) -- the USB
    thumb drive, unindexed, genuinely slow -- only if the index hasn't been
    built yet."""
    posts_con = _get_posts_con()
    if posts_con is not None:
        res = posts_con.cursor().execute(
            "SELECT title, selftext FROM posts WHERE id = ? LIMIT 1", [submission_id]
        ).fetchone()
        return res if res else (None, None)

    paths = [p for p in RAW_POSTS_PATHS if os.path.exists(p)]
    if not paths:
        return None, None
    con = duckdb.connect()
    paths_literal = "[" + ",".join(f"'{p}'" for p in paths) + "]"
    res = con.execute(f"""
        SELECT title, selftext FROM read_ndjson(
            {paths_literal},
            columns={{'id':'VARCHAR','title':'VARCHAR','selftext':'VARCHAR'}},
            ignore_errors=true
        ) WHERE id = ? LIMIT 1
    """, [submission_id]).fetchone()
    return res if res else (None, None)

# AI-silver rows only ever stored a +-15-word entity window, not the full
# comment (found 2026-08-02 reviewing frontier-judge disagreements) -- 64%
# (506/792) recovered via ai_silver_fulltext_recovery.py's reproduced
# sampling + the ATS pipeline's own already-intact full text. Injected at
# serve-time only (never rewrites a queue CSV in place, since queues may
# have live in-progress ratings) -- matched by (target_entity, full_text)
# since a recovered row's window text is exactly what queues currently
# store as full_text for ai_silver rows.
AI_SILVER_RECOVERED_PATH = _abs("data/processed/ai_silver_fulltext_recovered_combined.csv")
AI_SILVER_RECOVERED = {}
if os.path.exists(AI_SILVER_RECOVERED_PATH):
    try:
        import csv as _csv
        with open(AI_SILVER_RECOVERED_PATH, "r", encoding="utf-8") as f:
            for r in _csv.DictReader(f):
                if r.get("full_text_recovered"):
                    AI_SILVER_RECOVERED[(r.get("target_entity", ""), r.get("text", ""))] = r["full_text_recovered"]
        print(f"Loaded {len(AI_SILVER_RECOVERED)} recovered AI-silver full texts.")
    except Exception as e:
        print(f"Failed to load AI-silver recovered text: {e}")

# IRR (inter-rater-reliability) support, added 2026-07-21.
IRR_QUEUES = {"irr_stance_shared"}
IRR_RESPONSES_DIR = _abs("data/hitl/irr_responses")

# Pre-compiled context cache to bypass heavy parquet searches on VM, added 2026-07-22.
CONTEXT_CACHE = {}
CONTEXT_CACHE_PATH = _abs("data/hitl/context_cache.json")
if os.path.exists(CONTEXT_CACHE_PATH):
    try:
        with open(CONTEXT_CACHE_PATH, "r", encoding="utf-8") as f:
            CONTEXT_CACHE = json.load(f)
        print(f"Loaded context cache with {len(CONTEXT_CACHE)} items.")
    except Exception as e:
        print(f"Failed to load context cache: {e}")


def _irr_response_path(queue, rater):
    safe_rater = "".join(c if c.isalnum() or c in "-_" else "_" for c in rater) or "anonymous"
    return os.path.join(IRR_RESPONSES_DIR, f"{queue}__{safe_rater}.csv")


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1"><title>HITL Rater</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 780px; margin: 20px auto; padding: 0 16px; background:#111; color:#eee; }
  .tabs { margin-bottom: 16px; display:flex; flex-wrap:wrap; gap:6px; }
  .tabs button { padding: 8px 12px; cursor: pointer; background:#222; color:#eee; border:1px solid #444; border-radius:6px; font-size:13px; }
  .tabs button.active { background:#3a6; border-color:#3a6; }
  #progress { color: #999; margin-bottom: 10px; font-size:14px; }
  .nav { margin-bottom: 10px; display:flex; gap:6px; flex-wrap:wrap; }
  .nav button { padding: 10px 16px; cursor:pointer; background:#222; color:#eee; border:1px solid #444; border-radius:6px; font-size:14px; flex:1; min-width:80px; }
  .nav button:disabled { opacity: 0.35; cursor: default; }
  #current_label { color:#9c6; margin-left: 8px; }
  #text { white-space: pre-wrap; background:#1c1c1c; border:1px solid #333; border-radius:8px; padding:14px; line-height:1.6; margin-bottom:12px; min-height: 80px; font-size:15px; overflow-y:auto; }
  #text mark { background:#a60; color:#fff; padding:0 2px; border-radius:3px; }
  .labels { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:10px; }
  .labels button { padding: 14px 12px; cursor:pointer; border-radius:8px; border:1px solid #555; background:#222; color:#eee; font-size:15px; flex:1; min-width:100px; text-align:center; }
  .labels button:active { opacity:0.7; }
  .labels button.selected { outline: 3px solid #9c6; }
  .labels button.kp { background:#274; }
  .labels button.kn { background:#622; }
  textarea { width: 100%; box-sizing:border-box; margin-top:10px; background:#1c1c1c; color:#eee; border:1px solid #333; border-radius:6px; padding:10px; font-size:14px; }
  #done { font-size: 20px; margin-top: 40px; }
  kbd { background:#333; padding:1px 6px; border-radius:4px; font-size:12px; }
  #context_btn { margin-bottom: 10px; padding: 10px 14px; cursor:pointer; background:#333; color:#eee; border:1px solid #555; border-radius:6px; font-size:14px; width:100%; box-sizing:border-box; }
  #context { display:none; white-space: pre-wrap; background:#1a1a24; border:1px solid #335; border-radius:8px; padding:12px; margin-bottom:12px; font-size: 13px; color:#bcd; }
  #context h4 { margin: 0 0 6px 0; color:#89b; }
  @media (max-width: 600px) {
    body { margin: 8px auto; padding: 0 10px; padding-bottom: 140px; }
    #text { font-size:16px; line-height:1.65; max-height:45vh; overflow-y:auto; -webkit-overflow-scrolling:touch; }
    .labels { position:fixed; bottom:0; left:0; right:0; background:#181818; border-top:1px solid #333; padding:10px; gap:6px; margin:0; z-index:100; }
    .labels button { padding: 16px 8px; font-size:15px; min-width:60px; border-radius:10px; }
    .labels button kbd { display:none; }
    .nav button { padding: 12px; font-size:15px; }
    .tabs button { font-size:12px; padding:7px 10px; }
    #progress { font-size:13px; }
    #context_btn { font-size:15px; padding:12px; }
  }
</style></head>
<body>
<div class="tabs" id="tabs"></div>
<div style="margin-bottom:10px; color:#999;">
  Rater name (required for all queues):
  <input id="rater_name" type="text" placeholder="e.g. nash" style="background:#1c1c1c; color:#eee; border:1px solid #333; border-radius:4px; padding:4px 8px; margin-left:6px; outline:none;">
</div>
<div id="progress"></div>
<div class="nav" id="nav"></div>
<button id="context_btn" style="display:none">Load surrounding context (parent + sibling replies)</button>
<div id="context"></div>
<div id="comment_id_display" style="display:none; margin-bottom:8px; font-size:12px; color:#888;"></div>
<div id="frontier_hint" style="display:none; margin-bottom:8px; padding:10px 12px; background:#1a1a24; border:1px solid #335; border-radius:8px; font-size:13px; color:#bcd;"></div>
<div id="target_entity" style="display:none; margin-bottom:8px; font-weight:bold; color:#9c6;"></div>
<div id="text"></div>
<div class="labels" id="labels"></div>
<textarea id="notes" placeholder="notes (optional)" rows="2"></textarea>
<div id="done" style="display:none">All rows in this queue are labeled. Switch queue above.</div>

<script>
// Token management and apiFetch helper
const urlParams = new URLSearchParams(window.location.search);
const urlToken = urlParams.get('token');
if (urlToken) {
  localStorage.setItem('hitl_access_token', urlToken);
  window.history.replaceState({}, document.title, window.location.pathname);
}

function apiFetch(url, options = {}) {
  const token = localStorage.getItem('hitl_access_token') || '';
  const separator = url.includes('?') ? '&' : '?';
  const finalUrl = url + separator + 'token=' + encodeURIComponent(token);
  return fetch(finalUrl, options);
}

const queueNames = QUEUES_JSON;
let current = Object.keys(queueNames)[0];
let rows = [];       // full row list for the current queue
let idx = 0;          // current position in `rows`
let labelCol = 'human_label';

const raterInput = document.getElementById('rater_name');
raterInput.value = localStorage.getItem('hitl_rater_name') || '';
raterInput.addEventListener('input', () => {
  localStorage.setItem('hitl_rater_name', raterInput.value);
  raterInput.style.border = '1px solid #333';
});
function raterName() { return raterInput.value.trim(); }

function renderTabs() {
  const t = document.getElementById('tabs');
  t.innerHTML = '';
  for (const name of Object.keys(queueNames)) {
    const b = document.createElement('button');
    b.textContent = name;
    if (name === current) b.className = 'active';
    b.onclick = () => { current = name; idx = 0; loadQueue(true); };
    t.appendChild(b);
  }
}

function renderNav() {
  const n = document.getElementById('nav');
  n.innerHTML = '';
  const back = document.createElement('button');
  back.textContent = '← Back';
  back.disabled = idx <= 0;
  back.onclick = () => { idx = Math.max(0, idx - 1); showCurrent(); };
  n.appendChild(back);

  const fwd = document.createElement('button');
  fwd.textContent = 'Next →';
  fwd.disabled = idx >= rows.length - 1;
  fwd.onclick = () => { idx = Math.min(rows.length - 1, idx + 1); showCurrent(); };
  n.appendChild(fwd);

  const jumpUnlabeled = document.createElement('button');
  jumpUnlabeled.textContent = 'Jump to next unlabeled';
  jumpUnlabeled.onclick = () => {
    const i = rows.findIndex((r, j) => j > idx && isEmpty(r[labelCol]));
    if (i >= 0) { idx = i; showCurrent(); }
  };
  n.appendChild(jumpUnlabeled);
}

function isEmpty(v) {
  return v === null || v === undefined || v === '' || (typeof v === 'number' && isNaN(v));
}

function renderLabelButtons(selected) {
  const l = document.getElementById('labels');
  l.innerHTML = '';
  let opts = [];
  // Stance (endorsement/hostile/neutral/ambiguous) is the default for
  // every queue in this project except the few explicitly built around a
  // different construct -- inverted 2026-08-13 from a stance-queue
  // allowlist (which silently gave new/auto-discovered queues the wrong
  // buttons) to a non-stance denylist, since stance is actually the
  // common case, not the exception.
  const NON_STANCE_QUEUES = ['maverick_authority', 'personal_experience', 'procedural_skepticism'];
  if (current === 'domain_citation_tier') {
    // Matches the 5-tier link_source_tier taxonomy used everywhere else in
    // the pipeline (run_link_source_tier_regressions.py) minus no_link
    // (not applicable here -- every row already has a real citation).
    opts = [
      ['mainstream_reliable', 'kp', '1'], ['mixed_or_low_reliability', '', '2'],
      ['aggregator_or_platform', '', '3'], ['unmatched_link', 'kn', '4'],
      ['skip_unclear', 'kn', '5']
    ];
  } else if (NON_STANCE_QUEUES.includes(current)) {
    opts = [
      ['positive', 'kp', '1'], ['lean_positive', 'kp', '2'],
      ['negative', 'kn', '3'], ['unsure', '', '4']
    ];
  } else {
    opts = [
      ['endorsement', 'kp', '1'], ['hostile', 'kn', '2'],
      ['neutral', '', '3'], ['ambiguous', '', '4'],
      ['wrong_match', 'kn', '5']
    ];
  }
  for (const [label, cls, key] of opts) {
    const b = document.createElement('button');
    b.className = cls + (label === selected ? ' selected' : '');
    b.innerHTML = label + ' <kbd>' + key + '</kbd>';
    b.onclick = () => submit(label);
    l.appendChild(b);
  }
}

function highlightSpans(text, spansJson, targetEntity) {
  // Try span-based highlights first (precise, pre-computed)
  if (spansJson) {
    let spans;
    try { spans = JSON.parse(spansJson); } catch (e) { spans = null; }
    if (spans && spans.length) {
      spans.sort((a, b) => a.start - b.start);
      let out = '';
      let pos = 0;
      for (const s of spans) {
        if (s.start < pos) continue;
        out += escapeHtml(text.slice(pos, s.start));
        out += '<mark>' + escapeHtml(text.slice(s.start, s.end)) + '</mark>';
        pos = s.end;
      }
      out += escapeHtml(text.slice(pos));
      return out;
    }
  }
  // Fallback: case-insensitive search for the entity name. Tries the full
  // name first (as one phrase); separately, ALSO highlights every
  // individual token (first name, surname, etc.) found anywhere in the
  // text -- not just whichever needle happens to be checked first. Fixed
  // 2026-08-14: the old version picked exactly one needle (full name, or
  // else the first token that matched) and stopped, so a URL slug like
  // "aaron-swartz-was-murdered" (hyphenated, no space -- the full-name
  // phrase check fails) would highlight only "aaron" and never look for
  // "swartz" too, even though it's sitting right there.
  if (!targetEntity) return escapeHtml(text);
  const lower = text.toLowerCase();
  const tokens = targetEntity.split(/\s+/).filter(t => t.length > 3);
  const needles = [targetEntity.toLowerCase()];
  for (const t of tokens) {
    const tl = t.toLowerCase();
    if (!needles.includes(tl)) needles.push(tl);
  }
  // Collect every match for every needle that appears, then merge into
  // non-overlapping spans (longest/earliest wins on overlap, so the full
  // "aaron swartz" phrase pre-empts a separate "aaron" + "swartz" pair
  // when both are present).
  let matches = [];
  for (const n of needles) {
    let pos = 0, idx;
    while ((idx = lower.indexOf(n, pos)) !== -1) {
      matches.push({ start: idx, end: idx + n.length });
      pos = idx + n.length;
    }
  }
  matches.sort((a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start));
  let out = '';
  let pos = 0;
  for (const m of matches) {
    if (m.start < pos) continue;  // overlaps an already-highlighted (longer) span
    out += escapeHtml(text.slice(pos, m.start));
    out += '<mark>' + escapeHtml(text.slice(m.start, m.end)) + '</mark>';
    pos = m.end;
  }
  out += escapeHtml(text.slice(pos));
  return out;
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

let queueRequestId = 0;

async function loadQueue(resetToFirstUnlabeled) {
  renderTabs();
  document.getElementById('context').style.display = 'none';
  document.getElementById('context').innerHTML = '';
  const requestQueue = current;
  const thisRequestId = ++queueRequestId;
  const r = await apiFetch('/api/queue?queue=' + requestQueue + '&rater=' + encodeURIComponent(raterName()));
  const data = await r.json();
  if (thisRequestId !== queueRequestId) return; // a newer request superseded this one
  rows = data.rows;
  labelCol = data.label_col;
  if (rows.length === 0) {
    document.getElementById('done').style.display = 'block';
    document.getElementById('text').style.display = 'none';
    document.getElementById('labels').style.display = 'none';
    return;
  }
  if (resetToFirstUnlabeled) {
    const firstUnlabeled = rows.findIndex(r => isEmpty(r[labelCol]));
    idx = firstUnlabeled >= 0 ? firstUnlabeled : 0;
  }
  showCurrent();
}

function showCurrent() {
  const row = rows[idx];
  const total = rows.length;
  const labeled = rows.filter(r => !isEmpty(r[labelCol])).length;
  document.getElementById('progress').textContent =
    `${current}: ${labeled} / ${total} labeled  |  viewing row ${idx + 1} of ${total}`;
  document.getElementById('text').style.display = 'block';
  document.getElementById('labels').style.display = 'block';
  document.getElementById('done').style.display = 'none';
  if (row.recovered_full_text) {
    // AI-silver rows only ever stored a +-15-word window as full_text --
    // entity_spans were computed against that window, not the recovered
    // full comment, so highlighting would misalign here. Show the
    // recovered full text plain, with the original window (what was
    // actually scored/labeled) underneath for reference.
    document.getElementById('text').innerHTML =
      '<div style="font-size:11px; color:#9c6; margin-bottom:6px; text-transform:uppercase; letter-spacing:0.04em;">recovered full comment (AI-silver row -- originally only a short window)</div>' +
      escapeHtml(row.recovered_full_text) +
      '<div style="font-size:11px; color:#888; margin-top:12px; padding-top:8px; border-top:1px solid #333;">original window used for scoring/labeling: <em>' + escapeHtml(row.full_text) + '</em></div>';
  } else {
    document.getElementById('text').innerHTML = highlightSpans(row.full_text, row.entity_spans, row.target_entity);
  }
  const cidEl = document.getElementById('comment_id_display');
  const cid = row.comment_id || row.id;
  if (cid) {
    cidEl.textContent = 'comment id: ' + cid;
    cidEl.style.display = 'block';
  } else {
    cidEl.style.display = 'none';
  }
  const hintEl = document.getElementById('frontier_hint');
  if (row.frontier_score !== undefined && row.frontier_score !== null) {
    const src = row.source_kind ? ` (${row.source_kind})` : '';
    hintEl.innerHTML = `<strong>Current label: ${row.label}</strong>${src} — frontier judge score <strong>${Number(row.frontier_score).toFixed(2)}</strong> ` +
      `(-1 hostile … +1 endorsement), disagreement magnitude ${row.disagreement !== undefined ? Number(row.disagreement).toFixed(2) : '?'}<br>` +
      `<em>"${row.frontier_reason || ''}"</em>`;
    hintEl.style.display = 'block';
  } else {
    hintEl.style.display = 'none';
  }
  const targetEl = document.getElementById('target_entity');
  if (row.target_entity) {
    targetEl.textContent = 'Rate stance toward: ' + row.target_entity;
    targetEl.style.display = 'block';
  } else {
    targetEl.style.display = 'none';
  }
  document.getElementById('notes').value = row.notes || '';
  renderLabelButtons(row[labelCol]);
  renderNav();

  document.getElementById('context').style.display = 'none';
  document.getElementById('context').innerHTML = '';
  contextDepth = 0;
  const ctxBtn = document.getElementById('context_btn');
  if (row.parent_id) {
    ctxBtn.style.display = 'inline-block';
    ctxBtn.disabled = false;
    ctxBtn.textContent = 'Load surrounding context (parent + sibling replies)';
    ctxBtn.onclick = () => loadContext(row.id);
  } else {
    ctxBtn.style.display = 'none';
  }
}

let contextDepth = 0;

async function loadContext(id) {
  const ctx = document.getElementById('context');
  const ctxBtn = document.getElementById('context_btn');
  ctx.style.display = 'block';
  if (contextDepth === 0) ctx.textContent = 'Loading...';
  contextDepth += 1;
  const r = await apiFetch('/api/context?queue=' + current + '&id=' + encodeURIComponent(id) + '&depth=' + contextDepth);
  const data = await r.json();
  // `levels[0]` is the immediate parent, `levels[1]` its own parent
  // (grandparent), etc. -- oldest-to-newest display order matches how a
  // human would actually read the thread top-down.
  let html = '';
  const levels = data.levels || [];
  for (let i = levels.length - 1; i >= 0; i--) {
    const label = i === 0 ? 'Parent comment (being replied to):' : `Ancestor (${i + 1} levels up):`;
    html += '<h4>' + label + '</h4>' + escapeHtml(levels[i]) + '<br><br>';
  }
  if (data.post_title || data.post_selftext) {
    html += '<h4>Post (top of thread):</h4>';
    if (data.post_title) html += '<strong>' + escapeHtml(data.post_title) + '</strong><br>';
    if (data.post_selftext) html += escapeHtml(data.post_selftext) + '<br>';
    html += '<br>';
  }
  if (!levels.length && !data.post_title && data.is_toplevel) {
    html += '<h4>Parent:</h4>(top-level reply to the post — no parent comment)<br><br>';
  } else if (!levels.length && !data.post_title) {
    html += '<h4>Parent:</h4>(nested reply — parent comment not in local corpus)<br><br>';
  }
  if (data.sibling_texts && data.sibling_texts.length) {
    html += '<h4>Other replies to the same parent:</h4>';
    for (const s of data.sibling_texts) {
      html += '• ' + escapeHtml(s.slice(0, 300)) + '<br><br>';
    }
  }
  ctx.innerHTML = html;
  if (data.chain_exhausted) {
    ctxBtn.textContent = 'No more context available (reached top of thread)';
    ctxBtn.disabled = true;
  } else {
    ctxBtn.textContent = 'Load more context (go up one more level)';
    ctxBtn.disabled = false;
  }
}

async function submit(label) {
  const rater = raterName();
  if (!rater) {
    const input = document.getElementById('rater_name');
    input.focus();
    input.style.border = '2px solid #f55';
    input.placeholder = 'ENTER NAME FIRST!';
    setTimeout(() => { input.style.border = '1px solid #333'; }, 2000);
    return;
  }
  const row = rows[idx];
  const notes = document.getElementById('notes').value;
  row[labelCol] = label;
  row.notes = notes;
  await apiFetch('/api/label', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({queue: current, id: row.id, label_col: labelCol, human_label: label, notes: notes, rater: rater})
  });
  renderLabelButtons(label);
  // auto-advance only if this was the first time this row was labeled AND we're at the frontier
  if (idx === rows.length - 1 || isEmpty(rows[idx + 1] ? rows[idx + 1][labelCol] : undefined)) {
    if (idx < rows.length - 1) { idx += 1; showCurrent(); }
  }
  document.getElementById('progress').textContent =
    `${current}: ${rows.filter(r => !isEmpty(r[labelCol])).length} / ${rows.length} labeled  |  viewing row ${idx + 1} of ${rows.length}`;
}

document.addEventListener('keydown', (e) => {
  if (!rows.length) return;
  // FIX 2026-07-17: don't hijack keystrokes typed into the notes box,
  // and ignore anything with a modifier held (browser/OS shortcuts).
  const active = document.activeElement;
  if (active && (active.tagName === 'TEXTAREA' || active.tagName === 'INPUT')) return;
  if (e.metaKey || e.ctrlKey || e.altKey) return;

  let map = {};
  const NON_STANCE_QUEUES = ['maverick_authority', 'personal_experience', 'procedural_skepticism'];
  if (current === 'domain_citation_tier') {
    map = {'1': 'mainstream_reliable', '2': 'mixed_or_low_reliability', '3': 'aggregator_or_platform', '4': 'unmatched_link', '5': 'skip_unclear'};
  } else if (NON_STANCE_QUEUES.includes(current)) {
    map = {'1': 'positive', '2': 'lean_positive', '3': 'negative', '4': 'unsure'};
  } else {
    map = {'1': 'endorsement', '2': 'hostile', '3': 'neutral', '4': 'ambiguous', '5': 'wrong_match'};
  }
  if (map[e.key]) submit(map[e.key]);
  if (e.key === 'ArrowLeft' && idx > 0) { idx -= 1; showCurrent(); }
  if (e.key === 'ArrowRight' && idx < rows.length - 1) { idx += 1; showCurrent(); }
});

loadQueue(true);
</script>
</body></html>"""

LOGIN_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>HITL Rater - Access Required</title>
<style>
  body { font-family: -apple-system, sans-serif; background:#111; color:#eee; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
  .login-card { background: #1c1c1c; border: 1px solid #333; border-radius: 12px; padding: 30px; max-width: 380px; width: 100%; box-shadow: 0 8px 24px rgba(0,0,0,0.5); text-align: center; }
  h2 { margin-top: 0; color: #3a6; font-size: 22px; }
  p { color: #999; font-size: 14px; margin-bottom: 20px; }
  input { width: 100%; box-sizing: border-box; background: #222; color: #eee; border: 1px solid #444; border-radius: 6px; padding: 12px; font-size: 14px; margin-bottom: 16px; outline: none; border-color:#444; }
  input:focus { border-color: #3a6; }
  button { width: 100%; padding: 12px; font-weight: bold; background: #3a6; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; transition: background 0.2s; }
  button:hover { background: #2c5; }
  .error { color: #f55; font-size: 13px; margin-top: 10px; display: none; }
</style></head>
<body>
<div class="login-card">
  <h2>HITL Rater</h2>
  <p>Please enter the shared access token to continue.</p>
  <input id="token_input" type="password" placeholder="Access Token" autofocus>
  <button onclick="submitToken()">Submit</button>
  <div id="error" class="error">Invalid token. Please try again.</div>
</div>
<script>
  function submitToken() {
    const token = document.getElementById('token_input').value.trim();
    if (!token) return;
    localStorage.setItem('hitl_access_token', token);
    window.location.href = '/?token=' + encodeURIComponent(token);
  }
  document.getElementById('token_input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') submitToken();
  });
  // If we were redirected here with an error flag, show the error
  if (window.location.search.includes('error=1')) {
    document.getElementById('error').style.display = 'block';
  }
</script>
</body></html>"""


_DF_CACHE = {}  # path -> (mtime, df) -- avoids re-parsing a queue CSV on every
# request (e.g. every /api/context click) when it hasn't changed on disk.
# Safe: the only write path (do_POST's /api/label handler) saves via
# df.to_csv(path), which updates the file's mtime, so the next load_df()
# call for that path naturally sees a cache miss and reloads.


def load_df(path):
    mtime = os.path.getmtime(path)
    cached = _DF_CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    df = pd.read_csv(path)
    # A queue CSV whose human_stance/human_label, notes, or rater_id column
    # is entirely empty gets inferred as float64 (all-NaN) by read_csv --
    # writing a string label into that column then raises
    # "TypeError: Invalid value 'X' for dtype 'float64'" deep in pandas'
    # setitem path, which crashes the request handler with NO response
    # sent (net::ERR_EMPTY_RESPONSE client-side). Found 2026-08-13 on the
    # freshly-built round9 queues, whose label columns start fully blank.
    # Force these three known write-targets to object dtype unconditionally
    # so this can't recur for any future queue in the same state.
    for col in ("human_stance", "human_label", "notes", "rater_id"):
        if col in df.columns:
            df[col] = df[col].astype(object)
    _DF_CACHE[path] = (mtime, df)
    return df


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def is_authorized(self):
        if not TOKEN:
            return True
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        token_val = qs.get("token", [None])[0]
        if not token_val:
            token_val = self.headers.get("X-Access-Token")
        return token_val == TOKEN

    def do_GET(self):
        parsed = urlparse(self.path)
        if TOKEN and not self.is_authorized():
            if parsed.path == "/":
                # Serve the login page
                body = LOGIN_PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            else:
                self._json({"error": "unauthorized"}, 403)
                return

        if parsed.path == "/":
            qs = parse_qs(parsed.query)
            queue_param = qs.get("queue", [None])[0]
            if queue_param and queue_param in QUEUES:
                queues_to_serve = {queue_param: True}
            else:
                queues_to_serve = {k: True for k in QUEUES}
            html = PAGE.replace("QUEUES_JSON", json.dumps(queues_to_serve))
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif parsed.path == "/api/queue":
            qs = parse_qs(parsed.query)
            queue = qs.get("queue", [None])[0]
            rater = qs.get("rater", [None])[0]
            path = QUEUES.get(queue)
            if not path:
                self._json({"error": "unknown queue"}, 400)
                return
            # If the queue file doesn't exist yet, we can't load it (graceful fail)
            if not os.path.exists(path):
                self._json({"rows": [], "label_col": "human_label"})
                return
            df = load_df(path)
            col = "human_stance" if "human_stance" in df.columns else "human_label"
            if queue in IRR_QUEUES:
                df[col] = None
                df["notes"] = None
                resp_path = _irr_response_path(queue, rater) if rater else None
                if resp_path and os.path.exists(resp_path):
                    resp = pd.read_csv(resp_path)
                    resp_map = {str(r["id"]): (r.get(col), r.get("notes")) for _, r in resp.iterrows()}
                    for i, row in df.iterrows():
                        if str(row["id"]) in resp_map:
                            lbl, nts = resp_map[str(row["id"])]
                            df.at[i, col] = lbl
                            df.at[i, "notes"] = nts
            df = df.astype(object).where(pd.notna(df), None)
            rows = df.to_dict(orient="records")
            if AI_SILVER_RECOVERED and "target_entity" in df.columns and "full_text" in df.columns:
                for r in rows:
                    hit = AI_SILVER_RECOVERED.get((r.get("target_entity"), r.get("full_text")))
                    if hit:
                        r["recovered_full_text"] = hit
            self._json({"rows": rows, "label_col": col})

        elif parsed.path == "/api/context":
            qs = parse_qs(parsed.query)
            queue = qs.get("queue", [None])[0]
            comment_id = qs.get("id", [None])[0]
            try:
                depth = max(1, min(15, int(qs.get("depth", ["1"])[0])))
            except (TypeError, ValueError):
                depth = 1
            path = QUEUES.get(queue)
            if not path or not comment_id:
                self._json({"error": "bad request"}, 400)
                return
            if depth == 1 and CONTEXT_CACHE and str(comment_id) in CONTEXT_CACHE:
                cached = dict(CONTEXT_CACHE[str(comment_id)])
                cached.setdefault("levels", [])
                cached.setdefault("chain_exhausted", False)
                self._json(cached)
                return
            if not os.path.exists(path):
                self._json({"parent_text": None, "sibling_texts": [], "levels": [], "chain_exhausted": True})
                return
            df = load_df(path)
            row = df[df["id"].astype(str) == str(comment_id)]
            if row.empty or "parent_id" not in df.columns:
                self._json({"parent_text": None, "sibling_texts": [], "levels": [], "chain_exhausted": True})
                return
            r = row.iloc[0]
            parent_id_raw = str(r.get("parent_id", "") or "")
            link_id_raw = str(r.get("link_id", "") or "")
            sibling_texts = []
            # `levels`: ancestor texts from the immediate parent (levels[0])
            # upward, one entry per depth requested. Walks further each
            # time the frontend asks for a higher `depth`, reusing the same
            # comment-lookup this project's chain-walking training code
            # uses (LOCAL_CONTEXT_DB's full 44M-row comments table, or the
            # lexical parquet fallback) -- added 2026-08-13 so "Load more
            # context" can go past the immediate parent instead of stopping
            # there, matching what round9's epistemic/aleatoric chain-walk
            # already does offline.
            levels = []
            post_title = None
            post_selftext = None
            chain_exhausted = False
            try:
                use_db = os.path.exists(LOCAL_CONTEXT_DB)
                if use_db:
                    con = _get_context_con().cursor()
                    def _lookup_comment(cid):
                        res = con.execute(
                            "SELECT text, parent_id FROM comments WHERE id = ? LIMIT 1", [cid]
                        ).fetchone()
                        return res if res else None
                    def _lookup_siblings(pid, exclude_id):
                        return [s[0] for s in con.execute(
                            "SELECT DISTINCT text FROM comments WHERE parent_id = ? AND id != ? LIMIT 5",
                            [pid, exclude_id],
                        ).fetchall()]
                else:
                    # Fallback: query the full lexical parquet (slower but no pre-build needed)
                    pcon = duckdb.connect()
                    def _lookup_comment(cid):
                        res = pcon.execute(
                            f"SELECT text, parent_id FROM read_parquet('{LEXICAL_FULL_PATH}') WHERE id = ? LIMIT 1", [cid]
                        ).fetchone()
                        return res if res else None
                    def _lookup_siblings(pid, exclude_id):
                        return [s[0] for s in pcon.execute(
                            f"SELECT DISTINCT text FROM read_parquet('{LEXICAL_FULL_PATH}') WHERE parent_id = ? AND id != ? LIMIT 5",
                            [pid, exclude_id],
                        ).fetchall()]

                if parent_id_raw:
                    sibling_texts = _lookup_siblings(parent_id_raw, str(comment_id))

                cur_parent = parent_id_raw
                for _ in range(depth):
                    if not cur_parent:
                        chain_exhausted = True
                        break
                    if cur_parent.startswith("t3_"):
                        title, selftext = _lookup_post(cur_parent[3:])
                        post_title, post_selftext = title, selftext
                        chain_exhausted = True
                        break
                    if not cur_parent.startswith("t1_"):
                        chain_exhausted = True
                        break
                    found = _lookup_comment(cur_parent[3:])
                    if not found:
                        chain_exhausted = True
                        break
                    text, next_parent = found
                    levels.append(text)
                    cur_parent = str(next_parent or "")
                if not chain_exhausted and (not cur_parent or cur_parent.startswith("t3_")):
                    # loop ended because we hit `depth`, but the NEXT level
                    # would be the post or a dead end -- surface that now so
                    # the frontend can show it without one more round-trip,
                    # and mark exhausted since there's genuinely nothing
                    # further to load either way.
                    if cur_parent.startswith("t3_"):
                        title, selftext = _lookup_post(cur_parent[3:])
                        post_title, post_selftext = title, selftext
                    chain_exhausted = True
            except Exception as e:
                self._json({"error": str(e)}, 500)
                return
            is_toplevel = (not parent_id_raw) or (parent_id_raw == link_id_raw) or parent_id_raw.startswith("t3_")
            parent_text = levels[0] if levels else None
            self._json({
                "parent_text": parent_text, "sibling_texts": sibling_texts, "is_toplevel": is_toplevel,
                "levels": levels, "post_title": post_title, "post_selftext": post_selftext,
                "chain_exhausted": chain_exhausted,
            })

        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if TOKEN and not self.is_authorized():
            self._json({"error": "unauthorized"}, 403)
            return

        parsed = urlparse(self.path)
        if parsed.path == "/api/label":
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            queue = payload["queue"]
            path = QUEUES.get(queue)
            if not path:
                self._json({"error": "unknown queue"}, 400)
                return
            # If the queue directory doesn't exist, create it
            os.makedirs(os.path.dirname(path), exist_ok=True)
            col = payload.get("label_col") or "human_label"
            if queue in IRR_QUEUES:
                rater = (payload.get("rater") or "").strip()
                if not rater:
                    self._json({"error": "rater name required for IRR queues"}, 400)
                    return
                os.makedirs(IRR_RESPONSES_DIR, exist_ok=True)
                resp_path = _irr_response_path(queue, rater)
                resp = pd.read_csv(resp_path) if os.path.exists(resp_path) else pd.DataFrame(columns=["id", col, "notes"])
                mask = resp["id"].astype(str) == str(payload["id"])
                if mask.any():
                    resp.loc[mask, col] = payload["human_label"]
                    resp.loc[mask, "notes"] = payload.get("notes", "")
                else:
                    new_row = {"id": payload["id"], col: payload["human_label"], "notes": payload.get("notes", "")}
                    resp = pd.concat([resp, pd.DataFrame([new_row])], ignore_index=True)
                resp.to_csv(resp_path, index=False)
                self._json({"ok": True})
                return

            df = load_df(path)
            if "rater_id" not in df.columns:
                df["rater_id"] = None
            mask = df["id"].astype(str) == str(payload["id"])
            df.loc[mask, col] = payload["human_label"]
            df.loc[mask, "notes"] = payload.get("notes", "")
            df.loc[mask, "rater_id"] = (payload.get("rater") or "").strip()
            df.to_csv(path, index=False)
            self._json({"ok": True})
        else:
            self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8420, help="Port to run on (default: 8420)")
    parser.add_argument("--token", default="", help="Shared secret token for access safety")
    args = parser.parse_args()

    HOST = args.host
    PORT = args.port
    TOKEN = args.token

    print(f"HITL rater running at http://{HOST}:{PORT}")
    if TOKEN:
        print("Token protection enabled.")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
