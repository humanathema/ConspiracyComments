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
    
    if (btn.dataset.tab === 'topicquality') {
      loadTopicQualityTab();
    }
    if (btn.dataset.tab === 'ats' && !window._atsLoaded) {
      window._atsLoaded = true;
      loadAtsTab();
    }
  });
});

// ---------- AboveTopSecret tab ----------
// Browsing (the "Browse threads" index below) is the primary way in --
// a real forum index over all 339k threads, sorted/paginated/filterable.
// Keyword search further down is an adjunct for finding one specific
// comment by text, not the main navigation mode -- it starts empty and
// never auto-loads an unfiltered dump of arbitrary comments.
async function loadAtsTab() {
  loadAtsThreadIndex(true);
  document.getElementById('atsThreadIndexFilter')?.addEventListener('input', () => loadAtsThreadIndex(true));
  document.getElementById('atsThreadIndexSort')?.addEventListener('change', () => loadAtsThreadIndex(true));
  document.getElementById('atsThreadIndexLoadMore')?.addEventListener('click', () => loadAtsThreadIndex(false));

  try {
    const resp = await fetch(drillApiUrl('ats_domains'));
    const data = await resp.json();
    document.getElementById('atsDomainsBody').innerHTML = (data.rows || []).slice(0, 100).map(r =>
      `<tr class="clickable" data-domain="${r.domain}"><td>${(r.domain || '').replace(/</g,'&lt;')}</td><td class="num">${fmtN(r.mentions)}</td></tr>`
    ).join('');

    // Add click listener to domains
    document.querySelectorAll('#atsDomainsBody tr').forEach(tr => {
      tr.addEventListener('click', () => {
        const domain = tr.dataset.domain;
        const input = document.getElementById('atsSearchInput');
        if (input) {
          input.value = domain;
          atsSearch(domain);
          input.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      });
    });
  } catch (err) { console.warn('ats_domains failed:', err.message); }
}

let atsThreadIndexState = { offset: 0, total: 0, rows: [] };
let atsThreadIndexDebounce = null;
function loadAtsThreadIndex(reset) {
  clearTimeout(atsThreadIndexDebounce);
  atsThreadIndexDebounce = setTimeout(async () => {
    if (reset) { atsThreadIndexState = { offset: 0, total: 0, rows: [] }; }
    const q = document.getElementById('atsThreadIndexFilter')?.value || '';
    const sort = document.getElementById('atsThreadIndexSort')?.value || 'total_comments';
    const dir = sort === 'thread_title' ? 'asc' : 'desc';
    try {
      const resp = await fetch(drillApiUrl('ats_thread_index', { q, sort, dir, offset: atsThreadIndexState.offset, limit: 50 }));
      const data = await resp.json();
      atsThreadIndexState.rows = atsThreadIndexState.rows.concat(data.rows || []);
      atsThreadIndexState.total = data.total || 0;
      atsThreadIndexState.offset = atsThreadIndexState.rows.length;

      document.getElementById('atsThreadIndexBody').innerHTML = atsThreadIndexState.rows.map((r, i) =>
        `<tr class="clickable" data-idx="${i}"><td>${(r.thread_title || '').replace(/</g,'&lt;')}</td><td class="num">${fmtN(r.total_comments)}</td><td class="num">${fmtN(r.starred_comments)}</td></tr>`
      ).join('');
      document.querySelectorAll('#atsThreadIndexBody tr').forEach(tr => {
        tr.addEventListener('click', () => {
          const idx = parseInt(tr.dataset.idx);
          const r = atsThreadIndexState.rows[idx];
          if (r) openAtsThreadView(r.thread_id, null, r.thread_title);
        });
      });

      const shown = atsThreadIndexState.rows.length;
      document.getElementById('atsThreadIndexCount').textContent = fmtN(shown) + ' of ' + fmtN(atsThreadIndexState.total) + ' threads shown';
      document.getElementById('atsThreadIndexLoadMore').style.display = shown < atsThreadIndexState.total ? '' : 'none';
    } catch (err) { console.warn('ats_thread_index failed:', err.message); }
  }, reset ? 250 : 0);
}

let atsSearchDebounce = null;
function atsSearch(q) {
  clearTimeout(atsSearchDebounce);
  const q_str = (q || '').trim();
  if (!q_str) {
    document.getElementById('atsSearchBody').innerHTML = '';
    document.getElementById('atsSearchCount').textContent = '';
    return;
  }
  atsSearchDebounce = setTimeout(async () => {
    try {
      const resp = await fetch(drillApiUrl('ats_search', { q, limit: 50 }));
      const data = await resp.json();
      window._atsComments = data.rows || [];
      document.getElementById('atsSearchBody').innerHTML = (data.rows || []).map((r, i) =>
        `<tr class="clickable" data-idx="${i}"><td>${(r.thread_title || '').replace(/</g,'&lt;')}</td><td>${(r.author || '').replace(/</g,'&lt;')}</td>` +
        `<td style="white-space:nowrap;">${(r.raw_timestamp || '').replace(/</g,'&lt;')}</td>` +
        `<td>${(r.text || '').slice(0, 220).replace(/</g,'&lt;')}${(r.text||'').length > 220 ? '&hellip;' : ''}</td>` +
        `<td style="text-align:center;">${r.starred ? '&#9733;' : ''}</td></tr>`
      ).join('');

      // Add click listener to comment rows
      document.querySelectorAll('#atsSearchBody tr').forEach(tr => {
        tr.addEventListener('click', () => {
          const idx = parseInt(tr.dataset.idx);
          const r = window._atsComments[idx];
          if (r) openAtsThreadView(r.thread_id, r.comment_id, r.thread_title);
        });
      });

      document.getElementById('atsSearchCount').textContent = fmtN(data.total) + ' matching comments' + (data.total > 50 ? ' (showing first 50)' : '');
    } catch (err) { console.warn('ats_search failed:', err.message); }
  }, 300);
}
document.getElementById('atsSearchInput')?.addEventListener('input', (e) => atsSearch(e.target.value));

// ---------- ATS threaded forum view ----------
// Full thread scrolled as a sequential forum discussion (page/post order),
// loaded in chunks around the entry post since threads run up to ~10k
// posts. Only ~7% of posts have a detected reply-to (parsed from quoted
// text) -- those are visually indented under their parent when the parent
// is in the currently-loaded window; everything else renders inline in
// chronological order, same as reading the archived thread itself.
const ATS_THREAD_CHUNK = 70;
let atsThread = null; // { threadId, threadTitle, anchorCommentId, rows: [], total, minOffset, maxOffset, loading }

async function openAtsThreadView(threadId, anchorCommentId, threadTitle) {
  const pane = document.getElementById('drillDetail');
  pane.classList.remove('empty');
  pane.innerHTML = '<div class="thread-view"><div class="thread-scroll" style="display:flex; align-items:center; justify-content:center; color:var(--ink-3); font-size:13px;">Loading thread&hellip;</div></div>';

  document.getElementById('drillTitle').textContent = "AboveTopSecret Thread";
  document.getElementById('drillCaption').textContent = "Scroll to read the discussion in order; replies detected from quoted text are indented under their parent post.";

  const splitList = document.querySelector('.modal-split-list');
  const splitDetail = document.querySelector('.modal-split-detail');
  if (splitList) splitList.style.display = 'none';
  if (splitDetail) {
    splitDetail.style.width = '100%';
    splitDetail.style.maxWidth = '100%';
  }
  document.getElementById('drillOverlay').classList.add('open');

  atsThread = { threadId, threadTitle, anchorCommentId, rows: [], total: 0, minOffset: 0, maxOffset: 0, loading: false };

  try {
    const params = { thread_id: threadId, limit: ATS_THREAD_CHUNK };
    if (anchorCommentId) params.center_post_id = anchorCommentId; else params.offset = 0;
    const url = drillApiUrl('ats_thread_posts', params);
    const resp = await fetch(url);
    const data = await resp.json();
    atsThread.rows = data.rows || [];
    atsThread.total = data.total || 0;
    atsThread.minOffset = data.offset || 0;
    atsThread.maxOffset = (data.offset || 0) + atsThread.rows.length;
    renderAtsThreadView();
  } catch (err) {
    pane.innerHTML = '<div class="thread-view"><div class="thread-scroll" style="color:var(--neg); font-size:13px;">Could not load thread (' + err.message + ').</div></div>';
  }
}

function renderAtsThreadView() {
  const pane = document.getElementById('drillDetail');
  const t = atsThread;
  const loadedByCommentId = new Map(t.rows.map(r => [String(r.comment_id), r]));

  const postsHtml = t.rows.map(r => {
    const isAnchor = String(r.comment_id) === String(t.anchorCommentId);
    const parent = r.reply_to_post_ids ? loadedByCommentId.get(String(r.reply_to_post_ids)) : null;
    const isReply = !!parent;

    const { html: lexHtml } = highlightLexicon(escapeHtml(r.text || ''));
    const metaBits = [];
    metaBits.push('<span class="thread-post-author">' + escapeHtml(r.author || 'unknown') + '</span>');
    if (r.raw_timestamp) metaBits.push(escapeHtml(r.raw_timestamp));
    if (r.starred) metaBits.push('<span class="thread-post-star">&#9733; starred</span>');
    if (r.hs_prob != null) metaBits.push('hedged suspicion ' + Number(r.hs_prob).toFixed(3));

    return (
      '<div class="thread-post' + (isReply ? ' thread-post-reply' : '') + (isAnchor ? ' thread-post-anchor' : '') + '" ' +
      'id="ats-post-' + r.comment_id + '" data-comment-id="' + r.comment_id + '">' +
      '<div class="thread-post-meta">' + metaBits.join(' &nbsp;&middot;&nbsp; ') + '</div>' +
      (isReply ? '<div class="thread-post-replyto">&#8618; replying to ' + escapeHtml(parent.author || 'earlier post') + '</div>' : '') +
      '<div class="thread-post-text">' + lexHtml + '</div>' +
      '</div>'
    );
  }).join('');

  const topSentinel = t.minOffset > 0
    ? '<div class="thread-load-sentinel" id="atsThreadLoadOlder">Loading earlier posts&hellip;</div>'
    : '<div class="thread-load-sentinel">&mdash; start of thread &mdash;</div>';
  const bottomSentinel = t.maxOffset < t.total
    ? '<div class="thread-load-sentinel" id="atsThreadLoadNewer">Loading later posts&hellip;</div>'
    : '<div class="thread-load-sentinel">&mdash; end of thread &mdash;</div>';

  pane.innerHTML =
    '<div class="thread-view">' +
    '<div class="thread-view-head"><span class="label">Thread</span> ' + escapeHtml(t.threadTitle || 'AboveTopSecret Thread') +
    ' &nbsp;&middot;&nbsp; ' + fmtN(t.total) + ' posts</div>' +
    '<div class="thread-scroll" id="atsThreadScroll">' + topSentinel + postsHtml + bottomSentinel + '</div>' +
    '</div>';

  const scrollEl = document.getElementById('atsThreadScroll');
  const anchorEl = document.getElementById('ats-post-' + t.anchorCommentId);
  if (anchorEl) anchorEl.scrollIntoView({ block: 'center' });
  scrollEl.addEventListener('scroll', onAtsThreadScroll);
}

function onAtsThreadScroll(e) {
  const el = e.target;
  const t = atsThread;
  if (!t || t.loading) return;
  if (el.scrollTop < 200 && t.minOffset > 0) {
    loadMoreAtsThreadPosts('before');
  } else if (el.scrollHeight - el.scrollTop - el.clientHeight < 200 && t.maxOffset < t.total) {
    loadMoreAtsThreadPosts('after');
  }
}

async function loadMoreAtsThreadPosts(direction) {
  const t = atsThread;
  t.loading = true;
  const scrollEl = document.getElementById('atsThreadScroll');
  const prevScrollHeight = scrollEl ? scrollEl.scrollHeight : 0;
  const prevScrollTop = scrollEl ? scrollEl.scrollTop : 0;

  const fetchOffset = direction === 'before' ? Math.max(0, t.minOffset - ATS_THREAD_CHUNK) : t.maxOffset;
  const fetchLimit = direction === 'before' ? (t.minOffset - fetchOffset) : ATS_THREAD_CHUNK;

  try {
    const url = drillApiUrl('ats_thread_posts', { thread_id: t.threadId, offset: fetchOffset, limit: fetchLimit });
    const resp = await fetch(url);
    const data = await resp.json();
    const newRows = data.rows || [];
    if (direction === 'before') {
      t.rows = newRows.concat(t.rows);
      t.minOffset = fetchOffset;
    } else {
      t.rows = t.rows.concat(newRows);
      t.maxOffset = fetchOffset + newRows.length;
    }
    renderAtsThreadView();
    // Preserve scroll position relative to content rather than jumping to top/anchor
    const newScrollEl = document.getElementById('atsThreadScroll');
    if (newScrollEl && direction === 'before') {
      newScrollEl.scrollTop = newScrollEl.scrollHeight - prevScrollHeight + prevScrollTop;
    } else if (newScrollEl && direction === 'after') {
      newScrollEl.scrollTop = prevScrollTop;
    }
  } catch (err) {
    console.warn('loadMoreAtsThreadPosts failed:', err.message);
  } finally {
    t.loading = false;
  }
}

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
  url.searchParams.set('_cb', Date.now()); // Prevent browser and CDN caching
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
function closeDrill() {
  document.getElementById('drillOverlay').classList.remove('open');
  // Restore split layout if modified by single comment previewer
  const splitList = document.querySelector('.modal-split-list');
  const splitDetail = document.querySelector('.modal-split-detail');
  if (splitList) splitList.style.display = '';
  if (splitDetail) {
    splitDetail.style.width = '';
    splitDetail.style.maxWidth = '';
  }
}
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

  // Re-build entTsNames and update entAllCounts in-place
  const entAllCountsNew = {};
  DATA.entities.forEach(r => { entAllCountsNew[r.entity] = Math.max(entAllCountsNew[r.entity] || 0, r.mention_count || 0); });
  
  // Clear old keys in entAllCounts and copy new ones
  for (const k in entAllCounts) { delete entAllCounts[k]; }
  Object.assign(entAllCounts, entAllCountsNew);
  
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

// Pre-warm Cloud Run services (read API and NLP seed-probe API) in the background to mitigate cold starts
(async function preWarmCloudRun() {
  console.log("Pre-warming Cloud Run services in the background...");
  try {
    fetch(drillApiUrl('ats_domains', { limit: 1 }));
    fetch(drillApiUrl('probe_health'));
  } catch (e) {
    console.warn("Pre-warming background requests failed (non-fatal):", e.message);
  }
})();


// Extend NON_SUBSTANTIVE_TOPICS with any topic a rater has flagged 'noise_meaningless'
// in the Topic Quality tab -- generalizes the old hardcoded 2-topic exclusion list into
// a reviewable, human-driven one. Fetched once at load (independent of whether the
// Topic Quality tab is ever opened) so pickers/plots elsewhere on the page respect it
// from the start; re-renders anything that already drew before this resolved.
(async function loadNoiseTopicExclusions() {
  try {
    const resp = await fetch(drillApiUrl('topic_claims', { rater: getRater() }));
    const data = await resp.json();
    const noiseNames = (data.claims || [])
      .filter(c => c.has_claim === 'noise_meaningless')
      .map(c => c.topic_name);
    if (noiseNames.length === 0) return;
    let changed = false;
    noiseNames.forEach(n => { if (!NON_SUBSTANTIVE_TOPICS.has(n)) { NON_SUBSTANTIVE_TOPICS.add(n); changed = true; } });
    if (changed) {
      tsRenderPicker(document.getElementById('tsSearch')?.value || '');
      tsBuildChart(); tsRenderLegend();
      renderAllTopicsTable();
      renderAuthorChart();
    }
  } catch (err) {
    // Non-fatal -- falls back to the static exclusion list if this fetch fails.
    console.warn('Could not load noise-topic exclusions:', err.message);
  }
})();
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

// ============================================================================
// ==================== TOPIC QUALITY EXPLORER INTEGRATION ====================
// ============================================================================

let residualsLimit = 20;
let residualsOffset = 0;
let claimsSearchQuery = '';
let claimsFilterState = 'all';
let cachedClaimsData = [];
let isLocalServerActive = false;

async function loadTopicQualityTab() {
  console.log("Initializing Topic Quality Tab...");
  await checkLocalServerStatus();
  loadNearDuplicates();
  loadTopicClaims();
  loadResidualComments();
}

function getRater() {
  return (document.getElementById('hitl_rater_name_input')?.value || 'nash').trim() || 'nash';
}

// --- Piece 1: Near-Duplicate Merges ---
async function loadNearDuplicates() {
  const container = document.getElementById('topicNearDuplicatesBody');
  if (!container) return;
  container.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:1rem; color:var(--ink-3);">Loading near-duplicate pairs...</td></tr>';
  
  try {
    const url = drillApiUrl('topic_near_duplicates', { rater: getRater() });
    const resp = await fetch(url);
    const data = await resp.json();
    
    if (!data.pairs || data.pairs.length === 0) {
      container.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:1rem; color:var(--ink-3);">No near-duplicate pairs found.</td></tr>';
      return;
    }
    
    container.innerHTML = '';
    data.pairs.forEach(p => {
      const tr = document.createElement('tr');
      
      const colA = `<td><strong>${p.topic_a}</strong>: ${shortTopic(p.topic_a_name)}</td>`;
      const colB = `<td><strong>${p.topic_b}</strong>: ${shortTopic(p.topic_b_name)}</td>`;
      const colSim = `<td style="text-align:right;">${p.centroid_cosine_sim.toFixed(3)}</td>`;
      const colOverlap = `<td style="text-align:right;">${(p.keyword_jaccard * 100).toFixed(1)}%</td>`;
      
      let actionHtml = '';
      if (p.decision === 'merge') {
        actionHtml = `<td style="text-align:center;"><span style="color:var(--pos); font-weight:600; font-size:12px; margin-right:8px;">Merged</span><button class="btn" style="padding:2px 8px; font-size:11px; cursor:pointer; border:1px solid var(--border); border-radius:4px; background:transparent; color:var(--ink);" onclick="unmergeTopicPair('${p.topic_a_name}', '${p.topic_b_name}')">Undo</button></td>`;
      } else if (p.decision === 'keep_separate') {
        actionHtml = `<td style="text-align:center;"><span style="color:var(--ink-3); font-size:12px; margin-right:8px;">Separated</span><button class="btn" style="padding:2px 8px; font-size:11px; cursor:pointer; border:1px solid var(--border); border-radius:4px; background:transparent; color:var(--ink);" onclick="unmergeTopicPair('${p.topic_a_name}', '${p.topic_b_name}')">Undo</button></td>`;
      } else {
        actionHtml = `
          <td style="text-align:center; display:flex; gap:6px; justify-content:center;">
            <button class="btn" style="padding:3px 8px; font-size:11px; background:var(--accent); color:white; border:none; border-radius:4px; cursor:pointer; font-weight:600;" onclick="rateTopicMerge('${p.topic_a_name}', '${p.topic_b_name}', 'merge')">Merge</button>
            <button class="btn" style="padding:3px 8px; font-size:11px; border:1px solid var(--border); border-radius:4px; cursor:pointer; background:transparent; color:var(--ink);" onclick="rateTopicMerge('${p.topic_a_name}', '${p.topic_b_name}', 'keep_separate')">Keep Separate</button>
          </td>
        `;
      }
      
      tr.innerHTML = colA + colB + colSim + colOverlap + actionHtml;
      container.appendChild(tr);
    });
  } catch (err) {
    container.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:1rem; color:var(--neg);">Error loading duplicates: ${err.message}</td></tr>`;
  }
}

async function rateTopicMerge(source, target, decision) {
  try {
    const resp = await fetch(drillApiUrl('rate_topic_merge'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_topic: source,
        target_topic: target,
        decision: decision,
        rater: getRater()
      })
    });
    if (resp.ok) {
      loadNearDuplicates();
    } else {
      alert("Failed to submit decision");
    }
  } catch (err) {
    alert("Error: " + err.message);
  }
}

