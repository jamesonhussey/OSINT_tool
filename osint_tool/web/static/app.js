// ── Global state ───────────────────────────────────────────────────────────────

const EXPANDABLE = new Set(['GitHub', 'Reddit']);
const PLATFORM_KEY = { 'GitHub': 'github', 'Reddit': 'reddit' };

let capEnabled = true;
let drawerCounter = 0;   // global, always incrementing — guarantees unique drawer IDs
let blockCounter  = 0;   // global, always incrementing — guarantees unique block IDs
const paginationState = new Map();

// ── DOM refs ───────────────────────────────────────────────────────────────────

const form             = document.getElementById('search-form');
const input            = document.getElementById('query-input');
const statusEl         = document.getElementById('status');
const resultsEl        = document.getElementById('results');
const capBtn           = document.getElementById('cap-btn');
const hybridsBtn       = document.getElementById('hybrids-btn');
const collapseAllBtn   = document.getElementById('collapse-all-btn');
const hybridTray       = document.getElementById('hybrid-tray');
const settingsBtn      = document.getElementById('settings-btn');
const settingsModal    = document.getElementById('settings-modal');
const settingsClose    = document.getElementById('settings-close');
const settingsSave     = document.getElementById('settings-save');
const apiKeyInput      = document.getElementById('api-key-input');
const apiKeyStatus     = document.getElementById('api-key-status');
const autoVariantsToggle = document.getElementById('auto-variants-toggle');
const extractionNotice = document.getElementById('extraction-notice');
const resetExtractionBtn   = document.getElementById('reset-extraction-cache-btn');
const resetExtractionStatus = document.getElementById('reset-extraction-status');

// ── Cap toggle ─────────────────────────────────────────────────────────────────

capBtn.addEventListener('click', () => {
  capEnabled = !capEnabled;
  capBtn.classList.toggle('active', capEnabled);
});

// ── Collapse / Expand All ──────────────────────────────────────────────────────

let _allCollapsed = false;

collapseAllBtn.addEventListener('click', () => {
  _allCollapsed = !_allCollapsed;
  document.querySelectorAll('.search-block-body').forEach(b =>
    b.classList.toggle('collapsed', _allCollapsed));
  document.querySelectorAll('.block-collapse-btn').forEach(btn => {
    btn.classList.toggle('active', !_allCollapsed);
    btn.innerHTML = _allCollapsed ? '&#9654;' : '&#9660;';
  });
  collapseAllBtn.innerHTML = _allCollapsed ? '&#9654; Expand All' : '&#9660; Collapse All';
});

// ── Generate Hybrids ──────────────────────────────────────────────────────────

hybridsBtn.addEventListener('click', async () => {
  const blocks = [...document.querySelectorAll('.search-block')];
  if (!blocks.length) {
    setGlobalStatus('No searches on screen to generate hybrids from.', 3000);
    return;
  }

  const seeds = [];
  const seen  = new Set();
  const addSeed = value => {
    const key = value.trim().toLowerCase();
    if (key && !seen.has(key)) {
      seen.add(key);
      seeds.push({ value: value.trim(), type: value.includes('@') ? 'email' : 'username' });
    }
  };

  // Explicitly searched queries
  blocks.forEach(b => addSeed(b.dataset.query));

  // Discovered identities from every visible Unique Identities panel
  document.querySelectorAll('.uid-list .unique-id-value').forEach(el => addSeed(el.textContent));

  hybridTray.classList.remove('hidden');
  hybridTray.innerHTML = `<div class="variant-tray-loading">Analysing ${seeds.length} search${seeds.length !== 1 ? 'es' : ''}…</div>`;

  try {
    const res = await fetch('/api/generate-hybrids', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seeds }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    renderVariantTray(hybridTray, data, null, data.analysis);
  } catch (err) {
    hybridTray.innerHTML = `<div class="variant-tray-error">&#9888; ${esc(err.message)}</div>`;
  }
});

