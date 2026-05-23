// ════════════════════════════════════════════════════════════
// VN Stock Scanner — 3-Column Dashboard
// Single-screen, no scroll, click row → detail panel right
// ════════════════════════════════════════════════════════════

// ──────────── STRATEGIES CONFIG ────────────
const STRATEGIES = {
  pre_breakout: {
    name: 'Pre-Breakout',
    dataDir: './data',
    maxScore: 10,
    criteria: [
      { key: 'c1_atr_squeeze',  name: 'ATR Squeeze',         cat: 'squeeze' },
      { key: 'c2_bb_squeeze',   name: 'Bollinger Squeeze',   cat: 'squeeze' },
      { key: 'c3_near_high20',  name: 'Gần đỉnh 20 phiên',   cat: 'squeeze' },
      { key: 'c4_stealth_accum',name: 'Stealth Accumulation',cat: 'flow' },
      { key: 'c5_vol_surge',    name: 'Volume Surge',        cat: 'flow' },
      { key: 'c6_upper_close',  name: 'Đóng cửa nửa trên',   cat: 'flow' },
      { key: 'c9_pocket_pivot', name: 'Pocket Pivot',        cat: 'flow' },
      { key: 'c7_ma_align',     name: 'MA10 > MA20',         cat: 'trend' },
      { key: 'c8_rsi_zone',     name: 'RSI 50-65',           cat: 'trend' },
      { key: 'c10_no_gap_down', name: 'Không gap down',      cat: 'trend' },
    ],
  },
  golden_cross_long: {
    name: 'Golden Cross dài hạn',
    dataDir: './data/golden_cross_long',
    maxScore: 5,
    criteria: [
      { key: 'gc_recent_cross',    name: 'MA50 vừa cắt lên MA200', cat: 'squeeze' },
      { key: 'gc_price_above_fast',name: 'Giá > MA50',             cat: 'trend' },
      { key: 'gc_ma_stacking',     name: 'MA10 > MA20 > MA50',     cat: 'trend' },
      { key: 'gc_slow_rising',     name: 'MA200 hướng lên',        cat: 'trend' },
      { key: 'gc_volume_confirm',  name: 'Volume xác nhận cross',  cat: 'flow' },
    ],
  },
  golden_cross_short: {
    name: 'Golden Cross ngắn hạn',
    dataDir: './data/golden_cross_short',
    maxScore: 5,
    criteria: [
      { key: 'gc_recent_cross',    name: 'MA10 vừa cắt lên MA20',  cat: 'squeeze' },
      { key: 'gc_price_above_fast',name: 'Giá > MA10',             cat: 'trend' },
      { key: 'gc_ma_stacking',     name: 'MA5 > MA10 > MA20',      cat: 'trend' },
      { key: 'gc_slow_rising',     name: 'MA20 hướng lên',         cat: 'trend' },
      { key: 'gc_volume_confirm',  name: 'Volume xác nhận cross',  cat: 'flow' },
    ],
  },
  ichimoku: {
    name: 'Ichimoku',
    dataDir: './data/ichimoku',
    maxScore: 4,
    criteria: [
      { key: 'ich_tk_bullish',        name: 'Tenkan > Kijun',         cat: 'trend' },
      { key: 'ich_price_above_cloud', name: 'Giá trên Cloud',         cat: 'trend' },
      { key: 'ich_cloud_bullish',     name: 'Cloud bullish (A>B)',    cat: 'trend' },
      { key: 'ich_chikou_free',       name: 'Chikou thoát kháng cự',  cat: 'flow' },
    ],
  },
};

let activeStrategy = 'pre_breakout';
function currentConfig()   { return STRATEGIES[activeStrategy]; }
function currentCriteria() { return currentConfig().criteria; }
function currentMaxScore() { return currentConfig().maxScore; }
function currentDataDir()  { return currentConfig().dataDir; }

const state = {
  raw: [],
  filtered: [],
  currentDate: null,
  latestDate: null,
  availableDates: [],
  selectedTicker: null,
  sort: { column: null, direction: null },
  filters: { exchange: '', rating: '', search: '', volMin: null, volMax: null },
};