async function unmergeTopicPair(source, target) {
  try {
    const resp = await fetch(drillApiUrl('unmerge_topic'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_topic: source,
        target_topic: target,
        rater: getRater()
      })
    });
    if (resp.ok) {
      loadNearDuplicates();
    } else {
      alert("Failed to undo decision");
    }
  } catch (err) {
    alert("Error: " + err.message);
  }
}

// --- Piece 2: Topic Claims & Classification Review ---
async function loadTopicClaims() {
  try {
    const resp = await fetch(drillApiUrl('topic_claims', { rater: getRater() }));
    const data = await resp.json();
    cachedClaimsData = data.claims || [];
    
    // Populate dropdown
    const select = document.getElementById('probeTopicSelect');
    if (select && select.children.length <= 1) {
      select.innerHTML = '<option value="">-- Select a topic --</option>';
      cachedClaimsData.forEach(item => {
        const opt = document.createElement('option');
        opt.value = item.topic_name;
        opt.textContent = `${item.topic_id}: ${shortTopic(item.topic_name)} (${item.n_comments} comments)`;
        select.appendChild(opt);
      });
    }
    
    renderTopicClaims();
  } catch (err) {
    document.getElementById('topicClaimsBody').innerHTML = `<tr><td colspan="3" style="text-align:center; padding:1rem; color:var(--neg);">Error loading claims: ${err.message}</td></tr>`;
  }
}

