// Datasets over ~50 rows are shipped in a compact {lookups, cols, rows} form
// (deduplicated string columns + integer indices) to keep the embedded
// payload small -- expand back into plain row objects here, once, so the
// rest of the code can work with DATA.regressions etc. as normal arrays.
function hydrate(compact) {
  const { lookups, cols, rows } = compact;
  const strCols = Object.keys(lookups);
  return rows.map(row => {
    const obj = {};
    cols.forEach((c, i) => {
      obj[c] = strCols.includes(c) ? lookups[c][row[i]] : row[i];
    });
    return obj;
  });
}
DATA.regressions = hydrate(DATA.regressions);
DATA.credentialsCrosstab = hydrate(DATA.credentialsCrosstab);
DATA.entityStanceCrosstab = hydrate(DATA.entityStanceCrosstab);
DATA.entities = hydrate(DATA.entities);
DATA.domains = hydrate(DATA.domains);
DATA.topCitedUrls = hydrate(DATA.topCitedUrls);
// topicExamples/entityExamples/domainExamples/urlExamples used to be
// hydrated here -- now superseded by the live drill-down API (full text,
// unbounded pagination, no embed-size ceiling), so those static blobs are
// dropped from the payload entirely rather than shipped unused.
DATA.hitlCoverage = hydrate(DATA.hitlCoverage);
DATA.dataQuality = hydrate(DATA.dataQuality);
DATA.comparisonCorpora = hydrate(DATA.comparisonCorpora);
DATA.insiderSweep = hydrate(DATA.insiderSweep);
DATA.semanticKeyness = hydrate(DATA.semanticKeyness);
DATA.lexicalTurnover = hydrate(DATA.lexicalTurnover);
DATA.threadByDomain = hydrate(DATA.threadByDomain);
DATA.regressions = DATA.regressions.concat(hydrate(DATA.coreRegressionClustered));
DATA.regressions = DATA.regressions.concat(hydrate(DATA.synthesisRegression));
DATA.regressions = DATA.regressions.concat(hydrate(DATA.trumpVsClassical));

// Entities never run through the maverick/consensus stance pipeline (Bill Gates,
// Washington Post, etc.) -- real mention counts, no stance classification yet.
// Appended to DATA.entities as construct="other" so the table can show them
// without pretending they've been categorized. mention_count is scoped to the
// full/unfiltered corpus (a biased partial NER scan, not exhaustive -- see
// src/build_other_entities_mentions.py), so population="unfiltered", not a
// separate fake population value -- "other" is a construct, same axis as
// maverick/consensus, not a third population alongside pure/unfiltered.
DATA.entities = DATA.entities.concat(hydrate(DATA.otherEntities).map(r => ({
  entity: r.entity, construct: 'other', population: 'unfiltered', bucket: r.bucket,
  mean_p_hostile: null, pct_hostile: null, pct_predicted_endorsement: null,
  mention_count: r.mention_count,
})));

// Canonical experts (Tesla, Einstein, Darwin, etc.) -- a separate hardcoded
// regex list (CANONICAL_EXPERTS in src/refine_thesis_models.py) used only as
// a regression-level has_canonical_expert flag, never broken out per-entity
// before. Mention counts only, same "unfiltered"-scoped caveat as "other".
// Some bare surnames here are inherently ambiguous (e.g. "Koch" could be
// Robert Koch or the Koch brothers) -- known limitation of the underlying
// list, not fixed here.
DATA.entities = DATA.entities.concat(hydrate(DATA.canonicalEntities).map(r => ({
  entity: r.entity, construct: 'canonical', population: 'unfiltered', bucket: null,
  mean_p_hostile: null, pct_hostile: null, pct_predicted_endorsement: null,
  mention_count: r.mention_count,
})));

// Real, high-volume entities (Trump 158,810 mentions, Biden, CIA, Epstein, etc.)
// that were mined by the bottom-up NER pass but never even promoted to human
// review (in_candidate_list=False on every variant) -- a confirmed gap, not a
// deliberate exclusion. construct="unreviewed" is deliberately distinct from
// "other" (which HAS been bucketed, just not stance-scored) -- these haven't
// been looked at by a human at all. See data/processed/missing_entity_candidates.csv
// for the reviewable candidate list (mentions + 2 corpus examples each, blank
// decision column) -- entity-list judgment calls are Nash's, not auto-applied here.
DATA.entities = DATA.entities.concat(hydrate(DATA.missingEntities).map(r => ({
  entity: r.entity, construct: 'unreviewed', population: 'unfiltered', bucket: null,
  mean_p_hostile: null, pct_hostile: null, pct_predicted_endorsement: null,
  mention_count: r.corpus_mentions,
})));

const COVE_LIGHT = ['#2a78d6','#eb6834','#1baf7a','#eda100','#e87ba4','#008300','#4a3aa7','#e34948'];
const COVE_DARK  = ['#3987e5','#d95926','#199e70','#c98500','#d55181','#008300','#9085e9','#e66767'];
function isDark() {
  const t = document.documentElement.getAttribute('data-theme');
  if (t === 'dark') return true;
  if (t === 'light') return false;
  return matchMedia('(prefers-color-scheme: dark)').matches;
}
function cove() { return isDark() ? COVE_DARK : COVE_LIGHT; }
function gridColor() { return isDark() ? '#2c2c2a' : '#e1e0d9'; }
const tickColor = '#898781';
function fmtN(n) { return Number(n).toLocaleString(); }
function shortTopic(t) { return t.replace(/^\d+_/, '').replace(/_/g, ' '); }

// ---------- Tab switching ----------
document.querySelectorAll('nav.tabs button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('nav.tabs button').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('section.tab').forEach(s => s.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  });
});

// ---------- Drill-down modal (live comment examples per topic / entity / domain / URL) ----------
// Backed by a live API (full text, no truncation, real pagination) rather
// than the static baked-in samples this used to use -- see
// src/serve_drilldown_api.py / src/build_drilldown_backend_db.py. Private,
// token-gated (the token is embedded here client-side; that's the agreed
// access model -- deters casual scraping, not a defense against a
// determined attacker).
const API_BASE = 'https://api.kahatahi.co.nz';
const API_TOKEN = 'wCcvTs2IfGhWn64xDhZ8CQxS8Fa5uMzS';
const DRILL_PAGE_SIZE = 20;

const TOPIC_FIT_RATINGS = [
  { value: 'clearly_fits', label: 'Clearly fits' },
  { value: 'lean_fits', label: 'Lean fits' },
  { value: 'unsure', label: 'Unsure' },
  { value: 'lean_doesnt_fit', label: "Lean doesn't fit" },
  { value: 'clearly_doesnt_fit', label: "Clearly doesn't fit" },
];

const DRILL_COLUMN_SETS = {
  topic: {
    label: t => shortTopic(t),
    caption: 'Live, paginated, full comment text -- sort by any column, use "Load more" for further pages. Rate each comment\'s topic fit on the right; ratings save immediately and are staged separately from the topic model itself (nothing here rewrites the actual BERTopic assignment).',
    apiPath: 'topic_examples', apiParam: 'topic',
    cols: [
      { key: 'upvotes', label: 'Upvotes', num: true, sortable: true, default: true },
      { key: 'date', label: 'Date', num: false, sortable: true, default: true },
      { key: 'char_length', label: 'Length', num: true, sortable: true, default: false },
    ],
    ratable: true,
  },
  entity: {
    label: e => e,
    caption: 'Live, paginated, full comment text for any entity with stance data (maverick, consensus, canonical, or the newly-extended villain/mainstream/alternative-source buckets). Entities never run through the stance pipeline show nothing here.',
    apiPath: 'entity_examples', apiParam: 'entity',
    cols: [
      { key: 'predicted_label', label: 'Stance', num: false, sortable: false, default: true },
      { key: 'p_hostile', label: 'P(hostile)', num: true, sortable: true, render: v => v.toFixed(2), default: true },
      { key: 'p_endorsement', label: 'P(endorsement)', num: true, sortable: true, render: v => v.toFixed(2), default: false },
      { key: 'upvotes', label: 'Upvotes', num: true, sortable: true, default: true },
    ],
  },
  domain: {
    label: d => d,
    caption: 'Live, paginated, full comment text citing this domain -- every domain with any citation is covered now, not just a static top-N.',
    apiPath: 'domain_examples', apiParam: 'domain',
    cols: [{ key: 'upvotes', label: 'Upvotes', num: true, sortable: true, default: true }],
  },
  url: {
    label: u => u,
    caption: 'Live, paginated, full comment text citing this exact URL.',
    apiPath: 'url_examples', apiParam: 'url',
    cols: [{ key: 'upvotes', label: 'Upvotes', num: true, sortable: true, default: true }],
  },
};
let drillState = null; // { kind, key, sort, dir, offset, total, rows, activeCols }

function drillApiUrl(path, params = {}) {
  const url = new URL(API_BASE + '/api/' + path);
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  url.searchParams.set('token', API_TOKEN);
  const rater = localStorage.getItem('hitl_rater_name') || 'nash';
  url.searchParams.set('rater', rater);
  return url.toString();
}

async function fetchDrillPage(reset) {
  const spec = DRILL_COLUMN_SETS[drillState.kind];
  if (reset) { drillState.offset = 0; drillState.rows = []; }
  const body = document.getElementById('drillBody');
  if (reset) body.innerHTML = '<tr><td colspan="10" style="color:var(--ink-3); text-align:center; padding:1.5rem;">Loading&hellip;</td></tr>';
  try {
    const url = drillApiUrl(spec.apiPath, {
      [spec.apiParam]: drillState.key, sort: drillState.sort, dir: drillState.dir,
      offset: drillState.offset, limit: DRILL_PAGE_SIZE,
    });
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    drillState.total = data.total;
    drillState.rows = drillState.rows.concat(data.rows);
    drillState.offset = drillState.rows.length;
    renderDrillRows();
  } catch (err) {
    body.innerHTML = '<tr><td colspan="10" style="color:var(--neg); text-align:center; padding:1.5rem;">Could not reach the live backend (' + err.message + '). It may be offline.</td></tr>';
  }
}

