"""Minimal local HITL rating tool — no external deps beyond pandas/stdlib/duckdb.

Serves each queue's rows, writes `human_label`/`human_stance` and `notes`
straight back to the source CSV after every submission (so nothing is
lost if the browser or server dies mid-session).

Usage:
    python src/hitl_rater.py
    # then open http://localhost:8420 in a browser

Queues are hardcoded below — edit QUEUES to add/remove files.

CHANGELOG 2026-07-17 (Nash's feedback on real usage):
  1. Fixed accidental-rating bug: the old keydown handler fired on ANY
     keypress anywhere on the page, including while typing in the notes
     textarea (typing a note containing "2" would submit a "hostile"
     rating mid-sentence) or from stray keystrokes after switching tabs
     and back. Now ignores keydown when the notes textarea has focus or
     when any modifier key is held.
  2. Added Back/Next navigation across the WHOLE queue (not just "next
     unlabeled") so an accidental rating can be found and corrected --
     previously there was no way to revisit an already-labeled row.
  3. Added entity-span highlighting (queues with an `entity_spans`
     column, currently just consensus_stance) -- long comments with
     multiple entities now show which mention is the actual rating
     target via <mark> highlighting, while still showing the full
     comment for context.
  4. Added on-demand "Load context" button (queues with `parent_id`/
     `link_id` columns) -- fetches the parent comment being replied to
     and a few sibling replies to the same parent, so a rater can check
     whether the target comment is quoting/responding to something that
     changes its interpretation (sarcasm, quotation, etc). Fetched live
     via DuckDB against the raw corpus, not preloaded (keeps the tool
     fast by default, only queries when asked).
"""
import json
import os
import duckdb
import pandas as pd
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

PORT = 8420

# Anchored to the repo root via this file's own location, not the
# process's CWD -- this file has been launched both as
# `python3.12 src/hitl_rater.py` (from the repo root, per README.md) and
# as `cd src && python hitl_rater.py` (Nash's actual habit), and a
# relative path only works for one of those. Resolving from __file__
# makes it work the same way regardless of where it's launched from.
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
    "wikileaks_quality_check": _abs("data/hitl/queue_wikileaks_stance_quality_check.csv"),
    "assange_quality_check": _abs("data/hitl/queue_assange_stance_quality_check.csv"),
    "snowden_quality_check": _abs("data/hitl/queue_snowden_stance_quality_check.csv"),
    "greenwald_quality_check": _abs("data/hitl/queue_greenwald_stance_quality_check.csv"),
    "jones_short_quality_check": _abs("data/hitl/queue_jones_short_stance_quality_check.csv"),
}

EMPATH_PATH = _abs("data/processed/empath_scores_full.parquet")

# IRR (inter-rater-reliability) support, added 2026-07-21. Queue names
# listed here route submissions to a PER-RATER response file
# (data/hitl/irr_responses/{queue}__{rater}.csv) instead of writing
# directly into the master queue CSV -- so multiple raters labeling the
# SAME blind sample never collide/overwrite each other, and never see
# each other's (or Nash's original) answers. Currently empty -- populate
# once an actual IRR blind-sample queue exists (see
# handoff/task_irr_sample_builder.md) and is added to QUEUES above.
# Queues NOT in this set keep the original single-rater behavior exactly
# as before (write straight to the source CSV) -- this is purely additive,
# no change to any existing queue's behavior.
IRR_QUEUES = set()
IRR_RESPONSES_DIR = _abs("data/hitl/irr_responses")