function renderTopicClaims() {
  const container = document.getElementById('topicClaimsBody');
  if (!container) return;
  
  const query = claimsSearchQuery.toLowerCase().trim();
  const filter = claimsFilterState;
  
  const filtered = cachedClaimsData.filter(item => {
    const matchesSearch = item.topic_name.toLowerCase().includes(query) || 
                          item.top_signature_claims.toLowerCase().includes(query);
    const matchesFilter = (filter === 'all') || (item.has_claim === filter);
    return matchesSearch && matchesFilter;
  });
  
  if (filtered.length === 0) {
    container.innerHTML = '<tr><td colspan="3" style="text-align:center; padding:1rem; color:var(--ink-3);">No matching topics found.</td></tr>';
    return;
  }
  
  container.innerHTML = '';
  filtered.forEach(item => {
    const tr = document.createElement('tr');
    
    const colTopic = `<td><strong>${item.topic_id}</strong>: ${shortTopic(item.topic_name)}<br><small style="color:var(--ink-2);">${item.n_comments} comments</small></td>`;
    
    const sigHtml = `
      <div style="font-size:12px; display:flex; flex-direction:column; gap:4px;">
        <span style="color:var(--ink);"><strong>Top Phrase:</strong> ${item.top_claim_1} <small style="color:var(--accent); font-weight:600;">(local ratio: ${item.top_claim_1_local_ratio.toFixed(1)}x)</small></span>
        <span style="color:var(--ink-2);">2. ${item.top_claim_2} <small style="color:var(--ink-3);">(ratio: ${item.top_claim_2_local_ratio.toFixed(1)}x)</small></span>
        <span style="color:var(--ink-2);">3. ${item.top_claim_3} <small style="color:var(--ink-3);">(ratio: ${item.top_claim_3_local_ratio.toFixed(1)}x)</small></span>
      </div>
    `;
    
    const activeClassStyle = "padding:3px 6px; font-size:10.5px; font-weight:600; border-radius:4px; cursor:pointer;";
    const normalClassStyle = "padding:3px 6px; font-size:10.5px; border-radius:4px; cursor:pointer; background:transparent; color:var(--ink-2); border:1px solid var(--border);";
    
    const isHasClaim = item.has_claim === 'has_claim';
    const isNoClaim = item.has_claim === 'no_coherent_claim';
    const isNoise = item.has_claim === 'noise_meaningless';
    const isUnreviewed = item.has_claim === 'unreviewed';

    const colActions = `
      <td style="text-align:center; vertical-align:middle;">
        <div style="display:inline-flex; gap:4px; border:1px solid var(--border); padding:3px; border-radius:6px; background:var(--bg-panel); flex-wrap:wrap;">
          <button style="${isHasClaim ? activeClassStyle + ' background:var(--pos); color:white; border:none;' : normalClassStyle}" onclick="rateTopicClaim(${item.topic_id}, 'has_claim')">Has Claim</button>
          <button style="${isNoClaim ? activeClassStyle + ' background:var(--ink-2); color:white; border:none;' : normalClassStyle}" onclick="rateTopicClaim(${item.topic_id}, 'no_coherent_claim')" title="Diffuse mix of real content, just no single crisp claim -- still substantive, still shown in plots/pickers">Diffuse discussion</button>
          <button style="${isNoise ? activeClassStyle + ' background:var(--neg); color:white; border:none;' : normalClassStyle}" onclick="rateTopicClaim(${item.topic_id}, 'noise_meaningless')" title="Junk/meta/reddit-noise, not real conspiracy content -- excluded from topic pickers, plots, and central-claim display everywhere on this page">Noise / Meaningless</button>
          <button style="${isUnreviewed ? activeClassStyle + ' background:var(--accent-bg); color:var(--accent); border:1px solid var(--accent);' : normalClassStyle}" onclick="rateTopicClaim(${item.topic_id}, 'unreviewed')">Unreviewed</button>
        </div>
      </td>
    `;
    
    tr.innerHTML = colTopic + `<td>${sigHtml}</td>` + colActions;
    container.appendChild(tr);
  });
}

