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
    maxScore: 5,
    criteria: [
      { key: 'ich_tk_bullish',        name: 'Tenkan > Kijun (TK bullish)',  cat: 'trend' },
      { key: 'ich_recent_tk_cross',   name: 'TK vừa cắt lên (≤5 phiên) ⭐', cat: 'squeeze' },
      { key: 'ich_price_above_cloud', name: 'Giá trên Cloud',               cat: 'trend' },
      { key: 'ich_cloud_bullish',     name: 'Cloud bullish (A > B)',        cat: 'trend' },
      { key: 'ich_chikou_free',       name: 'Chikou thoát kháng cự',        cat: 'flow' },
    ],
  },
  combined: {
    name: 'Tổng hợp',
    dataDir: null,                 // multi-source; merged client-side
    maxScore: 4,                   // up to 4 strategies passed
    isCombined: true,
    sources: ['pre_breakout', 'golden_cross_long', 'golden_cross_short', 'ichimoku'],
    criteria: [],                  // built dynamically per source
  },
  analyzer: {
    name: 'Phân tích mã',
    dataDir: null,
    isAnalyzer: true,
    sources: ['pre_breakout', 'golden_cross_long', 'golden_cross_short', 'ichimoku'],
    criteria: [],
  },
};

// Short codes for strategy badges
const STRATEGY_BADGES = {
  pre_breakout:       { code: 'PB',  label: 'Pre-Breakout',  hint: 'Tín hiệu sắp break giá' },
  golden_cross_long:  { code: 'GCL', label: 'GC dài hạn',    hint: 'Golden Cross MA50×MA200' },
  golden_cross_short: { code: 'GCS', label: 'GC ngắn hạn',   hint: 'Golden Cross MA10×MA20' },
  ichimoku:           { code: 'ICH', label: 'Ichimoku',      hint: 'Tenkan/Kijun + Cloud' },
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
  filters: { exchange: '', rating: '', search: '', volMin: null, volMax: null, ich_special: '' },
  // ─── Combined mode ───
  combined: {
    enabledStrategies: { pre_breakout: true, golden_cross_long: true, golden_cross_short: true, ichimoku: true },
    logic: 'AND',                  // 'AND' or 'OR'
    sourceData: {},                // strategy → { signals, metadata }
  },
  // ─── Analyzer mode ───
  analyzer: {
    ticker: null,                  // currently analyzed ticker
    sourceData: {},                // shared with combined when both loaded
    universe: [],                  // list of all known tickers (for suggestions)
  },
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
  bindMobileDrawers();
  bindAnalyzerEvents();

  await loadLatestFirst();
  await loadDateIndex();
  renderDateOptions();
});

// ──────────── Mobile drawer handling ────────────
function bindMobileDrawers() {
  const filterBtn = document.getElementById('mobile-filter-btn');
  const filterCol = document.getElementById('col-filters');
  const detailCol = document.getElementById('col-detail');
  const backdrop  = document.getElementById('mobile-backdrop');

  if (!filterBtn || !backdrop) return;

  const closeDrawers = () => {
    filterCol?.classList.remove('mobile-open');
    detailCol?.classList.remove('mobile-open');
    backdrop.classList.remove('show');
  };

  filterBtn.addEventListener('click', () => {
    filterCol.classList.add('mobile-open');
    backdrop.classList.add('show');
  });

  backdrop.addEventListener('click', closeDrawers);

  // When row is clicked on mobile, open detail drawer
  // (works because openDetail() adds .mobile-open via this listener)
  document.addEventListener('detail-opened', () => {
    if (window.matchMedia('(max-width: 768px)').matches) {
      detailCol.classList.add('mobile-open');
      backdrop.classList.add('show');
    }
  });
}

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
  state.filters.ich_special = '';
  closeDetail();
  updateSortIndicators();

  const dashboard = document.getElementById('dashboard');
  const analyzerView = document.getElementById('analyzer-view');

  // Toggle layout mode
  if (strategy === 'analyzer') {
    dashboard.classList.add('analyzer-mode');
    if (analyzerView) analyzerView.style.display = '';
    // Load source data for analyzer (reuse if combined was loaded)
    if (Object.keys(state.combined.sourceData).length === 0) {
      await loadCombinedData(true);   // silent load (don't render combined table)
    }
    state.analyzer.sourceData = state.combined.sourceData;
    buildUniverseFromSourceData();
    // Focus search input
    setTimeout(() => document.getElementById('analyzer-search')?.focus(), 100);
    // Render last analyzed ticker, or empty
    if (state.analyzer.ticker) {
      analyzeTicker(state.analyzer.ticker);
    } else {
      showAnalyzerEmpty();
    }
    return;
  }
  // Leaving analyzer
  dashboard.classList.remove('analyzer-mode');
  if (analyzerView) analyzerView.style.display = 'none';

  // Show ichimoku-specific filter only on Ichimoku tab
  const ichFilter = document.getElementById('fg-ichimoku');
  if (ichFilter) {
    ichFilter.style.display = strategy === 'ichimoku' ? '' : 'none';
    ichFilter.querySelectorAll('.chip').forEach((c, i) => c.classList.toggle('active', i === 0));
  }

  // Show combined filter only on Combined tab
  const combFilter = document.getElementById('fg-combined');
  if (combFilter) {
    combFilter.style.display = strategy === 'combined' ? '' : 'none';
  }

  if (strategy === 'combined') {
    await loadCombinedData();
  } else {
    await loadLatestFirst();
    await loadDateIndex();
    renderDateOptions();
  }
}