function submitTopicRating(commentId, topicName, rating, btnRow) {
  const rater = localStorage.getItem('hitl_rater_name') || 'nash';
  fetch(drillApiUrl('rate_topic_fit', {}), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ comment_id: commentId, topic_name: topicName, rating, rater }),
  }).then(resp => resp.json()).then(data => {
    if (data.status === 'ok') {
      const row = drillState.rows.find(r => r.comment_id === commentId);
      if (row) row.rating = rating;
      renderDrillRows();
    }
  }).catch(() => { btnRow.querySelector('.rating-status').textContent = 'save failed'; });
}

// ---------- Rich single-comment detail view (entity/lexicon highlighting) ----------
// DATA.lexicon is utils/epistemic_lexicon.py's term lists (evidence, hedge,
// adversarial, certainty, alt_authority, intuitive, pattern, meta, demand,
// anecdotal, quantitative) -- the same lexicon that produced the corpus's
// per-comment marker counts. Multi-word terms use underscores as the
// original convention; matched against real text as flexible whitespace.
const LEXICON_TERMS = (() => {
  const terms = [];
  Object.entries(DATA.lexicon).forEach(([cat, words]) => {
    words.forEach(w => terms.push({ cat, term: w }));
  });
  terms.sort((a, b) => b.term.length - a.term.length); // longer phrases match first
  return terms;
})();
const LEXICON_REGEX = new RegExp('\\b(' + LEXICON_TERMS.map(t => t.term.replace(/_/g, '\\s+')).join('|') + ')\\b', 'gi');
const LEXICON_CATEGORY_BY_TERM = (() => {
  const m = {};
  LEXICON_TERMS.forEach(t => { m[t.term.replace(/_/g, ' ').toLowerCase()] = t.cat; });
  return m;
})();

function escapeHtml(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

function highlightLexicon(escapedText) {
  const seen = {};
  const highlighted = escapedText.replace(LEXICON_REGEX, (match) => {
    const norm = match.toLowerCase().replace(/\s+/g, ' ');
    const cat = LEXICON_CATEGORY_BY_TERM[norm] || 'meta';
    seen[cat] = (seen[cat] || 0) + 1;
    return '<mark class="hl-lex hl-' + cat + '" title="' + cat.replace(/_/g, ' ') + '">' + match + '</mark>';
  });
  return { html: highlighted, counts: seen };
}

function highlightEntity(escapedText, entityName) {
  const pattern = '\\b' + entityName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+') + '\\b';
  const re = new RegExp('(' + pattern + ')', 'gi');
  return escapedText.replace(re, '<mark class="hl-entity">$1</mark>');
}

window.ALL_TOPICS = [];
function initializeAllTopics() {
  if (window.ALL_TOPICS.length > 0) return;
  const topicsSet = new Set();
  if (DATA.semanticKeyness) {
    DATA.semanticKeyness.forEach(row => {
      if (row.topic_name && !row.topic_name.startsWith('-1_')) {
        topicsSet.add(row.topic_name);
      }
    });
  }
  window.ALL_TOPICS = Array.from(topicsSet).sort();
}

async function fetchCommentContext(commentId, containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;
  try {
    const url = drillApiUrl('comment_context', { comment_id: commentId });
    const resp = await fetch(url);
    if (!resp.ok) {
      if (resp.status === 404) {
        container.style.display = 'none';
        return;
      }
      throw new Error('HTTP ' + resp.status);
    }
    const data = await resp.json();
    const threadLink = `https://www.reddit.com/comments/${data.post_id}`;
    const scoreText = data.thread_score != null ? `(Score: ${data.thread_score.toLocaleString()})` : '';
    const domainText = data.thread_domain ? `<span class="chip" style="background:var(--bg); margin-left:6px;">${escapeHtml(data.thread_domain)}</span>` : '';
    
    let parentHtml = '';
    if (data.parent_text) {
      parentHtml = `
        <div style="margin-top:8px; border-left:3px solid var(--grid); padding-left:10px; color:var(--ink-2); font-style:italic; font-size:11.5px;">
          <strong>Parent Comment:</strong> ${escapeHtml(data.parent_text)}
        </div>
      `;
    }
    
    container.innerHTML = `
      <div style="font-weight:600; font-size:12.5px; color:var(--accent);">
        Thread: <a href="${threadLink}" target="_blank" style="color:var(--accent); text-decoration:underline;">${escapeHtml(data.thread_title || 'Reddit Thread')}</a> ${scoreText} ${domainText}
      </div>
      ${parentHtml}
    `;
  } catch (err) {
    container.innerHTML = `<span style="color:var(--neg); font-size:11px;">Thread context: ${err.message}</span>`;
  }
}

async function fetchOutlierSuggestions(commentId, containerId, originalTopic) {
  const container = document.getElementById(containerId);
  if (!container) return;
  try {
    const url = drillApiUrl('outlier_suggestions', { comment_id: commentId });
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    
    if (data.suggestions && data.suggestions.length > 0) {
      container.innerHTML = `
        <div style="margin-top:10px; padding:10px; background:var(--surface-2); border-radius:6px; border:1px solid var(--grid);">
          <h4 style="margin:0 0 6px 0; font-size:12px; font-weight:600; color:var(--ink-1);">Suggested Topics (TF-IDF/kNN):</h4>
          <div style="display:flex; flex-wrap:wrap; gap:5px;">
            ${data.suggestions.map(s => `
              <button class="examples-link" style="padding:3px 8px; font-size:11px;" onclick="window.submitOutlierAssignment('${commentId}', '${originalTopic}', '${s.topic_name}')" title="TF-IDF score: ${s.score}">
                ${shortTopic(s.topic_name)} (${s.score})
              </button>
            `).join('')}
          </div>
        </div>
      `;
    } else {
      container.innerHTML = `
        <div style="margin-top:10px; padding:6px; background:var(--surface-2); border-radius:6px; border:1px solid var(--grid); text-align:center; font-size:11px; color:var(--ink-3);">
          No high-confidence topic suggestions found for this outlier comment.
        </div>
      `;
    }
  } catch (err) {
    container.innerHTML = `<span style="color:var(--neg); font-size:11px;">Suggestions error: ${err.message}</span>`;
  }
}

window.submitOutlierAssignment = function(commentId, originalTopic, assignedTopic) {
  const select = document.getElementById('outlier-assign-select-' + commentId);
  const status = document.getElementById('assign-status-' + commentId);
  
  const targetTopic = assignedTopic || (select ? select.value : '');
  if (!targetTopic) return;
  
  if (status) status.textContent = 'saving...';
  const rater = localStorage.getItem('hitl_rater_name') || 'nash';
  
  fetch(drillApiUrl('assign_outlier_topic', {}), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ comment_id: commentId, original_topic_name: originalTopic, assigned_topic_name: targetTopic, rater }),
  }).then(resp => resp.json()).then(data => {
    if (data.status === 'ok') {
      if (status) {
        status.textContent = 'Saved!';
        status.style.color = 'var(--pos)';
      }
      if (select) select.value = targetTopic;
      // Let suggestions live-refresh to incorporate kNN online feedback instantly!
      fetchOutlierSuggestions(commentId, 'outlier-suggestions-container-' + commentId, originalTopic);
    } else {
      if (status) status.textContent = 'error: ' + data.error;
    }
  }).catch(err => {
    if (status) status.textContent = 'failed to save';
  });
};

function generateRandomRaterName() {
  const prefixes = ["Random", "Receding", "Rescending", "Maverick", "Consensus", "Ambitious", "Hedged", "Hostile", "Conspiratorial", "Deep", "Verifiable", "Shadow", "Cloaked", "Unbrigaded", "Fuzzy", "Expert"];
  const nouns = ["Unicorn", "Expert", "Whistleblower", "Cabal", "Insider", "Alien", "Reptilian", "Rater", "Glitch", "Protocol", "Agent", "Validator", "Auditor"];
  const p = prefixes[Math.floor(Math.random() * prefixes.length)];
  const n = nouns[Math.floor(Math.random() * nouns.length)];
  return `${p} ${n}`;
}

// Initialize Rater Identity
(function() {
  const raterInput = document.getElementById('hitl_rater_name_input');
  if (raterInput) {
    let savedName = localStorage.getItem('hitl_rater_name');
    if (!savedName) {
      savedName = generateRandomRaterName();
      localStorage.setItem('hitl_rater_name', savedName);
    }
    raterInput.value = savedName;
    raterInput.addEventListener('input', () => {
      const val = raterInput.value.trim() || 'Anonymous';
      localStorage.setItem('hitl_rater_name', val);
      const indicator = document.getElementById('rater_save_indicator');
      if (indicator) {
        indicator.style.display = 'inline';
        setTimeout(() => { indicator.style.display = 'none'; }, 1000);
      }
    });
  }
})();