async function rateTopicClaim(topicId, hasClaim) {
  try {
    const resp = await fetch(drillApiUrl('rate_topic_claim'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic_id: topicId,
        has_claim: hasClaim,
        rater: getRater()
      })
    });
    if (resp.ok) {
      const idx = cachedClaimsData.findIndex(item => item.topic_id === topicId);
      if (idx !== -1) {
        cachedClaimsData[idx].has_claim = hasClaim;
        renderTopicClaims();
      }
    } else {
      alert("Failed to rate topic claim");
    }
  } catch (err) {
    alert("Error: " + err.message);
  }
}

// Bind search and filter events
document.getElementById('claimsSearch')?.addEventListener('input', (e) => {
  claimsSearchQuery = e.target.value;
  renderTopicClaims();
});
document.getElementById('claimsFilterSelect')?.addEventListener('change', (e) => {
  claimsFilterState = e.target.value;
  renderTopicClaims();
});


// --- Piece 4: Noise-Topic Residual Reassignments ---
async function loadResidualComments() {
  const container = document.getElementById('topicResidualsBody');
  if (!container) return;
  container.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:1rem; color:var(--ink-3);">Loading residual comments queue...</td></tr>';
  
  try {
    const resp = await fetch(drillApiUrl('topic_residual_comments', { limit: residualsLimit, offset: residualsOffset }));
    const data = await resp.json();
    
    if (!data.rows || data.rows.length === 0) {
      container.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:1rem; color:var(--ink-3);">No residual comments in the queue.</td></tr>';
      return;
    }
    
    container.innerHTML = '';
    data.rows.forEach(r => {
      const tr = document.createElement('tr');
      
      // Make text click-expandable
      const shortText = r.text.length > 120 ? r.text.slice(0, 115) + '...' : r.text;
      const fullTextEscaped = r.text.replace(/"/g, '&quot;');
      const colText = `
        <td style="font-size:12px; line-height:1.4; max-width:300px; cursor:help;" title="Click to view full text" onclick="alert(this.dataset.full)" data-full="${fullTextEscaped}">
          ${shortText}
        </td>
      `;
      
      const colAssigned = `<td><span style="font-size:11px; background:var(--accent-bg); color:var(--accent); padding:2px 5px; border-radius:4px; font-weight:600;">${r.assigned_topic}</span><br><small style="color:var(--ink-3);">sim: ${r.assigned_sim.toFixed(3)}</small></td>`;
      const colBestOther = `<td><span style="font-size:11px; background:var(--pos-bg); color:var(--pos); padding:2px 5px; border-radius:4px; font-weight:600;">${r.best_other_topic}</span><br><small style="color:var(--ink-3);">sim: ${r.best_other_sim.toFixed(3)}</small></td>`;
      const colGap = `<td style="text-align:right; font-weight:bold; font-size:12px; color:${r.gap <= 0 ? 'var(--pos)' : 'var(--ink)'};">${r.gap.toFixed(3)}</td>`;
      
      const colAction = `
        <td style="text-align:center; vertical-align:middle;">
          <button class="btn" style="padding:4px 10px; font-size:11.5px; font-weight:600; background:var(--pos); color:white; border:none; border-radius:4px; cursor:pointer;" onclick="reassignResidualComment('${r.comment_id}', '${r.assigned_topic}', '${r.best_other_topic}')">
            Reassign
          </button>
        </td>
      `;
      
      tr.innerHTML = colText + colAssigned + colBestOther + colGap + colAction;
      container.appendChild(tr);
    });
    
    // Pagination labels
    const totalPages = Math.ceil(data.total / residualsLimit);
    const currPage = Math.floor(residualsOffset / residualsLimit) + 1;
    document.getElementById('residualsPageLabel').textContent = `Page ${currPage} of ${totalPages || 1} (Total: ${data.total})`;
    
    document.getElementById('residualsPrevBtn').disabled = (residualsOffset === 0);
    document.getElementById('residualsNextBtn').disabled = (residualsOffset + residualsLimit >= data.total);
  } catch (err) {
    container.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:1rem; color:var(--neg);">Error loading residual comments: ${err.message}</td></tr>`;
  }
}

async function reassignResidualComment(commentId, originalTopic, bestOtherTopic) {
  try {
    const resp = await fetch(drillApiUrl('assign_outlier_topic'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        comment_id: commentId,
        original_topic_name: originalTopic,
        assigned_topic_name: bestOtherTopic,
        rater: getRater()
      })
    });
    if (resp.ok) {
      loadResidualComments();
    } else {
      alert("Failed to reassign comment");
    }
  } catch (err) {
    alert("Error reassigning comment: " + err.message);
  }
}