// ──────────── COMBINED MODE: Load all 4 strategies & merge ────────────
async function loadCombinedData(silent = false) {
  const sources = STRATEGIES.combined.sources;
  state.combined.sourceData = {};

  // Load all source latest.json in parallel
  const loadOne = async (key) => {
    try {
      const dir = STRATEGIES[key].dataDir;
      const r = await fetch(`${dir}/latest.json?_=${Date.now()}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      return { key, signals: d.signals || [], metadata: d.metadata || {} };
    } catch (e) {
      console.warn(`Combined: failed to load ${key}:`, e.message);
      return { key, signals: [], metadata: {} };
    }
  };

  const results = await Promise.all(sources.map(loadOne));

  // Index signals by ticker per strategy
  const byTicker = {};      // ticker -> { strategies: Set, data: best signal record }
  let universeSize = 0;
  let demoFlag = false;
  let scanDate = null;

  for (const { key, signals, metadata } of results) {
    state.combined.sourceData[key] = { signals, metadata };
    if (metadata.universe_size && metadata.universe_size > universeSize) universeSize = metadata.universe_size;
    if (metadata.demo) demoFlag = true;
    if (metadata.scan_date) scanDate = metadata.scan_date;
    // Update count in filter UI
    const cntEl = document.getElementById(`cnt-${key}`);
    if (cntEl) cntEl.textContent = signals.length;

    for (const s of signals) {
      if (!byTicker[s.ticker]) {
        byTicker[s.ticker] = {
          ticker: s.ticker,
          strategies: new Set(),
          perStrategyScore: {},
          best: s,         // pick first; will replace with highest-scoring later
        };
      }
      byTicker[s.ticker].strategies.add(key);
      byTicker[s.ticker].perStrategyScore[key] = s.total_score;
      // Keep the signal from the strategy with highest score (for displaying base data)
      if (s.total_score > (byTicker[s.ticker].best.total_score || 0)) {
        byTicker[s.ticker].best = s;
      }
    }
  }

  // Flatten: each ticker becomes a "combined signal"
  state.raw = Object.values(byTicker).map(entry => ({
    ...entry.best,
    _strategies: Array.from(entry.strategies),
    _perStrategyScore: entry.perStrategyScore,
    _passCount: entry.strategies.size,
  }));

  // Update metadata
  state.currentDate = scanDate;
  state.latestDate = scanDate;
  if (!silent) {
    document.getElementById('stat-scanned').textContent = universeSize.toLocaleString();
    const demoBanner = document.getElementById('demo-banner');
    if (demoFlag) {
      demoBanner.style.display = 'block';
      document.getElementById('dashboard').classList.add('has-banner');
    } else {
      demoBanner.style.display = 'none';
      document.getElementById('dashboard').classList.remove('has-banner');
    }
    render();
  }
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
        // Update Ichimoku filter hint dynamically
        if (filter === 'ich_special') {
          const hint = document.getElementById('ich-filter-hint');
          if (hint) {
            const map = {
              '': 'Lọc tín hiệu Ichimoku theo loại',
              'recent_cross': 'Lọc mã có Tenkan vừa cắt lên Kijun (≤5 phiên)',
              'turnaround': 'Đảo chiều sớm: TK cross + đang break cloud + volume xác nhận',
            };
            hint.textContent = map[chip.dataset.value] || map[''];
          }
        }
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
    state.filters = { exchange: '', rating: '', search: '', volMin: null, volMax: null, ich_special: '' };
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

  // ─── Combined strategy filter binds ───
  document.querySelectorAll('.combined-strat-check').forEach(cb => {
    cb.addEventListener('change', () => {
      const key = cb.dataset.strategy;
      state.combined.enabledStrategies[key] = cb.checked;
      render();
    });
  });
  document.querySelectorAll('.combined-logic-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.combined-logic-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.combined.logic = btn.dataset.logic;
      const hint = document.getElementById('combined-hint');
      if (hint) {
        hint.textContent = btn.dataset.logic === 'AND'
          ? 'AND: mã thỏa MỌI chiến lược tick'
          : 'OR: mã thỏa BẤT KỲ chiến lược nào tick';
      }
      render();
    });
  });
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

  // Update table headers based on mode
  const criteriaLabel = document.getElementById('th-criteria-label');
  const scoreLabel = document.getElementById('th-score-label');
  if (criteriaLabel && scoreLabel) {
    if (activeStrategy === 'combined') {
      // Hide TIÊU CHÍ column in combined (badges live in MÃ cell)
      criteriaLabel.style.display = 'none';
      scoreLabel.innerHTML = 'PASS <span class="sort-ind"></span>';
      scoreLabel.dataset.sort = '_passCount';
    } else {
      criteriaLabel.style.display = '';
      criteriaLabel.textContent = 'TIÊU CHÍ';
      scoreLabel.innerHTML = 'ĐIỂM <span class="sort-ind"></span>';
      scoreLabel.dataset.sort = 'total_score';
    }
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

  // Ichimoku special filter: "Vừa cắt TK" / "Đảo chiều sớm"
  if (state.filters.ich_special === 'recent_cross') {
    arr = arr.filter(s => s.ich_recent_tk_cross === 1);
  } else if (state.filters.ich_special === 'turnaround') {
    arr = arr.filter(s => s.m_is_turnaround === true);
  }

  // ─── COMBINED MODE FILTER ───
  if (activeStrategy === 'combined') {
    const enabled = Object.entries(state.combined.enabledStrategies)
      .filter(([, on]) => on)
      .map(([k]) => k);

    if (enabled.length === 0) {
      arr = [];
    } else if (state.combined.logic === 'AND') {
      // Mã phải có trong MỌI strategy được tick
      arr = arr.filter(s => enabled.every(k => s._strategies?.includes(k)));
    } else {
      // OR: mã có trong BẤT KỲ strategy nào tick
      arr = arr.filter(s => enabled.some(k => s._strategies?.includes(k)));
    }
  }

  // Sort: default by total_score desc; for combined default by _passCount desc, then total_score
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
  } else if (activeStrategy === 'combined') {
    arr.sort((a, b) => {
      const dp = (b._passCount || 0) - (a._passCount || 0);
      if (dp !== 0) return dp;
      return (b.total_score || 0) - (a.total_score || 0);
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

  let ratingClass = '';
  if (s.rating === 'A+') ratingClass = 'aplus';
  else if (s.rating === 'A') ratingClass = 'a';
  else if (s.rating === 'B') ratingClass = 'b';
  else ratingClass = 'c';

  // Event flag
  const eventFlag = s.m_upcoming_event ? `<span class="event-flag" title="Sự kiện: ${s.m_upcoming_event.type} ${s.m_upcoming_event.ex_date}">⚑</span>` : '';

  // Fibo S/R cells
  const supports = s.m_supports || [];
  const resistances = s.m_resistances || [];
  const supCell = supports.length ? renderFibCell(supports[0], 'support') : '<span class="dim">—</span>';
  const resCell = resistances.length ? renderFibCell(resistances[0], 'resistance') : '<span class="dim">—</span>';

  const selectedClass = s.ticker === state.selectedTicker ? 'selected' : '';

  // ── Combined mode: badges INLINE trong cell MÃ ──
  if (activeStrategy === 'combined') {
    const passedStrats = s._strategies || [];
    const passCount = s._passCount || 0;
    const totalStrats = STRATEGIES.combined.sources.length;

    // Chỉ badge những strategy mã PASS (đỡ noise)
    const badgesInline = passedStrats.map(key => {
      const b = STRATEGY_BADGES[key];
      const shortCls = key === 'pre_breakout' ? 'pb'
                     : key === 'golden_cross_long' ? 'gcl'
                     : key === 'golden_cross_short' ? 'gcs' : 'ich';
      return `<span class="strat-badge strat-badge-${shortCls}" title="${b.label}: PASS">${b.code}</span>`;
    }).join('');

    const passCls = passCount === totalStrats ? 'full' : passCount >= 2 ? 'high' : 'low';

    return `<tr data-ticker="${s.ticker}" class="${selectedClass}">
      <td class="th-idx">${idx}</td>
      <td class="ticker-with-badges"><span class="ticker-cell">${s.ticker}</span>${eventFlag}<span class="ticker-badges">${badgesInline}</span></td>
      <td><span class="exchange-cell">${s.exchange}</span></td>
      <td class="num">${fmtPrice(s.close)}</td>
      <td class="num ${changeClass}">${sign}${change.toFixed(2)}%</td>
      <td class="num">${fmtVolume(s.volume)}</td>
      <td class="num">${fmtValue(s.close, s.volume)}</td>
      <td class="num">${(s.m_vol_ratio || 0).toFixed(2)}×</td>
      <td class="num">${(s.m_rsi14 || 0).toFixed(0)}</td>
      <td class="num">${supCell}</td>
      <td class="num">${resCell}</td>
      <td class="combined-criteria-cell" style="display:none;"></td>
      <td class="num"><span class="combined-pass ${passCls}">${passCount}/${totalStrats}</span></td>
      <td><span class="rating-tag ${ratingClass}">${s.rating}</span></td>
    </tr>`;
  }

  // ── Default (single-strategy) row ──
  let scoreClass = '';
  const ratio = s.total_score / currentMaxScore();
  if (ratio >= 0.8) scoreClass = 'high';
  else if (ratio >= 0.6) scoreClass = 'mid';

  const pills = currentCriteria().map(c => {
    const on = s[c.key] === 1;
    return `<span class="criteria-pill ${on ? 'on' : ''} cat-${c.cat}"></span>`;
  }).join('');

  const tkCrossFlag = (activeStrategy === 'ichimoku' && s.ich_recent_tk_cross === 1)
    ? `<span class="tk-cross-flag" title="Tenkan vừa cắt lên Kijun (${s.m_tk_cross_days_ago ?? '?'} phiên trước)">⭐</span>`
    : '';

  const turnaroundFlag = (activeStrategy === 'ichimoku' && s.m_is_turnaround === true)
    ? `<span class="tk-turnaround-flag" title="${(s.m_turnaround_reasons||[]).join(' · ')}">🎯 TURN</span>`
    : '';

  return `<tr data-ticker="${s.ticker}" class="${selectedClass}">
    <td class="th-idx">${idx}</td>
    <td><span class="ticker-cell">${s.ticker}</span>${tkCrossFlag}${turnaroundFlag}${eventFlag}</td>
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
  
  // Dispatch event for mobile drawer
  document.dispatchEvent(new CustomEvent('detail-opened', { detail: { ticker: s.ticker } }));

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

  // TK cross callout for Ichimoku
  let tkCrossCallout = '';
  if (activeStrategy === 'ichimoku' && s.ich_recent_tk_cross === 1) {
    const daysAgo = s.m_tk_cross_days_ago;
    const dayText = daysAgo === 0 ? 'hôm nay'
                  : daysAgo === 1 ? 'hôm qua'
                  : daysAgo != null ? `${daysAgo} phiên trước` : 'gần đây';
    tkCrossCallout = `
      <div class="tk-cross-callout">
        <div class="tk-cross-title">⭐ Tenkan vừa cắt lên Kijun</div>
        <div class="tk-cross-detail">
          Tenkan-sen (xanh) đã cắt lên Kijun-sen (đỏ) <strong>${dayText}</strong> — đây là tín hiệu mạnh nhất của Ichimoku.
          Entry sớm trước khi xu hướng lớn xuất hiện.
        </div>
        <div class="tk-cross-values">
          <span>Tenkan: <strong>${fmtPrice(s.m_tenkan)}</strong></span>
          <span>Kijun: <strong>${fmtPrice(s.m_kijun)}</strong></span>
          <span>Chênh lệch: <strong>+${(((s.m_tenkan - s.m_kijun) / s.m_kijun) * 100).toFixed(2)}%</strong></span>
        </div>
      </div>
    `;
  }

  // Turnaround callout — early reversal signal
  let turnaroundCallout = '';
  if (activeStrategy === 'ichimoku' && s.m_is_turnaround === true) {
    const reasons = s.m_turnaround_reasons || [];
    turnaroundCallout = `
      <div class="turnaround-callout">
        <div class="turnaround-title">🎯 Tín hiệu đảo chiều sớm</div>
        <div class="turnaround-detail">
          Đây là setup vàng của Ichimoku: TK cross + giá đang break cloud + volume xác nhận.
          Vùng entry sớm với R:R thường rất tốt vì stop loss gần (đáy gần nhất) và target xa (kháng cự cloud trên / Fibo).
        </div>
        <ul class="turnaround-reasons">
          ${reasons.map(r => `<li>✓ ${r}</li>`).join('')}
        </ul>
      </div>
    `;
  }

  document.getElementById('detail-body').innerHTML = `
    ${entryHint}
    ${turnaroundCallout}
    ${tkCrossCallout}
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

    ${renderIchimokuSection(s)}

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
  // Close mobile drawer if open
  document.getElementById('col-detail')?.classList.remove('mobile-open');
  document.getElementById('mobile-backdrop')?.classList.remove('show');
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

// ──────────── Ichimoku section in detail ────────────
function renderIchimokuSection(s) {
  // Only render if we're in Ichimoku strategy
  if (activeStrategy !== 'ichimoku') return '';
  if (s.m_tenkan == null || s.m_kijun == null) return '';

  const tkBullish = s.m_tenkan > s.m_kijun;
  const priceAboveCloud = s.close > s.m_cloud_top;
  const cloudBullish = s.m_senkou_a > s.m_senkou_b;

  return `
    <div class="dt-section">
      <div class="dt-section-title">Ichimoku Components</div>
      <table class="ich-table">
        <tr>
          <td class="ich-label">Tenkan-sen <span class="ich-color-dot" style="background: var(--up)"></span></td>
          <td class="ich-val">${fmtPrice(s.m_tenkan)}</td>
        </tr>
        <tr>
          <td class="ich-label">Kijun-sen <span class="ich-color-dot" style="background: var(--down)"></span></td>
          <td class="ich-val">${fmtPrice(s.m_kijun)}</td>
        </tr>
        <tr>
          <td class="ich-label">TK Cross</td>
          <td class="ich-val ${tkBullish ? 'up' : 'down'}">
            ${tkBullish ? '▲ Tenkan > Kijun' : '▼ Tenkan < Kijun'}
            <span class="ich-sub">+${(((s.m_tenkan - s.m_kijun) / s.m_kijun) * 100).toFixed(2)}%</span>
          </td>
        </tr>
        <tr class="ich-sep">
          <td class="ich-label">Cloud trên (Span A)</td>
          <td class="ich-val">${fmtPrice(s.m_senkou_a)}</td>
        </tr>
        <tr>
          <td class="ich-label">Cloud dưới (Span B)</td>
          <td class="ich-val">${fmtPrice(s.m_senkou_b)}</td>
        </tr>
        <tr>
          <td class="ich-label">Giá vs Cloud</td>
          <td class="ich-val ${priceAboveCloud ? 'up' : 'down'}">
            ${priceAboveCloud ? '▲ Trên Cloud' : '▼ Dưới Cloud'}
            <span class="ich-sub">${(s.m_cloud_distance_pct || 0).toFixed(2)}%</span>
          </td>
        </tr>
        <tr>
          <td class="ich-label">Trạng thái Cloud</td>
          <td class="ich-val ${cloudBullish ? 'up' : 'down'}">
            ${cloudBullish ? '▲ Bullish (A > B)' : '▼ Bearish (A < B)'}
          </td>
        </tr>
      </table>
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

// ═══════════════════════════════════════════════════════════════
// TAB 6: TICKER ANALYZER — multi-strategy analysis for any ticker
// ═══════════════════════════════════════════════════════════════

const STRATEGY_INFO = {
  pre_breakout: {
    name: 'Pre-Breakout',
    icon: '🚀',
    desc: 'Phát hiện mã sắp break giá (10 tiêu chí)',
    badge: 'PB',
    color: 'pb',
    maxScore: 10,
  },
  golden_cross_long: {
    name: 'GC dài hạn (MA50×MA200)',
    icon: '📈',
    desc: 'Position trade dài hạn, đảo chiều trend',
    badge: 'GCL',
    color: 'gcl',
    maxScore: 5,
  },
  golden_cross_short: {
    name: 'GC ngắn hạn (MA10×MA20)',
    icon: '⚡',
    desc: 'Swing trade 2-4 tuần',
    badge: 'GCS',
    color: 'gcs',
    maxScore: 5,
  },
  ichimoku: {
    name: 'Ichimoku',
    icon: '☁',
    desc: 'Tenkan/Kijun + Cloud, xác nhận trend',
    badge: 'ICH',
    color: 'ich',
    maxScore: 5,
  },
};

// Build universe of all known tickers (from loaded source data)
function buildUniverseFromSourceData() {
  const tickers = new Set();
  for (const key of Object.keys(state.analyzer.sourceData)) {
    for (const s of (state.analyzer.sourceData[key]?.signals || [])) {
      tickers.add(s.ticker);
    }
  }
  // Also add hardcoded popular tickers in case they're not in any signal
  const popular = ['FPT','VNM','VCB','VIC','VHM','HPG','MWG','MSN','GAS','POW','BID','CTG','TCB','VPB','MBB','ACB','VRE','SAB','PNJ','SSI','VND','HCM','SHB','STB','TPB','HDB','OCB','EIB','LPB','VIB','GVR','PLX','BCM','REE','BMP','DGC','DHG','HSG','NKG','NLG','PDR','KDH','DXG','VCG','CEO','IDC','PVS','PVD','VEA','FRT','PNS','DGW','SAM','TLG','DBC','NTL','HAH','PHR','PVB','SIP','TNG','SHS','HUT','VNN','BMI'];
  popular.forEach(t => tickers.add(t));
  state.analyzer.universe = Array.from(tickers).sort();
}

// Search universe for matches
function searchTickerUniverse(query) {
  if (!query) return [];
  const q = query.toUpperCase();
  const matches = state.analyzer.universe.filter(t => t.startsWith(q));
  // Add tickers containing query (lower priority)
  if (matches.length < 8) {
    const contains = state.analyzer.universe.filter(t => !t.startsWith(q) && t.includes(q));
    matches.push(...contains);
  }
  return matches.slice(0, 8);
}

// Show suggestion dropdown
function renderAnalyzerSuggestions(query) {
  const box = document.getElementById('analyzer-suggestions');
  if (!box) return;
  const matches = searchTickerUniverse(query);
  if (!matches.length || !query) {
    box.classList.remove('show');
    box.innerHTML = '';
    return;
  }
  box.innerHTML = matches.map(t => {
    // Count strategies this ticker appears in
    let count = 0;
    for (const key of Object.keys(state.analyzer.sourceData)) {
      if ((state.analyzer.sourceData[key]?.signals || []).some(s => s.ticker === t)) count++;
    }
    const meta = count > 0 ? `${count}/4 chiến lược pass` : 'Không có tín hiệu';
    return `<div class="analyzer-suggestion" data-ticker="${t}">
      <span class="analyzer-suggestion-ticker">${t}</span>
      <span class="analyzer-suggestion-meta">${meta}</span>
    </div>`;
  }).join('');
  box.classList.add('show');
  // Bind clicks
  box.querySelectorAll('.analyzer-suggestion').forEach(el => {
    el.addEventListener('click', () => {
      const t = el.dataset.ticker;
      document.getElementById('analyzer-search').value = t;
      box.classList.remove('show');
      if (activeStrategy !== 'analyzer') {
        switchStrategy('analyzer');
      } else {
        analyzeTicker(t);
      }
    });
  });
}

// ── Recommendation engine ──
function buildRecommendation(passCount, hasAplus, primarySignal) {
  let cls, stars, title, desc, position;
  const rsi = primarySignal?.m_rsi14 || 50;
  const supports = primarySignal?.m_supports || [];
  const nearestSup = supports[0];

  // Modifiers
  let warnings = [];
  if (rsi > 75) warnings.push(`RSI ${rsi.toFixed(0)} — quá mua, cẩn trọng vào lệnh full size hoặc đợi pullback`);
  else if (rsi > 70) warnings.push(`RSI ${rsi.toFixed(0)} — gần quá mua, vào lệnh từ tốn`);
  if (rsi < 30) warnings.push(`RSI ${rsi.toFixed(0)} — quá bán, có thể có rebound nhưng risk cao`);
  if (nearestSup && nearestSup.distance_pct > 8) {
    warnings.push(`Cách hỗ trợ gần nhất ${nearestSup.distance_pct.toFixed(1)}% — R:R kém, đợi pullback về hỗ trợ`);
  }
  if (primarySignal?.m_upcoming_event) {
    const ev = primarySignal.m_upcoming_event;
    warnings.push(`Sự kiện sắp tới: ${ev.type} ${ev.ratio || ''} (ex-date ${ev.ex_date}) — giá có thể adjust`);
  }

  // Decision matrix
  if (passCount === 4 && hasAplus >= 2) {
    cls = 'rec-strong-buy';
    stars = '⭐⭐⭐⭐';
    title = 'MUA MẠNH';
    desc = 'Mã pass đồng thời cả 4 chiến lược với nhiều A+. Đây là tín hiệu hiếm và rất đáng tin cậy. Có thể tham gia vị thế lớn nếu phù hợp khẩu vị rủi ro.';
    position = '8-12% NAV';
  } else if (passCount === 4) {
    cls = 'rec-strong-buy';
    stars = '⭐⭐⭐⭐';
    title = 'MUA MẠNH';
    desc = 'Mã pass đồng thời cả 4 chiến lược. Đây là tín hiệu rất mạnh, đa nguồn xác nhận.';
    position = '6-10% NAV';
  } else if (passCount === 3 && hasAplus >= 1) {
    cls = 'rec-buy';
    stars = '⭐⭐⭐';
    title = 'MUA';
    desc = `Mã pass 3/4 chiến lược với ít nhất 1 A+. Tín hiệu mạnh, có thể tham gia với vị thế trung bình.`;
    position = '5-8% NAV';
  } else if (passCount === 3) {
    cls = 'rec-buy';
    stars = '⭐⭐⭐';
    title = 'MUA';
    desc = 'Mã pass 3/4 chiến lược. Tín hiệu khá tốt, đa số chiến lược xác nhận.';
    position = '4-6% NAV';
  } else if (passCount === 2) {
    cls = 'rec-watch';
    stars = '⭐⭐';
    title = 'THEO DÕI';
    desc = 'Mã pass 2/4 chiến lược. Tín hiệu trung bình — nên theo dõi thêm, chờ confirm từ chiến lược khác hoặc đợi pullback.';
    position = '3-5% NAV (nếu vào lệnh, ở mức thận trọng)';
  } else if (passCount === 1) {
    cls = 'rec-weak';
    stars = '⭐';
    title = 'YẾU';
    desc = 'Chỉ pass 1/4 chiến lược. Tín hiệu yếu, không khuyến nghị mở vị thế mới.';
    position = 'Không khuyến nghị';
  } else {
    cls = 'rec-avoid';
    stars = '—';
    title = 'KHÔNG CÓ TÍN HIỆU';
    desc = 'Mã không xuất hiện trong bất kỳ chiến lược nào. Có thể đang trong giai đoạn không có cấu hình kỹ thuật rõ ràng, hoặc thanh khoản thấp.';
    position = 'Tránh';
  }

  // Apply warning modifiers
  if (rsi > 75 && (passCount === 4 || passCount === 3)) {
    desc += ' Tuy nhiên RSI rất cao — đợi pullback hoặc vào với size nhỏ hơn.';
    position = position.replace(/(\d+)-(\d+)% NAV/, (_, a, b) => `${Math.max(1, +a - 2)}-${Math.max(2, +b - 3)}% NAV`);
  }

  return { cls, stars, title, desc, position, warnings };
}

// Compute entry levels for analyzer (similar to existing detail panel)
function computeAnalyzerLevels(s) {
  if (!s) return null;
  const supports = s.m_supports || [];
  const resistances = s.m_resistances || [];
  if (!supports.length) return null;

  // Prefer Golden Ratio support for entry
  const golden = supports.find(x => x.is_golden);
  const nearestSup = supports[0];
  const nearestRes = resistances[0];

  const entry = golden ? golden.price : nearestSup.price;
  // Stop = deepest support, but must be < entry. Fallback: 7% below entry.
  let stop;
  if (supports.length > 1) {
    const deepest = supports[supports.length - 1].price;
    stop = deepest < entry * 0.99 ? deepest : entry * 0.93;
  } else {
    stop = entry * 0.93;
  }
  const target = nearestRes && nearestRes.price > entry * 1.01 ? nearestRes.price : entry * 1.08;
  const riskPct = ((entry - stop) / entry * 100);
  const gainPct = ((target - entry) / entry * 100);
  const rr = riskPct > 0.1 ? gainPct / riskPct : 0;

  return { entry, stop, target, riskPct, gainPct, rr };
}

// ── Main analyzer entry point ──
function analyzeTicker(ticker) {
  ticker = ticker.toUpperCase().trim();
  if (!ticker) {
    showAnalyzerEmpty();
    return;
  }
  state.analyzer.ticker = ticker;
  document.getElementById('analyzer-empty').style.display = 'none';
  const content = document.getElementById('analyzer-content');
  content.style.display = 'block';

  // Gather signals from each strategy
  const perStrategy = {};
  let primarySignal = null;        // most "complete" signal (most fields)
  let passCount = 0;
  let hasAplus = 0;

  for (const key of STRATEGIES.analyzer.sources) {
    const signals = state.analyzer.sourceData[key]?.signals || [];
    const found = signals.find(s => s.ticker === ticker);
    perStrategy[key] = found || null;
    if (found) {
      passCount++;
      if (found.rating === 'A+') hasAplus++;
      // Pick signal with most metric fields as primary
      if (!primarySignal || Object.keys(found).length > Object.keys(primarySignal).length) {
        primarySignal = found;
      }
    }
  }

  // If ticker not found anywhere
  if (passCount === 0) {
    content.innerHTML = renderAnalyzerNotFound(ticker);
    return;
  }

  // Build recommendation
  const rec = buildRecommendation(passCount, hasAplus, primarySignal);
  const levels = computeAnalyzerLevels(primarySignal);

  content.innerHTML = renderAnalyzer(ticker, primarySignal, perStrategy, passCount, rec, levels);
}

function showAnalyzerEmpty() {
  document.getElementById('analyzer-empty').style.display = '';
  document.getElementById('analyzer-content').style.display = 'none';
}

function renderAnalyzerNotFound(ticker) {
  return `<div class="analyzer-not-found">
    <div class="analyzer-not-found-icon">❓</div>
    <div class="analyzer-not-found-title">Không tìm thấy <strong>${ticker}</strong> trong bất kỳ chiến lược nào</div>
    <div class="analyzer-not-found-desc">
      Mã này có thể:<br>
      • Không nằm trong top 623 mã liquid được scan<br>
      • Đang không có cấu hình kỹ thuật đáp ứng tiêu chí nào<br>
      • Mã chưa tồn tại hoặc gõ sai
    </div>
  </div>`;
}

function renderAnalyzer(ticker, signal, perStrategy, passCount, rec, levels) {
  const change = signal.m_change_5d_pct || 0;
  const changeCls = change > 0 ? 'up' : change < 0 ? 'down' : '';
  const sign = change > 0 ? '+' : '';

  const passClass = passCount === 4 ? 'full' : passCount === 3 ? 'high' : '';

  // Strategy breakdown cards
  const cards = STRATEGIES.analyzer.sources.map(key => {
    const info = STRATEGY_INFO[key];
    const s = perStrategy[key];
    const passed = !!s;
    const cls = passed ? 'pass' : '';
    const status = passed ? '✓ PASS' : '✗ KHÔNG ĐẠT';
    let body;
    if (passed) {
      // Show passed criteria
      const criteriaKeys = Object.keys(s).filter(k => k.startsWith('c') && /^c\d+/.test(k));
      const criteriaTags = criteriaKeys
        .filter(k => s[k] === 1)
        .map(k => `<span class="criteria-tag passed">${k.toUpperCase().replace(/_/g, ' ')}</span>`)
        .join('');
      body = `
        <div class="strategy-card-body">
          ${s.rating ? `<strong style="color:var(--text)">Hạng: ${s.rating}</strong> · ` : ''}
          <span class="strategy-card-score">Điểm: <span class="score-num">${s.total_score || 0}</span>/${info.maxScore}</span>
        </div>
        ${criteriaTags ? `<div class="strategy-card-criteria">${criteriaTags}</div>` : ''}
      `;
    } else {
      let reason = '';
      if (key === 'golden_cross_long') reason = 'MA50 chưa cắt lên MA200 trong 5 phiên gần đây';
      else if (key === 'golden_cross_short') reason = 'MA10 chưa cắt lên MA20 trong 5 phiên gần đây';
      else if (key === 'ichimoku') reason = 'Không đủ điều kiện Cloud + TK cross';
      else reason = 'Không pass đủ tiêu chí của chiến lược';
      body = `<div class="strategy-card-body">${reason}</div>`;
    }
    return `<div class="strategy-card ${cls}">
      <div class="strategy-card-head">
        <div class="strategy-card-name"><span>${info.icon}</span> ${info.name}</div>
        <div class="strategy-card-status">${status}</div>
      </div>
      ${body}
    </div>`;
  }).join('');

  // Entry levels
  let levelsHtml = '';
  if (levels && passCount >= 2) {
    levelsHtml = `<div class="rec-levels">
      <div class="rec-level rec-level-entry">
        <div class="rec-level-label">VÀO LỆNH</div>
        <div class="rec-level-value">${levels.entry.toFixed(2).replace('.',',')}</div>
        <div class="rec-level-sub">${levels.entry < signal.close ? '↓ Đợi pullback' : '≈ Giá hiện tại'}</div>
      </div>
      <div class="rec-level rec-level-stop">
        <div class="rec-level-label">CẮT LỖ</div>
        <div class="rec-level-value">${levels.stop.toFixed(2).replace('.',',')}</div>
        <div class="rec-level-sub">−${levels.riskPct.toFixed(1)}%</div>
      </div>
      <div class="rec-level rec-level-target">
        <div class="rec-level-label">CHỐT LÃI</div>
        <div class="rec-level-value">${levels.target.toFixed(2).replace('.',',')}</div>
        <div class="rec-level-sub">+${levels.gainPct.toFixed(1)}%</div>
      </div>
      <div class="rec-level rec-level-rr">
        <div class="rec-level-label">R:R</div>
        <div class="rec-level-value">1 : ${levels.rr.toFixed(1)}</div>
        <div class="rec-level-sub">${levels.rr >= 2 ? 'Tốt' : levels.rr >= 1.5 ? 'Khá' : 'Trung bình'}</div>
      </div>
    </div>`;
  }

  // Warnings
  let warningsHtml = '';
  if (rec.warnings.length) {
    warningsHtml = `<div class="warning-list">
      <div class="analyzer-section-title"><span class="section-icon">⚠️</span> Cảnh báo</div>
      <ul>${rec.warnings.map(w => `<li>${w}</li>`).join('')}</ul>
    </div>`;
  }

  // Fibonacci
  let fiboHtml = '';
  const fiboSwing = signal.m_fibo_swing;
  if (fiboSwing) {
    const supports = signal.m_supports || [];
    const resistances = signal.m_resistances || [];
    const supRows = supports.map(s => {
      const goldenTag = s.is_golden ? ` <span class="fibo-golden-tag" title="Mức 61.8% — vùng pullback lý tưởng">GOLDEN</span>` : '';
      return `<div class="fibo-row">
        <span class="fibo-pct">${s.label}${goldenTag}</span>
        <span class="fibo-price">${s.price.toFixed(2).replace('.',',')}</span>
        <span class="fibo-dist down">${s.distance_pct > 0 ? '-' : ''}${Math.abs(s.distance_pct).toFixed(2)}%</span>
      </div>`;
    }).join('');
    const resRows = resistances.map(r => `<div class="fibo-row">
      <span class="fibo-pct">${r.label}</span>
      <span class="fibo-price">${r.price.toFixed(2).replace('.',',')}</span>
      <span class="fibo-dist up">+${r.distance_pct.toFixed(2)}%</span>
    </div>`).join('');

    fiboHtml = `<div class="analyzer-fibo">
      <div class="analyzer-section-title"><span class="section-icon">📈</span> Fibonacci Retracement</div>
      <div class="fibo-swing-info">${fiboSwing.direction === 'up' ? '↑ Uptrend' : '↓ Downtrend'} · Swing ${fiboSwing.low.toFixed(2).replace('.',',')} → ${fiboSwing.high.toFixed(2).replace('.',',')}</div>
      ${resRows ? `<div style="margin-top:8px"><strong style="color:var(--text-dim);font-size:11px">KHÁNG CỰ</strong>${resRows}</div>` : ''}
      <div class="fibo-row fibo-current" style="margin-top:6px;padding:8px;background:var(--bg-elev-2);border-radius:3px">
        <span class="fibo-pct" style="color:var(--text)">GIÁ HIỆN TẠI</span>
        <span class="fibo-price" style="color:var(--text);font-weight:700">${signal.close.toFixed(2).replace('.',',')}</span>
        <span></span>
      </div>
      ${supRows ? `<div style="margin-top:6px"><strong style="color:var(--text-dim);font-size:11px">HỖ TRỢ</strong>${supRows}</div>` : ''}
    </div>`;
  }

  return `
    <div class="analyzer-header">
      <div class="analyzer-h-left">
        <div class="analyzer-h-ticker">${ticker}</div>
        <div class="analyzer-h-meta">${signal.exchange || ''} · Cập nhật ${state.currentDate || '—'}</div>
      </div>
      <div>
        <span class="analyzer-h-price">${signal.close.toFixed(2).replace('.',',')}</span>
        <span class="analyzer-h-change ${changeCls}">${sign}${change.toFixed(2)}%</span>
      </div>
    </div>

    <div class="recommendation ${rec.cls}">
      <div class="rec-stars">${rec.stars}</div>
      <div class="rec-body">
        <div class="rec-title">
          ${rec.title}
          <span class="rec-pass-badge ${passClass}">Pass ${passCount}/4 chiến lược</span>
        </div>
        <div class="rec-desc">${rec.desc}</div>
        <div class="rec-position">
          <span class="rec-position-label">VỊ THẾ ĐỀ XUẤT:</span>
          <span class="rec-position-pct">${rec.position}</span>
        </div>
      </div>
      ${levelsHtml}
    </div>

    ${warningsHtml}

    <div class="analyzer-section-title"><span class="section-icon">🎯</span> Chi tiết từng chiến lược</div>
    <div class="strategy-cards">${cards}</div>

    ${fiboHtml}

    <div style="text-align:center;margin-top:24px">
      <a class="btn-primary" href="https://www.tradingview.com/chart/?symbol=${signal.exchange || 'HOSE'}:${ticker}" target="_blank" rel="noopener">Mở TradingView ↗</a>
    </div>
  `;
}

// Bind analyzer events
function bindAnalyzerEvents() {
  const input = document.getElementById('analyzer-search');
  const box = document.getElementById('analyzer-suggestions');
  if (!input) return;

  input.addEventListener('input', () => {
    renderAnalyzerSuggestions(input.value);
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const val = input.value.toUpperCase().trim();
      if (val) {
        box.classList.remove('show');
        if (activeStrategy !== 'analyzer') {
          switchStrategy('analyzer').then(() => analyzeTicker(val));
        } else {
          analyzeTicker(val);
        }
      }
    } else if (e.key === 'Escape') {
      box.classList.remove('show');
      input.blur();
    }
  });

  input.addEventListener('focus', () => {
    if (input.value) renderAnalyzerSuggestions(input.value);
  });

  // Click outside to close suggestions
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.topbar-analyzer')) {
      box.classList.remove('show');
    }
  });

  // Quick buttons
  document.querySelectorAll('.analyzer-quick-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const t = btn.dataset.ticker;
      input.value = t;
      analyzeTicker(t);
    });
  });
}
