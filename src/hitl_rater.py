"""Minimal local HITL rating tool — no external deps beyond pandas/stdlib.

Serves each queue's unlabeled rows one at a time, writes `human_label` and
`notes` straight back to the source CSV after every submission (so nothing
is lost if the browser or server dies mid-session).

Usage:
    python src/hitl_rater.py
    # then open http://localhost:8420 in a browser

Queues are hardcoded below — edit QUEUES to add/remove files.
"""
import json
import pandas as pd
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

PORT = 8420

QUEUES = {
    "personal_experience": "data/hitl/queue_personal_experience.csv",
    "procedural_skepticism": "data/hitl/queue_procedural_skepticism.csv",
    "maverick_authority": "data/hitl/queue_maverick_authority.csv",
}

LABEL_OPTIONS = ["positive", "lean_positive", "negative", "unsure"]

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>HITL Rater</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 780px; margin: 40px auto; padding: 0 20px; background:#111; color:#eee; }
  .tabs { margin-bottom: 20px; }
  .tabs button { padding: 8px 14px; margin-right: 8px; cursor: pointer; background:#222; color:#eee; border:1px solid #444; border-radius:6px; }
  .tabs button.active { background:#3a6; border-color:#3a6; }
  #progress { color: #999; margin-bottom: 12px; }
  #text { white-space: pre-wrap; background:#1c1c1c; border:1px solid #333; border-radius:8px; padding:18px; line-height:1.5; margin-bottom:16px; min-height: 120px; }
  .labels button { padding: 10px 16px; margin: 4px 6px 4px 0; cursor:pointer; border-radius:6px; border:1px solid #555; background:#222; color:#eee; font-size:14px; }
  .labels button:hover { background:#333; }
  .labels button.kp { background:#274; }
  .labels button.kn { background:#622; }
  textarea { width: 100%; box-sizing:border-box; margin-top:14px; background:#1c1c1c; color:#eee; border:1px solid #333; border-radius:6px; padding:10px; }
  #done { font-size: 20px; margin-top: 40px; }
  kbd { background:#333; padding:1px 6px; border-radius:4px; }
</style></head>
<body>
<div class="tabs" id="tabs"></div>
<div id="progress"></div>
<div id="text"></div>
<div class="labels" id="labels"></div>
<textarea id="notes" placeholder="notes (optional)" rows="2"></textarea>
<div id="done" style="display:none">All rows in this queue are labeled. Switch queue above.</div>

<script>
const queues = QUEUES_JSON;
let current = Object.keys(queues)[0];
let row = null;

function renderTabs() {
  const t = document.getElementById('tabs');
  t.innerHTML = '';
  for (const name of Object.keys(queues)) {
    const b = document.createElement('button');
    b.textContent = name;
    if (name === current) b.className = 'active';
    b.onclick = () => { current = name; loadNext(); };
    t.appendChild(b);
  }
}

function renderLabelButtons() {
  const l = document.getElementById('labels');
  l.innerHTML = '';
  const opts = [
    ['positive', 'kp', '1'], ['lean_positive', 'kp', '2'],
    ['negative', 'kn', '3'], ['unsure', '', '4']
  ];
  for (const [label, cls, key] of opts) {
    const b = document.createElement('button');
    b.className = cls;
    b.innerHTML = label + ' <kbd>' + key + '</kbd>';
    b.onclick = () => submit(label);
    l.appendChild(b);
  }
}

async function loadNext() {
  renderTabs();
  const r = await fetch('/api/next?queue=' + current);
  const data = await r.json();
  document.getElementById('progress').textContent =
    data.remaining > 0
      ? `${current}: ${data.total - data.remaining} / ${data.total} labeled (${data.remaining} left)`
      : `${current}: ${data.total} / ${data.total} labeled — done!`;
  document.getElementById('notes').value = '';
  if (!data.row) {
    document.getElementById('text').style.display = 'none';
    document.getElementById('labels').style.display = 'none';
    document.getElementById('notes').style.display = 'none';
    document.getElementById('done').style.display = 'block';
    row = null;
    return;
  }
  document.getElementById('text').style.display = 'block';
  document.getElementById('labels').style.display = 'block';
  document.getElementById('notes').style.display = 'block';
  document.getElementById('done').style.display = 'none';
  row = data.row;
  document.getElementById('text').textContent = row.full_text;
  renderLabelButtons();
}

async function submit(label) {
  if (!row) return;
  const notes = document.getElementById('notes').value;
  await fetch('/api/label', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({queue: current, id: row.id, human_label: label, notes: notes})
  });
  loadNext();
}

document.addEventListener('keydown', (e) => {
  if (!row) return;
  const map = {'1': 'positive', '2': 'lean_positive', '3': 'negative', '4': 'unsure'};
  if (map[e.key]) submit(map[e.key]);
});

loadNext();
</script>
</body></html>"""


def load_df(path):
    return pd.read_csv(path)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
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
        elif parsed.path == "/api/next":
            qs = parse_qs(parsed.query)
            queue = qs.get("queue", [None])[0]
            path = QUEUES.get(queue)
            if not path:
                self._json({"error": "unknown queue"}, 400)
                return
            df = load_df(path)
            unlabeled = df[df["human_label"].isna()]
            total = len(df)
            remaining = len(unlabeled)
            if remaining == 0:
                self._json({"row": None, "total": total, "remaining": 0})
                return
            r = unlabeled.iloc[0]
            self._json({
                "row": {"id": int(r["id"]), "full_text": str(r["full_text"])},
                "total": total,
                "remaining": remaining,
            })
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/label":
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            path = QUEUES.get(payload["queue"])
            if not path:
                self._json({"error": "unknown queue"}, 400)
                return
            df = load_df(path)
            mask = df["id"] == payload["id"]
            df.loc[mask, "human_label"] = payload["human_label"]
            df.loc[mask, "notes"] = payload.get("notes", "")
            df.to_csv(path, index=False)
            self._json({"ok": True})
        else:
            self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    print(f"HITL rater running at http://localhost:{PORT}")
    HTTPServer(("localhost", PORT), Handler).serve_forever()