document.getElementById('residualsPrevBtn')?.addEventListener('click', () => {
  if (residualsOffset >= residualsLimit) {
    residualsOffset -= residualsLimit;
    loadResidualComments();
  }
});
document.getElementById('residualsNextBtn')?.addEventListener('click', () => {
  residualsOffset += residualsLimit;
  loadResidualComments();
});


// --- Piece 3: Local Server Status & Seed Probing ---
async function checkLocalServerStatus() {
  const statusIndicator = document.getElementById('localServerStatus');
  const badge = document.getElementById('microMatchMethodBadge');
  try {
    const resp = await fetch(drillApiUrl('probe_health'), { method: 'GET' });
    const data = await resp.json();
    if (data.status === 'ok') {
      isLocalServerActive = true;
      if (statusIndicator) {
        statusIndicator.innerHTML = '<span style="color:var(--pos); font-weight:bold; font-size:12px;">● Cloud Embedding Server Active (ONNX neural matching)</span>';
      }
      if (badge) {
        badge.textContent = "SentenceTransformer vectors";
        badge.style.background = "var(--pos-bg)";
        badge.style.color = "var(--pos)";
      }
    } else {
      throw new Error();
    }
  } catch (err) {
    isLocalServerActive = false;
    if (statusIndicator) {
      statusIndicator.innerHTML = '<span style="color:var(--neg); font-size:12px;">○ Cloud Embedding Server Disconnected (lightweight TF-IDF baseline active)</span>';
    }
    if (badge) {
      badge.textContent = "TF-IDF keyword overlap";
      badge.style.background = "var(--accent-bg)";
      badge.style.color = "var(--accent)";
    }
  }
}