def _irr_response_path(queue, rater):
    safe_rater = "".join(c if c.isalnum() or c in "-_" else "_" for c in rater) or "anonymous"
    return os.path.join(IRR_RESPONSES_DIR, f"{queue}__{safe_rater}.csv")

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>HITL Rater</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 780px; margin: 40px auto; padding: 0 20px; background:#111; color:#eee; }
  .tabs { margin-bottom: 20px; }
  .tabs button { padding: 8px 14px; margin-right: 8px; cursor: pointer; background:#222; color:#eee; border:1px solid #444; border-radius:6px; }
  .tabs button.active { background:#3a6; border-color:#3a6; }
  #progress { color: #999; margin-bottom: 12px; }
  .nav { margin-bottom: 10px; }
  .nav button { padding: 6px 12px; margin-right: 8px; cursor:pointer; background:#222; color:#eee; border:1px solid #444; border-radius:6px; }
  .nav button:disabled { opacity: 0.35; cursor: default; }
  #current_label { color:#9c6; margin-left: 8px; }
  #text { white-space: pre-wrap; background:#1c1c1c; border:1px solid #333; border-radius:8px; padding:18px; line-height:1.5; margin-bottom:16px; min-height: 120px; }
  #text mark { background:#a60; color:#fff; padding:0 2px; border-radius:3px; }
  .labels button { padding: 10px 16px; margin: 4px 6px 4px 0; cursor:pointer; border-radius:6px; border:1px solid #555; background:#222; color:#eee; font-size:14px; }
  .labels button:hover { background:#333; }
  .labels button.selected { outline: 2px solid #9c6; }
  .labels button.kp { background:#274; }
  .labels button.kn { background:#622; }
  textarea { width: 100%; box-sizing:border-box; margin-top:14px; background:#1c1c1c; color:#eee; border:1px solid #333; border-radius:6px; padding:10px; }
  #done { font-size: 20px; margin-top: 40px; }
  kbd { background:#333; padding:1px 6px; border-radius:4px; }
  #context_btn { margin-bottom: 12px; padding: 8px 14px; cursor:pointer; background:#333; color:#eee; border:1px solid #555; border-radius:6px; }
  #context { display:none; white-space: pre-wrap; background:#1a1a24; border:1px solid #335; border-radius:8px; padding:14px; margin-bottom:16px; font-size: 13px; color:#bcd; }
  #context h4 { margin: 0 0 6px 0; color:#89b; }
</style></head>
<body>
<div class="tabs" id="tabs"></div>
<div style="margin-bottom:10px; color:#999;">
  Rater name (only used for IRR queues, ignored otherwise):
  <input id="rater_name" type="text" placeholder="e.g. nash" style="background:#1c1c1c; color:#eee; border:1px solid #333; border-radius:4px; padding:4px 8px; margin-left:6px;">
</div>
<div id="progress"></div>
<div class="nav" id="nav"></div>
<button id="context_btn" style="display:none">Load surrounding context (parent + sibling replies)</button>
<div id="context"></div>
<div id="target_entity" style="display:none; margin-bottom:8px; font-weight:bold; color:#9c6;"></div>
<div id="text"></div>
<div class="labels" id="labels"></div>
<textarea id="notes" placeholder="notes (optional)" rows="2"></textarea>
<div id="done" style="display:none">All rows in this queue are labeled. Switch queue above.</div>

<script>
const queueNames = QUEUES_JSON;
let current = Object.keys(queueNames)[0];
let rows = [];       // full row list for the current queue
let idx = 0;          // current position in `rows`
let labelCol = 'human_label';

const raterInput = document.getElementById('rater_name');
raterInput.value = localStorage.getItem('hitl_rater_name') || '';
raterInput.addEventListener('input', () => localStorage.setItem('hitl_rater_name', raterInput.value));
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
  const STANCE_QUEUES = ['consensus_stance', 'maverick_stance', 'consensus_stance_politics', 'maverick_stance_politics',
    'maverick_stance_round2', 'maverick_stance_round3', 'maverick_stance_round4', 'maverick_stance_round5',
    'maverick_stance_round6', 'maverick_stance_round7', 'wikileaks_quality_check', 'assange_quality_check',
    'snowden_quality_check', 'greenwald_quality_check', 'jones_short_quality_check'];
  if (STANCE_QUEUES.includes(current)) {
    opts = [
      ['endorsement', 'kp', '1'], ['hostile', 'kn', '2'],
      ['neutral', '', '3'], ['ambiguous', '', '4'],
      ['wrong_match', 'kn', '5']
    ];
  } else {
    opts = [
      ['positive', 'kp', '1'], ['lean_positive', 'kp', '2'],
      ['negative', 'kn', '3'], ['unsure', '', '4']
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

function highlightSpans(text, spansJson) {
  if (!spansJson) return escapeHtml(text);
  let spans;
  try { spans = JSON.parse(spansJson); } catch (e) { return escapeHtml(text); }
  if (!spans || !spans.length) return escapeHtml(text);
  spans.sort((a, b) => a.start - b.start);
  let out = '';
  let pos = 0;
  for (const s of spans) {
    if (s.start < pos) continue; // skip overlapping
    out += escapeHtml(text.slice(pos, s.start));
    out += '<mark>' + escapeHtml(text.slice(s.start, s.end)) + '</mark>';
    pos = s.end;
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
  // Guard against out-of-order responses: if tabs are switched quickly, a
  // slower earlier request can resolve AFTER a faster later one and
  // silently overwrite it -- the tab button shows the queue you clicked,
  // but the content is whichever response happened to arrive last, not
  // whichever was requested last. Only apply a response if it's still the
  // most recently issued request by the time it comes back.
  const requestQueue = current;
  const thisRequestId = ++queueRequestId;
  const r = await fetch('/api/queue?queue=' + requestQueue + '&rater=' + encodeURIComponent(raterName()));
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
  document.getElementById('text').innerHTML = highlightSpans(row.full_text, row.entity_spans);
  const targetEl = document.getElementById('target_entity');
  if (row.target_entity) {
    targetEl.textContent = 'This comment mentions multiple entities -- rate stance toward: ' + row.target_entity;
    targetEl.style.display = 'block';
  } else {
    targetEl.style.display = 'none';
  }
  document.getElementById('notes').value = row.notes || '';
  renderLabelButtons(row[labelCol]);
  renderNav();

  document.getElementById('context').style.display = 'none';
  document.getElementById('context').innerHTML = '';
  const ctxBtn = document.getElementById('context_btn');
  if (row.parent_id) {
    ctxBtn.style.display = 'inline-block';
    ctxBtn.onclick = () => loadContext(row.id);
  } else {
    ctxBtn.style.display = 'none';
  }
}

async function loadContext(id) {
  const ctx = document.getElementById('context');
  ctx.style.display = 'block';
  ctx.textContent = 'Loading...';
  const r = await fetch('/api/context?queue=' + current + '&id=' + encodeURIComponent(id));
  const data = await r.json();
  let html = '';
  if (data.parent_text) {
    html += '<h4>Parent comment (being replied to):</h4>' + escapeHtml(data.parent_text) + '<br><br>';
  } else {
    html += '<h4>Parent:</h4>(top-level reply to the post, or parent not found)<br><br>';
  }
  if (data.sibling_texts && data.sibling_texts.length) {
    html += '<h4>Other replies to the same parent:</h4>';
    for (const s of data.sibling_texts) {
      html += '• ' + escapeHtml(s.slice(0, 300)) + '<br><br>';
    }
  }
  ctx.innerHTML = html;
}

async function submit(label) {
  const row = rows[idx];
  const notes = document.getElementById('notes').value;
  row[labelCol] = label;
  row.notes = notes;
  await fetch('/api/label', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({queue: current, id: row.id, label_col: labelCol, human_label: label, notes: notes, rater: raterName()})
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
  const STANCE_QUEUES = ['consensus_stance', 'maverick_stance', 'consensus_stance_politics', 'maverick_stance_politics',
    'maverick_stance_round2', 'maverick_stance_round3', 'maverick_stance_round4', 'maverick_stance_round5',
    'maverick_stance_round6', 'maverick_stance_round7', 'wikileaks_quality_check', 'assange_quality_check',
    'snowden_quality_check', 'greenwald_quality_check', 'jones_short_quality_check'];
  if (STANCE_QUEUES.includes(current)) {
    map = {'1': 'endorsement', '2': 'hostile', '3': 'neutral', '4': 'ambiguous', '5': 'wrong_match'};
  } else {
    map = {'1': 'positive', '2': 'lean_positive', '3': 'negative', '4': 'unsure'};
  }
  if (map[e.key]) submit(map[e.key]);
  if (e.key === 'ArrowLeft' && idx > 0) { idx -= 1; showCurrent(); }
  if (e.key === 'ArrowRight' && idx < rows.length - 1) { idx += 1; showCurrent(); }
});

loadQueue(true);
</script>
</body></html>"""


def load_df(path):
    return pd.read_csv(path)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        # allow_nan=False: fail loudly with a server-side traceback if a
        # non-standard-JSON float (NaN/Infinity) ever leaks into a response,
        # instead of silently shipping invalid JSON that the browser's
        # strict JSON.parse() then rejects with no visible error on this
        # side at all (exactly what happened with the maverick_stance bug
        # this was added alongside).
        body = json.dumps(obj, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            html = PAGE.replace("QUEUES_JSON", json.dumps({k: True for k in QUEUES}))
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
            df = load_df(path)
            col = "human_stance" if "human_stance" in df.columns else "human_label"
            if queue in IRR_QUEUES:
                # Blind base rows -- the master file's label column is never
                # read (or written) for IRR queues, only this rater's own
                # response file is, so no rater ever sees anyone else's answer.
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
            # BUG FIXED 2026-07-20: `df.where(pd.notna(df), None)` doesn't
            # actually put None into a float64 column -- pandas silently
            # coerces it right back to np.nan (a well-known gotcha; float
            # columns can't natively hold Python None). A freshly-generated,
            # zero-rated queue (e.g. maverick_stance before any rating) has
            # its human_stance/notes columns read in as all-NaN float64, so
            # this never took effect for it. The leftover float NaN then hit
            # json.dumps, which serializes it as the bareword `NaN` -- valid
            # for Python's json module but not standard JSON, so the
            # browser's strict JSON.parse() threw and silently aborted the
            # whole queue load (every row, not just some). Casting to
            # object dtype first makes the None substitution actually stick.
            df = df.astype(object).where(pd.notna(df), None)
            self._json({"rows": df.to_dict(orient="records"), "label_col": col})

        elif parsed.path == "/api/context":
            qs = parse_qs(parsed.query)
            queue = qs.get("queue", [None])[0]
            comment_id = qs.get("id", [None])[0]
            path = QUEUES.get(queue)
            if not path or not comment_id:
                self._json({"error": "bad request"}, 400)
                return
            df = load_df(path)
            row = df[df["id"].astype(str) == str(comment_id)]
            if row.empty or "parent_id" not in df.columns:
                self._json({"parent_text": None, "sibling_texts": []})
                return
            r = row.iloc[0]
            parent_id_raw = str(r.get("parent_id", "") or "")
            link_id_raw = str(r.get("link_id", "") or "")
            parent_text = None
            sibling_texts = []
            try:
                con = duckdb.connect()
                if parent_id_raw and parent_id_raw != link_id_raw and parent_id_raw.startswith("t1_"):
                    parent_comment_id = parent_id_raw[3:]
                    res = con.execute(
                        f"SELECT text FROM read_parquet('{EMPATH_PATH}') WHERE id = ? LIMIT 1",
                        [parent_comment_id],
                    ).fetchone()
                    if res:
                        parent_text = res[0]
                if parent_id_raw:
                    sib = con.execute(
                        f"""SELECT DISTINCT text FROM read_parquet('{EMPATH_PATH}')
                            WHERE parent_id = ? AND id != ? LIMIT 5""",
                        [parent_id_raw, str(comment_id)],
                    ).fetchall()
                    sibling_texts = [s[0] for s in sib]
            except Exception as e:
                self._json({"error": str(e)}, 500)
                return
            self._json({"parent_text": parent_text, "sibling_texts": sibling_texts})

        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/label":
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            queue = payload["queue"]
            path = QUEUES.get(queue)
            if not path:
                self._json({"error": "unknown queue"}, 400)
                return
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
            mask = df["id"].astype(str) == str(payload["id"])
            df.loc[mask, col] = payload["human_label"]
            df.loc[mask, "notes"] = payload.get("notes", "")
            df.to_csv(path, index=False)
            self._json({"ok": True})
        else:
            self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    print(f"HITL rater running at http://localhost:{PORT}")
    HTTPServer(("localhost", PORT), Handler).serve_forever()