// ──────────── Init ────────────
window.addEventListener('DOMContentLoaded', async () => {
  startClock();
  bindStrategyTabs();
  bindFilters();
  bindSort();
  bindKeyboard();
  bindHelp();
  bindCollapseFilters();
  bindDetailClose();

  await loadLatestFirst();
  await loadDateIndex();
  renderDateOptions();
});

// ──────────── Clock & Market State ────────────
function startClock() {
  const tick = () => {
    const now = new Date();
    const hhmm = now.toLocaleTimeString('en-GB', {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      timeZone: 'Asia/Ho_Chi_Minh',
    });
    document.getElementById('clock').textContent = hhmm + ' ICT';

    // Market state: 9:00-15:00 ICT Mon-Fri
    const vnTime = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Ho_Chi_Minh' }));
    const day = vnTime.getDay();
    const hr  = vnTime.getHours();
    const min = vnTime.getMinutes();
    const totalMin = hr * 60 + min;
    const isWeekday = day >= 1 && day <= 5;
    const isOpen = isWeekday && totalMin >= 9*60 && totalMin < 15*60;
    const stateEl = document.querySelector('.market-state');
    if (isOpen) {
      stateEl.classList.add('open');
      document.getElementById('market-text').textContent = 'MARKET OPEN';
    } else {
      stateEl.classList.remove('open');
      document.getElementById('market-text').textContent = 'MARKET CLOSED';
    }
  };
  tick();
  setInterval(tick, 1000);
}

// ──────────── Strategy tabs ────────────
function bindStrategyTabs() {
  document.querySelectorAll('.strat-tab').forEach(tab => {
    tab.addEventListener('click', async () => {
      const strategy = tab.dataset.strategy;
      if (strategy === activeStrategy) return;
      await switchStrategy(strategy);
    });
  });
}

async function switchStrategy(strategy) {
  if (!STRATEGIES[strategy]) return;
  activeStrategy = strategy;
  document.querySelectorAll('.strat-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.strategy === strategy);
  });
  state.sort = { column: null, direction: null };
  state.selectedTicker = null;
  closeDetail();
  updateSortIndicators();
  await loadLatestFirst();
  await loadDateIndex();
  renderDateOptions();
}

// ──────────── Load data ────────────
async function loadLatestFirst() {
  try {
    const url = `${currentDataDir()}/latest.json?_=${Date.now()}`;
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    state.raw = data.signals || [];
    state.currentDate = data.metadata?.scan_date || null;
    state.latestDate = state.currentDate;

    document.getElementById('stat-scanned').textContent =
      (data.metadata?.universe_size || 0).toLocaleString();
    const demoBanner = document.getElementById('demo-banner');
    if (data.metadata?.demo) {
      demoBanner.style.display = 'block';
      document.getElementById('dashboard').classList.add('has-banner');
    } else {
      demoBanner.style.display = 'none';
      document.getElementById('dashboard').classList.remove('has-banner');
    }

    render();
  } catch (e) {
    console.error('Load latest failed:', e);
    document.getElementById('signal-rows').innerHTML =
      `<tr><td colspan="14" class="empty">Không tải được dữ liệu: ${e.message}</td></tr>`;
  }
}

async function loadDateIndex() {
  try {
    const url = `${currentDataDir()}/archive/index.json?_=${Date.now()}`;
    const r = await fetch(url);
    if (!r.ok) { state.availableDates = []; return; }
    const idx = await r.json();
    state.availableDates = idx.dates || [];
    state.latestDate = idx.latest || state.currentDate;
  } catch (e) {
    state.availableDates = [];
  }
}

async function loadDateData(date) {
  if (date === state.latestDate) {
    return loadLatestFirst();
  }
  try {
    const url = `${currentDataDir()}/archive/${date}.json?_=${Date.now()}`;
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    state.raw = data.signals || [];
    state.currentDate = data.metadata?.scan_date || date;
    document.getElementById('stat-scanned').textContent =
      (data.metadata?.universe_size || 0).toLocaleString();
    render();
  } catch (e) {
    console.error('Load date failed:', e);
  }
}