// Add/Remove probe seed inputs dynamically
document.getElementById('probeAddSeedBtn')?.addEventListener('click', () => {
  const container = document.getElementById('probeSeedsContainer');
  if (!container) return;
  
  const div = document.createElement('div');
  div.style.display = 'flex';
  div.style.gap = '8px';
  
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'probe-seed-input';
  input.placeholder = 'Type another candidate seed claim...';
  input.style.flex = '1';
  input.style.padding = '6px 9px';
  input.style.fontSize = '12.5px';
  input.style.borderRadius = '6px';
  input.style.border = '1px solid var(--border)';
  input.style.background = 'var(--bg)';
  input.style.color = 'var(--ink)';
  
  const removeBtn = document.createElement('button');
  removeBtn.className = 'btn';
  removeBtn.textContent = '×';
  removeBtn.style.padding = '2px 8px';
  removeBtn.style.fontSize = '14px';
  removeBtn.style.cursor = 'pointer';
  removeBtn.style.borderRadius = '6px';
  removeBtn.style.border = '1px solid var(--border)';
  removeBtn.style.background = 'transparent';
  removeBtn.style.color = 'var(--neg)';
  
  removeBtn.addEventListener('click', () => {
    div.remove();
  });
  
  div.appendChild(input);
  div.appendChild(removeBtn);
  container.appendChild(div);
});