let drillZoom = 1;
function renderDrillDetail(r) {
  const spec = DRILL_COLUMN_SETS[drillState.kind];
  const pane = document.getElementById('drillDetail');
  pane.classList.remove('empty');

  let html = escapeHtml(r.text);
  if (drillState.kind === 'entity') html = highlightEntity(html, drillState.key);
  const { html: lexHtml, counts } = highlightLexicon(html);
  html = lexHtml;

  const legendChips = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([cat, n]) =>
    '<span class="chip">' + cat.replace(/_/g, ' ') + ' &times;' + n + '</span>'
  ).join('') || '<span class="chip">no lexicon markers detected</span>';

  const contextBits = [];
  if (r.date) contextBits.push('<span class="label">Date</span> ' + r.date);
  contextBits.push('<span class="label">Upvotes</span> ' + fmtN(r.upvotes));
  if (r.predicted_label) contextBits.push('<span class="label">Stance</span> ' + r.predicted_label + ' (P=' + (r.p_hostile != null ? r.p_hostile.toFixed(2) : '?') + ' hostile)');

  const ratingHtml = spec.ratable ? '<div class="detail-rating-row">' + TOPIC_FIT_RATINGS.map(rt =>
    '<button class="examples-link" data-detail-rating-btn="' + rt.value + '"' + (r.rating === rt.value ? ' style="background:var(--accent); color:var(--surface);"' : '') + '>' + rt.label + '</button>'
  ).join('') + '</div>' : '';

  const isOutlier = drillState.kind === 'topic' && drillState.key.startsWith('-1_');
  let outlierSectionHtml = '';
  if (isOutlier) {
    initializeAllTopics();
    const selectOptions = window.ALL_TOPICS.map(t => `<option value="${t}">${shortTopic(t)}</option>`).join('');
    outlierSectionHtml = `
      <div id="outlier-suggestions-container-${r.comment_id}">
        <span style="color:var(--ink-3); font-size:11px;">Fetching keyword overlap topic suggestions...</span>
      </div>
      <div style="margin-top:12px; padding:10px; border-top:1px dashed var(--grid); font-size:12px;">
        <span class="label" style="font-weight:600;">Manual Topic Assignment:</span>
        <div style="display:flex; align-items:center; gap:6px; margin-top:5px;">
          <select id="outlier-assign-select-${r.comment_id}" style="background:var(--bg); color:var(--ink); border:1px solid var(--grid); border-radius:4px; padding:4px 8px; flex:1; font-size:12px;">
            <option value="">-- select target topic --</option>
            ${selectOptions}
          </select>
          <button class="examples-link" style="padding:4px 10px; font-size:11px;" onclick="window.submitOutlierAssignment('${r.comment_id}', '${drillState.key}')">Assign</button>
        </div>
        <span id="assign-status-${r.comment_id}" style="font-size:11px; color:var(--ink-3); display:inline-block; margin-top:4px;"></span>
      </div>
    `;
  }

  pane.innerHTML =
    '<div class="detail-zoom"><span style="color:var(--ink-3); font-size:11px;">Zoom</span>' +
    '<button id="drillZoomOut">&minus;</button><button id="drillZoomIn">+</button></div>' +
    `<div id="comment-context-container-${r.comment_id}" style="background:var(--surface-2); padding:8px 12px; border-radius:6px; margin-bottom:12px; border-left:4px solid var(--accent); font-size:12.5px;">` +
    '<span style="color:var(--ink-3);">Loading thread context...</span>' +
    '</div>' +
    '<div class="detail-context">' + contextBits.join(' &nbsp;&middot;&nbsp; ') + '</div>' +
    '<div class="detail-legend">' + legendChips + '</div>' +
    '<div class="detail-text" style="font-size:' + (14 * drillZoom).toFixed(0) + 'px;">' + html + '</div>' +
    ratingHtml +
    outlierSectionHtml;

  document.getElementById('drillZoomIn').addEventListener('click', () => { drillZoom = Math.min(drillZoom + 0.15, 2); renderDrillDetail(r); });
  document.getElementById('drillZoomOut').addEventListener('click', () => { drillZoom = Math.max(drillZoom - 0.15, 0.7); renderDrillDetail(r); });
  if (spec.ratable) {
    pane.querySelectorAll('[data-detail-rating-btn]').forEach(btn => {
      btn.addEventListener('click', () => submitTopicRating(r.comment_id, drillState.key, btn.dataset.detailRatingBtn, btn.closest('tr') || pane));
    });
  }

  // Trigger async loads
  fetchCommentContext(r.comment_id, `comment-context-container-${r.comment_id}`);
  if (isOutlier) {
    fetchOutlierSuggestions(r.comment_id, `outlier-suggestions-container-${r.comment_id}`, drillState.key);
  }
}

function renderDrillRows() {
  const spec = DRILL_COLUMN_SETS[drillState.kind];
  const activeColDefs = spec.cols.filter(c => drillState.activeCols.has(c.key));
  const headRow = document.getElementById('drillHeadRow');
  headRow.innerHTML = activeColDefs.map(c => '<th' + (c.sortable ? ' data-sort="' + c.key + '"' : '') + '>' + c.label + (drillState.sort === c.key ? (drillState.dir === 'asc' ? ' ↑' : ' ↓') : '') + '</th>').join('')
    + (spec.ratable ? '<th>Fit</th>' : '') + '<th>Preview</th>';
  headRow.querySelectorAll('th[data-sort]').forEach(th => {
    th.style.cursor = 'pointer';
    th.addEventListener('click', () => {
      const col = th.dataset.sort;
      drillState.dir = (drillState.sort === col && drillState.dir === 'desc') ? 'asc' : 'desc';
      drillState.sort = col;
      fetchDrillPage(true);
    });
  });

  const body = document.getElementById('drillBody');
  if (drillState.rows.length === 0) {
    body.innerHTML = '<tr><td colspan="10" style="color:var(--ink-3); text-align:center; padding:1.5rem;">No example comments available for this item yet.</td></tr>';
  } else {
    body.innerHTML = drillState.rows.map((r, i) => {
      const cells = activeColDefs.map(c => '<td' + (c.num ? ' class="num"' : '') + '>' + (c.render ? c.render(r[c.key]) : (c.num ? fmtN(r[c.key]) : r[c.key])) + '</td>').join('');
      const ratingCell = spec.ratable ? '<td>' + TOPIC_FIT_RATINGS.map(rt =>
        '<button class="examples-link" data-rating-btn="' + rt.value + '" data-comment-id="' + r.comment_id + '" style="margin:1px;' + (r.rating === rt.value ? ' background:var(--accent); color:var(--surface);' : '') + '" title="' + rt.label + '">' + rt.label.split(' ').map(w => w[0]).join('') + '</button>'
      ).join('') + '<div class="rating-status" style="font-size:10px;color:var(--ink-3);"></div></td>' : '';
      const preview = (r.text || '').slice(0, 70).replace(/</g, '&lt;');
      return '<tr class="drill-row' + (drillState.selectedComment === r.comment_id ? ' selected' : '') + '" data-row-idx="' + i + '">' + cells + ratingCell + '<td class="snippet" style="max-width:220px;">' + preview + '&hellip;</td></tr>';
    }).join('');
    if (spec.ratable) {
      body.querySelectorAll('[data-rating-btn]').forEach(btn => {
        btn.addEventListener('click', (e) => { e.stopPropagation(); submitTopicRating(btn.dataset.commentId, drillState.key, btn.dataset.ratingBtn, btn.closest('tr')); });
      });
    }
    body.querySelectorAll('tr.drill-row').forEach(tr => {
      tr.addEventListener('click', () => {
        const r = drillState.rows[+tr.dataset.rowIdx];
        drillState.selectedComment = r.comment_id;
        body.querySelectorAll('tr.drill-row').forEach(t => t.classList.remove('selected'));
        tr.classList.add('selected');
        renderDrillDetail(r);
      });
    });
  }
  document.getElementById('drillRowCount').innerHTML = drillState.rows.length + ' of ' + fmtN(drillState.total) + ' loaded'
    + (drillState.rows.length < drillState.total ? ' &mdash; <button class="examples-link" id="drillLoadMore">Load more</button>' : '');
  const loadMoreBtn = document.getElementById('drillLoadMore');
  if (loadMoreBtn) loadMoreBtn.addEventListener('click', () => fetchDrillPage(false));
}