function renderDateOptions() {
  const sel = document.getElementById('date-select');
  if (!state.availableDates.length) {
    sel.innerHTML = `<option value="${state.currentDate}">${formatDateLong(state.currentDate)}</option>`;
    return;
  }
  sel.innerHTML = state.availableDates.map(d => {
    const isLatest = d === state.latestDate;
    return `<option value="${d}" ${d === state.currentDate ? 'selected' : ''}>
      ${formatDateLong(d)}${isLatest ? '  (mới nhất)' : ''}
    </option>`;
  }).join('');

  sel.onchange = () => loadDateData(sel.value);
  document.getElementById('date-prev').onclick = () => {
    const i = state.availableDates.indexOf(state.currentDate);
    if (i < state.availableDates.length - 1) loadDateData(state.availableDates[i+1]);
  };
  document.getElementById('date-next').onclick = () => {
    const i = state.availableDates.indexOf(state.currentDate);
    if (i > 0) loadDateData(state.availableDates[i-1]);
  };
  document.getElementById('date-latest').onclick = () => loadDateData(state.latestDate);
}

// ──────────── Filters ────────────
function bindFilters() {
  document.querySelectorAll('.chip-row').forEach(group => {
    const filter = group.dataset.filter;
    group.querySelectorAll('.chip').forEach(chip => {
      chip.addEventListener('click', () => {
        group.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        state.filters[filter] = chip.dataset.value;
        render();
      });
    });
  });

  document.getElementById('search').addEventListener('input', e => {
    state.filters.search = e.target.value.trim().toUpperCase();
    render();
  });

  document.getElementById('vol-min').addEventListener('input', e => {
    state.filters.volMin = parseVolumeInput(e.target.value);
    e.target.classList.toggle('active', !!e.target.value);
    render();
  });
  document.getElementById('vol-max').addEventListener('input', e => {
    state.filters.volMax = parseVolumeInput(e.target.value);
    e.target.classList.toggle('active', !!e.target.value);
    render();
  });
  document.getElementById('vol-clear').addEventListener('click', () => {
    document.getElementById('vol-min').value = '';
    document.getElementById('vol-max').value = '';
    document.getElementById('vol-min').classList.remove('active');
    document.getElementById('vol-max').classList.remove('active');
    state.filters.volMin = null;
    state.filters.volMax = null;
    render();
  });

  document.getElementById('reset-filters').addEventListener('click', () => {
    state.filters = { exchange: '', rating: '', search: '', volMin: null, volMax: null };
    document.querySelectorAll('.chip-row').forEach(group => {
      group.querySelectorAll('.chip').forEach((c, i) => c.classList.toggle('active', i === 0));
    });
    document.getElementById('search').value = '';
    document.getElementById('vol-min').value = '';
    document.getElementById('vol-max').value = '';
    document.getElementById('vol-min').classList.remove('active');
    document.getElementById('vol-max').classList.remove('active');
    render();
  });

  document.getElementById('export-csv').addEventListener('click', exportCSV);
}

function parseVolumeInput(s) {
  if (!s) return null;
  s = s.trim().toUpperCase().replace(',', '.');
  let mult = 1;
  if (s.endsWith('K')) { mult = 1e3; s = s.slice(0, -1); }
  else if (s.endsWith('M')) { mult = 1e6; s = s.slice(0, -1); }
  else if (s.endsWith('B')) { mult = 1e9; s = s.slice(0, -1); }
  const n = parseFloat(s);
  return isNaN(n) ? null : n * mult;
}

// ──────────── Sort ────────────
function bindSort() {
  document.querySelectorAll('th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.sort;
      if (state.sort.column === col) {
        if (state.sort.direction === 'desc') state.sort.direction = 'asc';
        else if (state.sort.direction === 'asc') { state.sort.column = null; state.sort.direction = null; }
      } else {
        state.sort.column = col;
        state.sort.direction = 'desc';
      }
      updateSortIndicators();
      render();
    });
  });
}

function updateSortIndicators() {
  document.querySelectorAll('th.sortable').forEach(th => {
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.sort === state.sort.column) {
      th.classList.add(state.sort.direction === 'asc' ? 'sort-asc' : 'sort-desc');
    }
  });
}