// Run claim probe
document.getElementById('probeSubmitBtn')?.addEventListener('click', async () => {
  const topicSelect = document.getElementById('probeTopicSelect');
  const topicName = topicSelect.value;
  if (!topicName) {
    alert("Please select a topic to probe.");
    return;
  }
  
  const inputs = document.querySelectorAll('.probe-seed-input');
  const seeds = [];
  inputs.forEach(inp => {
    const val = inp.value.trim();
    if (val) seeds.push(val);
  });
  
  if (seeds.length === 0) {
    alert("Please enter at least one seed claim phrase.");
    return;
  }
  
  const resultsArea = document.getElementById('probeResultsArea');
  const macroDiv = document.getElementById('probeMacroResults');
  const microDiv = document.getElementById('probeMicroResults');
  
  resultsArea.style.display = 'block';
  macroDiv.innerHTML = '<div style="color:var(--ink-3); font-size:12px;">Computing macro alignments...</div>';
  microDiv.innerHTML = '<div style="color:var(--ink-3); font-size:12px;">Computing micro clusters...</div>';
  
  try {
    if (isLocalServerActive) {
      // Stage 2: Heavyweight Neural embeddings comparison via Cloud Embedding Server
      console.log("Routing seed probe to Cloud Embedding Server...");
      const resp = await fetch(drillApiUrl('probe_local'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic_id: topicName,
          seeds: seeds
        })
      });
      if (!resp.ok) {
        throw new Error("Cloud Embedding Server probe failed.");
      }
      const data = await resp.json();
      
      // Render local neural macro alignments
      macroDiv.innerHTML = '';
      data.macro_alignment.forEach(m => {
        const percent = Math.max(0, Math.min(100, Math.round(m.cosine_sim * 100)));
        macroDiv.innerHTML += `
          <div style="font-size:12px; display:flex; flex-direction:column; gap:4px; border:1px solid var(--border); padding:8px; border-radius:6px; background:var(--bg-panel);">
            <div style="display:flex; justify-content:space-between; font-weight:600;">
              <span style="color:var(--ink); max-width:75%; word-wrap:break-word;">&ldquo;${m.seed}&rdquo;</span>
              <span style="color:var(--pos);">${m.cosine_sim.toFixed(4)} similarity</span>
            </div>
            <div style="background:var(--border); height:6px; border-radius:3px; overflow:hidden;">
              <div style="background:var(--pos); width:${percent}%; height:100%;"></div>
            </div>
          </div>
        `;
      });
      
      // Render local neural micro clusters
      microDiv.innerHTML = '';
      data.micro_clusters.forEach((cluster, cIdx) => {
        const div = document.createElement('div');
        div.style.border = '1px solid var(--border)';
        div.style.borderRadius = '6px';
        div.style.padding = '8px';
        div.style.background = 'var(--bg-panel)';
        div.style.display = 'flex';
        div.style.flexDirection = 'column';
        div.style.gap = '6px';
        
        div.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border); padding-bottom:6px; margin-bottom:4px;">
            <strong style="font-size:12px; color:var(--ink); max-width:65%; word-wrap:break-word;">Seed: &ldquo;${cluster.seed}&rdquo;</strong>
            <span style="font-size:11px; background:var(--pos-bg); color:var(--pos); padding:2px 6px; border-radius:4px; font-weight:600;">
              ${cluster.size} comments (mean sim: ${cluster.mean_sim.toFixed(3)})
            </span>
          </div>
        `;
        
        const commContainer = document.createElement('div');
        commContainer.style.display = 'flex';
        commContainer.style.flexDirection = 'column';
        commContainer.style.gap = '6px';
        commContainer.style.maxHeight = '150px';
        commContainer.style.overflowY = 'auto';
        commContainer.style.paddingRight = '4px';
        
        if (cluster.comments.length === 0) {
          commContainer.innerHTML = '<div style="color:var(--ink-3); font-size:11px; text-align:center; padding:4px;">No comments assigned.</div>';
        } else {
          cluster.comments.forEach(c => {
            commContainer.innerHTML += `
              <div style="font-size:11px; line-height:1.4; border-bottom:1px dashed var(--border); padding-bottom:4px; margin-bottom:2px;">
                <div style="display:flex; justify-content:space-between; margin-bottom:2px; font-weight:600; color:var(--ink-2);">
                  <span>Comment ${c.comment_id} (${c.upvotes} upvotes)</span>
                  <span style="color:var(--pos);">sim: ${c.similarity.toFixed(4)}</span>
                </div>
                <div style="color:var(--ink); font-style:italic;">&ldquo;${c.text.slice(0, 150)}${c.text.length > 150 ? '...' : ''}&rdquo;</div>
              </div>
            `;
          });
        }
        
        div.appendChild(commContainer);
        microDiv.appendChild(div);
      });
      
    } else {
      // Stage 1: Lightweight TF-IDF overlap comparison via VM (standard fallback)
      console.log("Routing seed probe to Live VM (TF-IDF overlap)...");
      const url = drillApiUrl('probe_seed_claims_stage1', {
        topic: topicName,
        seeds: JSON.stringify(seeds)
      });
      const resp = await fetch(url);
      const data = await resp.json();
      
      // Render Stage 1 macro info
      macroDiv.innerHTML = `
        <div style="font-size:12px; border:1px solid var(--border); padding:8px; border-radius:6px; background:var(--bg-panel); color:var(--ink-2); line-height:1.4;">
          <strong>Stage 1 (TF-IDF keyword overlap mode):</strong> Showing up to 100 sample comments matching keywords from the seed phrases: <br>
          <ul style="margin:5px 0 0 15px; padding:0;">
            ${seeds.map(s => `<li>&ldquo;${s}&rdquo;</li>`).join('')}
          </ul>
        </div>
      `;
      
      // Render Stage 1 matching comments
      microDiv.innerHTML = '';
      if (!data.results || data.results.length === 0) {
        microDiv.innerHTML = '<div style="color:var(--ink-3); font-size:11px; text-align:center; padding:10px;">No overlap comments found matching any seed keywords.</div>';
        return;
      }
      
      const div = document.createElement('div');
      div.style.border = '1px solid var(--border)';
      div.style.borderRadius = '6px';
      div.style.padding = '8px';
      div.style.background = 'var(--bg-panel)';
      div.style.display = 'flex';
      div.style.flexDirection = 'column';
      div.style.gap = '6px';
      
      div.innerHTML = `
        <div style="border-bottom:1px solid var(--border); padding-bottom:6px; margin-bottom:4px; font-weight:600; font-size:12px; color:var(--ink);">
          Top Comments Matching Keyword Seeds (sorted by overlap score)
        </div>
      `;
      
      const commContainer = document.createElement('div');
      commContainer.style.display = 'flex';
      commContainer.style.flexDirection = 'column';
      commContainer.style.gap = '6px';
      commContainer.style.maxHeight = '250px';
      commContainer.style.overflowY = 'auto';
      
      data.results.forEach(c => {
        commContainer.innerHTML += `
          <div style="font-size:11px; line-height:1.4; border-bottom:1px dashed var(--border); padding-bottom:4px; margin-bottom:2px;">
            <div style="display:flex; justify-content:space-between; margin-bottom:2px; font-weight:600; color:var(--ink-2);">
              <span>Comment ${c.comment_id} (${c.upvotes} upvotes)</span>
              <span style="color:var(--accent);">score: ${c.overlap_score} words</span>
            </div>
            <div style="color:var(--ink); margin-bottom:2px; font-style:italic;">&ldquo;${c.text.slice(0, 150)}${c.text.length > 150 ? '...' : ''}&rdquo;</div>
            <div style="color:var(--accent); font-size:10px;">Matched keywords in: &ldquo;${c.matched_seed}&rdquo; &rarr; [${c.overlap_words.join(', ')}]</div>
          </div>
        `;
      });
      
      div.appendChild(commContainer);
      microDiv.appendChild(div);
    }
  } catch (err) {
    macroDiv.innerHTML = `<div style="color:var(--neg); font-size:12px;">Error: ${err.message}</div>`;
    microDiv.innerHTML = `<div style="color:var(--neg); font-size:12px;">Error: ${err.message}</div>`;
  }
});

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