// ── Settings modal ─────────────────────────────────────────────────────────────

settingsBtn.addEventListener('click', openSettings);
settingsClose.addEventListener('click', () => settingsModal.classList.add('hidden'));
settingsModal.addEventListener('click', e => { if (e.target === settingsModal) settingsModal.classList.add('hidden'); });

resetExtractionBtn?.addEventListener('click', async () => {
  resetExtractionBtn.disabled = true;
  resetExtractionStatus.textContent = 'Resetting…';
  resetExtractionStatus.style.color = 'var(--text-muted)';
  try {
    const res = await fetch('/api/reset-extraction-cache', { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText);
    resetExtractionStatus.textContent = data.message || 'Local cache cleared.';
    resetExtractionStatus.style.color = 'var(--green)';
  } catch (e) {
    resetExtractionStatus.textContent = String(e.message);
    resetExtractionStatus.style.color = 'var(--red)';
  }
  resetExtractionBtn.disabled = false;
});

settingsSave.addEventListener('click', async () => {
  settingsSave.disabled = true;
  settingsSave.textContent = 'Saving…';
  const body = { auto_search_variants: autoVariantsToggle.checked };
  const keyVal = apiKeyInput.value.trim();
  if (keyVal) body.anthropic_api_key = keyVal;
  await fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  settingsSave.textContent = 'Saved!';
  apiKeyInput.value = '';
  setTimeout(() => {
    settingsSave.disabled = false;
    settingsSave.textContent = 'Save';
    settingsModal.classList.add('hidden');
    loadSettings();
  }, 800);
});

async function openSettings() {
  settingsModal.classList.remove('hidden');
  await loadSettings();
}

async function loadSettings() {
  try {
    const res = await fetch('/api/settings');
    const data = await res.json();
    autoVariantsToggle.checked = data.auto_search_variants;
    if (data.has_api_key) {
      apiKeyInput.placeholder = `Current key: ${data.api_key_preview} — enter new to replace`;
      apiKeyStatus.textContent = 'API key configured.';
      apiKeyStatus.style.color = 'var(--green)';
      extractionNotice.classList.add('hidden');
    } else {
      apiKeyInput.placeholder = 'sk-ant-…';
      apiKeyStatus.textContent = 'No API key — AI features will use programmatic fallback.';
      apiKeyStatus.style.color = 'var(--yellow)';
      extractionNotice.textContent = 'Running in basic mode \u2014 profile existence only, no identity extraction. Configure an API key in Settings to enable LLM-powered extraction.';
      extractionNotice.classList.remove('hidden');
    }
  } catch {}
}

// Check extraction mode on page load
loadSettings();

// ── Form submit ────────────────────────────────────────────────────────────────

form.addEventListener('submit', async e => {
  e.preventDefault();
  const q = input.value.trim();
  if (!q) return;
  resultsEl.classList.remove('hidden');
  const blockEl = startSearch(q, null);

  // Auto-variants if enabled
  try {
    const res = await fetch('/api/settings');
    const cfg = await res.json();
    if (cfg.auto_search_variants) {
      const vtray = blockEl.querySelector('.block-variant-tray');
      vtray.classList.remove('hidden');
      showVariantTray(vtray, q, null, blockEl);
    }
  } catch {}
});

// ── Search block ───────────────────────────────────────────────────────────────

function startSearch(query, parentBlockEl) {
  const blockEl = buildSearchBlock(query, parentBlockEl);
  runSSESearch(query, blockEl);
  return blockEl;
}

function buildSearchBlock(query, parentBlockEl) {
  const id = ++blockCounter;
  const el = document.createElement('div');
  el.className = 'search-block';
  el.dataset.query = query;
  el.dataset.blockId = id;

  el.innerHTML = `
    <div class="search-block-header">
      <span class="search-block-query">${esc(query)}</span>
      <div class="search-block-actions">
        <button class="block-variants-btn cap-btn" title="Generate variants for this search">&#10024; Variants</button>
        <button class="block-collapse-btn cap-btn active" title="Collapse">&#9660;</button>
        <button class="block-delete-btn" title="Remove this search">&#10005;</button>
      </div>
    </div>
    <div class="block-variant-tray hidden" id="bvt-${id}"></div>
    <div class="search-block-body" id="bsb-${id}">
      <div class="block-status status hidden" id="bst-${id}"></div>
      <div class="block-results" id="br-${id}"></div>
    </div>
    <div class="child-searches" id="bcs-${id}"></div>`;

  // Delete
  el.querySelector('.block-delete-btn').addEventListener('click', () => {
    if (el._eventSource) el._eventSource.close();
    el.remove();
  });

  // Collapse/expand
  const collapseBtn = el.querySelector('.block-collapse-btn');
  const body = el.querySelector('.search-block-body');
  collapseBtn.addEventListener('click', () => {
    const collapsed = body.classList.toggle('collapsed');
    collapseBtn.classList.toggle('active', !collapsed);
    collapseBtn.innerHTML = collapsed ? '&#9654;' : '&#9660;';
  });

  // Variants tray toggle
  const vtray = el.querySelector('.block-variant-tray');
  el.querySelector('.block-variants-btn').addEventListener('click', async () => {
    if (!vtray.classList.contains('hidden') && vtray._loaded) {
      vtray.classList.add('hidden');
      vtray._loaded = false;
      return;
    }
    vtray.classList.remove('hidden');
    await showVariantTray(vtray, query, null, el);
    vtray._loaded = true;
  });

  // Append: nested under parent's child-searches, or top-level
  if (parentBlockEl) {
    parentBlockEl.querySelector('.child-searches').appendChild(el);
  } else {
    resultsEl.appendChild(el);
  }

  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  return el;
}

// ── SSE search runner ──────────────────────────────────────────────────────────

function runSSESearch(query, blockEl) {
  const localHopEls = new Map();
  let localCurrentHopEl = null;

  const resultsDiv  = blockEl.querySelector('.block-results');
  const blockStatus = blockEl.querySelector('.block-status');

  const setBlockStatus = msg => {
    if (msg) { blockStatus.textContent = msg; blockStatus.classList.remove('hidden'); }
    else blockStatus.classList.add('hidden');
  };

  const url = `/api/search/stream?q=${encodeURIComponent(query)}&cap=${capEnabled}`;
  const es  = new EventSource(url);
  blockEl._eventSource = es;

  const on = (type, fn) => es.addEventListener(type, e => fn(JSON.parse(e.data)));

  on('start', () => {
    setBlockStatus('Searching…');
    resultsDiv.innerHTML = `
      <div class="section uid-section">
        <div class="section-header unique-id-header" onclick="toggleSection(this)">
          <span class="tree-collapse-icon">&#9660;</span>
          Unique Identities
          <span class="uid-count unique-id-count">0</span>
        </div>
        <div class="uid-list unique-id-list">
          <span class="unique-id-empty">None discovered yet…</span>
        </div>
      </div>
      <div class="section extraction-activity-section">
        <div class="section-header extraction-activity-header" onclick="toggleSection(this)">
          <span class="tree-collapse-icon">&#9660;</span>
          Extraction activity
        </div>
        <div class="extraction-activity-log">
          <span class="extraction-activity-empty">No HTML extraction steps yet…</span>
        </div>
      </div>
      <div class="discovery-tree"></div>`;
  });

  on('hop_start', data => {
    const tree   = resultsDiv.querySelector('.discovery-tree');
    const indent = Math.min(data.hop, 5) * 20;
    const prov   = data.parent_seed
      ? `hop ${data.hop} · via ${esc(data.parent_platform)} from ${esc(data.parent_seed)}`
      : 'initial seed';

    const el = document.createElement('div');
    el.className = 'tree-node';
    el.dataset.hop  = data.hop;
    el.dataset.seed = data.seed;
    el.style.marginLeft = `${indent}px`;
    el._found = 0; el._notFound = 0; el._total = 0;

    el.innerHTML = `
      <div class="tree-node-header" onclick="toggleNode(this)">
        <span class="tree-collapse-icon">&#9660;</span>
        <span class="tree-seed">${esc(data.seed)}</span>
        <span class="tree-type-badge">${esc(data.seed_type)}</span>
        <span class="tree-provenance">${prov}</span>
        <span class="tree-status">searching…</span>
      </div>
      <div class="tree-node-body"></div>`;

    tree.appendChild(el);
    localHopEls.set(data.seed.toLowerCase(), el);
    localCurrentHopEl = el;
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });

  on('extraction_activity', data => {
    const log = resultsDiv.querySelector('.extraction-activity-log');
    if (!log) return;
    log.querySelector('.extraction-activity-empty')?.remove();

    const mode    = data.mode || '';
    const isLlm   = mode === 'llm';
    const badge   = isLlm ? 'llm-badge' : 'cache-badge';
    const summary = data.message || `${mode} · ${data.domain || ''}`;

    const row = document.createElement('div');
    row.className = 'extraction-activity-row';
    row.innerHTML = `
      <div class="extraction-activity-meta">
        <span class="extraction-activity-badge ${badge}">${esc(mode)}</span>
        <span class="extraction-activity-platform">${esc(data.platform || '')}</span>
        <span class="extraction-activity-domain">${esc(data.domain || '')}</span>
      </div>
      <div class="extraction-activity-summary">${esc(summary)}</div>`;

    if (data.preview) {
      const pre = document.createElement('pre');
      pre.className = 'extraction-activity-preview';
      pre.textContent = data.preview;
      row.appendChild(pre);
    }
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
  });

  on('gravatar', data => {
    const el = localHopEls.get(data.seed.toLowerCase()) || localCurrentHopEl;
    if (!el) return;
    const g = data.data;
    el.querySelector('.tree-node-body').insertAdjacentHTML('beforeend', `
      <div class="gravatar-row">
        ${g.avatar_url ? `<img class="gravatar-avatar" src="${esc(g.avatar_url)}?s=80" alt="avatar" />` : ''}
        <div class="gravatar-info">
          ${g.display_name ? `<div class="gravatar-name">Gravatar: ${esc(g.display_name)}</div>` : ''}
          <div class="gravatar-meta">
            ${g.location ? `<div>&#128205; ${esc(g.location)}</div>` : ''}
            ${g.about    ? `<div>${esc(g.about)}</div>` : ''}
            ${g.profile_url ? `<div><a href="${esc(g.profile_url)}" target="_blank" rel="noopener">${esc(g.profile_url)}</a></div>` : ''}
          </div>
        </div>
      </div>`);
  });

  on('account_result', data => {
    const el = localHopEls.get(data.seed.toLowerCase()) || localCurrentHopEl;
    if (!el) return;
    el._total++;
    if (data.status === 'not_found') { el._notFound++; return; }
    if (data.status === 'found')     { el._found++;    el.classList.add('has-found'); }

    const body      = el.querySelector('.tree-node-body');
    const canExpand = data.status === 'found' && EXPANDABLE.has(data.platform);
    const rowId     = drawerCounter++;
    const drawerId  = `drawer-${rowId}`;
    const wbId      = `wb-${rowId}`;
    const showUser  = data.username.toLowerCase() !== data.seed.toLowerCase();

    body.insertAdjacentHTML('beforeend', `
      <div class="account-row" data-platform="${esc(data.platform)}" data-username="${esc(data.username)}">
        <div class="status-dot ${data.status}"></div>
        <div class="platform-name">${esc(data.platform)}</div>
        ${data.status === 'found'
          ? `<a class="account-url" href="${esc(data.url)}" target="_blank" rel="noopener">${esc(data.url)}</a>`
          : `<span class="account-url" style="color:var(--red)">${esc(data.url)}</span>`}
        ${showUser ? `<span class="account-username">@${esc(data.username)}</span>` : ''}
        ${canExpand ? `<button class="expand-btn" data-drawer="${drawerId}">&#9660; Activity</button>` : ''}
        <button class="archive-btn" data-wb="${wbId}" data-url="${esc(data.url)}">&#128337; Archive</button>
      </div>
      ${canExpand ? `<div class="content-drawer" id="${drawerId}"></div>` : ''}
      <div class="wayback-drawer" id="${wbId}"></div>`);

    if (canExpand) {
      const btn = body.querySelector(`[data-drawer="${drawerId}"]`);
      btn.addEventListener('click', () => handleExpand(btn));
    }
    body.querySelector(`[data-wb="${wbId}"]`).addEventListener('click', function() { handleWayback(this); });
  });

  on('identity_discovered', data => {
    const list    = resultsDiv.querySelector('.uid-list');
    const countEl = resultsDiv.querySelector('.uid-count');
    if (list) {
      list.querySelector('.unique-id-empty')?.remove();

      const hint   = data.hint_platform ? ` · ${esc(data.hint_platform)}` : '';
      const itemId = `uid-${drawerCounter++}`;

      const sourceDomain = data.source_platform ? platformToDomain(data.source_platform) : '';

      list.insertAdjacentHTML('beforeend', `
        <div class="unique-id-item" id="uid-item-${itemId}">
          <span class="identity-type-badge">${esc(data.value_type)}</span>
          <span class="unique-id-value">${esc(data.value)}</span>
          <span class="unique-id-source">via ${esc(data.source_platform)}${hint}</span>
          <button class="identity-flag-btn"
            data-domain="${esc(sourceDomain)}"
            data-value="${esc(data.value)}"
            data-item="uid-item-${itemId}"
            title="Flag this identity as incorrect">&#9873; Flag</button>
          <button class="identity-variants-btn"
            data-value="${esc(data.value)}"
            data-context="${esc(data.source_platform)}"
            data-tray="${itemId}">&#10024; Variants</button>
        </div>
        <div class="identity-variant-tray" id="${itemId}"></div>`);

      const varBtn = list.querySelector(`[data-tray="${itemId}"]`);
      varBtn?.addEventListener('click', async () => {
        const tray = document.getElementById(itemId);
        if (tray.classList.contains('open')) { tray.classList.remove('open'); return; }
        tray.classList.add('open');
        await showVariantTray(tray, varBtn.dataset.value, varBtn.dataset.context, blockEl);
      });

      const flagBtn = list.querySelector(`#uid-item-${itemId} .identity-flag-btn`);
      flagBtn?.addEventListener('click', () => handleFlagIdentity(flagBtn));

      if (countEl) countEl.textContent = list.querySelectorAll('.unique-id-item').length;
    }

    // Inline badge in the tree
    const el     = localHopEls.get(data.source_seed.toLowerCase()) || localCurrentHopEl;
    if (!el) return;
    const detail = data.source_detail || data.source_platform;
    const hint2  = data.hint_platform ? ` · likely ${esc(data.hint_platform)}` : '';
    el.querySelector('.tree-node-body').insertAdjacentHTML('beforeend', `
      <div class="identity-badge">
        <span class="identity-arrow">↳</span>
        <span>Discovered</span>
        <span class="identity-type-badge">${esc(data.value_type)}</span>
        <span class="identity-badge-value">${esc(data.value)}</span>
        <span class="identity-badge-source">via ${esc(detail)}${hint2}</span>
      </div>`);
  });

  on('hop_complete', data => {
    const el = localHopEls.get(data.seed.toLowerCase()) || localCurrentHopEl;
    if (!el) return;
    const st = el.querySelector('.tree-status');
    if (st) {
      if (el._found > 0) { st.textContent = `${el._found} found`; st.className = 'tree-status found'; }
      else               { st.textContent = 'none found';          st.className = 'tree-status'; }
    }
    if (el._notFound > 0) {
      el.querySelector('.tree-node-body').insertAdjacentHTML('beforeend',
        `<div class="not-found-summary">${el._notFound} platform${el._notFound !== 1 ? 's' : ''} not found</div>`);
    }
  });

  on('cap_reached', data => {
    resultsDiv.querySelector('.discovery-tree')?.insertAdjacentHTML('beforeend',
      `<div class="cap-notice">&#9889; ${data.cap}-hop cap reached. Toggle the cap off and search again to go further.</div>`);
    setBlockStatus(`Cap reached at ${data.cap} hops.`);
  });

  on('done', data => {
    const tree = resultsDiv.querySelector('.discovery-tree');
    if (tree) {
      const ids = data.total_usernames + data.total_emails;
      tree.insertAdjacentHTML('beforeend', `
        <div class="done-banner">
          Search complete — ${data.total_hops} hop${data.total_hops !== 1 ? 's' : ''},
          ${ids} unique identit${ids !== 1 ? 'ies' : 'y'} explored
        </div>`);
    }
    setBlockStatus('');
    es.close();
  });

  es.onerror = () => {
    if (es.readyState !== EventSource.CLOSED) {
      setBlockStatus('Connection error — search may be incomplete.');
      es.close();
    }
  };
}

// ── Variant generation ─────────────────────────────────────────────────────────

async function showVariantTray(trayEl, inputVal, context, parentBlockEl) {
  trayEl.innerHTML = `<div class="variant-tray-loading">Generating variants…</div>`;
  try {
    const res = await fetch('/api/generate-variants', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input: inputVal, context }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new Error(body?.detail ?? `HTTP ${res.status}`);
    }
    const data = await res.json();
    renderVariantTray(trayEl, data, parentBlockEl, null);
  } catch (err) {
    trayEl.innerHTML = `<div class="variant-tray-error">&#9888; ${esc(err.message)}</div>`;
  }
}

