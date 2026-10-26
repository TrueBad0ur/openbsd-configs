const API = '__API_PATH__';
const PAGE = 100;
let _data = null;
let _feed = { items: [], total: 0, loading: false };
let _threads = { items: [], total: 0, loading: false };
let _scrollY = 0;
let _activeTab = 'feed';
let _activeFilters = new Set();
let _filterOpen = false;
let _returnTab = 'feed';
let _showBack = false;

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function toMSK(dateStr) {
  if (!dateStr) return dateStr;
  const d = new Date(dateStr.replace(' ', 'T') + 'Z');
  const msk = new Date(d.getTime() + 3 * 3600 * 1000);
  return msk.toISOString().replace('T', ' ').slice(0, 16) + ' MSK';
}

// --- URL state ---

function pushState(params) {
  const url = params ? '/mails?' + new URLSearchParams(params).toString() : '/mails';
  history.pushState(params || null, '', url);
}

function readURLParams() {
  const p = new URLSearchParams(location.search);
  if (p.has('thread')) return { thread: p.get('thread') };
  if (p.has('msg'))    return { msg: p.get('msg') };
  return null;
}

window.addEventListener('popstate', (e) => {
  const state = e.state;
  if (!state) {
    showList(false);
  } else if (state.thread) {
    openThread(state.thread, false);
  } else if (state.msg) {
    openMessage(state.msg, false);
  }
});

// --- Tab / filter ---

function switchTab(tab) {
  _activeTab = tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  document.querySelectorAll('.section').forEach(s => s.classList.toggle('active', s.id === 'sec-'+tab));
  renderFilters();
  loadMore(tab);
}

function toggleFilter(list) {
  if (list === 'all') {
    _activeFilters.clear();
  } else {
    if (_activeFilters.has(list)) _activeFilters.delete(list);
    else _activeFilters.add(list);
  }
  renderFilters();
  _feed = { items: [], total: 0, loading: false };
  _threads = { items: [], total: 0, loading: false };
  renderCurrentTab();
}

function toggleFilterDropdown(e) {
  e.stopPropagation();
  _filterOpen = !_filterOpen;
  renderFilters();
}

function renderFilters() {
  const el = document.getElementById('filters');
  if (!_data) { el.innerHTML = ''; return; }
  let left = '';
  if (!_showBack) {
    const isAll = _activeFilters.size === 0;
    const label = isAll ? 'All lists'
      : _activeFilters.size === 1 ? [..._activeFilters][0].replace('openbsd-', '')
      : _activeFilters.size + ' lists';
    const options = ['all', ..._data.lists].map(l => {
      const checked = l === 'all' ? isAll : _activeFilters.has(l);
      const display = l === 'all' ? 'All' : esc(l.replace('openbsd-', ''));
      return '<div class="filter-option' + (checked ? ' checked' : '') + '" onclick="toggleFilter(\'' + l + '\'); event.stopPropagation()">'
        + '<span class="filter-check">' + (checked ? '&#10003;' : '') + '</span>'
        + display + '</div>';
    }).join('');
    left = '<div class="filter-select">'
      + '<button class="filter-trigger" onclick="toggleFilterDropdown(event)">'
      + esc(label) + '<span class="filter-arrow">' + (_filterOpen ? '&#9652;' : '&#9662;') + '</span></button>'
      + '<div class="filter-dropdown' + (_filterOpen ? ' open' : '') + '">'
      + options + '</div></div>';
  }
  const right = _showBack
    ? '<button class="back-btn" onclick="showList()">&larr; Back</button>'
    : '';
  el.innerHTML = '<div class="nav-row">' + left + right + '</div>';
}

function renderCurrentTab() {
  renderFilters();
  document.getElementById('sec-feed').innerHTML = '';
  document.getElementById('sec-threads').innerHTML = '';
  loadMore(_activeTab);
}

// --- Paged data ---

function listsParam() {
  return _activeFilters.size ? '&lists=' + encodeURIComponent([..._activeFilters].join(',')) : '';
}

async function loadMore(kind) {
  if (kind !== 'feed' && kind !== 'threads') return;
  const st = kind === 'feed' ? _feed : _threads;
  if (st.loading || (st.items.length && st.items.length >= st.total)) return;
  st.loading = true;
  const sec = document.getElementById('sec-' + kind);
  const btn = sec.querySelector('.load-more');
  if (btn) btn.textContent = 'loading...';
  try {
    const r = await fetch(API + '/' + kind + '?offset=' + st.items.length + '&limit=' + PAGE + listsParam());
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const j = await r.json();
    const first = st.items.length === 0;
    st.total = j.total;
    st.items = st.items.concat(j.items);
    renderPage(kind, j.items, first);
  } catch(e) {
    sec.insertAdjacentHTML('beforeend', '<p class="spinner">error: ' + esc(e.message) + '</p>');
  } finally {
    st.loading = false;
  }
}