// ──────────── Keyboard shortcuts ────────────
function bindKeyboard() {
  document.addEventListener('keydown', e => {
    // Don't trigger when typing in input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') {
      if (e.key === 'Escape') e.target.blur();
      return;
    }

    if (e.key === '/') {
      e.preventDefault();
      document.getElementById('search').focus();
    } else if (e.key === 'Escape') {
      closeDetail();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      moveSelection(1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      moveSelection(-1);
    }
  });
}

function moveSelection(delta) {
  if (!state.filtered.length) return;
  let idx = state.filtered.findIndex(s => s.ticker === state.selectedTicker);
  if (idx === -1) idx = 0;
  else idx = Math.max(0, Math.min(state.filtered.length - 1, idx + delta));
  const target = state.filtered[idx];
  if (target) openDetail(target);
}

// ──────────── Help modal ────────────
function bindHelp() {
  const modal = document.getElementById('help-modal');
  document.getElementById('help-btn').addEventListener('click', () => modal.style.display = 'flex');
  document.getElementById('help-close').addEventListener('click', () => modal.style.display = 'none');
  modal.addEventListener('click', e => {
    if (e.target === modal) modal.style.display = 'none';
  });
}

// ──────────── Collapse filters column ────────────
function bindCollapseFilters() {
  document.getElementById('collapse-filters').addEventListener('click', () => {
    document.getElementById('dashboard').classList.toggle('filters-collapsed');
  });
}

// ──────────── Render table ────────────
function render() {
  state.filtered = applyFilters();
  document.getElementById('result-count').textContent = state.filtered.length;
  document.getElementById('stat-total').textContent = state.raw.length;
  document.getElementById('stat-aplus').textContent =
    state.raw.filter(s => s.rating === 'A+').length;

  // Update date in topbar
  const statDate = document.getElementById('stat-date');
  if (state.currentDate) {
    const [y, m, day] = state.currentDate.split('-');
    const isLatest = state.currentDate === state.latestDate;
    statDate.textContent = isLatest ? `· LIVE ${day}/${m}` : `· ${day}/${m}`;
    statDate.style.color = isLatest ? 'var(--up)' : 'var(--text-mute)';
  }

  // Event warning count
  const eventCount = state.raw.filter(s => s.m_upcoming_event).length;
  const eventWarn = document.getElementById('event-warn');
  if (eventCount > 0) {
    eventWarn.style.display = '';
    document.getElementById('event-count').textContent = eventCount;
  } else {
    eventWarn.style.display = 'none';
  }

  renderRows();
}

function applyFilters() {
  let arr = state.raw.slice();
  if (state.filters.exchange)
    arr = arr.filter(s => s.exchange === state.filters.exchange);
  if (state.filters.rating)
    arr = arr.filter(s => s.rating === state.filters.rating);
  if (state.filters.search)
    arr = arr.filter(s => s.ticker.includes(state.filters.search));
  if (state.filters.volMin != null)
    arr = arr.filter(s => s.volume >= state.filters.volMin);
  if (state.filters.volMax != null)
    arr = arr.filter(s => s.volume <= state.filters.volMax);

  // Sort: default by total_score desc; custom sort if state.sort.column
  if (state.sort.column) {
    arr.sort((a, b) => {
      let av, bv;
      if (state.sort.column === '_gtgd') {
        av = (a.close || 0) * (a.volume || 0);
        bv = (b.close || 0) * (b.volume || 0);
      } else {
        av = a[state.sort.column] ?? 0;
        bv = b[state.sort.column] ?? 0;
      }
      const cmp = (av < bv) ? -1 : (av > bv) ? 1 : 0;
      return state.sort.direction === 'asc' ? cmp : -cmp;
    });
  } else {
    arr.sort((a, b) => (b.total_score || 0) - (a.total_score || 0));
  }
  return arr;
}

function renderRows() {
  const tbody = document.getElementById('signal-rows');
  if (!state.filtered.length) {
    tbody.innerHTML = `<tr><td colspan="14" class="empty">Không có tín hiệu khớp bộ lọc</td></tr>`;
    return;
  }
  tbody.innerHTML = state.filtered.map((s, i) => renderRow(s, i + 1)).join('');

  // Bind row clicks
  tbody.querySelectorAll('tr[data-ticker]').forEach(tr => {
    tr.addEventListener('click', () => {
      const ticker = tr.dataset.ticker;
      const sig = state.filtered.find(x => x.ticker === ticker);
      if (sig) openDetail(sig);
    });
  });
}