function openDrill(kind, key) {
  const spec = DRILL_COLUMN_SETS[kind];
  drillState = { kind, key, sort: spec.cols[0].key, dir: 'desc', offset: 0, total: 0, rows: [], activeCols: new Set(spec.cols.filter(c => c.default).map(c => c.key)), selectedComment: null };
  document.getElementById('drillTitle').textContent = spec.label(key);
  document.getElementById('drillCaption').textContent = spec.caption;
  document.getElementById('drillCols').innerHTML = spec.cols.map(c =>
    '<label><input type="checkbox" data-col="' + c.key + '"' + (c.default ? ' checked' : '') + '> ' + c.label + '</label>'
  ).join('');
  document.querySelectorAll('#drillCols input').forEach(cb => {
    cb.addEventListener('change', () => {
      const col = cb.dataset.col;
      if (cb.checked) drillState.activeCols.add(col); else drillState.activeCols.delete(col);
      renderDrillRows();
    });
  });
  const pane = document.getElementById('drillDetail');
  pane.classList.add('empty');
  pane.textContent = 'Click a row for the full annotated view.';
  document.getElementById('drillOverlay').classList.add('open');
  fetchDrillPage(true);
}
function closeDrill() { document.getElementById('drillOverlay').classList.remove('open'); }
document.getElementById('drillClose').addEventListener('click', closeDrill);
document.getElementById('drillOverlay').addEventListener('click', (e) => { if (e.target.id === 'drillOverlay') closeDrill(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrill(); });

// ---------- Overview ----------
function renderOverview() {
  const pops = DATA.populations;
  const full = pops.find(p => p.population === 'full_long');
  const short = pops.find(p => p.population === 'full_short');
  const stats = document.getElementById('overviewStats');
  const rows = [
    { label: 'full long comments', value: fmtN(full.n), sub: (full.outliers/full.n*100).toFixed(1) + '% outliers' },
    { label: 'full short comments (&le;100 char)', value: fmtN(short.n), sub: (short.outliers/short.n*100).toFixed(1) + '% outliers' },
    { label: 'combined corpus', value: fmtN(full.n + short.n), sub: 'Feb 2008 – Jun 2026' },
    { label: 'pure r/conspiracy (regression pop.)', value: '1,968,864', sub: 'unbrigaded, insider-heavy' },
    { label: 'r/politics control sample', value: '140,824', sub: 'matched-scope comparison' },
    { label: 'topics', value: '101', sub: '97 fitted + 3 seeded + outlier' },
  ];
  stats.innerHTML = rows.map(r => '<div class="stat-tile"><p class="stat-label">' + r.label + '</p><p class="stat-value">' + r.value + '</p><p class="stat-sub">' + r.sub + '</p></div>').join('');

  const bucketOrder = ['<0','0','1-4','5-19','20-99','100+'];
  const uv = DATA.upvoteHist.sort((a,b) => bucketOrder.indexOf(a.upvote_bucket) - bucketOrder.indexOf(b.upvote_bucket));
  new Chart(document.getElementById('upvoteChart'), {
    type: 'bar',
    data: { labels: uv.map(r => r.upvote_bucket), datasets: [{ data: uv.map(r => r.n), backgroundColor: cove()[0], borderRadius: 4 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { x: { grid: { display: false }, ticks: { color: tickColor } }, y: { grid: { color: gridColor() }, ticks: { color: tickColor, callback: v => fmtN(v) } } } }
  });

  const lenOrder = ['<50','50-99','100-249','250-499','500-999','1000+'];
  const lh = DATA.lenHist.sort((a,b) => lenOrder.indexOf(a.len_bucket) - lenOrder.indexOf(b.len_bucket));
  new Chart(document.getElementById('lenChart'), {
    type: 'bar',
    data: { labels: lh.map(r => r.len_bucket), datasets: [{ data: lh.map(r => r.n), backgroundColor: cove()[2], borderRadius: 4 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { x: { grid: { display: false }, ticks: { color: tickColor } }, y: { grid: { color: gridColor() }, ticks: { color: tickColor, callback: v => fmtN(v) } } } }
  });
}

// ---------- Topics over time (reused pattern) ----------
const topicNames = Object.keys(DATA.timeseries.topics);
let tsSelected = ['2_vaccine_vaccines_vaccinated_covid','12_fbi_cia_mueller_assange','50_trump_president_establishment_people','13_election_fraud_vote_ballots','4_conspiracy_conspiracies_sub_reddit'].filter(t => topicNames.includes(t));
let tsMode = 'share';
let tsChart = null;

function tsColorFor(topic) { const idx = tsSelected.indexOf(topic); return idx === -1 ? null : cove()[idx % 8]; }
function tsMonthLabels() { return DATA.timeseries.months.map(m => { const [y, mo] = m.split('-'); return mo === '01' ? y : ''; }); }

function tsBuildChart() {
  const wrap = document.getElementById('tsChartWrap');
  if (tsSelected.length === 0) { wrap.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--ink-3);font-size:13px;">Select a topic on the left to plot it.</div>'; tsChart = null; return; }
  if (!document.getElementById('tsChart')) wrap.innerHTML = '<canvas id="tsChart" role="img" aria-label="Line chart of selected topics over time"></canvas>';
  const datasets = tsSelected.map((t, i) => {
    const series = DATA.timeseries.topics[t];
    const raw = tsMode === 'share' ? series.share.map(v => v * 100) : series.n;
    return { label: t, data: raw, borderColor: cove()[i % 8], backgroundColor: cove()[i % 8], borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.15 };
  });
  if (tsChart) tsChart.destroy();
  tsChart = new Chart(document.getElementById('tsChart'), {
    type: 'line',
    data: { labels: tsMonthLabels(), datasets },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false }, tooltip: { callbacks: {
        title: (items) => DATA.timeseries.months[items[0].dataIndex],
        label: (item) => item.dataset.label + ': ' + (tsMode === 'share' ? item.parsed.y.toFixed(2) + '%' : Math.round(item.parsed.y).toLocaleString())
      } } },
      scales: {
        x: { grid: { display: false }, ticks: { color: tickColor, font: { size: 11 }, maxRotation: 0, autoSkip: false, callback: function(val) { const l = this.getLabelForValue(val); return l || null; } } },
        y: { beginAtZero: true, grid: { color: gridColor() }, ticks: { color: tickColor, font: { size: 11 }, callback: v => tsMode === 'share' ? v + '%' : v.toLocaleString() } },
      },
    },
  });
}

function tsPeak(topic) {
  const series = DATA.timeseries.topics[topic];
  const arr = tsMode === 'share' ? series.share : series.n;
  let best = 0; for (let i = 1; i < arr.length; i++) if (arr[i] > arr[best]) best = i;
  return { month: DATA.timeseries.months[best], value: arr[best] };
}

function tsRenderLegend() {
  const strip = document.getElementById('tsLegend');
  if (tsSelected.length === 0) { strip.innerHTML = ''; return; }
  strip.innerHTML = tsSelected.map((t, i) => {
    const peak = tsPeak(t);
    const val = tsMode === 'share' ? (peak.value * 100).toFixed(1) + '%' : Math.round(peak.value).toLocaleString();
    return '<span class="legend-item"><span class="legend-swatch" style="background:' + cove()[i % 8] + '"></span><span class="legend-label">' + shortTopic(t) + '</span><span class="legend-peak">peak ' + peak.month + ' (' + val + ')</span></span>';
  }).join('');
}

function tsRenderPicker(filter) {
  const list = document.getElementById('tsTopicList');
  const q = (filter || '').toLowerCase();
  const sorted = [...topicNames].sort((a, b) => DATA.timeseries.topics[b].total - DATA.timeseries.topics[a].total);
  const filtered = sorted.filter(t => !NON_SUBSTANTIVE_TOPICS.has(t) && t.toLowerCase().includes(q));
  list.innerHTML = filtered.map(t => {
    const isChecked = tsSelected.includes(t);
    const disabled = !isChecked && tsSelected.length >= 8;
    const color = isChecked ? tsColorFor(t) : 'transparent';
    return '<div class="topic-row' + (isChecked ? ' checked' : '') + (disabled ? ' disabled' : '') + '" data-topic="' + t.replace(/"/g, '&quot;') + '"><span class="swatch" style="background:' + color + '"></span><span class="topic-name">' + shortTopic(t) + '</span><span class="topic-n">' + fmtN(DATA.timeseries.topics[t].total) + '</span><button class="examples-link" data-examples-topic="' + t.replace(/"/g, '&quot;') + '">examples</button></div>';
  }).join('');
  document.getElementById('tsPickerCount').textContent = tsSelected.length + ' / 8 selected';
  list.querySelectorAll('.topic-row').forEach(row => {
    row.addEventListener('click', () => {
      const t = row.getAttribute('data-topic');
      const idx = tsSelected.indexOf(t);
      if (idx >= 0) tsSelected.splice(idx, 1); else { if (tsSelected.length >= 8) return; tsSelected.push(t); }
      tsRenderPicker(document.getElementById('tsSearch').value); tsBuildChart(); tsRenderLegend();
    });
  });
  list.querySelectorAll('[data-examples-topic]').forEach(btn => {
    btn.addEventListener('click', (e) => { e.stopPropagation(); openDrill('topic', btn.getAttribute('data-examples-topic')); });
  });
}

document.getElementById('tsSearch').addEventListener('input', (e) => tsRenderPicker(e.target.value));
document.getElementById('tsModeShare').addEventListener('click', () => { tsMode = 'share'; document.getElementById('tsModeShare').classList.add('active'); document.getElementById('tsModeCount').classList.remove('active'); tsBuildChart(); tsRenderLegend(); });
document.getElementById('tsModeCount').addEventListener('click', () => { tsMode = 'count'; document.getElementById('tsModeCount').classList.add('active'); document.getElementById('tsModeShare').classList.remove('active'); tsBuildChart(); tsRenderLegend(); });

// ---------- All topics table ----------
let allTopicsSort = { col: 'total', dir: -1 };
function renderAllTopicsTable() {
  const q = document.getElementById('allTopicsSearch').value.toLowerCase();
  let rows = topicNames.filter(t => !NON_SUBSTANTIVE_TOPICS.has(t) && (!q || t.toLowerCase().includes(q)))
    .map(t => ({ topic: t, total: DATA.timeseries.topics[t].total }));
  rows.sort((a, b) => {
    const av = a[allTopicsSort.col], bv = b[allTopicsSort.col];
    if (typeof av === 'string') return av.localeCompare(bv) * allTopicsSort.dir;
    return (av - bv) * allTopicsSort.dir;
  });
  const body = document.getElementById('allTopicsTableBody');
  body.innerHTML = rows.map(r =>
    '<tr class="clickable" data-topic="' + r.topic.replace(/"/g, '&quot;') + '"><td>' + shortTopic(r.topic) + '</td><td class="num">' + fmtN(r.total) + '</td></tr>'
  ).join('');
  document.getElementById('allTopicsRowCount').textContent = rows.length + ' topics';
  body.querySelectorAll('tr[data-topic]').forEach(row => {
    row.addEventListener('click', () => openDrill('topic', row.getAttribute('data-topic')));
  });
}
document.querySelectorAll('#allTopicsTable th[data-sort]').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.sort;
    allTopicsSort.dir = (allTopicsSort.col === col) ? -allTopicsSort.dir : -1;
    allTopicsSort.col = col;
    renderAllTopicsTable();
  });
});
document.getElementById('allTopicsSearch').addEventListener('input', renderAllTopicsTable);

// ---------- Author interests ----------
const NON_SUBSTANTIVE_TOPICS = new Set(['Outliers', '0_ha_thanks_thank_lol', '23_banned_mods_ban_reddit']);
function renderAuthorChart() {
  const rows = [...DATA.authorPrimary].filter(r => r.n_authors >= 200 && !NON_SUBSTANTIVE_TOPICS.has(r.top_topic_name)).sort((a,b) => b.n_authors - a.n_authors).slice(0, 20).reverse();
  document.getElementById('authorChartWrap').innerHTML = '<canvas id="authorChart" role="img" aria-label="Horizontal bar chart of topics by number of authors for whom this is their top topic"></canvas>';
  new Chart(document.getElementById('authorChart'), {
    type: 'bar',
    data: { labels: rows.map(r => shortTopic(r.top_topic_name)), datasets: [{ data: rows.map(r => r.n_authors), backgroundColor: cove()[4], borderRadius: 4 }] },
    options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false },
      tooltip: { callbacks: { label: (item) => fmtN(item.parsed.x) + ' authors -- click bar for example comments' } } },
      scales: { x: { grid: { color: gridColor() }, ticks: { color: tickColor, callback: v => fmtN(v) } }, y: { grid: { display: false }, ticks: { color: tickColor, font: { size: 11 } } } },
      onHover: (e, els) => { e.native.target.style.cursor = els.length ? 'pointer' : 'default'; },
      onClick: (e, els) => { if (els.length) openDrill('topic', rows[els[0].index].top_topic_name); } }
  });
}