function renderVariantTray(trayEl, data, parentBlockEl, analysisNote) {
  const usernames = data.username_variants ?? [];
  const realnames = data.realname_variants ?? [];

  if (!usernames.length && !realnames.length) {
    trayEl.innerHTML = `<div class="variant-tray-loading">No variants generated.</div>`;
    return;
  }

  let html = `<div class="variant-tray-header">Click a variant to search it</div>`;

  if (analysisNote) {
    html += `<div class="variant-analysis">${esc(analysisNote)}</div>`;
  }

  if (usernames.length) {
    html += `<div class="variant-section">
      <div class="variant-section-label">Username variants</div>
      <div class="variant-chips">
        ${usernames.map(v => `<button class="variant-chip" data-value="${esc(v)}">${esc(v)}</button>`).join('')}
      </div></div>`;
  }
  if (realnames.length) {
    html += `<div class="variant-section">
      <div class="variant-section-label">Real-name searches</div>
      <div class="variant-chips">
        ${realnames.map(v => `<button class="variant-chip" data-value="${esc(v)}">${esc(v)}</button>`).join('')}
      </div></div>`;
  }

  trayEl.innerHTML = html;

  trayEl.querySelectorAll('.variant-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      if (chip.classList.contains('used')) return;
      chip.classList.add('used');
      startSearch(chip.dataset.value, parentBlockEl);
    });
  });
}