function renderPage(kind, items, first) {
  const st = kind === 'feed' ? _feed : _threads;
  const sec = document.getElementById('sec-' + kind);
  const rows = items.map(kind === 'feed' ? feedRow : threadRow).join('');
  if (first) {
    sec.innerHTML = '<p class="subtitle">' + st.total + (kind === 'feed' ? ' messages' : ' threads')
      + '</p><div class="card">' + rows + '</div>';
  } else {
    sec.querySelector('.card').insertAdjacentHTML('beforeend', rows);
  }
  const old = sec.querySelector('.load-more');
  if (old) old.remove();
  if (st.items.length < st.total) {
    sec.insertAdjacentHTML('beforeend', '<button class="load-more" onclick="loadMore(\'' + kind + '\')">Load more ('
      + (st.total - st.items.length) + ' left)</button>');
  }
}

// --- Body rendering ---

function cleanBody(text) {
  if (!text) return '';
  let t = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  t = t.replace(/\n{3,}/g, '\n\n').replace(/^\n+/, '');
  return t;
}

function _renderBody(text) {
  const hasDiff = /^(@@|diff |Index:|\+\+\+|---)/m.test(text);
  const result = [];
  let inHunk = false;
  for (const line of text.split('\n')) {
    if (line.startsWith('>')) {
      result.push('<span class="quote">' + esc(line) + '</span>\n');
    } else if (line.startsWith('@@')) {
      inHunk = true;
      result.push('<span class="diff-hunk">' + esc(line) + '</span>\n');
    } else if (/^(diff |Index:|===)/.test(line)) {
      inHunk = false;
      result.push('<span class="diff-header">' + esc(line) + '</span>\n');
    } else if (!inHunk && /^\s*(---|\+\+\+|index )/.test(line)) {
      result.push('<span class="diff-file">' + esc(line) + '</span>\n');
    } else if (inHunk && line.startsWith('+')) {
      result.push('<span class="diff-add">' + esc(line) + '</span>\n');
    } else if (inHunk && line.startsWith('-')) {
      result.push('<span class="diff-del">' + esc(line) + '</span>\n');
    } else {
      result.push(esc(line) + '\n');
    }
  }
  return '<pre class="msg-body' + (hasDiff ? ' diff' : '') + '">' + result.join('') + '</pre>';
}

