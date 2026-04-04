// ── State ─────────────────────────────────────────────────────────────────────

const EXPANDABLE = new Set(['GitHub', 'Reddit']);
const PLATFORM_KEY = { 'GitHub': 'github', 'Reddit': 'reddit' };

let capEnabled = true;
let eventSource = null;
let drawerCounter = 0;
const paginationState = new Map();

// Map seed (lowercased) → tree-node element, used to find the right node
// when events reference a seed by value.
const hopElements = new Map();
let currentHopEl = null;

// Per-hop counters stored directly on the element
// el._found, el._notFound, el._total

// ── DOM refs ──────────────────────────────────────────────────────────────────

const form     = document.getElementById('search-form');
const input    = document.getElementById('query-input');
const statusEl = document.getElementById('status');
const resultsEl = document.getElementById('results');
const capBtn   = document.getElementById('cap-btn');

// ── Cap toggle ────────────────────────────────────────────────────────────────

capBtn.addEventListener('click', () => {
  capEnabled = !capEnabled;
  capBtn.classList.toggle('active', capEnabled);
});

// ── Search ────────────────────────────────────────────────────────────────────

form.addEventListener('submit', (e) => {
  e.preventDefault();
  const query = input.value.trim();
  if (query) startSearch(query);
});

function startSearch(query) {
  if (eventSource) { eventSource.close(); eventSource = null; }

  paginationState.clear();
  hopElements.clear();
  drawerCounter = 0;
  currentHopEl = null;

  resultsEl.innerHTML = '';
  resultsEl.classList.remove('hidden');
  setStatus('Starting…');

  const url = `/api/search/stream?q=${encodeURIComponent(query)}&cap=${capEnabled}`;
  eventSource = new EventSource(url);

  const on = (type, fn) =>
    eventSource.addEventListener(type, (e) => fn(JSON.parse(e.data)));

  on('start',              onStart);
  on('hop_start',          onHopStart);
  on('gravatar',           onGravatar);
  on('account_result',     onAccountResult);
  on('identity_discovered', onIdentityDiscovered);
  on('hop_complete',       onHopComplete);
  on('cap_reached',        onCapReached);
  on('done',               onDone);

  eventSource.onerror = () => {
    if (eventSource && eventSource.readyState !== EventSource.CLOSED) {
      setStatus('Connection error — search may be incomplete.');
      eventSource.close();
      eventSource = null;
    }
  };
}

// ── SSE event handlers ────────────────────────────────────────────────────────

function onStart() {
  setStatus('Searching…');
  resultsEl.innerHTML = `
    <div class="section" id="unique-identities-section">
      <div class="section-header unique-id-header" onclick="toggleUniqueIds()">
        <span class="tree-collapse-icon" id="unique-id-icon">▼</span>
        Unique Identities
        <span id="unique-id-count" class="unique-id-count">0</span>
      </div>
      <div id="unique-id-list" class="unique-id-list">
        <span class="unique-id-empty">None discovered yet…</span>
      </div>
    </div>
    <div class="discovery-tree"></div>`;
}