function renderRow(s, idx) {
  const change = s.m_change_5d_pct || 0;
  const changeClass = change > 0 ? 'up' : change < 0 ? 'down' : 'flat';
  const sign = change > 0 ? '+' : '';

  let scoreClass = '';
  const ratio = s.total_score / currentMaxScore();
  if (ratio >= 0.8) scoreClass = 'high';
  else if (ratio >= 0.6) scoreClass = 'mid';

  let ratingClass = '';
  if (s.rating === 'A+') ratingClass = 'aplus';
  else if (s.rating === 'A') ratingClass = 'a';
  else if (s.rating === 'B') ratingClass = 'b';
  else ratingClass = 'c';

  // Criteria pills
  const pills = currentCriteria().map(c => {
    const on = s[c.key] === 1;
    return `<span class="criteria-pill ${on ? 'on' : ''} cat-${c.cat}"></span>`;
  }).join('');

  // Event flag
  const eventFlag = s.m_upcoming_event ? `<span class="event-flag" title="Sự kiện: ${s.m_upcoming_event.type} ${s.m_upcoming_event.ex_date}">⚑</span>` : '';

  // Fibo S/R cells
  const supports = s.m_supports || [];
  const resistances = s.m_resistances || [];
  const supCell = supports.length ? renderFibCell(supports[0], 'support') : '<span class="dim">—</span>';
  const resCell = resistances.length ? renderFibCell(resistances[0], 'resistance') : '<span class="dim">—</span>';

  const selectedClass = s.ticker === state.selectedTicker ? 'selected' : '';

  return `<tr data-ticker="${s.ticker}" class="${selectedClass}">
    <td class="th-idx">${idx}</td>
    <td><span class="ticker-cell">${s.ticker}</span>${eventFlag}</td>
    <td><span class="exchange-cell">${s.exchange}</span></td>
    <td class="num">${fmtPrice(s.close)}</td>
    <td class="num ${changeClass}">${sign}${change.toFixed(2)}%</td>
    <td class="num">${fmtVolume(s.volume)}</td>
    <td class="num">${fmtValue(s.close, s.volume)}</td>
    <td class="num">${(s.m_vol_ratio || 0).toFixed(2)}×</td>
    <td class="num">${(s.m_rsi14 || 0).toFixed(0)}</td>
    <td class="num">${supCell}</td>
    <td class="num">${resCell}</td>
    <td><div class="criteria-pills">${pills}</div></td>
    <td class="num score-cell ${scoreClass}">${s.total_score}/${currentMaxScore()}</td>
    <td><span class="rating-tag ${ratingClass}">${s.rating}</span></td>
  </tr>`;
}

function renderFibCell(level, kind) {
  if (!level) return '<span class="dim">—</span>';
  const isGolden = level.is_golden;
  const sign = kind === 'support' ? '-' : '+';
  return `<span class="fib-cell fib-${kind} ${isGolden ? 'golden' : ''}" title="Fibo ${level.label} · ${level.price}">
    <span class="fib-price">${fmtPrice(level.price)}</span>
    <span class="fib-label">${level.label}${isGolden ? ' ⭐' : ''}</span>
    <span class="fib-dist">${sign}${level.distance_pct}%</span>
  </span>`;
}

