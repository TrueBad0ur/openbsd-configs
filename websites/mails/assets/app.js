const API = '__API_PATH__';
let _data = null;
let _activeTab = 'feed';
let _activeFilters = new Set();
let _filterOpen = false;
let _returnTab = 'feed';
let _showBack = false;

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function startTimer(lastUpdated, nextUpdate) {
  if (window._timer) clearInterval(window._timer);
  const updStr = new Date(lastUpdated*1000).toISOString().replace('T',' ').slice(0,16)+' UTC';
  window._timer = setInterval(() => {
    const secs = Math.max(0, Math.round((nextUpdate*1000 - Date.now())/1000));
    const m = Math.floor(secs/60), s = secs%60;
    const el = document.getElementById('ts');
    if (el) el.textContent = 'Updated '+updStr+'  ·  refresh in '+(secs>0 ? m+':'+String(s).padStart(2,'0') : 'updating...');
  }, 1000);
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
}

function toggleFilter(list) {
  if (list === 'all') {
    _activeFilters.clear();
  } else {
    if (_activeFilters.has(list)) _activeFilters.delete(list);
    else _activeFilters.add(list);
  }
  renderFilters();
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
  if (_activeTab === 'feed') renderFeed();
  else if (_activeTab === 'threads') renderThreads();
  else if (_activeTab === 'stats') renderStats();
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
  if (push) { _returnTab = _activeTab; pushState({ thread: String(threadId) }); }
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
        + '<div class="conv-date">' + esc(msg.date) + '</div>'
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
      + '<div class="msg-meta-row"><span class="msg-meta-label">Date</span><span class="msg-meta-val">' + esc(msg.date) + '</span></div>'
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
  if (_data) { render(_data); switchTab(_returnTab); }
}

// --- List views ---

function renderFeed() {
  if (!_data) return;
  let msgs = _data.messages;
  if (_activeFilters.size > 0) msgs = msgs.filter(m => _activeFilters.has(m.list));
  const rows = msgs.map(m => {
    return '<div class="msg-row" onclick="openMessage('+m.id+')">'
      + '<span class="msg-date">'+esc(m.date)+'</span>'
      + '<span class="msg-subj">'+esc(m.subject)+'</span>'
      + '<span class="msg-author">'+esc(m.author)+'</span></div>';
  }).join('');
  document.getElementById('sec-feed').innerHTML =
    '<p class="subtitle">'+msgs.length+' messages</p><div class="card">'+rows+'</div>';
}

function renderThreads() {
  if (!_data) return;
  let threads = _data.threads;
  if (_activeFilters.size > 0) threads = threads.filter(t => t.lists && t.lists.some(l => _activeFilters.has(l)));
  const rows = threads.map(t => {
    const authors = (t.authors || []).join(', ');
    const badges = (t.lists || []).map(l =>
      '<span class="badge">'+esc(l.replace('openbsd-',''))+'</span>').join(' ');
    return '<div class="thread-row" onclick="openThread('+t.thread_id+')">'
      + '<div class="thread-subj">'+esc(t.subject)+'</div>'
      + '<div class="thread-meta"><span>'+t.count+' messages</span><span>'+esc(authors)+'</span>'+badges+'</div></div>';
  }).join('');
  document.getElementById('sec-threads').innerHTML =
    '<p class="subtitle">'+threads.length+' threads</p><div class="card">'+rows+'</div>';
}

function renderStats() {
  if (!_data || !_data.stats) return;
  const s = _data.stats;
  const mx = s.top_authors.length ? s.top_authors[0].count : 1;
  const cards = [
    '<div class="stat-card"><div class="stat-val">'+s.total+'</div><div class="stat-label">messages</div></div>',
    '<div class="stat-card"><div class="stat-val">'+(_data.threads||[]).length+'</div><div class="stat-label">threads</div></div>',
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
  renderFilters(); renderFeed(); renderThreads(); renderStats();
}

// --- Bootstrap ---

let _nextFetch = null;
async function fetchData() {
  if (_nextFetch) clearTimeout(_nextFetch);
  try {
    const r = await fetch(API);
    if (r.status === 503) {
      document.getElementById('content').innerHTML = '<p class="spinner">fetching...</p>';
      _nextFetch = setTimeout(fetchData, 3000);
      return;
    }
    const j = await r.json();
    _data = j.data;
    startTimer(j.last_updated, j.next_update);

    // Handle direct URL load (shareable link)
    const params = readURLParams();
    if (params && params.thread) {
      openThread(params.thread, false);
    } else if (params && params.msg) {
      openMessage(params.msg, false);
    } else {
      render(_data);
    }

    _nextFetch = setTimeout(fetchData, Math.max(5000, j.next_update * 1000 - Date.now() + 3000));
  } catch(e) {
    document.getElementById('content').innerHTML = '<p class="spinner">error: ' + e.message + '</p>';
    _nextFetch = setTimeout(fetchData, 10000);
  }
}

fetchData();

document.addEventListener('click', () => {
  if (_filterOpen) { _filterOpen = false; renderFilters(); }
});