// ---------- Credentials & stance by topic ----------
function renderCredGapChart() {
  const rows = DATA.credentialsCrosstab.filter(r => r.category === 'movement_internal_anonymous');
  const byTopic = {};
  rows.forEach(r => { if (!byTopic[r.topic_name]) byTopic[r.topic_name] = {}; byTopic[r.topic_name][r.comment_stance] = r.share_within_stance; });
  const gaps = Object.entries(byTopic)
    .filter(([_, v]) => 'Anti-Consensus' in v && 'Consensus-Aligned' in v)
    .map(([topic, v]) => ({ topic, gap: v['Anti-Consensus'] - v['Consensus-Aligned'] }))
    .sort((a,b) => b.gap - a.gap);
  const top = gaps.slice(0, 10);
  const bottom = gaps.slice(-6).reverse();
  const combined = [...top, ...bottom].reverse();
  document.getElementById('credGapChartWrap').innerHTML = '<canvas id="credGapChart" role="img" aria-label="Bar chart of movement-internal citation gap by topic"></canvas>';
  new Chart(document.getElementById('credGapChart'), {
    type: 'bar',
    data: { labels: combined.map(r => shortTopic(r.topic)), datasets: [{ data: combined.map(r => (r.gap*100).toFixed(1)), backgroundColor: combined.map(r => r.gap >= 0 ? cove()[1] : cove()[0]), borderRadius: 4 }] },
    options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false },
      tooltip: { callbacks: { label: (item) => (item.parsed.x >= 0 ? '+' : '') + item.parsed.x + ' pts -- click bar for example comments' } } },
      scales: { x: { grid: { color: gridColor() }, ticks: { color: tickColor, callback: v => v + '%' } }, y: { grid: { display: false }, ticks: { color: tickColor, font: { size: 10.5 } } } },
      onHover: (e, els) => { e.native.target.style.cursor = els.length ? 'pointer' : 'default'; },
      onClick: (e, els) => { if (els.length) openDrill('topic', combined[els[0].index].topic); } }
  });
}

function renderStanceChart() {
  const rows = DATA.entityStanceCrosstab.filter(r => r.construct === 'maverick' && r.predicted_label === 'hostile');
  const sorted = [...rows].sort((a,b) => b.share_within_construct_topic - a.share_within_construct_topic);
  const top = sorted.slice(0, 10);
  const bottom = sorted.slice(-8).reverse();
  const combined = [...top, ...bottom].reverse();
  document.getElementById('stanceChartWrap').innerHTML = '<canvas id="stanceChart" role="img" aria-label="Bar chart of maverick hostility share by topic"></canvas>';
  new Chart(document.getElementById('stanceChart'), {
    type: 'bar',
    data: { labels: combined.map(r => shortTopic(r.topic_name)), datasets: [{ data: combined.map(r => (r.share_within_construct_topic*100).toFixed(1)), backgroundColor: cove()[6], borderRadius: 4 }] },
    options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false },
      tooltip: { callbacks: { label: (item) => item.parsed.x + '% hostile -- click bar for example comments' } } },
      scales: { x: { grid: { color: gridColor() }, ticks: { color: tickColor, callback: v => v + '%' }, max: 100 }, y: { grid: { display: false }, ticks: { color: tickColor, font: { size: 10.5 } } } },
      onHover: (e, els) => { e.native.target.style.cursor = els.length ? 'pointer' : 'default'; },
      onClick: (e, els) => { if (els.length) openDrill('topic', combined[els[0].index].topic_name); } }
  });
}

// ---------- Named entities over time ----------
// Any entity with stance data is now selectable (live-fetched from the
// backend, not just the 25 baked into the static artifact) -- the picker
// list itself (names + mention counts) still comes from the already-
// embedded DATA.entities, which is small; only the monthly series is
// fetched on demand, once per entity, and cached client-side.
const entAllCounts = (() => {
  const m = {};
  DATA.entities.forEach(r => { m[r.entity] = Math.max(m[r.entity] || 0, r.mention_count || 0); });
  return m;
})();
const entTsNames = Object.keys(entAllCounts);
let entTsSelected = ['Alex Jones','WikiLeaks','Anthony Fauci','Tucker Carlson'].filter(e => entTsNames.includes(e));
let entTsMode = 'mentions';
let entTsChart = null;
let entTsSeriesCache = {};
Object.entries(DATA.entityTimeseries.entities).forEach(([name, series]) => {
  entTsSeriesCache[name] = { months: DATA.entityTimeseries.months, mentions: series.mentions, hostile_share: series.hostile_share, total: series.total };
});

function normalizeMonthlyRows(rows) {
  const byMonth = {};
  rows.forEach(r => {
    if (!byMonth[r.month]) byMonth[r.month] = { mentions: 0, n_hostile: 0 };
    byMonth[r.month].mentions += r.mentions;
    byMonth[r.month].n_hostile += r.n_hostile;
  });
  const months = DATA.entityTimeseries.months;
  const mentions = months.map(m => (byMonth[m] ? byMonth[m].mentions : 0));
  const hostile_share = months.map(m => {
    const b = byMonth[m];
    if (!b || b.mentions < 5) return null;
    return b.n_hostile / b.mentions;
  });
  return { months, mentions, hostile_share, total: mentions.reduce((a, b) => a + b, 0) };
}

async function ensureEntTsSeries(name) {
  if (entTsSeriesCache[name]) return entTsSeriesCache[name];
  try {
    const resp = await fetch(drillApiUrl('entity_monthly', { entity: name }));
    const data = await resp.json();
    entTsSeriesCache[name] = normalizeMonthlyRows(data.rows || []);
  } catch (e) {
    entTsSeriesCache[name] = { months: DATA.entityTimeseries.months, mentions: DATA.entityTimeseries.months.map(() => 0), hostile_share: DATA.entityTimeseries.months.map(() => null), total: 0 };
  }
  return entTsSeriesCache[name];
}

function entTsColorFor(e) { const idx = entTsSelected.indexOf(e); return idx === -1 ? null : cove()[idx % 8]; }
function entTsMonthLabels() { return DATA.entityTimeseries.months.map(m => { const [y, mo] = m.split('-'); return mo === '01' ? y : ''; }); }

async function entTsBuildChart() {
  const wrap = document.getElementById('entTsChartWrap');
  if (entTsSelected.length === 0) { wrap.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--ink-3);font-size:13px;">Select an entity on the left to plot it.</div>'; entTsChart = null; return; }
  if (!document.getElementById('entTsChart')) wrap.innerHTML = '<canvas id="entTsChart" role="img" aria-label="Line chart of selected entities over time"></canvas>';
  await Promise.all(entTsSelected.map(ensureEntTsSeries));
  const datasets = entTsSelected.map((e, i) => {
    const series = entTsSeriesCache[e];
    const raw = entTsMode === 'mentions' ? series.mentions : series.hostile_share.map(v => v === null ? null : v * 100);
    return { label: e, data: raw, borderColor: cove()[i % 8], backgroundColor: cove()[i % 8], borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.15, spanGaps: false };
  });
  if (entTsChart) entTsChart.destroy();
  entTsChart = new Chart(document.getElementById('entTsChart'), {
    type: 'line',
    data: { labels: entTsMonthLabels(), datasets },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false }, tooltip: { callbacks: {
        title: (items) => DATA.entityTimeseries.months[items[0].dataIndex],
        label: (item) => item.dataset.label + ': ' + (item.parsed.y === null ? 'n/a (too few mentions)' : (entTsMode === 'mentions' ? Math.round(item.parsed.y).toLocaleString() : item.parsed.y.toFixed(1) + '%'))
      } } },
      scales: {
        x: { grid: { display: false }, ticks: { color: tickColor, font: { size: 11 }, maxRotation: 0, autoSkip: false, callback: function(val) { const l = this.getLabelForValue(val); return l || null; } } },
        y: { beginAtZero: true, grid: { color: gridColor() }, ticks: { color: tickColor, font: { size: 11 }, callback: v => entTsMode === 'mentions' ? v.toLocaleString() : v + '%' } },
      },
    },
  });
}

function entTsPeak(e) {
  const series = entTsSeriesCache[e];
  if (!series) return null;
  const arr = entTsMode === 'mentions' ? series.mentions : series.hostile_share;
  let best = -1;
  for (let i = 0; i < arr.length; i++) if (arr[i] !== null && (best === -1 || arr[i] > arr[best])) best = i;
  return best === -1 ? null : { month: DATA.entityTimeseries.months[best], value: arr[best] };
}

function entTsRenderLegend() {
  const strip = document.getElementById('entTsLegend');
  if (entTsSelected.length === 0) { strip.innerHTML = ''; return; }
  strip.innerHTML = entTsSelected.map((e, i) => {
    const peak = entTsPeak(e);
    const val = peak ? (entTsMode === 'mentions' ? Math.round(peak.value).toLocaleString() : (peak.value*100).toFixed(1) + '%') : 'n/a';
    const month = peak ? peak.month : '';
    return '<span class="legend-item"><span class="legend-swatch" style="background:' + cove()[i % 8] + '"></span><span class="legend-label">' + e + '</span><span class="legend-peak">' + (peak ? 'peak ' + month + ' (' + val + ')' : '') + '</span></span>';
  }).join('');
}

function entTsRenderPicker(filter) {
  const list = document.getElementById('entTsList');
  const q = (filter || '').toLowerCase();
  const sorted = [...entTsNames].sort((a, b) => entAllCounts[b] - entAllCounts[a]);
  const filtered = sorted.filter(e => e.toLowerCase().includes(q));
  list.innerHTML = filtered.map(e => {
    const isChecked = entTsSelected.includes(e);
    const disabled = !isChecked && entTsSelected.length >= 8;
    const color = isChecked ? entTsColorFor(e) : 'transparent';
    return '<div class="topic-row' + (isChecked ? ' checked' : '') + (disabled ? ' disabled' : '') + '" data-entity="' + e.replace(/"/g, '&quot;') + '"><span class="swatch" style="background:' + color + '"></span><span class="topic-name">' + e + '</span><span class="topic-n">' + fmtN(entAllCounts[e]) + '</span><button class="examples-link" data-examples-entity="' + e.replace(/"/g, '&quot;') + '">examples</button></div>';
  }).join('');
  document.getElementById('entTsPickerCount').textContent = entTsSelected.length + ' / 8 selected';
  list.querySelectorAll('[data-examples-entity]').forEach(btn => {
    btn.addEventListener('click', (e) => { e.stopPropagation(); openDrill('entity', btn.getAttribute('data-examples-entity')); });
  });
  list.querySelectorAll('.topic-row').forEach(row => {
    row.addEventListener('click', () => {
      const e = row.getAttribute('data-entity');
      const idx = entTsSelected.indexOf(e);
      if (idx >= 0) entTsSelected.splice(idx, 1); else { if (entTsSelected.length >= 8) return; entTsSelected.push(e); }
      entTsRenderPicker(document.getElementById('entTsSearch').value); entTsBuildChart(); entTsRenderLegend();
    });
  });
}