// ──────────── Detail panel (col 3) ────────────
function openDetail(s) {
  state.selectedTicker = s.ticker;

  // Mark selected row
  document.querySelectorAll('tr[data-ticker]').forEach(tr => {
    tr.classList.toggle('selected', tr.dataset.ticker === s.ticker);
  });

  // Scroll selected row into view
  const row = document.querySelector(`tr[data-ticker="${s.ticker}"]`);
  if (row) row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });

  // Hide empty state, show panel
  document.getElementById('detail-empty').style.display = 'none';
  document.getElementById('detail-panel').style.display = 'flex';

  // Header
  document.getElementById('detail-ticker').textContent = s.ticker;
  document.getElementById('detail-meta').textContent =
    `${s.exchange} · ${formatDateLong(s.date)} · ${s.rating}`;

  // TradingView link
  const tvSymbol = s.exchange === 'UPCOM' ? `UPCOM:${s.ticker}` : `${s.exchange}:${s.ticker}`;
  document.getElementById('tv-link').href = `https://www.tradingview.com/chart/?symbol=${tvSymbol}`;

  // Body content
  const passed = currentCriteria().filter(c => s[c.key] === 1).length;
  const total = currentCriteria().length;

  const entryHint = computeEntryHint(s);
  const eventCallout = s.m_upcoming_event
    ? `<div class="event-callout">⚑ Sự kiện sắp đến: <strong>${s.m_upcoming_event.type}</strong> · ngày ${s.m_upcoming_event.ex_date}${s.m_upcoming_event.ratio ? ' · tỷ lệ ' + s.m_upcoming_event.ratio : ''}. Giá có thể điều chỉnh.</div>`
    : '';

  document.getElementById('detail-body').innerHTML = `
    ${entryHint}
    ${eventCallout}

    <div class="dt-section">
      <div class="dt-section-title">Thông tin giá</div>
      <div class="metrics-grid">
        <div class="metric">
          <div class="metric-lbl">GIÁ ĐÓNG</div>
          <div class="metric-val">${fmtPrice(s.close)}</div>
        </div>
        <div class="metric">
          <div class="metric-lbl">±5 PHIÊN</div>
          <div class="metric-val ${(s.m_change_5d_pct || 0) > 0 ? 'up' : 'down'}">${(s.m_change_5d_pct || 0) > 0 ? '+' : ''}${(s.m_change_5d_pct || 0).toFixed(2)}%</div>
        </div>
        <div class="metric">
          <div class="metric-lbl">KHỐI LƯỢNG</div>
          <div class="metric-val">${fmtVolume(s.volume)}</div>
        </div>
        <div class="metric">
          <div class="metric-lbl">GIÁ TRỊ GD</div>
          <div class="metric-val">${fmtValue(s.close, s.volume)}</div>
        </div>
        <div class="metric">
          <div class="metric-lbl">VOL / MA20</div>
          <div class="metric-val">${(s.m_vol_ratio || 0).toFixed(2)}×</div>
        </div>
        <div class="metric">
          <div class="metric-lbl">RSI (14)</div>
          <div class="metric-val">${(s.m_rsi14 || 0).toFixed(1)}</div>
        </div>
      </div>
    </div>

    ${renderFiboSection(s)}

    <div class="dt-section">
      <div class="dt-section-title">Tiêu chí đạt được (${passed}/${total})</div>
      <ul class="crit-list">
        ${currentCriteria().map(c => {
          const on = s[c.key] === 1;
          return `<li class="${on ? 'on' : 'off'}">
            <span class="crit-check ${on ? 'on' : 'off'}">${on ? '✓' : '·'}</span>
            ${c.name}
          </li>`;
        }).join('')}
      </ul>
    </div>
  `;
}

function closeDetail() {
  state.selectedTicker = null;
  document.querySelectorAll('tr[data-ticker]').forEach(tr => tr.classList.remove('selected'));
  document.getElementById('detail-empty').style.display = 'flex';
  document.getElementById('detail-panel').style.display = 'none';
}

function bindDetailClose() {
  document.getElementById('detail-close').addEventListener('click', closeDetail);
}