function onHopStart(data) {
  const tree = resultsEl.querySelector('.discovery-tree');
  const indent = Math.min(data.hop, 5) * 20;

  const provenance = data.parent_seed
    ? `hop ${data.hop} · discovered via ${esc(data.parent_platform)} from ${esc(data.parent_seed)}`
    : 'initial seed';

  const el = document.createElement('div');
  el.className = 'tree-node';
  el.dataset.hop = data.hop;
  el.dataset.seed = data.seed;
  el.style.marginLeft = `${indent}px`;
  el._found = 0;
  el._notFound = 0;
  el._total = 0;

  el.innerHTML = `
    <div class="tree-node-header" onclick="toggleNode(this)">
      <span class="tree-collapse-icon">▼</span>
      <span class="tree-seed">${esc(data.seed)}</span>
      <span class="tree-type-badge">${esc(data.seed_type)}</span>
      <span class="tree-provenance">${provenance}</span>
      <span class="tree-status">searching…</span>
    </div>
    <div class="tree-node-body"></div>`;

  tree.appendChild(el);
  hopElements.set(data.seed.toLowerCase(), el);
  currentHopEl = el;
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function onGravatar(data) {
  const el = hopElements.get(data.seed.toLowerCase()) || currentHopEl;
  if (!el) return;
  const body = el.querySelector('.tree-node-body');
  const g = data.data;

  body.insertAdjacentHTML('beforeend', `
    <div class="gravatar-row">
      ${g.avatar_url
        ? `<img class="gravatar-avatar" src="${esc(g.avatar_url)}?s=80" alt="avatar" />`
        : ''}
      <div class="gravatar-info">
        ${g.display_name ? `<div class="gravatar-name">Gravatar: ${esc(g.display_name)}</div>` : ''}
        <div class="gravatar-meta">
          ${g.location ? `<div>📍 ${esc(g.location)}</div>` : ''}
          ${g.about    ? `<div>${esc(g.about)}</div>` : ''}
          ${g.profile_url
            ? `<div><a href="${esc(g.profile_url)}" target="_blank" rel="noopener">${esc(g.profile_url)}</a></div>`
            : ''}
        </div>
      </div>
    </div>`);
}

function onAccountResult(data) {
  const el = hopElements.get(data.seed.toLowerCase()) || currentHopEl;
  if (!el) return;

  el._total++;
  if (data.status === 'not_found') { el._notFound++; return; }
  if (data.status === 'found') { el._found++; el.classList.add('has-found'); }

  const body = el.querySelector('.tree-node-body');
  const canExpand = data.status === 'found' && EXPANDABLE.has(data.platform);
  const rowId = drawerCounter++;
  const drawerId = `drawer-${rowId}`;
  const wbId = `wb-${rowId}`;
  const showUsername = data.username.toLowerCase() !== data.seed.toLowerCase();

  body.insertAdjacentHTML('beforeend', `
    <div class="account-row"
        data-platform="${esc(data.platform)}"
        data-username="${esc(data.username)}">
      <div class="status-dot ${data.status}"></div>
      <div class="platform-name">${esc(data.platform)}</div>
      ${data.status === 'found'
        ? `<a class="account-url" href="${esc(data.url)}" target="_blank" rel="noopener">${esc(data.url)}</a>`
        : `<span class="account-url" style="color:var(--red)">${esc(data.url)}</span>`}
      ${showUsername ? `<span class="account-username">@${esc(data.username)}</span>` : ''}
      ${canExpand ? `<button class="expand-btn" data-drawer="${drawerId}">&#9660; Activity</button>` : ''}
      <button class="archive-btn" data-wb="${wbId}" data-url="${esc(data.url)}">&#128337; Archive</button>
    </div>
    ${canExpand ? `<div class="content-drawer" id="${drawerId}"></div>` : ''}
    <div class="wayback-drawer" id="${wbId}"></div>`);

  if (canExpand) {
    const btn = body.querySelector(`[data-drawer="${drawerId}"]`);
    btn.addEventListener('click', () => handleExpand(btn));
  }
  const archiveBtn = body.querySelector(`[data-wb="${wbId}"]`);
  archiveBtn.addEventListener('click', () => handleWayback(archiveBtn));
}

function onIdentityDiscovered(data) {
  // Update the Unique Identities panel
  const list = document.getElementById('unique-id-list');
  const countEl = document.getElementById('unique-id-count');
  if (list) {
    const empty = list.querySelector('.unique-id-empty');
    if (empty) empty.remove();

    const hint = data.hint_platform ? ` · ${esc(data.hint_platform)}` : '';
    list.insertAdjacentHTML('beforeend', `
      <div class="unique-id-item">
        <span class="identity-type-badge">${esc(data.value_type)}</span>
        <span class="unique-id-value">${esc(data.value)}</span>
        <span class="unique-id-source">via ${esc(data.source_platform)}${hint}</span>
      </div>`);

    if (countEl) countEl.textContent = list.querySelectorAll('.unique-id-item').length;
  }

  // Update the tree node inline badge (existing behaviour)
  const el = hopElements.get(data.source_seed.toLowerCase()) || currentHopEl;
  if (!el) return;
  const body = el.querySelector('.tree-node-body');

  const detail = data.source_detail || data.source_platform;
  const hint = data.hint_platform ? ` · likely ${esc(data.hint_platform)}` : '';

  body.insertAdjacentHTML('beforeend', `
    <div class="identity-badge">
      <span class="identity-arrow">↳</span>
      <span>Discovered</span>
      <span class="identity-type-badge">${esc(data.value_type)}</span>
      <span class="identity-badge-value">${esc(data.value)}</span>
      <span class="identity-badge-source">via ${esc(detail)}${hint}</span>
    </div>`);
}

function onHopComplete(data) {
  const el = hopElements.get(data.seed.toLowerCase()) || currentHopEl;
  if (!el) return;

  const statusEl = el.querySelector('.tree-status');
  if (statusEl) {
    if (el._found > 0) {
      statusEl.textContent = `${el._found} found`;
      statusEl.className = 'tree-status found';
    } else {
      statusEl.textContent = 'none found';
      statusEl.className = 'tree-status';
    }
  }

  if (el._notFound > 0) {
    el.querySelector('.tree-node-body').insertAdjacentHTML('beforeend', `
      <div class="not-found-summary">${el._notFound} platform${el._notFound !== 1 ? 's' : ''} not found</div>`);
  }
}

function onCapReached(data) {
  const tree = resultsEl.querySelector('.discovery-tree');
  if (tree) {
    tree.insertAdjacentHTML('beforeend', `
      <div class="cap-notice">
        &#9889; ${data.cap}-hop cap reached. Toggle the cap off and search again to go further.
      </div>`);
  }
  setStatus(`Cap reached at ${data.cap} hops.`);
}

function onDone(data) {
  const tree = resultsEl.querySelector('.discovery-tree');
  if (tree) {
    const ids = data.total_usernames + data.total_emails;
    tree.insertAdjacentHTML('beforeend', `
      <div class="done-banner">
        Search complete — ${data.total_hops} hop${data.total_hops !== 1 ? 's' : ''},
        ${ids} unique identit${ids !== 1 ? 'ies' : 'y'} explored
      </div>`);
  }
  setStatus('');
  if (eventSource) { eventSource.close(); eventSource = null; }
}

// ── Unique Identities collapse/expand ────────────────────────────────────────

function toggleUniqueIds() {
  const list = document.getElementById('unique-id-list');
  const icon = document.getElementById('unique-id-icon');
  if (!list) return;
  const collapsed = list.classList.toggle('collapsed');
  icon.textContent = collapsed ? '▶' : '▼';
}

// ── Tree collapse/expand ──────────────────────────────────────────────────────

function toggleNode(header) {
  const body = header.nextElementSibling;
  const icon = header.querySelector('.tree-collapse-icon');
  const collapsed = body.classList.toggle('collapsed');
  icon.textContent = collapsed ? '▶' : '▼';
}

// ── Wayback Machine ───────────────────────────────────────────────────────────

async function handleWayback(btn) {
  const wbId = btn.dataset.wb;
  const url  = btn.dataset.url;
  const drawer = document.getElementById(wbId);

  if (drawer.classList.contains('open')) {
    drawer.classList.remove('open');
    btn.innerHTML = '&#128337; Archive';
    return;
  }
  if (drawer.dataset.loaded === '1') {
    drawer.classList.add('open');
    btn.innerHTML = '&#128337; Archive';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Loading…';

  try {
    const res = await fetch(`/api/wayback?url=${encodeURIComponent(url)}`);
    const data = await res.json();
    drawer.innerHTML = renderWaybackPanel(data);
    drawer.dataset.loaded = '1';
  } catch (err) {
    drawer.innerHTML = `<div class="wayback-panel"><span class="wb-error">Request failed: ${esc(err.message)}</span></div>`;
  }

  drawer.classList.add('open');
  btn.disabled = false;
  btn.innerHTML = '&#128337; Archive';
}

function renderWaybackPanel(data) {
  if (!data.archived) {
    return `<div class="wayback-panel">
      <span class="wb-never">Never archived by the Wayback Machine.</span>
    </div>`;
  }

  const deletedFlag = data.possibly_deleted
    ? `<div class="wb-deleted-flag">&#9888; Account may have been deleted &mdash; last recorded status: ${esc(data.last_status)}</div>`
    : '';

  const timeline = data.timeline.map(t => {
    const cls = t.status === '200' ? 'wb-ok' : t.status.startsWith('4') ? 'wb-gone' : 'wb-other';
    return `<span class="wb-tick ${cls}">${esc(t.date)}&nbsp;[${t.status}]</span>`;
  }).join('<span class="wb-arrow"> → </span>');

  const snapshotLink = data.snapshot_url
    ? `<a class="wb-snapshot-link" href="${esc(data.snapshot_url)}" target="_blank" rel="noopener">View archived snapshot &#8594;</a>`
    : '';

  return `<div class="wayback-panel">
    ${deletedFlag}
    <div class="wb-stats">
      <div class="wb-stat"><span class="wb-label">First archived</span><span class="wb-value">${esc(data.first_seen)}</span></div>
      <div class="wb-stat"><span class="wb-label">Last archived</span><span class="wb-value">${esc(data.last_seen)}</span></div>
      <div class="wb-stat"><span class="wb-label">Snapshots</span><span class="wb-value">~${data.snapshot_count}</span></div>
      <div class="wb-stat"><span class="wb-label">Last status</span><span class="wb-value">${esc(data.last_status)}</span></div>
    </div>
    ${timeline ? `<div class="wb-timeline">${timeline}</div>` : ''}
    ${snapshotLink}
  </div>`;
}

// ── Activity expand (Reddit / GitHub) ─────────────────────────────────────────

async function handleExpand(btn) {
  const drawerId = btn.dataset.drawer;
  const drawer = document.getElementById(drawerId);
  const row = btn.closest('.account-row');
  const platform = row.dataset.platform;
  const username = row.dataset.username;

  if (drawer.classList.contains('open')) {
    drawer.classList.remove('open');
    btn.innerHTML = '&#9660; Activity';
    return;
  }
  if (drawer.dataset.loaded === '1') {
    drawer.classList.add('open');
    btn.innerHTML = '&#9650; Activity';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Loading…';

  try {
    const key = PLATFORM_KEY[platform];
    const res = await fetch(
      `/api/content?platform=${encodeURIComponent(key)}&username=${encodeURIComponent(username)}`
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      drawer.innerHTML = `<div class="content-empty" style="padding-bottom:.75rem">Error: ${esc(err.detail ?? res.statusText)}</div>`;
    } else {
      const data = await res.json();
      if (platform === 'GitHub') renderGitHubDrawer(drawer, drawerId, username, data);
      else renderRedditDrawer(drawer, drawerId, username, data);
      drawer.dataset.loaded = '1';
      attachTabListeners(drawer);
      attachLoadMoreListeners(drawer);
    }
  } catch (err) {
    drawer.innerHTML = `<div class="content-empty" style="padding-bottom:.75rem">Request failed: ${esc(err.message)}</div>`;
  }

  drawer.classList.add('open');
  btn.disabled = false;
  btn.innerHTML = '&#9650; Activity';
}

// ── GitHub drawer ─────────────────────────────────────────────────────────────

function renderGitHubDrawer(drawer, drawerId, username, data) {
  const { repos, events } = data;
  paginationState.set(`${drawerId}-repos`,  { username, page: repos.page + 1, exhausted: !repos.has_more });
  paginationState.set(`${drawerId}-events`, { username, page: events.page + 1, exhausted: !events.has_more });

  drawer.innerHTML = `
    <div class="content-tabs">
      <button class="tab-btn active" data-tab="gh-repos-${drawerId}">
        Repositories (${repos.items.length}${repos.has_more ? '+' : ''})
      </button>
      <button class="tab-btn" data-tab="gh-events-${drawerId}">
        Recent Activity (${events.items.length}${events.has_more ? '+' : ''})
      </button>
    </div>
    <div class="content-scroll">
      <div class="tab-panel active" id="gh-repos-${drawerId}">
        ${renderRepoItems(repos.items)}
        ${repos.has_more ? loadMoreBtn('github', 'repos', drawerId) : ''}
      </div>
      <div class="tab-panel" id="gh-events-${drawerId}">
        ${renderEventItems(events.items)}
        ${events.has_more ? loadMoreBtn('github', 'events', drawerId) : ''}
      </div>
    </div>`;
}

function renderRepoItems(items) {
  if (!items.length) return `<div class="content-empty">No public repositories.</div>`;
  return items.map(r => `
    <div class="content-item">
      <div class="content-item-title">
        <a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.name)}</a>
        ${r.fork ? `<span class="lang-badge">fork</span>` : ''}
        ${r.language ? `<span class="lang-badge">${esc(r.language)}</span>` : ''}
        ${r.stars ? `<span class="star-count">&#9733; ${r.stars}</span>` : ''}
      </div>
      ${r.description ? `<div class="content-item-body">${esc(r.description)}</div>` : ''}
      <div class="content-item-meta">Updated ${formatDate(r.updated_at)}</div>
    </div>`).join('');
}

function renderEventItems(items) {
  if (!items.length) return `<div class="content-empty">No recent public activity.</div>`;
  return items.map(e => `
    <div class="content-item">
      <div class="content-item-title">
        <a href="${esc(e.repo_url)}" target="_blank" rel="noopener">${esc(e.repo)}</a>
      </div>
      <div class="content-item-body">${esc(e.summary)}</div>
      <div class="content-item-meta">${formatDate(e.created_at)}</div>
    </div>`).join('');
}

// ── Reddit drawer ─────────────────────────────────────────────────────────────

function renderRedditDrawer(drawer, drawerId, username, data) {
  const { posts, comments } = data;
  paginationState.set(`${drawerId}-posts`,    { username, after: posts.after, exhausted: !posts.after });
  paginationState.set(`${drawerId}-comments`, { username, after: comments.after, exhausted: !comments.after });

  drawer.innerHTML = `
    <div class="content-tabs">
      <button class="tab-btn active" data-tab="rd-posts-${drawerId}">
        Posts (${posts.items.length}${posts.after ? '+' : ''})
      </button>
      <button class="tab-btn" data-tab="rd-comments-${drawerId}">
        Comments (${comments.items.length}${comments.after ? '+' : ''})
      </button>
    </div>
    <div class="content-scroll">
      <div class="tab-panel active" id="rd-posts-${drawerId}">
        ${renderPostItems(posts.items)}
        ${posts.after ? loadMoreBtn('reddit', 'posts', drawerId) : ''}
      </div>
      <div class="tab-panel" id="rd-comments-${drawerId}">
        ${renderCommentItems(comments.items)}
        ${comments.after ? loadMoreBtn('reddit', 'comments', drawerId) : ''}
      </div>
    </div>`;
}

function renderPostItems(items) {
  if (!items.length) return `<div class="content-empty">No recent posts.</div>`;
  return items.map(p => `
    <div class="content-item">
      <div class="content-item-title">
        <a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a>
      </div>
      <div class="content-item-meta">
        ${esc(p.subreddit)} &nbsp;&#183;&nbsp; &#9650; ${p.score} &nbsp;&#183;&nbsp; ${formatUnix(p.created_utc)}
      </div>
    </div>`).join('');
}

function renderCommentItems(items) {
  if (!items.length) return `<div class="content-empty">No recent comments.</div>`;
  return items.map(c => `
    <div class="content-item">
      <div class="content-item-body">${esc(c.body)}</div>
      <div class="content-item-meta">
        <a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.subreddit)}</a>
        &nbsp;&#183;&nbsp; &#9650; ${c.score} &nbsp;&#183;&nbsp; ${formatUnix(c.created_utc)}
      </div>
    </div>`).join('');
}

// ── Load More ─────────────────────────────────────────────────────────────────

function loadMoreBtn(platform, type, drawerId) {
  return `<button class="load-more-btn"
      data-platform="${platform}" data-type="${type}" data-drawer="${drawerId}">Load more</button>`;
}

function attachLoadMoreListeners(drawer) {
  drawer.querySelectorAll('.load-more-btn').forEach(btn => {
    btn.addEventListener('click', () => loadMore(btn));
  });
}

async function loadMore(btn) {
  const { platform, type, drawer: drawerId } = btn.dataset;
  const stateKey = `${drawerId}-${type}`;
  const state = paginationState.get(stateKey);
  if (!state || state.exhausted) return;

  btn.disabled = true;
  btn.textContent = 'Loading…';

  try {
    let url;
    if (platform === 'reddit') {
      url = `/api/content?platform=reddit&username=${encodeURIComponent(state.username)}&type=${type}`;
      if (state.after) url += `&after=${encodeURIComponent(state.after)}`;
    } else {
      url = `/api/content?platform=github&username=${encodeURIComponent(state.username)}&type=${type}&page=${state.page}`;
    }

    const res = await fetch(url);
    if (!res.ok) { btn.disabled = false; btn.textContent = 'Load more'; return; }

    const data = await res.json();
    if (data.rate_limited) {
      btn.replaceWith(makeEl(`<div class="rate-limit-note">Rate limit reached — try again later.</div>`));
      return;
    }

    const items = data.items ?? [];
    const newHtml = platform === 'reddit'
      ? (type === 'posts' ? renderPostItems(items) : renderCommentItems(items))
      : (type === 'repos' ? renderRepoItems(items) : renderEventItems(items));

    btn.insertAdjacentHTML('beforebegin', newHtml);

    const hasMore = platform === 'reddit' ? !!data.after : data.has_more;
    if (!hasMore || items.length === 0) {
      btn.remove();
      state.exhausted = true;
    } else {
      if (platform === 'reddit') state.after = data.after;
      else state.page = data.page + 1;
      btn.disabled = false;
      btn.textContent = 'Load more';
    }
    paginationState.set(stateKey, state);
  } catch {
    btn.disabled = false;
    btn.textContent = 'Load more';
  }
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

function attachTabListeners(drawer) {
  drawer.querySelectorAll('.tab-btn').forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      drawer.querySelectorAll('.tab-btn').forEach(t => t.classList.remove('active'));
      drawer.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById(target).classList.add('active');
    });
  });
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function setStatus(msg) {
  if (msg) {
    statusEl.textContent = msg;
    statusEl.classList.remove('hidden');
  } else {
    statusEl.classList.add('hidden');
  }
}

function makeEl(html) {
  const div = document.createElement('div');
  div.innerHTML = html;
  return div.firstElementChild;
}

function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function formatUnix(ts) {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