document.getElementById('entTsSearch').addEventListener('input', (e) => entTsRenderPicker(e.target.value));
document.getElementById('entTsModeMentions').addEventListener('click', () => { entTsMode = 'mentions'; document.getElementById('entTsModeMentions').classList.add('active'); document.getElementById('entTsModeHostile').classList.remove('active'); entTsBuildChart(); entTsRenderLegend(); });
document.getElementById('entTsModeHostile').addEventListener('click', () => { entTsMode = 'hostile'; document.getElementById('entTsModeHostile').classList.add('active'); document.getElementById('entTsModeMentions').classList.remove('active'); entTsBuildChart(); entTsRenderLegend(); });

// ---------- Named entities ----------
let entSort = { col: 'mention_count', dir: -1 };
function renderEntTable() {
  const pop = document.getElementById('entPopulation').value;
  const construct = document.getElementById('entConstruct').value;
  const q = document.getElementById('entSearch').value.toLowerCase();
  let rows = DATA.entities.filter(r =>
    r.population === pop && (!construct || r.construct === construct) &&
    (!q || r.entity.toLowerCase().includes(q))
  );
  rows.sort((a, b) => {
    const av = a[entSort.col], bv = b[entSort.col];
    if (av == null && bv == null) return 0;
    if (av == null) return 1; if (bv == null) return -1;
    if (typeof av === 'string') return av.localeCompare(bv) * entSort.dir;
    return (av - bv) * entSort.dir;
  });
  const body = document.getElementById('entTableBody');
  body.innerHTML = rows.slice(0, 300).map(r => {
    const isChecked = selectedEntities.has(r.entity) ? ' checked' : '';
    return '<tr class="clickable" data-entity="' + r.entity.replace(/"/g, '&quot;') + '">' +
      '<td style="text-align: center;"><input type="checkbox" class="ent-select" data-entity="' + r.entity.replace(/"/g, '&quot;') + '"' + isChecked + ' style="cursor: pointer;"></td>' +
      '<td>' + r.entity + '</td><td>' + r.construct + (r.bucket ? ' (' + r.bucket.replace(/_/g, ' ') + ')' : '') + '</td>' +
      '<td class="num">' + fmtN(r.mention_count) + '</td>' +
      '<td class="num">' + (r.pct_hostile != null ? (r.pct_hostile*100).toFixed(1) + '%' : '&mdash;') + '</td>' +
      '<td class="num">' + (r.pct_predicted_endorsement != null ? (r.pct_predicted_endorsement*100).toFixed(1) + '%' : '&mdash;') + '</td>' +
      '<td class="num">' + (r.mean_p_hostile != null ? r.mean_p_hostile.toFixed(3) : '&mdash;') + '</td></tr>';
  }).join('');
  document.getElementById('entRowCount').textContent = rows.length + ' entities' + (rows.length > 300 ? ' (showing first 300, narrow your filter)' : '') + ' — click a row for example comments';
  
  body.querySelectorAll('.ent-select').forEach(chk => {
    chk.addEventListener('click', (e) => {
      e.stopPropagation();
      const entity = chk.getAttribute('data-entity');
      if (chk.checked) {
        selectedEntities.add(entity);
      } else {
        selectedEntities.delete(entity);
      }
      updateEntSelectionBar();
    });
  });
  
  body.querySelectorAll('tr[data-entity]').forEach(row => {
    row.addEventListener('click', (e) => {
      if (e.target.closest('td') && e.target.closest('td').querySelector('.ent-select')) {
        return;
      }
      openDrill('entity', row.getAttribute('data-entity'));
    });
  });
}
document.querySelectorAll('#entTable th[data-sort]').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.sort;
    entSort.dir = (entSort.col === col) ? -entSort.dir : -1;
    entSort.col = col;
    renderEntTable();
  });
});
['entPopulation','entConstruct','entSearch'].forEach(id => document.getElementById(id).addEventListener('input', renderEntTable));

// ---------- Domains ----------
function blank(v) { return v === null || v === undefined || v === '' ? '&mdash;' : v; }
function populateSelectOptions(selectId, values, labelFn) {
  const el = document.getElementById(selectId);
  const existing = new Set([...el.options].map(o => o.value));
  values.forEach(v => { if (v && !existing.has(v)) el.innerHTML += '<option value="' + v + '">' + (labelFn ? labelFn(v) : v) + '</option>'; });
}
populateSelectOptions('domTier', [...new Set(DATA.domains.map(r => r.link_source_tier))].filter(Boolean).sort());
populateSelectOptions('domCred', [...new Set(DATA.domains.map(r => r.credentials_taxonomy_tier))].filter(Boolean).sort());
populateSelectOptions('domMbfc', [...new Set(DATA.domains.map(r => r.mbfc_reliability_label))].filter(Boolean).sort());

let domSort = { col: 'total_citations', dir: -1 };
function renderDomTable() {
  const tier = document.getElementById('domTier').value;
  const cred = document.getElementById('domCred').value;
  const mbfc = document.getElementById('domMbfc').value;
  const q = document.getElementById('domSearch').value.toLowerCase();
  let rows = DATA.domains.filter(r =>
    (!tier || r.link_source_tier === tier) && (!cred || r.credentials_taxonomy_tier === cred) &&
    (!mbfc || r.mbfc_reliability_label === mbfc) && (!q || r.domain.toLowerCase().includes(q))
  );
  rows.sort((a, b) => {
    const av = a[domSort.col], bv = b[domSort.col];
    if (av == null && bv == null) return 0;
    if (av == null) return 1; if (bv == null) return -1;
    if (typeof av === 'string') return av.localeCompare(bv) * domSort.dir;
    return (av - bv) * domSort.dir;
  });
  const body = document.getElementById('domTableBody');
  body.innerHTML = rows.slice(0, 400).map(r =>
    '<tr class="clickable" data-domain="' + r.domain.replace(/"/g, '&quot;') + '"><td>' + r.domain + '</td>' +
    '<td class="num">' + fmtN(r.n_distinct_urls) + '</td>' +
    '<td class="num">' + fmtN(r.total_citations) + '</td>' +
    '<td class="num">' + fmtN(r.total_distinct_authors) + '</td>' +
    '<td>' + blank(r.credentials_taxonomy_tier) + '</td>' +
    '<td>' + blank(r.link_source_tier) + '</td>' +
    '<td>' + blank(r.mbfc_reliability_label) + '</td>' +
    '<td>' + blank(r.sjr_quartile) + '</td></tr>'
  ).join('');
  document.getElementById('domRowCount').textContent = rows.length + ' domains' + (rows.length > 400 ? ' (showing first 400, narrow your filter)' : '') + ' — click a row for example comments';
  body.querySelectorAll('tr[data-domain]').forEach(row => {
    row.addEventListener('click', () => openDrill('domain', row.getAttribute('data-domain')));
  });
}
document.querySelectorAll('#domTable th[data-sort]').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.sort;
    domSort.dir = (domSort.col === col) ? -domSort.dir : -1;
    domSort.col = col;
    renderDomTable();
  });
});
['domTier','domCred','domMbfc','domSearch'].forEach(id => document.getElementById(id).addEventListener('input', renderDomTable));

// ---------- Top cited sources ----------
populateSelectOptions('srcTier', [...new Set(DATA.topCitedUrls.map(r => r.link_source_tier))].filter(Boolean).sort());

let srcSort = { col: 'distinct_authors', dir: -1 };
function truncMid(s, n) { return s.length <= n ? s : s.slice(0, n - 1) + '&hellip;'; }
function renderSrcTable() {
  const tier = document.getElementById('srcTier').value;
  const q = document.getElementById('srcSearch').value.toLowerCase();
  let rows = DATA.topCitedUrls.filter(r =>
    (!tier || r.link_source_tier === tier) &&
    (!q || [r.url, r.domain, r.extracted_byline, r.title].some(v => v && v.toLowerCase().includes(q)))
  );
  rows.sort((a, b) => {
    const av = a[srcSort.col], bv = b[srcSort.col];
    if (av == null && bv == null) return 0;
    if (av == null) return 1; if (bv == null) return -1;
    if (typeof av === 'string') return av.localeCompare(bv) * srcSort.dir;
    return (av - bv) * srcSort.dir;
  });
  const body = document.getElementById('srcTableBody');
  body.innerHTML = rows.map(r =>
    '<tr class="clickable" data-url="' + r.url.replace(/"/g, '&quot;') + '"><td><a href="' + r.url + '" target="_blank" rel="noopener">' + truncMid(r.url.replace(/^https?:\/\//, ''), 60) + '</a></td>' +
    '<td>' + r.domain + '</td>' +
    '<td class="num">' + fmtN(r.distinct_authors) + '</td>' +
    '<td class="num">' + fmtN(r.mention_count) + '</td>' +
    '<td>' + blank(r.link_source_tier) + '</td>' +
    '<td>' + blank(r.sjr_quartile) + '</td>' +
    '<td>' + blank(r.extracted_byline) + '</td>' +
    '<td>' + blank(r.title ? truncMid(r.title, 50) : null) + '</td></tr>'
  ).join('');
  document.getElementById('srcRowCount').textContent = rows.length + ' URLs — click a row for example comments';
  body.querySelectorAll('tr[data-url] a').forEach(a => a.addEventListener('click', (e) => e.stopPropagation()));
  body.querySelectorAll('tr[data-url]').forEach(row => {
    row.addEventListener('click', () => openDrill('url', row.getAttribute('data-url')));
  });
}
document.querySelectorAll('#srcTable th[data-sort]').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.sort;
    srcSort.dir = (srcSort.col === col) ? -srcSort.dir : -1;
    srcSort.col = col;
    renderSrcTable();
  });
});
['srcTier','srcSearch'].forEach(id => document.getElementById(id).addEventListener('input', renderSrcTable));