// ──────────── Entry Hint ────────────
function computeEntryHint(s) {
  const supports = s.m_supports || [];
  const resistances = s.m_resistances || [];
  const rsi = s.m_rsi14 || 50;
  const close = s.close;

  const goldenSupport = supports.find(x => x.is_golden);
  const nearestSupport = supports[0];
  const nearestResistance = resistances[0];

  let title = 'Theo dõi';
  let detail = '';
  let entry = null, stop = null, target = null;
  let color = 'var(--system)';
  let borderColor = 'var(--system)';

  if (s.rating === 'A+' && goldenSupport && goldenSupport.distance_pct < 4 && rsi < 65) {
    title = 'Vùng vào lệnh đẹp';
    detail = 'Tín hiệu mạnh + giá gần mức Golden Ratio 61.8% — vùng pullback lý tưởng để mua.';
    entry = goldenSupport.price;
    stop = supports.find(x => x.label === '78.6%')?.price || supports[supports.length - 1]?.price;
    target = nearestResistance?.price;
    color = 'var(--up)';
    borderColor = 'var(--up)';
  } else if ((s.rating === 'A+' || s.rating === 'A') && nearestSupport &&
             nearestSupport.distance_pct < 3 && rsi >= 45 && rsi <= 65) {
    title = 'Có thể vào lệnh';
    detail = `Giá gần hỗ trợ ${nearestSupport.label} — entry hợp lý nếu volume xác nhận.`;
    entry = nearestSupport.price;
    stop = supports[1]?.price || (close * 0.95);
    target = nearestResistance?.price;
    color = 'var(--system-active)';
    borderColor = 'var(--system-active)';
  } else if (rsi > 70 || (nearestSupport && nearestSupport.distance_pct > 8)) {
    title = 'Đã chạy — đợi pullback';
    detail = rsi > 70
      ? `RSI ${rsi.toFixed(0)} đã quá mua. Đợi RSI <65 hoặc pullback về hỗ trợ.`
      : `Giá cách hỗ trợ ${nearestSupport.distance_pct.toFixed(1)}%. R:R kém, đợi pullback.`;
    color = 'var(--down)';
    borderColor = 'var(--down)';
  } else if (s.rating === 'C' || s.total_score < currentMaxScore() * 0.5) {
    title = 'Tín hiệu yếu — không đề xuất';
    detail = 'Số tiêu chí đạt thấp. Không nên vào lệnh ở mức này.';
    color = 'var(--text-mute)';
    borderColor = 'var(--text-mute)';
  } else {
    title = 'Theo dõi';
    detail = `RSI ${rsi.toFixed(0)} · ${s.rating}. Tín hiệu hợp lệ nhưng entry không lý tưởng.`;
    color = 'var(--system-active)';
    borderColor = 'var(--system-active)';
  }

  let levelsHtml = '';
  if (entry != null) {
    const rrRatio = (target && stop) ? ((target - entry) / (entry - stop)).toFixed(1) : null;
    levelsHtml = `
      <div class="entry-levels">
        <div class="entry-level entry-level-buy">
          <div class="entry-level-label">VÀO LỆNH</div>
          <div class="entry-level-price">${fmtPrice(entry)}</div>
        </div>
        ${stop ? `
        <div class="entry-level entry-level-stop">
          <div class="entry-level-label">CẮT LỖ</div>
          <div class="entry-level-price">${fmtPrice(stop)}</div>
          <div class="entry-level-sub">-${(((entry - stop) / entry) * 100).toFixed(1)}%</div>
        </div>` : ''}
        ${target ? `
        <div class="entry-level entry-level-target">
          <div class="entry-level-label">CHỐT LÃI</div>
          <div class="entry-level-price">${fmtPrice(target)}</div>
          <div class="entry-level-sub">+${(((target - entry) / entry) * 100).toFixed(1)}%</div>
        </div>` : ''}
        ${rrRatio ? `
        <div class="entry-level entry-level-rr">
          <div class="entry-level-label">R:R</div>
          <div class="entry-level-price">1:${rrRatio}</div>
        </div>` : ''}
      </div>
    `;
  }

  return `
    <div class="entry-hint" style="border-left-color: ${borderColor};">
      <div class="entry-hint-head">
        <span class="entry-hint-signal" style="color: ${color};">${title}</span>
        <span class="entry-hint-tag">GỢI Ý</span>
      </div>
      <div class="entry-hint-detail">${detail}</div>
      ${levelsHtml}
    </div>
  `;
}