function highlightBody(text) {
  if (!text) return '';
  const toggleId = 'body-' + Math.random().toString(36).slice(2, 8);
  const btns = '<div class="body-toggle">'
    + '<button class="toggle-btn active" onclick="toggleRaw(this,\'' + toggleId + '\',false)">Clean</button>'
    + '<button class="toggle-btn" onclick="toggleRaw(this,\'' + toggleId + '\',true)">Raw</button>'
    + '</div>';
  return btns + '<div id="' + toggleId + '" data-raw="' + esc(text).replace(/"/g, '&quot;') + '">'
    + _renderBody(cleanBody(text)) + '</div>';
}

function toggleRaw(btn, id, showRaw) {
  const container = document.getElementById(id);
  const text = container.dataset.raw;
  container.innerHTML = _renderBody(showRaw ? text : cleanBody(text));
  btn.parentElement.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

// --- Navigation ---

async function openThread(threadId, push = true) {
  if (push) { _scrollY = window.scrollY; _returnTab = _activeTab; pushState({ thread: String(threadId) }); }
  _showBack = true; renderFilters();
  const el = document.getElementById('content');
  el.innerHTML = '<p class="spinner">loading thread...</p>';
  try {
    const r = await fetch('/mails/thread/' + threadId);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const thread = await r.json();
    if (thread.error) throw new Error(thread.error);
    const msgs = thread.messages;
    const subject = thread.subject || (msgs.length ? msgs[0].subject : '');
    let html = '<div class="thread-view">'
      + '<h2 class="thread-subject">' + esc(subject) + '</h2>'
      + '<p class="subtitle">' + msgs.length + ' messages</p>';
    msgs.forEach((msg) => {
      html += '<div class="conv-msg">'
        + '<div class="conv-header">'
        + '<div class="conv-avatar">' + esc((msg.author || '?')[0].toUpperCase()) + '</div>'
        + '<div class="conv-meta">'
        + '<div class="conv-author">' + esc(msg.author) + '</div>'
        + '<div class="conv-date">' + esc(toMSK(msg.date)) + '</div>'
        + '</div>'
        + '<span class="badge">' + esc(msg.list.replace('openbsd-','')) + '</span>'
        + '<button class="msg-link-btn" onclick="openMessage('+msg.id+'); event.stopPropagation();" title="Permalink">&#9900;</button>'
        + '</div>'
        + '<div class="conv-body">' + highlightBody(msg.body) + '</div>'
        + '</div>';
    });
    html += '</div>';
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = '<p class="spinner">error: ' + e.message + '</p>';
  }
}

async function openMessage(msgId, push = true) {
  if (push) { _scrollY = window.scrollY; }
  if (push) pushState({ msg: String(msgId) });
  _showBack = true; renderFilters();
  const el = document.getElementById('content');
  el.innerHTML = '<p class="spinner">loading message...</p>';
  try {
    const r = await fetch('/mails/msg/' + msgId);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const msg = await r.json();
    if (msg.error) throw new Error(msg.error);
    el.innerHTML = '<div class="msg-detail">'
      + '<div class="msg-detail-meta">'
      + '<div class="msg-meta-row"><span class="msg-meta-label">From</span><span class="msg-meta-val">' + esc(msg.author) + '</span></div>'
      + '<div class="msg-meta-row"><span class="msg-meta-label">Date</span><span class="msg-meta-val">' + esc(toMSK(msg.date)) + '</span></div>'
      + '<div class="msg-meta-row"><span class="msg-meta-label">Subject</span><span class="msg-meta-val">' + esc(msg.subject) + '</span></div>'
      + '</div>'
      + highlightBody(msg.body)
      + '</div>';
  } catch(e) {
    el.innerHTML = '<p class="spinner">error: ' + e.message + '</p>';
  }
}

function showList(push = true) {
  if (push) pushState(null);
  _showBack = false;
  if (_data) { render(_data); switchTab(_returnTab); window.scrollTo(0, _scrollY); }
}

// --- List views ---

function feedRow(m) {
  return '<div class="msg-row" onclick="openMessage('+m.id+')">'
    + '<span class="msg-date">'+esc(toMSK(m.date))+'</span>'
    + '<span class="msg-subj">'+esc(m.subject)+'</span>'
    + '<span class="msg-author">'+esc(m.author)+'</span></div>';
}

function threadRow(t) {
  const authors = (t.authors || []).join(', ');
  const badges = (t.lists || []).map(l =>
    '<span class="badge">'+esc(l.replace('openbsd-',''))+'</span>').join(' ');
  return '<div class="thread-row" onclick="openThread('+t.thread_id+')">'
    + '<div class="thread-subj">'+esc(t.subject)+'</div>'
    + '<div class="thread-meta"><span>'+esc(toMSK(t.last_date))+'</span><span>'+t.count+' msg</span><span>'+esc(authors)+'</span>'+badges+'</div></div>';
}

function renderStats() {
  if (!_data || !_data.stats) return;
  const s = _data.stats;
  const mx = s.top_authors.length ? s.top_authors[0].count : 1;
  const cards = [
    '<div class="stat-card"><div class="stat-val">'+s.total+'</div><div class="stat-label">messages</div></div>',
    '<div class="stat-card"><div class="stat-val">'+_data.total_threads+'</div><div class="stat-label">threads</div></div>',
    '<div class="stat-card"><div class="stat-val">'+s.top_authors.length+'</div><div class="stat-label">authors</div></div>',
    '<div class="stat-card"><div class="stat-val">'+(_data.lists||[]).length+'</div><div class="stat-label">lists</div></div>',
  ].join('');
  const authors = s.top_authors.map(a =>
    '<div class="author-row"><span class="author-name">'+esc(a.name)+'</span><span class="author-count">'+a.count+'</span></div>'
    + '<div class="bar"><div class="bar-fill" style="width:'+(a.count/mx*100)+'%"></div></div>').join('');
  const lists = (s.list_breakdown||[]).map(l =>
    '<div class="author-row"><span class="author-name">'+esc(l.list)+'</span><span class="author-count">'+l.count+'</span></div>').join('');
  document.getElementById('sec-stats').innerHTML =
    '<div style="margin-bottom:24px">'+cards+'</div>'
    + '<div style="margin-bottom:24px"><h2>Top Authors</h2><div class="card"><div class="card-inner">'+authors+'</div></div></div>'
    + '<div><h2>By List</h2><div class="card"><div class="card-inner">'+lists+'</div></div></div>';
}

function render(d) {
  _data = d;
  document.getElementById('content').innerHTML =
    '<div class="tabs">'
    + '<div class="tab active" data-tab="feed" onclick="switchTab(\'feed\')">Feed</div>'
    + '<div class="tab" data-tab="threads" onclick="switchTab(\'threads\')">Threads</div>'
    + '<div class="tab" data-tab="stats" onclick="switchTab(\'stats\')">Stats</div></div>'
    + '<div id="sec-feed" class="section active"></div>'
    + '<div id="sec-threads" class="section"></div>'
    + '<div id="sec-stats" class="section"></div>';
  renderFilters(); renderStats();
  if (_feed.items.length) renderPage('feed', _feed.items, true); else loadMore('feed');
  if (_threads.items.length) renderPage('threads', _threads.items, true);
}

// --- Bootstrap ---

async function fetchData() {
  try {
    const r = await fetch(API);
    if (r.status === 503) {
      document.getElementById('content').innerHTML = '<p class="spinner">fetching...</p>';
      setTimeout(fetchData, 3000);
      return;
    }
    const j = await r.json();
    _data = j.data;

    // Handle direct URL load (shareable link)
    const params = readURLParams();
    if (params && params.thread) {
      openThread(params.thread, false);
    } else if (params && params.msg) {
      openMessage(params.msg, false);
    } else {
      render(_data);
    }
  } catch(e) {
    document.getElementById('content').innerHTML = '<p class="spinner">error: ' + e.message + '</p>';
  }
}

fetchData();

document.addEventListener('click', () => {
  if (_filterOpen) { _filterOpen = false; renderFilters(); }
});