// ---------- Methods & robustness ----------
function renderQualityTable() {
  document.getElementById('qualityTableBody').innerHTML = DATA.dataQuality.map(r =>
    '<tr><td>' + r.metric + '</td>' +
    '<td class="num">' + fmtN(r.n_flagged) + '</td>' +
    '<td class="num">' + (r.n_total != null ? fmtN(r.n_total) : '&mdash;') + '</td>' +
    '<td class="num">' + (r.pct != null ? r.pct + '%' : '&mdash;') + '</td>' +
    '<td style="white-space:normal; max-width:420px;">' + r.detail + '</td></tr>'
  ).join('');
}
function renderInsiderTable() {
  const rows = [...DATA.insiderSweep].sort((a,b) => a.insider_presence_threshold - b.insider_presence_threshold);
  document.getElementById('insiderTableBody').innerHTML = rows.map(r =>
    '<tr><td class="num">' + r.insider_presence_threshold + '</td>' +
    '<td class="num">' + fmtN(r.n_obs) + '</td>' +
    '<td class="num">' + r.ols_coef + '</td>' +
    '<td class="num">' + r.ols_pvalue.toExponential(2) + '</td>' +
    '<td class="num">' + r.logit_coef + '</td>' +
    '<td class="num">' + r.logit_pvalue.toExponential(2) + '</td></tr>'
  ).join('');
}
function renderHitlTable() {
  document.getElementById('hitlTableBody').innerHTML = DATA.hitlCoverage.map(r =>
    '<tr><td>' + r.construct + '</td>' +
    '<td>' + (r.group === 'A' ? 'A (real human labels)' : 'B (LLM-only, no codebook)') + '</td>' +
    '<td class="num">' + fmtN(r.n_labeled) + '</td>' +
    '<td>' + r.label_scheme + '</td>' +
    '<td style="white-space:normal; max-width:320px;">' + r.note + '</td></tr>'
  ).join('');
}
function renderCorporaTable() {
  document.getElementById('corporaTableBody').innerHTML = DATA.comparisonCorpora.map(r => {
    const fmtDate = ts => new Date(ts * 1000).toISOString().slice(0, 10);
    return '<tr><td>' + r.corpus + '</td>' +
      '<td>' + r.status + '</td>' +
      '<td class="num">' + fmtN(r.n_comments) + '</td>' +
      '<td>' + fmtDate(r.earliest_utc) + ' &ndash; ' + fmtDate(r.latest_utc) + '</td>' +
      '<td style="white-space:normal; max-width:380px;">' + r.reason + '</td></tr>';
  }).join('');
}

// ---------- Semantic keyness ----------
populateSelectOptions('keySubreddit', [...new Set(DATA.semanticKeyness.map(r => r.subreddit))].filter(Boolean).sort());

let keySort = { col: 'log_likelihood', dir: -1 };
function renderKeyTable() {
  const comparison = document.getElementById('keyComparison').value;
  const subreddit = document.getElementById('keySubreddit').value;
  const q = document.getElementById('keySearch').value.toLowerCase();
  let rows = DATA.semanticKeyness.filter(r =>
    (!comparison || r.comparison === comparison) && (!subreddit || r.subreddit === subreddit) &&
    (!q || r.word.toLowerCase().includes(q))
  );
  rows.sort((a, b) => {
    const av = a[keySort.col], bv = b[keySort.col];
    if (typeof av === 'string') return av.localeCompare(bv) * keySort.dir;
    return (av - bv) * keySort.dir;
  });
  document.getElementById('keyTableBody').innerHTML = rows.map(r =>
    '<tr><td>' + r.word + '</td><td>' + r.comparison + '</td><td>' + r.subreddit + '</td>' +
    '<td class="num">' + fmtN(r.freq_c1) + '</td><td class="num">' + fmtN(r.freq_c2) + '</td>' +
    '<td class="num">' + r.log_likelihood.toFixed(1) + '</td></tr>'
  ).join('');
  document.getElementById('keyRowCount').textContent = rows.length + ' words';
}
document.querySelectorAll('#keyTable th[data-sort]').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.sort;
    keySort.dir = (keySort.col === col) ? -keySort.dir : -1;
    keySort.col = col;
    renderKeyTable();
  });
});
['keyComparison','keySubreddit','keySearch'].forEach(id => document.getElementById(id).addEventListener('input', renderKeyTable));

// ---------- Threads ----------
let threadSort = { col: 'n_threads', dir: -1 };
function renderThreadTable() {
  const q = document.getElementById('threadSearch').value.toLowerCase();
  let rows = DATA.threadByDomain.filter(r => !q || r.domain.toLowerCase().includes(q));
  rows.sort((a, b) => {
    const av = a[threadSort.col], bv = b[threadSort.col];
    if (typeof av === 'string') return av.localeCompare(bv) * threadSort.dir;
    return (av - bv) * threadSort.dir;
  });
  document.getElementById('threadTableBody').innerHTML = rows.map(r =>
    '<tr><td>' + r.domain + '</td>' +
    '<td class="num">' + fmtN(r.n_threads) + '</td>' +
    '<td class="num">' + r.avg_post_score.toFixed(1) + '</td>' +
    '<td class="num">' + r.avg_total_comments.toFixed(1) + '</td>' +
    '<td class="num">' + r.avg_comment_upvotes.toFixed(2) + '</td>' +
    '<td class="num">' + r.avg_controversiality.toFixed(3) + '</td>' +
    '<td class="num">' + r.avg_evidence_score.toFixed(3) + '</td>' +
    '<td class="num">' + r.avg_rhetoric_score.toFixed(3) + '</td>' +
    '<td class="num">' + r.avg_certainty_score.toFixed(3) + '</td>' +
    '<td class="num">' + r.avg_authority_score.toFixed(3) + '</td>' +
    '<td class="num">' + r.avg_hedge_score.toFixed(3) + '</td></tr>'
  ).join('');
  document.getElementById('threadRowCount').textContent = rows.length + ' domains';
}
document.querySelectorAll('#threadTable th[data-sort]').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.sort;
    threadSort.dir = (threadSort.col === col) ? -threadSort.dir : -1;
    threadSort.col = col;
    renderThreadTable();
  });
});
document.getElementById('threadSearch').addEventListener('input', renderThreadTable);

// ---------- Vocabulary turnover ----------
let turnoverChart = null;
function renderTurnoverChart() {
  const rows = DATA.lexicalTurnover;
  if (turnoverChart) turnoverChart.destroy();
  turnoverChart = new Chart(document.getElementById('turnoverChart'), {
    type: 'line',
    data: {
      labels: rows.map(r => { const [y, mo] = r.month.split('-'); return mo === '01' ? y : ''; }),
      datasets: [{ data: rows.map(r => r.overlap_with_previous * 100), borderColor: cove()[3], backgroundColor: cove()[3], borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.15 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false }, tooltip: { callbacks: {
        title: (items) => rows[items[0].dataIndex].month,
        label: (item) => item.parsed.y.toFixed(1) + '% overlap with previous month (' + fmtN(rows[item.dataIndex].new_words_count) + ' new words)',
      } } },
      scales: {
        x: { grid: { display: false }, ticks: { color: tickColor, font: { size: 11 }, maxRotation: 0, autoSkip: false, callback: function(val) { const l = this.getLabelForValue(val); return l || null; } } },
        y: { beginAtZero: true, grid: { color: gridColor() }, ticks: { color: tickColor, font: { size: 11 }, callback: v => v + '%' } },
      },
    },
  });
}

// ---------- Regression browser ----------
let regSort = { col: 'pvalue', dir: 1 };
function populateRegFilters() {
  const sources = [...new Set(DATA.regressions.map(r => r.source))];
  const models = [...new Set(DATA.regressions.map(r => r.model_type))];
  document.getElementById('regSource').innerHTML += sources.map(s => '<option value="' + s + '">' + s + '</option>').join('');
  document.getElementById('regModel').innerHTML += models.map(m => '<option value="' + m + '">' + m + '</option>').join('');
}
function renderRegTable() {
  const src = document.getElementById('regSource').value;
  const model = document.getElementById('regModel').value;
  const q = document.getElementById('regSearch').value.toLowerCase();
  const sigOnly = document.getElementById('regSigOnly').checked;
  let rows = DATA.regressions.filter(r =>
    (!src || r.source === src) && (!model || r.model_type === model) &&
    (!q || (r.stratum + ' ' + r.variable).toLowerCase().includes(q)) &&
    (!sigOnly || r.pvalue < 0.05)
  );
  rows.sort((a, b) => {
    const av = a[regSort.col], bv = b[regSort.col];
    if (typeof av === 'string') return av.localeCompare(bv) * regSort.dir;
    return (av - bv) * regSort.dir;
  });
  const body = document.getElementById('regTableBody');
  body.innerHTML = rows.slice(0, 400).map(r => {
    const sig = r.pvalue < 0.05;
    return '<tr><td>' + r.source + '</td><td>' + r.stratum + '</td><td>' + r.model_type + '</td><td>' + r.variable + '</td>' +
      '<td class="num">' + Number(r.coef).toFixed(4) + '</td>' +
      '<td class="num' + (sig ? ' sig' : '') + '">' + Number(r.pvalue).toExponential(2) + '</td>' +
      '<td class="num">' + fmtN(r.n_obs) + '</td></tr>';
  }).join('');
  document.getElementById('regRowCount').textContent = rows.length + ' rows' + (rows.length > 400 ? ' (showing first 400, narrow your filter)' : '');
}
document.querySelectorAll('#regTable th[data-sort]').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.sort;
    regSort.dir = (regSort.col === col) ? -regSort.dir : 1;
    regSort.col = col;
    renderRegTable();
  });
});
['regSource','regModel','regSearch','regSigOnly'].forEach(id => document.getElementById(id).addEventListener('input', renderRegTable));