// ──────────── Fibonacci section in detail ────────────
function renderFiboSection(s) {
  const swing = s.m_fibo_swing;
  const supports = s.m_supports || [];
  const resistances = s.m_resistances || [];
  if (!swing || (supports.length === 0 && resistances.length === 0)) return '';

  const currentPrice = s.close;
  const dirLabel = swing.direction === 'up' ? '▲ Uptrend' : '▼ Downtrend';
  const dirColor = swing.direction === 'up' ? 'var(--up)' : 'var(--down)';
  const rangePct = ((swing.range / swing.low) * 100).toFixed(1);

  const allLevels = [
    ...resistances.map(r => ({ ...r, kind: 'resistance' })),
    { price: currentPrice, kind: 'current', label: 'GIÁ HIỆN TẠI' },
    ...supports.map(s => ({ ...s, kind: 'support' })),
  ];

  return `
    <div class="dt-section">
      <div class="dt-section-title">Fibonacci Retracement</div>
      <div class="fibo-swing-info">
        <div><span class="fibo-direction" style="color: ${dirColor}">${dirLabel}</span></div>
        <div>Swing: <span style="color: var(--down)">${fmtPrice(swing.low)}</span> ${swing.low_date} → <span style="color: var(--up)">${fmtPrice(swing.high)}</span> ${swing.high_date}</div>
        <div>Biên độ: <span style="color: var(--system-active)">${rangePct}%</span></div>
      </div>
      <div class="fibo-ladder">
        ${allLevels.map(lv => {
          if (lv.kind === 'current') {
            return `<div class="fibo-row fibo-current">
              <span class="fibo-label">${lv.label}</span>
              <span class="fibo-price">${fmtPrice(lv.price)}</span>
              <span class="fibo-dist">←</span>
            </div>`;
          }
          const goldenCls = lv.is_golden ? 'golden' : '';
          const kindCls = lv.kind === 'support' ? 'fibo-support' : 'fibo-resistance';
          const sign = lv.kind === 'support' ? '-' : '+';
          return `<div class="fibo-row ${kindCls} ${goldenCls}">
            <span class="fibo-label">
              ${lv.kind === 'support' ? 'Hỗ trợ' : 'Kháng cự'} ${lv.label}
              ${lv.is_golden ? '<span class="fibo-golden-tag">GOLDEN</span>' : ''}
            </span>
            <span class="fibo-price">${fmtPrice(lv.price)}</span>
            <span class="fibo-dist">${sign}${lv.distance_pct}%</span>
          </div>`;
        }).join('')}
      </div>
    </div>
  `;
}

// ──────────── Export CSV ────────────
function exportCSV() {
  if (!state.filtered.length) return;
  const headers = ['Ticker', 'Sàn', 'Giá', '±5D%', 'KLGD', 'GTGD (tỷ)', 'Vol×', 'RSI', 'Điểm', 'Hạng'];
  const rows = state.filtered.map(s => [
    s.ticker, s.exchange, s.close, s.m_change_5d_pct,
    s.volume, ((s.close * s.volume * 1000) / 1e9).toFixed(2),
    s.m_vol_ratio, s.m_rsi14, s.total_score, s.rating,
  ]);
  const csv = [headers, ...rows].map(r => r.join(',')).join('\n');
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `signals_${state.currentDate}_${activeStrategy}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ──────────── Format helpers ────────────
function fmtPrice(p) {
  if (p == null) return '—';
  return p.toFixed(2).replace('.', ',');
}
function fmtVolume(v) {
  if (!v) return '—';
  if (v >= 1e6) return (v / 1e6).toFixed(2) + 'M';
  if (v >= 1e3) return (v / 1e3).toFixed(1) + 'K';
  return v.toString();
}
function fmtValue(price, volume) {
  if (!price || !volume) return '—';
  const v = price * volume * 1000;  // VND × number of shares
  if (v >= 1e12) return (v / 1e12).toFixed(2) + ' nghìn tỷ';
  if (v >= 1e9)  return (v / 1e9).toFixed(2) + ' tỷ';
  if (v >= 1e6)  return (v / 1e6).toFixed(1) + 'tr';
  return v.toFixed(0);
}
function formatDateLong(d) {
  if (!d) return '—';
  const date = new Date(d);
  const days = ['Chủ Nhật', 'Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy'];
  const day = days[date.getDay()];
  const dd = String(date.getDate()).padStart(2, '0');
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const yyyy = date.getFullYear();
  return `${day} · ${dd}/${mm}/${yyyy}`;
}