// ── Unique identity section collapse ──────────────────────────────────────────

function toggleSection(header) {
  const list = header.nextElementSibling;
  const icon = header.querySelector('.tree-collapse-icon');
  if (!list) return;
  const collapsed = list.classList.toggle('collapsed');
  icon.textContent = collapsed ? '▶' : '▼';
}

// ── Tree collapse/expand ───────────────────────────────────────────────────────

function toggleNode(header) {
  const body = header.nextElementSibling;
  const icon = header.querySelector('.tree-collapse-icon');
  const collapsed = body.classList.toggle('collapsed');
  icon.textContent = collapsed ? '▶' : '▼';
}

// ── Wayback Machine ────────────────────────────────────────────────────────────

async function handleWayback(btn) {
  const wbId   = btn.dataset.wb;
  const url    = btn.dataset.url;
  const drawer = document.getElementById(wbId);

  if (drawer.classList.contains('open')) {
    drawer.classList.remove('open');
    btn.innerHTML = '&#128337; Archive';
    return;
  }
  if (drawer.dataset.loaded === '1') {
    drawer.classList.add('open');
    return;
  }

  btn.disabled    = true;
  btn.textContent = 'Loading…';

  try {
    const res  = await fetch(`/api/wayback?url=${encodeURIComponent(url)}`);
    const data = await res.json();
    drawer.innerHTML    = renderWaybackPanel(data);
    drawer.dataset.loaded = '1';
  } catch (err) {
    drawer.innerHTML = `<div class="wayback-panel"><span class="wb-error">Request failed: ${esc(err.message)}</span></div>`;
  }

  drawer.classList.add('open');
  btn.disabled    = false;
  btn.innerHTML   = '&#128337; Archive';
}

function renderWaybackPanel(data) {
  if (!data.archived) {
    return `<div class="wayback-panel"><span class="wb-never">Never archived by the Wayback Machine.</span></div>`;
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
  const drawer   = document.getElementById(drawerId);
  const row      = btn.closest('.account-row');
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

  btn.disabled    = true;
  btn.textContent = 'Loading…';

  try {
    const key = PLATFORM_KEY[platform];
    const res = await fetch(`/api/content?platform=${encodeURIComponent(key)}&username=${encodeURIComponent(username)}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      drawer.innerHTML = `<div class="content-empty" style="padding-bottom:.75rem">Error: ${esc(err.detail ?? res.statusText)}</div>`;
    } else {
      const data = await res.json();
      if (platform === 'GitHub') renderGitHubDrawer(drawer, drawerId, username, data);
      else                        renderRedditDrawer(drawer, drawerId, username, data);
      drawer.dataset.loaded = '1';
      attachTabListeners(drawer);
      attachLoadMoreListeners(drawer);
    }
  } catch (err) {
    drawer.innerHTML = `<div class="content-empty" style="padding-bottom:.75rem">Request failed: ${esc(err.message)}</div>`;
  }

  drawer.classList.add('open');
  btn.disabled  = false;
  btn.innerHTML = '&#9650; Activity';
}

// ── GitHub drawer ──────────────────────────────────────────────────────────────

function renderGitHubDrawer(drawer, drawerId, username, data) {
  const { repos, events } = data;
  paginationState.set(`${drawerId}-repos`,  { username, page: repos.page + 1,   exhausted: !repos.has_more });
  paginationState.set(`${drawerId}-events`, { username, page: events.page + 1,  exhausted: !events.has_more });

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
        ${r.fork     ? `<span class="lang-badge">fork</span>` : ''}
        ${r.language ? `<span class="lang-badge">${esc(r.language)}</span>` : ''}
        ${r.stars    ? `<span class="star-count">&#9733; ${r.stars}</span>` : ''}
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

// ── Reddit drawer ──────────────────────────────────────────────────────────────

function renderRedditDrawer(drawer, drawerId, username, data) {
  const { posts, comments } = data;
  paginationState.set(`${drawerId}-posts`,    { username, after: posts.after,    exhausted: !posts.after });
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

// ── Load More ──────────────────────────────────────────────────────────────────

function loadMoreBtn(platform, type, drawerId) {
  return `<button class="load-more-btn"
    data-platform="${platform}" data-type="${type}" data-drawer="${drawerId}">Load more</button>`;
}

function attachLoadMoreListeners(drawer) {
  drawer.querySelectorAll('.load-more-btn').forEach(btn => btn.addEventListener('click', () => loadMore(btn)));
}

async function loadMore(btn) {
  const { platform, type, drawer: drawerId } = btn.dataset;
  const stateKey = `${drawerId}-${type}`;
  const state    = paginationState.get(stateKey);
  if (!state || state.exhausted) return;

  btn.disabled    = true;
  btn.textContent = 'Loading…';

  try {
    let url;
    if (platform === 'reddit') {
      url = `/api/content?platform=reddit&username=${encodeURIComponent(state.username)}&type=${type}`;
      if (state.after) url += `&after=${encodeURIComponent(state.after)}`;
    } else {
      url = `/api/content?platform=github&username=${encodeURIComponent(state.username)}&type=${type}&page=${state.page}`;
    }

    const res  = await fetch(url);
    if (!res.ok) { btn.disabled = false; btn.textContent = 'Load more'; return; }

    const data  = await res.json();
    if (data.rate_limited) {
      btn.replaceWith(makeEl(`<div class="rate-limit-note">Rate limit reached — try again later.</div>`));
      return;
    }

    const items  = data.items ?? [];
    const newHtml = platform === 'reddit'
      ? (type === 'posts' ? renderPostItems(items) : renderCommentItems(items))
      : (type === 'repos' ? renderRepoItems(items) : renderEventItems(items));

    btn.insertAdjacentHTML('beforebegin', newHtml);

    const hasMore = platform === 'reddit' ? !!data.after : data.has_more;
    if (!hasMore || items.length === 0) {
      btn.remove(); state.exhausted = true;
    } else {
      if (platform === 'reddit') state.after  = data.after;
      else                        state.page   = data.page + 1;
      btn.disabled    = false;
      btn.textContent = 'Load more';
    }
    paginationState.set(stateKey, state);
  } catch {
    btn.disabled    = false;
    btn.textContent = 'Load more';
  }
}

// ── Tabs ───────────────────────────────────────────────────────────────────────

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

// ── Flag identity ──────────────────────────────────────────────────────

const PLATFORM_DOMAINS = {
  'GitHub': 'github.com',
  'Twitter/X': 'x.com',
  'Instagram': 'instagram.com',
  'Reddit': 'reddit.com',
  'LinkedIn': 'linkedin.com',
  'Pinterest': 'pinterest.com',
  'TikTok': 'tiktok.com',
  'YouTube': 'youtube.com',
  'Steam': 'steamcommunity.com',
  'Medium': 'medium.com',
};

function platformToDomain(platform) {
  return PLATFORM_DOMAINS[platform] || platform.toLowerCase().replace(/[^a-z0-9.]/g, '') + '.com';
}

async function handleFlagIdentity(btn) {
  if (btn.classList.contains('flagged')) return;
  const domain = btn.dataset.domain;
  const value  = btn.dataset.value;
  const itemId = btn.dataset.item;

  btn.disabled = true;
  btn.textContent = 'Flagging…';

  try {
    await fetch('/api/flag-identity', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain, identity_value: value }),
    });
    btn.classList.add('flagged');
    btn.innerHTML = '&#9873; Flagged';
    const item = document.getElementById(itemId);
    if (item) item.classList.add('flagged');
  } catch {
    btn.textContent = 'Error';
  }
  btn.disabled = false;
}

// ── Utilities ──────────────────────────────────────────────────────────────────

function setGlobalStatus(msg, clearAfterMs) {
  statusEl.textContent = msg;
  statusEl.classList.remove('hidden');
  if (clearAfterMs) setTimeout(() => statusEl.classList.add('hidden'), clearAfterMs);
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