// ---------- Manual Entity Merging HITL Support ----------
const selectedEntities = new Set();
let entityMerges = {}; // source_key (lower) -> target_key (lower)
let canonicalMergeNames = {}; // lower_key -> original Cased Name

function applyMergesToEntities() {
  if (!window.originalEntities) window.originalEntities = [...DATA.entities];
  
  canonicalMergeNames = {};
  window.originalEntities.forEach(e => {
    canonicalMergeNames[e.entity.toLowerCase()] = e.entity;
  });
  
  const rolled = {};
  window.originalEntities.forEach(e => {
    const ek = e.entity.toLowerCase();
    
    let targetKey = ek;
    while (entityMerges[targetKey]) {
      targetKey = entityMerges[targetKey];
      if (targetKey === ek) break;
    }
    
    const targetCasedName = canonicalMergeNames[targetKey] || targetKey.charAt(0).toUpperCase() + targetKey.slice(1);
    
    if (!rolled[targetKey]) {
      rolled[targetKey] = {
        ...e,
        entity: targetCasedName,
        _source_entities: [],
        mention_count: 0,
        _hostile_mentions: 0,
        _endorsement_mentions: 0,
        _has_stance: false
      };
    }
    
    if (ek !== targetKey) {
      rolled[targetKey]._source_entities.push(e.entity);
    }
    
    rolled[targetKey].mention_count += e.mention_count;
    
    if (e.pct_hostile != null) {
      rolled[targetKey]._has_stance = true;
      rolled[targetKey]._hostile_mentions += e.mention_count * e.pct_hostile;
    }
    if (e.pct_predicted_endorsement != null) {
      rolled[targetKey]._endorsement_mentions += e.mention_count * e.pct_predicted_endorsement;
    }
  });
  
  DATA.entities = Object.values(rolled).map(e => {
    if (e._has_stance && e.mention_count > 0) {
      e.pct_hostile = e._hostile_mentions / e.mention_count;
      e.pct_predicted_endorsement = e._endorsement_mentions / e.mention_count;
    }
    return e;
  });

  // Re-build entTsNames
  const entAllCountsNew = {};
  DATA.entities.forEach(r => { entAllCountsNew[r.entity] = Math.max(entAllCountsNew[r.entity] || 0, r.mention_count || 0); });
  entTsNames.length = 0;
  entTsNames.push(...Object.keys(entAllCountsNew));
}

async function loadEntityMerges() {
  try {
    const resp = await fetch(drillApiUrl('entity_merges'));
    const data = await resp.json();
    if (data.merges) {
      entityMerges = {};
      data.merges.forEach(m => {
        entityMerges[m.source_key] = m.target_key;
      });
      // Reset the cache to force refetching of the newly combined timelines
      entTsSeriesCache = {};
      
      document.getElementById('mergeCountLabel').textContent = data.merges.length;
      applyMergesToEntities();
      renderEntTable();
      entTsRenderPicker(document.getElementById('entTsSearch').value);
      entTsBuildChart();
    }
  } catch (err) {
    console.error("Failed to load merges:", err);
  }
}

function updateEntSelectionBar() {
  const bar = document.getElementById('entCombineBar');
  if (selectedEntities.size >= 2) {
    bar.style.display = 'flex';
    document.getElementById('entCombineText').textContent = `${selectedEntities.size} entities selected`;
  } else {
    bar.style.display = 'none';
  }
}

// Open combine dialog modal
document.getElementById('entCombineBtn').addEventListener('click', () => {
  const list = [...selectedEntities];
  document.getElementById('mergeCountText').textContent = list.length;
  
  // Populate target select dropdown
  const sel = document.getElementById('mergeTargetSelect');
  sel.innerHTML = list.map(e => `<option value="${e}">${e}</option>`).join('');
  
  // Populate sources list view
  const lst = document.getElementById('mergeSourcesList');
  lst.innerHTML = list.map(e => `<div>• <strong>${e}</strong></div>`).join('');
  
  document.getElementById('mergeTargetCustom').value = '';
  document.getElementById('mergeOverlay').classList.add('open');
});

// Cancel combine dialog
const closeCombineModal = () => {
  document.getElementById('mergeOverlay').classList.remove('open');
};
document.getElementById('mergeClose').addEventListener('click', closeCombineModal);
document.getElementById('mergeCancelBtn').addEventListener('click', closeCombineModal);

// Confirm combine POST to API
document.getElementById('mergeConfirmBtn').addEventListener('click', async () => {
  const custom = document.getElementById('mergeTargetCustom').value.trim();
  const target = custom || document.getElementById('mergeTargetSelect').value;
  const list = [...selectedEntities];
  const rater = (document.getElementById('hitl_rater_name_input')?.value || 'Anonymous').trim();
  
  const sources = list.filter(e => e !== target);
  if (sources.length === 0) {
    alert("Please enter or choose a target that is different from your sources to combine.");
    return;
  }
  
  try {
    const resp = await fetch(drillApiUrl('combine_entities'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target, sources, rater })
    });
    const data = await resp.json();
    if (data.status === 'ok') {
      selectedEntities.clear();
      updateEntSelectionBar();
      document.getElementById('entSelectAll').checked = false;
      closeCombineModal();
      await loadEntityMerges();
    } else {
      alert("Error: " + (data.error || "Unknown error"));
    }
  } catch (err) {
    alert("Request failed: " + err.message);
  }
});

// Clear selection
document.getElementById('entClearSelectionBtn').addEventListener('click', () => {
  selectedEntities.clear();
  updateEntSelectionBar();
  document.getElementById('entSelectAll').checked = false;
  renderEntTable();
});

// Select All Checkbox
document.getElementById('entSelectAll').addEventListener('change', (e) => {
  const chks = document.querySelectorAll('.ent-select');
  chks.forEach(chk => {
    const ent = chk.getAttribute('data-entity');
    chk.checked = e.target.checked;
    if (e.target.checked) {
      selectedEntities.add(ent);
    } else {
      selectedEntities.delete(ent);
    }
  });
  updateEntSelectionBar();
});

// Manage merges modal trigger
document.getElementById('btnManageMerges').addEventListener('click', async () => {
  const tableBody = document.getElementById('manageMergesTableBody');
  tableBody.innerHTML = '<tr><td colspan="3" style="text-align:center;">Loading...</td></tr>';
  document.getElementById('manageMergesOverlay').classList.add('open');
  
  try {
    const resp = await fetch(drillApiUrl('entity_merges'));
    const data = await resp.json();
    
    if (data.merges && data.merges.length > 0) {
      tableBody.innerHTML = data.merges.map(m => {
        const source_cased = canonicalMergeNames[m.source_key] || m.source_key;
        const target_cased = canonicalMergeNames[m.target_key] || m.target_key;
        return `<tr>
          <td style="font-weight:600;">${target_cased}</td>
          <td>${source_cased}</td>
          <td style="text-align:center;">
            <button class="btn btn-uncombine" data-source="${m.source_key}" style="padding:3px 8px; font-size:11px; background:var(--neg); color:white; border:none; border-radius:4px; cursor:pointer;">Uncombine</button>
          </td>
        </tr>`;
      }).join('');
      
      tableBody.querySelectorAll('.btn-uncombine').forEach(btn => {
        btn.addEventListener('click', async () => {
          const source = btn.getAttribute('data-source');
          const rater = (document.getElementById('hitl_rater_name_input')?.value || 'Anonymous').trim();
          if (confirm(`Are you sure you want to uncombine this entity?`)) {
            try {
              const r = await fetch(drillApiUrl('uncombine_entity'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source, rater })
              });
              const rdata = await r.json();
              if (rdata.status === 'ok') {
                await loadEntityMerges();
                // re-click manage merges to refresh list
                document.getElementById('btnManageMerges').click();
              } else {
                alert("Error: " + rdata.error);
              }
            } catch (err) {
              alert("Request failed: " + err.message);
            }
          }
        });
      });
    } else {
      tableBody.innerHTML = '<tr><td colspan="3" style="text-align:center; color:var(--ink-3); padding:1rem;">No combined entities found.</td></tr>';
    }
  } catch (err) {
    tableBody.innerHTML = `<tr><td colspan="3" style="text-align:center; color:var(--neg);">Error loading merges: ${err.message}</td></tr>`;
  }
});

const closeManageMerges = () => {
  document.getElementById('manageMergesOverlay').classList.remove('open');
};
document.getElementById('manageMergesClose').addEventListener('click', closeManageMerges);
document.getElementById('manageMergesDoneBtn').addEventListener('click', closeManageMerges);

// Clear timeline plots event listeners
document.getElementById('btnClearTopics').addEventListener('click', () => {
  tsSelected = [];
  tsRenderPicker(document.getElementById('tsSearch').value);
  tsBuildChart();
});

document.getElementById('btnClearEntities').addEventListener('click', () => {
  entTsSelected = [];
  entTsRenderPicker(document.getElementById('entTsSearch').value);
  entTsBuildChart();
});
// ---------- Init ----------
loadEntityMerges();
renderOverview();
tsRenderPicker(''); tsBuildChart(); tsRenderLegend();
renderAllTopicsTable();
renderAuthorChart();
renderCredGapChart();
renderStanceChart();
renderEntTable();
entTsRenderPicker(''); entTsBuildChart(); entTsRenderLegend();
renderDomTable();
renderSrcTable();
populateRegFilters();
renderRegTable();
renderQualityTable();
renderInsiderTable();
renderHitlTable();
renderCorporaTable();
renderKeyTable();
renderThreadTable();
renderTurnoverChart();

function rerenderAll() {
  document.getElementById('overviewStats').innerHTML = '';
  renderOverview();
  tsBuildChart(); tsRenderLegend();
  renderAuthorChart();
  renderCredGapChart();
  renderStanceChart();
  entTsBuildChart(); entTsRenderLegend();
  renderTurnoverChart();
}
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', rerenderAll);
new MutationObserver(rerenderAll).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });