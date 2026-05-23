// ────────────────────────────────────────────────────────────
// VN Multi-Strategy Scanner — Dashboard logic
// ────────────────────────────────────────────────────────────

// ============================
//  STRATEGIES CONFIG
// ============================
const STRATEGIES = {
  pre_breakout: {
    name: 'Pre-Breakout',
    dataDir: './data',
    maxScore: 10,
    criteria: [
      { key: 'c1_atr_squeeze',  name: 'ATR Squeeze',         group: 1 },
      { key: 'c2_bb_squeeze',   name: 'Bollinger Squeeze',   group: 1 },
      { key: 'c3_near_high20',  name: 'Gần đỉnh 20 phiên',   group: 1 },
      { key: 'c4_stealth_accum',name: 'Stealth Accumulation',group: 2 },
      { key: 'c5_vol_surge',    name: 'Volume Surge',        group: 2 },
      { key: 'c6_upper_close',  name: 'Đóng cửa nửa trên',   group: 2 },
      { key: 'c9_pocket_pivot', name: 'Pocket Pivot',        group: 2 },
      { key: 'c7_ma_align',     name: 'MA10 > MA20',         group: 3 },
      { key: 'c8_rsi_zone',     name: 'RSI 50-65',           group: 3 },
      { key: 'c10_no_gap_down', name: 'Không gap down',      group: 3 },
    ],
  },
  golden_cross_long: {
    name: 'Golden Cross dài hạn',
    dataDir: './data/golden_cross_long',
    maxScore: 5,
    criteria: [
      { key: 'gc_recent_cross',    name: 'MA50 vừa cắt lên MA200',  group: 1 },
      { key: 'gc_price_above_fast',name: 'Giá > MA50',              group: 3 },
      { key: 'gc_ma_stacking',     name: 'MA10 > MA20 > MA50',      group: 3 },
      { key: 'gc_slow_rising',     name: 'MA200 đang hướng lên',    group: 3 },
      { key: 'gc_volume_confirm',  name: 'Volume xác nhận cross',   group: 2 },
    ],
  },
  golden_cross_short: {
    name: 'Golden Cross ngắn hạn',
    dataDir: './data/golden_cross_short',
    maxScore: 5,
    criteria: [
      { key: 'gc_recent_cross',    name: 'MA10 vừa cắt lên MA20',   group: 1 },
      { key: 'gc_price_above_fast',name: 'Giá > MA10',              group: 3 },
      { key: 'gc_ma_stacking',     name: 'MA5 > MA10 > MA20',       group: 3 },
      { key: 'gc_slow_rising',     name: 'MA20 đang hướng lên',     group: 3 },
      { key: 'gc_volume_confirm',  name: 'Volume xác nhận cross',   group: 2 },
    ],
  },
  ichimoku: {
    name: 'Ichimoku',
    dataDir: './data/ichimoku',
    maxScore: 4,
    criteria: [
      { key: 'ich_tk_bullish',        name: 'Tenkan > Kijun',        group: 3 },
      { key: 'ich_price_above_cloud', name: 'Giá trên Cloud (Kumo)', group: 3 },
      { key: 'ich_cloud_bullish',     name: 'Cloud bullish (A > B)', group: 3 },
      { key: 'ich_chikou_free',       name: 'Chikou thoát kháng cự', group: 2 },
    ],
  },
};

let activeStrategy = 'pre_breakout';

function currentConfig() { return STRATEGIES[activeStrategy]; }
function currentDataDir() { return currentConfig().dataDir; }
function currentArchiveDir() { return `${currentDataDir()}/archive`; }
function currentCriteria() { return currentConfig().criteria; }
function currentMaxScore() { return currentConfig().maxScore; }

// Legacy aliases (for backward compatibility in code below)
const DATA_DIR = './data';  // overridden dynamically per strategy
const ARCHIVE_DIR = './data/archive';
const CRITERIA = STRATEGIES.pre_breakout.criteria;  // default; render() uses currentCriteria()

const EVENT_TYPE_LABELS = {
  cash_dividend: 'Cổ tức tiền',
  stock_dividend: 'Cổ tức cổ phiếu',
  split: 'Chia tách',
  rights_issue: 'Phát hành quyền',
  unknown: 'Sự kiện',
};

let state = {
  raw: [],
  filtered: [],
  filters: { exchange: '', rating: '', volMin: null, volMax: null, search: '' },
  sort: { column: null, direction: null },
  availableDates: [],
  latestDate: null,
  currentDate: null,
  currentData: null,
};

// ──────────── Init ────────────
async function init() {
  updateClock();
  setInterval(updateClock, 1000);
  bindFilters();
  bindDatePicker();
  bindSortHandlers();
  bindStrategyTabs();
  // Load latest.json FIRST to know the actual latest date
  await loadLatestFirst();
  // Then load archive index for the date picker
  await loadDateIndex();
  renderDateOptions();
  updateDateNavButtons();
}

// ──────────── Sort handlers ────────────
function bindSortHandlers() {
  document.querySelectorAll('th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.sort;
      cycleSort(col);
    });
  });
}

function cycleSort(column) {
  if (state.sort.column !== column) {
    // Click new column → start with descending (more intuitive for numbers)
    state.sort = { column, direction: 'desc' };
  } else if (state.sort.direction === 'desc') {
    state.sort.direction = 'asc';
  } else if (state.sort.direction === 'asc') {
    state.sort = { column: null, direction: null };  // back to default
  }
  updateSortIndicators();
  render();
}

function updateSortIndicators() {
  document.querySelectorAll('th.sortable').forEach(th => {
    th.classList.remove('active', 'asc', 'desc');
    if (th.dataset.sort === state.sort.column) {
      th.classList.add('active', state.sort.direction);
    }
  });
}

// ──────────── Strategy tabs ────────────
function bindStrategyTabs() {
  // Support both .lean-tab (new) and .strategy-tab (legacy)
  document.querySelectorAll('.lean-tab, .strategy-tab').forEach(tab => {
    tab.addEventListener('click', async () => {
      const strategy = tab.dataset.strategy;
      if (strategy === activeStrategy) return;
      await switchStrategy(strategy);
    });
  });

  // Hero toggle (collapse/expand intro)
  const heroToggle = document.getElementById('hero-toggle');
  const heroSection = document.getElementById('hero-section');
  if (heroToggle && heroSection) {
    heroToggle.addEventListener('click', () => {
      const isHidden = heroSection.style.display === 'none';
      heroSection.style.display = isHidden ? 'block' : 'none';
      heroToggle.textContent = isHidden ? '× Đóng' : 'ℹ Giới thiệu';
    });
  }
}

async function switchStrategy(strategy) {
  if (!STRATEGIES[strategy]) return;
  activeStrategy = strategy;

  // Update tab UI (both lean-tab and strategy-tab)
  document.querySelectorAll('.lean-tab, .strategy-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.strategy === strategy);
  });

  // Reset sort and filters when switching strategies (criteria differ)
  state.sort = { column: null, direction: null };
  updateSortIndicators();

  // Reload data for the new strategy
  await loadLatestFirst();
  await loadDateIndex();
  renderDateOptions();
  updateDateNavButtons();
}

// ──────────── Load latest.json first ────────────
async function loadLatestFirst() {
  setStatus('connecting', 'LOADING');
  try {
    const res = await fetch(`${currentDataDir()}/latest.json?_=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.currentData = data;
    state.raw = (data.signals || []).sort((a, b) => b.total_score - a.total_score);

    // Determine the actual latest date from the data, not from index.json
    const firstSignal = state.raw[0];
    if (firstSignal && firstSignal.date) {
      // Strip time component if present
      state.latestDate = firstSignal.date.split('T')[0];
    } else if (data.generated_at) {
      state.latestDate = data.generated_at.split('T')[0];
    }
    state.currentDate = state.latestDate;

    // Show demo banner if data is marked as demo
    const demoBanner = document.getElementById('demo-banner');
    if (data.metadata?.demo === true) {
      demoBanner.style.display = 'flex';
    } else {
      demoBanner.style.display = 'none';
    }

    document.getElementById('last-scan-time').textContent =
      data.generated_at ? formatTime(new Date(data.generated_at)) : '—';
    document.getElementById('stat-scanned').textContent =
      (data.metadata?.total_scanned || state.raw.length).toLocaleString('vi-VN');

    setStatus('live', 'LIVE');
    render();
  } catch (err) {
    console.error(err);
    setStatus('error', 'OFFLINE');
    renderEmpty(`Không tải được dữ liệu mới nhất.\n${err.message}`);
  }
}

// ──────────── Date index ────────────
async function loadDateIndex() {
  try {
    const res = await fetch(`${currentArchiveDir()}/index.json?_=${Date.now()}`);
    if (res.ok) {
      const idx = await res.json();
      state.availableDates = idx.dates || [];
      // Add latestDate if not in list (in case archive index is outdated)
      if (state.latestDate && !state.availableDates.includes(state.latestDate)) {
        state.availableDates = [state.latestDate, ...state.availableDates];
      }
    } else {
      // No archive index — only latest available
      state.availableDates = state.latestDate ? [state.latestDate] : [];
    }
  } catch (err) {
    console.warn('No archive index found');
    state.availableDates = state.latestDate ? [state.latestDate] : [];
  }
}

function renderDateOptions() {
  const sel = document.getElementById('date-select');
  if (state.availableDates.length === 0) {
    sel.innerHTML = '<option value="">Phiên gần nhất</option>';
    sel.disabled = true;
    document.getElementById('date-prev').disabled = true;
    document.getElementById('date-next').disabled = true;
    return;
  }
  sel.innerHTML = state.availableDates.map(d => {
    const label = formatDateLabel(d);
    return `<option value="${d}">${label}</option>`;
  }).join('');
  sel.disabled = false;
}

function formatDateLabel(isoDate) {
  const d = new Date(isoDate + 'T00:00:00');
  const dayNames = ['Chủ Nhật', 'Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy'];
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  return `${dayNames[d.getDay()]} · ${dd}/${mm}/${d.getFullYear()}`;
}

// ──────────── Data loading ────────────
async function loadDataForDate(dateStr) {
  // Normalize date: strip time component if present
  if (dateStr) dateStr = dateStr.split('T')[0];

  setStatus('connecting', 'LOADING');
  try {
    let url;
    if (!dateStr || dateStr === state.latestDate) {
      url = `${currentDataDir()}/latest.json?_=${Date.now()}`;
    } else {
      url = `${currentArchiveDir()}/${dateStr}.json?_=${Date.now()}`;
    }
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.currentDate = dateStr || state.latestDate;
    state.currentData = data;
    state.raw = (data.signals || []).sort((a, b) => b.total_score - a.total_score);

    // Show demo banner if data is marked as demo
    const demoBanner = document.getElementById('demo-banner');
    if (data.metadata?.demo === true) {
      demoBanner.style.display = 'flex';
    } else {
      demoBanner.style.display = 'none';
    }

    document.getElementById('last-scan-time').textContent =
      data.generated_at ? formatTime(new Date(data.generated_at)) : '—';
    document.getElementById('stat-scanned').textContent =
      (data.metadata?.total_scanned || state.raw.length).toLocaleString('vi-VN');

    const sel = document.getElementById('date-select');
    if (state.currentDate && sel.value !== state.currentDate) {
      sel.value = state.currentDate;
    }
    updateDateNavButtons();
    setStatus('live', state.currentDate === state.latestDate ? 'LIVE' : 'ARCHIVE');
    render();
  } catch (err) {
    console.error(err);
    setStatus('error', 'OFFLINE');
    renderEmpty(`Không tải được dữ liệu cho ${dateStr || 'phiên gần nhất'}.\n${err.message}`);
  }
}

function bindDatePicker() {
  document.getElementById('date-select').addEventListener('change', e => {
    loadDataForDate(e.target.value);
  });
  document.getElementById('date-prev').addEventListener('click', () => {
    const idx = state.availableDates.indexOf(state.currentDate);
    if (idx >= 0 && idx < state.availableDates.length - 1) {
      loadDataForDate(state.availableDates[idx + 1]);
    }
  });
  document.getElementById('date-next').addEventListener('click', () => {
    const idx = state.availableDates.indexOf(state.currentDate);
    if (idx > 0) {
      loadDataForDate(state.availableDates[idx - 1]);
    }
  });
  document.getElementById('date-latest').addEventListener('click', () => {
    loadDataForDate(state.latestDate);
  });
}

function updateDateNavButtons() {
  const idx = state.availableDates.indexOf(state.currentDate);
  const prevBtn = document.getElementById('date-prev');
  const nextBtn = document.getElementById('date-next');
  const latestBtn = document.getElementById('date-latest');
  if (state.availableDates.length === 0) return;
  prevBtn.disabled = idx >= state.availableDates.length - 1;
  nextBtn.disabled = idx <= 0;
  if (state.currentDate === state.latestDate) {
    latestBtn.classList.add('hidden');
  } else {
    latestBtn.classList.remove('hidden');
  }
}

// ──────────── Filters ────────────
function bindFilters() {
  document.querySelectorAll('.chip-group').forEach(group => {
    const filterName = group.dataset.filter;
    group.addEventListener('click', e => {
      if (!e.target.classList.contains('chip')) return;
      group.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
      e.target.classList.add('active');
      state.filters[filterName] = e.target.dataset.value;
      render();
    });
  });

  document.getElementById('search').addEventListener('input', e => {
    state.filters.search = e.target.value.trim().toUpperCase();
    render();
  });

  // Volume range inputs
  const volMinInput = document.getElementById('vol-min');
  const volMaxInput = document.getElementById('vol-max');
  const volClear = document.getElementById('vol-clear');

  function updateVolFilter() {
    state.filters.volMin = parseVolumeInput(volMinInput.value);
    state.filters.volMax = parseVolumeInput(volMaxInput.value);
    volMinInput.classList.toggle('active', state.filters.volMin != null);
    volMaxInput.classList.toggle('active', state.filters.volMax != null);
    render();
  }

  volMinInput.addEventListener('input', updateVolFilter);
  volMaxInput.addEventListener('input', updateVolFilter);
  volClear.addEventListener('click', () => {
    volMinInput.value = '';
    volMaxInput.value = '';
    updateVolFilter();
  });

  document.getElementById('export-csv').addEventListener('click', exportCSV);
}

// Parse "500K", "1M", "1.5M", "100000" → number
function parseVolumeInput(str) {
  if (!str) return null;
  str = String(str).trim().toUpperCase().replace(/[,\s]/g, '');
  if (!str) return null;
  const match = str.match(/^([0-9.]+)\s*([KMB]?)$/);
  if (!match) return null;
  let num = parseFloat(match[1]);
  if (isNaN(num)) return null;
  const suffix = match[2];
  if (suffix === 'K') num *= 1_000;
  else if (suffix === 'M') num *= 1_000_000;
  else if (suffix === 'B') num *= 1_000_000_000;
  return num;
}

function applyFilters() {
  const { exchange, rating, volMin, volMax, search } = state.filters;
  let result = state.raw.filter(s => {
    if (exchange && s.exchange !== exchange) return false;
    if (rating && s.rating !== rating) return false;
    if (search && !s.ticker.includes(search)) return false;

    // Volume range filter
    const vol = s.volume || 0;
    if (volMin != null && vol < volMin) return false;
    if (volMax != null && vol > volMax) return false;

    return true;
  });

  // Apply custom sort if active
  if (state.sort.column) {
    const col = state.sort.column;
    const dir = state.sort.direction === 'asc' ? 1 : -1;
    result = [...result].sort((a, b) => {
      let va, vb;
      if (col === '_gtgd') {
        va = (a.close || 0) * (a.volume || 0);
        vb = (b.close || 0) * (b.volume || 0);
      } else {
        va = a[col];
        vb = b[col];
      }
      if (va == null) va = -Infinity;
      if (vb == null) vb = -Infinity;
      if (va < vb) return -1 * dir;
      if (va > vb) return 1 * dir;
      return 0;
    });
  }

  return result;
}

// ──────────── Render ────────────
function render() {
  state.filtered = applyFilters();
  document.getElementById('result-count').textContent = state.filtered.length;
  document.getElementById('stat-total').textContent = state.raw.length;
  document.getElementById('stat-aplus').textContent =
    state.raw.filter(s => s.rating === 'A+').length;

  // Update date label in lean strip
  const statDate = document.getElementById('stat-date');
  if (statDate && state.currentDate) {
    const d = state.currentDate.split('T')[0];
    const [y, m, day] = d.split('-');
    const dateStr = `${day}/${m}`;
    const isLatest = state.currentDate === state.latestDate;
    statDate.textContent = isLatest ? `· LIVE ${dateStr}` : `· ${dateStr}`;
    statDate.style.color = isLatest ? 'var(--green)' : 'var(--text-mute)';
  }

  renderDateContext();

  const eventCount = state.filtered.filter(s => s.m_upcoming_event).length;
  const meta = document.getElementById('result-meta');
  if (eventCount > 0) {
    meta.innerHTML = `<span style="color: var(--accent)">⚑</span> ${eventCount} mã có sự kiện sắp tới`;
  } else {
    meta.innerHTML = '';
  }

  if (state.filtered.length === 0) {
    renderEmpty('Không có tín hiệu nào khớp bộ lọc hiện tại.');
    return;
  }

  const tbody = document.getElementById('signal-rows');
  tbody.innerHTML = state.filtered.map((s, i) => renderRow(s, i + 1)).join('');

  tbody.querySelectorAll('tr[data-idx]').forEach(tr => {
    tr.addEventListener('click', () => openDrawer(state.filtered[+tr.dataset.idx]));
  });
}

function renderDateContext() {
  const banner = document.getElementById('date-context');
  if (!state.currentDate) {
    banner.classList.remove('show');
    return;
  }

  const isLatest = state.currentDate === state.latestDate;
  const adjusted = state.currentData?.metadata?.adjusted_prices !== false;
  const filtered = state.currentData?.metadata?.corporate_actions_filtered !== false;

  banner.className = 'date-context show' + (isLatest ? '' : ' historical');
  banner.innerHTML = `
    <div>
      <div class="date-context-label">Ngày phân tích</div>
      <div class="date-context-value">${formatDateLabel(state.currentDate)}</div>
    </div>
    <div class="date-context-divider"></div>
    <div>
      <div class="date-context-label">Trạng thái</div>
      <div class="date-context-value" style="color: ${isLatest ? 'var(--green)' : 'var(--blue)'}">
        ${isLatest ? '● Phiên mới nhất' : '◆ Dữ liệu lịch sử'}
      </div>
    </div>
    <div class="date-context-divider"></div>
    <div style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center;">
      ${adjusted ? '<span style="font-size: 11px; color: var(--green); padding: 3px 8px; border: 1px solid rgba(0, 214, 143, 0.3); border-radius: 3px;">✓ GIÁ ĐÃ ĐIỀU CHỈNH</span>' : ''}
      ${filtered ? '<span style="font-size: 11px; color: var(--green); padding: 3px 8px; border: 1px solid rgba(0, 214, 143, 0.3); border-radius: 3px;">✓ LỌC CORPORATE ACTIONS</span>' : ''}
    </div>
  `;
}

function renderRow(s, idx) {
  const change = s.m_change_5d_pct || 0;
  const changeClass = change >= 0 ? 'change-pos' : 'change-neg';
  const sign = change >= 0 ? '+' : '';

  const pills = currentCriteria().map(c => {
    const on = s[c.key] === 1;
    return `<span class="pill ${on ? 'on-' + c.group : 'off'}" title="${c.name}: ${on ? '✓' : '✗'}"></span>`;
  }).join('');

  const ratingClass = s.rating === 'A+' ? 'aplus' :
                      s.rating === 'A' ? 'a' :
                      s.rating === 'B' ? 'b' : 'c';

  const scoreClass = s.total_score >= 8 ? 'high' : s.total_score >= 6 ? 'mid' : '';

  let eventFlag = '';
  if (s.m_upcoming_event) {
    const ev = s.m_upcoming_event;
    const daysToEx = Math.ceil((new Date(ev.ex_date) - new Date(s.date)) / (1000 * 60 * 60 * 24));
    const urgentClass = daysToEx <= 5 ? 'urgent' : '';
    const label = EVENT_TYPE_LABELS[ev.type] || ev.type;
    const ratioText = ev.type === 'cash_dividend'
      ? `${(ev.ratio).toLocaleString('vi-VN')} VND`
      : `${(ev.ratio * 100).toFixed(0)}%`;
    eventFlag = `<span class="event-flag ${urgentClass}" title="${label} · Ngày GDKHQ: ${ev.ex_date} (sau ${daysToEx} ngày) · Tỷ lệ: ${ratioText}">⚑</span>`;
  }

  // Format Fibonacci support/resistance — show nearest only
  const supports = s.m_supports || [];
  const resistances = s.m_resistances || [];
  const nearestSupport = supports.length > 0
    ? renderFibCell(supports[0], 'support')
    : '<span style="color: var(--text-mute)">—</span>';
  const nearestResistance = resistances.length > 0
    ? renderFibCell(resistances[0], 'resistance')
    : '<span style="color: var(--text-mute)">—</span>';

  return `<tr data-idx="${idx - 1}">
    <td style="color: var(--text-mute)">${idx}</td>
    <td>
      <div class="ticker-cell-wrap">
        <span class="ticker-cell">${s.ticker}</span>
        ${eventFlag}
      </div>
    </td>
    <td><span class="exchange-cell">${s.exchange}</span></td>
    <td class="num">${fmtPrice(s.close)}</td>
    <td class="num ${changeClass}">${sign}${change.toFixed(2)}%</td>
    <td class="num">${fmtVolume(s.volume)}</td>
    <td class="num">${fmtValue(s.close, s.volume)}</td>
    <td class="num">${(s.m_vol_ratio || 0).toFixed(2)}×</td>
    <td class="num">${(s.m_rsi14 || 0).toFixed(0)}</td>
    <td class="num">${nearestSupport}</td>
    <td class="num">${nearestResistance}</td>
    <td><div class="criteria-pills">${pills}</div></td>
    <td class="num score-cell ${scoreClass}">${s.total_score}/${currentMaxScore()}</td>
    <td><span class="rating-tag ${ratingClass}">${s.rating}</span></td>
  </tr>`;
}

// Render a single Fibo level cell (support or resistance)
function renderFibCell(level, kind) {
  if (!level) return '<span style="color: var(--text-mute)">—</span>';
  const isGolden = level.is_golden;
  const goldenClass = isGolden ? ' golden' : '';
  const sign = kind === 'support' ? '-' : '+';
  const tooltip = `Mức Fibonacci ${level.label} · giá ${level.price}${isGolden ? ' · GOLDEN RATIO ⭐' : ''}`;
  return `<span class="fib-cell fib-${kind}${goldenClass}" title="${tooltip}">
    <span class="fib-price">${fmtPrice(level.price)}</span>
    <span class="fib-label">${level.label}${isGolden ? ' ⭐' : ''}</span>
    <span class="fib-dist">${sign}${level.distance_pct}%</span>
  </span>`;
}

// Render Fibonacci section in drawer with visual ladder
function renderFiboSection(s) {
  const swing = s.m_fibo_swing;
  const supports = s.m_supports || [];
  const resistances = s.m_resistances || [];
  if (!swing || (supports.length === 0 && resistances.length === 0)) {
    return '';
  }

  const currentPrice = s.close;
  const directionLabel = swing.direction === 'up' ? 'Uptrend' : 'Downtrend';
  const directionColor = swing.direction === 'up' ? 'var(--green)' : 'var(--red)';

  // Combine all levels for visual ladder (top = high, bottom = low)
  const allLevels = [
    ...resistances.map(r => ({ ...r, kind: 'resistance' })),
    { price: currentPrice, kind: 'current', label: 'GIÁ HIỆN TẠI' },
    ...supports.map(s => ({ ...s, kind: 'support' })),
  ];

  return `
    <div class="drawer-section">
      <div class="drawer-section-title">Fibonacci Retracement</div>

      <div class="fibo-swing-info">
        <div class="fibo-swing-meta">
          <span class="fibo-direction" style="color: ${directionColor}">▲ ${directionLabel}</span>
          <span class="fibo-swing-range">
            Swing: <span style="color: var(--red)">${fmtPrice(swing.low)}</span>
            <span style="color: var(--text-mute)"> ${swing.low_date} </span>
            →
            <span style="color: var(--green)">${fmtPrice(swing.high)}</span>
            <span style="color: var(--text-mute)"> ${swing.high_date} </span>
          </span>
          <span class="fibo-swing-pct">
            Biên độ: <span style="color: var(--accent)">${((swing.range/swing.low)*100).toFixed(1)}%</span>
          </span>
        </div>
      </div>

      <div class="fibo-ladder">
        ${allLevels.map(lv => {
          if (lv.kind === 'current') {
            return `
              <div class="fibo-row fibo-current">
                <span class="fibo-label-cell">${lv.label}</span>
                <span class="fibo-price-cell">${fmtPrice(lv.price)}</span>
                <span class="fibo-dist-cell">←</span>
              </div>
            `;
          }
          const isGolden = lv.is_golden ? ' golden' : '';
          const kindClass = lv.kind === 'support' ? 'fibo-support' : 'fibo-resistance';
          const sign = lv.kind === 'support' ? '-' : '+';
          return `
            <div class="fibo-row ${kindClass}${isGolden}">
              <span class="fibo-label-cell">
                ${lv.kind === 'support' ? 'Hỗ trợ' : 'Kháng cự'} ${lv.label}
                ${lv.is_golden ? '<span class="fibo-golden-tag">⭐ GOLDEN</span>' : ''}
              </span>
              <span class="fibo-price-cell">${fmtPrice(lv.price)}</span>
              <span class="fibo-dist-cell">${sign}${lv.distance_pct}%</span>
            </div>
          `;
        }).join('')}
      </div>

      <div class="fibo-explainer">
        <strong style="color: var(--accent)">⭐ 61.8%</strong> là mức "Golden Ratio" — quan trọng nhất trong Fibo, thường là điểm vào lệnh tốt khi giá pullback về.
      </div>
    </div>
  `;
}

function renderEmpty(msg) {
  document.getElementById('signal-rows').innerHTML =
    `<tr><td colspan="14" class="empty" style="white-space: pre-line;">${msg}</td></tr>`;
}

// ──────────── Drawer ────────────
// ──────────── Entry Hint logic ────────────
// Answers Q3: "Đồ thị có điểm vào lệnh đẹp không?" in 5 seconds.
//
// Heuristic:
//   1. STRONG BUY:  RSI < 60 AND price near golden support (61.8%, distance < 3%)
//                   AND rating A+ → "Mua gần. Điểm vào: golden price, stop: dưới 78.6%"
//   2. WATCH:       RSI ok AND price between MA20 and resistance → "Theo dõi"
//   3. EXTENDED:    RSI > 65 OR price far from supports → "Đã chạy. Đợi pullback"
//   4. WEAK:        Score < threshold OR rating C → "Không đề xuất"
function computeEntryHint(s) {
  const supports = s.m_supports || [];
  const resistances = s.m_resistances || [];
  const rsi = s.m_rsi14 || 50;
  const close = s.close;

  // Find golden support if any
  const goldenSupport = supports.find(x => x.is_golden);
  const nearestSupport = supports[0];
  const nearestResistance = resistances[0];

  let signal = 'NEUTRAL';   // STRONG_BUY | BUY | WATCH | EXTENDED | NEUTRAL
  let title = 'Theo dõi';
  let detail = '';
  let entry = null;
  let stop = null;
  let target = null;
  let color = 'var(--text-dim)';
  let bg = 'var(--bg-elev-2)';

  // Best case: A+ rating + golden support nearby + RSI not overbought
  if (s.rating === 'A+' && goldenSupport && goldenSupport.distance_pct < 4 && rsi < 65) {
    signal = 'STRONG_BUY';
    title = 'Vùng vào lệnh đẹp';
    detail = 'Tín hiệu mạnh + giá đang gần mức Golden Ratio 61.8% — vùng pullback lý tưởng để mua.';
    entry = goldenSupport.price;
    stop = supports.find(x => x.label === '78.6%')?.price || supports[supports.length - 1]?.price;
    target = nearestResistance?.price;
    color = 'var(--green)';
    bg = 'rgba(0, 214, 143, 0.08)';
  }
  // Decent case: A+/A rating with RSI in healthy zone, near a support
  else if ((s.rating === 'A+' || s.rating === 'A') && nearestSupport &&
           nearestSupport.distance_pct < 3 && rsi >= 45 && rsi <= 65) {
    signal = 'BUY';
    title = 'Có thể vào lệnh';
    detail = `Giá gần hỗ trợ ${nearestSupport.label} — entry hợp lý nếu volume xác nhận.`;
    entry = nearestSupport.price;
    stop = supports[1]?.price || (close * 0.95);
    target = nearestResistance?.price;
    color = 'var(--accent)';
    bg = 'rgba(255, 181, 71, 0.08)';
  }
  // Extended: RSI overbought or price too far from supports
  else if (rsi > 70 || (nearestSupport && nearestSupport.distance_pct > 8)) {
    signal = 'EXTENDED';
    title = 'Đã chạy — đợi pullback';
    detail = rsi > 70
      ? `RSI ${rsi.toFixed(0)} đã ở vùng quá mua. Đợi RSI về <65 hoặc pullback về hỗ trợ trước khi vào.`
      : `Giá đã cách hỗ trợ gần nhất ${nearestSupport.distance_pct.toFixed(1)}%. Rủi ro reward kém — đợi pullback.`;
    color = 'var(--red)';
    bg = 'rgba(255, 71, 87, 0.06)';
  }
  // Weak signal
  else if (s.rating === 'C' || s.total_score < currentMaxScore() * 0.5) {
    signal = 'WEAK';
    title = 'Tín hiệu yếu — không đề xuất';
    detail = 'Số tiêu chí đạt thấp. Theo dõi nhưng không nên vào lệnh ở mức này.';
    color = 'var(--text-mute)';
    bg = 'var(--bg-elev-2)';
  }
  // Default: watch
  else {
    signal = 'WATCH';
    title = 'Theo dõi';
    detail = `RSI ${rsi.toFixed(0)} · ${s.rating}. Tín hiệu hợp lệ nhưng vùng vào không lý tưởng — theo dõi pullback.`;
    color = 'var(--accent)';
    bg = 'var(--bg-elev-2)';
  }

  // Build the levels grid if entry exists
  let levelsHtml = '';
  if (entry != null) {
    const rrRatio = (target && stop)
      ? ((target - entry) / (entry - stop)).toFixed(1)
      : null;
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
          <div class="entry-level-sub">${(((entry - stop) / entry) * 100).toFixed(1)}%</div>
        </div>
        ` : ''}
        ${target ? `
        <div class="entry-level entry-level-target">
          <div class="entry-level-label">CHỐT LÃI</div>
          <div class="entry-level-price">${fmtPrice(target)}</div>
          <div class="entry-level-sub">+${(((target - entry) / entry) * 100).toFixed(1)}%</div>
        </div>
        ` : ''}
        ${rrRatio ? `
        <div class="entry-level entry-level-rr">
          <div class="entry-level-label">R:R</div>
          <div class="entry-level-price">1:${rrRatio}</div>
        </div>
        ` : ''}
      </div>
    `;
  }

  return `
    <div class="entry-hint" style="background: ${bg}; border-left: 3px solid ${color};">
      <div class="entry-hint-head">
        <span class="entry-hint-signal" style="color: ${color};">${title}</span>
        <span class="entry-hint-tag">GỢI Ý NHANH</span>
      </div>
      <div class="entry-hint-detail">${detail}</div>
      ${levelsHtml}
    </div>
  `;
}

function openDrawer(s) {
  document.getElementById('drawer-ticker').textContent = `${s.ticker} · ${s.exchange}`;
  const passed = currentCriteria().filter(c => s[c.key] === 1).length;
  const body = document.getElementById('drawer-body');

  // === ENTRY HINT — answers Q3 in 5 seconds ===
  const entryHint = computeEntryHint(s);

  let eventSection = '';
  if (s.m_upcoming_event) {
    const ev = s.m_upcoming_event;
    const daysToEx = Math.ceil((new Date(ev.ex_date) - new Date(s.date)) / (1000 * 60 * 60 * 24));
    const label = EVENT_TYPE_LABELS[ev.type] || ev.type;
    const ratioText = ev.type === 'cash_dividend'
      ? `${(ev.ratio).toLocaleString('vi-VN')} VND/cp`
      : `${(ev.ratio * 100).toFixed(1)}%`;
    const urgentColor = daysToEx <= 5 ? 'var(--red)' : 'var(--accent)';
    eventSection = `
      <div class="drawer-section">
        <div class="drawer-section-title">⚑ Sự kiện sắp tới</div>
        <div style="padding: 14px; background: var(--bg-elev-2); border-left: 3px solid ${urgentColor}; border-radius: 3px;">
          <div style="font-family: var(--font-mono); font-size: 11px; color: var(--text-dim); margin-bottom: 6px;">
            ${label.toUpperCase()}
          </div>
          <div style="font-size: 16px; color: ${urgentColor}; font-weight: 600; margin-bottom: 8px;">
            Ngày GDKHQ: ${ev.ex_date} (sau ${daysToEx} ngày)
          </div>
          <div style="font-size: 13px; color: var(--text-dim);">
            Tỷ lệ: <span style="color: var(--text); font-family: var(--font-mono);">${ratioText}</span>
          </div>
          ${daysToEx <= 5 ? `
            <div style="margin-top: 12px; font-size: 12px; color: var(--red); padding: 8px; background: rgba(255, 71, 87, 0.08); border-radius: 3px;">
              ⚠ Tín hiệu cận ngày sự kiện — cần thận trọng vì giá có thể biến động mạnh quanh ngày GDKHQ.
            </div>
          ` : ''}
        </div>
      </div>
    `;
  }

  body.innerHTML = `
    ${entryHint}
    ${eventSection}

    <div class="drawer-section">
      <div class="drawer-section-title">Thông tin giá · ${formatDate(s.date)}</div>
      <div class="drawer-metric-grid">
        <div class="drawer-metric">
          <div class="drawer-metric-label">Giá đóng cửa</div>
          <div class="drawer-metric-value">${fmtPrice(s.close)}</div>
        </div>
        <div class="drawer-metric">
          <div class="drawer-metric-label">Thay đổi 5D</div>
          <div class="drawer-metric-value" style="color: ${s.m_change_5d_pct >= 0 ? 'var(--green)' : 'var(--red)'}">
            ${s.m_change_5d_pct >= 0 ? '+' : ''}${(s.m_change_5d_pct || 0).toFixed(2)}%
          </div>
        </div>
        <div class="drawer-metric">
          <div class="drawer-metric-label">Khối lượng GD</div>
          <div class="drawer-metric-value">${fmtVolume(s.volume)}</div>
        </div>
        <div class="drawer-metric">
          <div class="drawer-metric-label">Giá trị GD</div>
          <div class="drawer-metric-value">${fmtValue(s.close, s.volume)}</div>
        </div>
        <div class="drawer-metric">
          <div class="drawer-metric-label">Vol / MA20</div>
          <div class="drawer-metric-value">${(s.m_vol_ratio || 0).toFixed(2)}×</div>
        </div>
        <div class="drawer-metric">
          <div class="drawer-metric-label">Đỉnh 20 phiên</div>
          <div class="drawer-metric-value">${fmtPrice(s.m_high20)}</div>
        </div>
        <div class="drawer-metric">
          <div class="drawer-metric-label">Cách đỉnh</div>
          <div class="drawer-metric-value">${(s.m_dist_to_high20_pct || 0).toFixed(2)}%</div>
        </div>
        <div class="drawer-metric">
          <div class="drawer-metric-label">RSI(14)</div>
          <div class="drawer-metric-value">${(s.m_rsi14 || 0).toFixed(1)}</div>
        </div>
      </div>
    </div>

    ${renderFiboSection(s)}

    <div class="drawer-section">
      <div class="drawer-section-title">Tiêu chí đạt được (${passed}/${currentMaxScore()})</div>
      <ul class="criteria-detail-list">
        ${currentCriteria().map(c => {
          const on = s[c.key] === 1;
          return `<li>
            <div class="criteria-check ${on ? 'on' : 'off'}">${on ? '✓' : '·'}</div>
            <div style="color: ${on ? 'var(--text)' : 'var(--text-mute)'}">${c.name}</div>
          </li>`;
        }).join('')}
      </ul>
    </div>

    <div class="drawer-section">
      <div class="drawer-section-title">Liên kết</div>
      <div style="display: flex; gap: 8px; flex-wrap: wrap;">
        <a href="https://www.tradingview.com/chart/?symbol=${s.exchange}:${s.ticker}" target="_blank"
           style="display: inline-block; padding: 8px 12px; border: 1px solid var(--border-strong); border-radius: 3px; color: var(--accent); text-decoration: none; font-family: var(--font-mono); font-size: 12px;">
          TradingView →
        </a>
        <a href="https://stockbiz.vn/Stocks/${s.ticker}/Overview.aspx" target="_blank"
           style="display: inline-block; padding: 8px 12px; border: 1px solid var(--border-strong); border-radius: 3px; color: var(--accent); text-decoration: none; font-family: var(--font-mono); font-size: 12px;">
          StockBiz →
        </a>
        <a href="https://cafef.vn/du-lieu/lich-su-giao-dich-${s.ticker.toLowerCase()}.chn" target="_blank"
           style="display: inline-block; padding: 8px 12px; border: 1px solid var(--border-strong); border-radius: 3px; color: var(--accent); text-decoration: none; font-family: var(--font-mono); font-size: 12px;">
          CafeF →
        </a>
      </div>
    </div>
  `;

  document.getElementById('detail-drawer').classList.add('open');
  document.getElementById('drawer-overlay').classList.add('open');
}

function closeDrawer() {
  document.getElementById('detail-drawer').classList.remove('open');
  document.getElementById('drawer-overlay').classList.remove('open');
}

// ──────────── Helpers ────────────
function setStatus(stateName, text) {
  const dot = document.getElementById('status-dot');
  const txt = document.getElementById('status-text');
  dot.className = 'status-dot ' + (stateName === 'live' ? 'live' : '');
  txt.textContent = text;
}

function updateClock() {
  const now = new Date();
  const ictTime = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Ho_Chi_Minh' }));
  const hh = String(ictTime.getHours()).padStart(2, '0');
  const mm = String(ictTime.getMinutes()).padStart(2, '0');
  const ss = String(ictTime.getSeconds()).padStart(2, '0');
  document.getElementById('market-time').textContent = `${hh}:${mm}:${ss} ICT`;

  const day = ictTime.getDay();
  const hours = ictTime.getHours();
  const isWeekday = day >= 1 && day <= 5;
  const isOpen = isWeekday && hours >= 9 && hours < 15;
  const ms = document.getElementById('market-status');
  ms.textContent = isOpen ? 'MARKET OPEN' : 'MARKET CLOSED';
  ms.className = 'market-status ' + (isOpen ? 'open' : 'closed');
}

function fmtPrice(p) {
  if (p == null) return '—';
  return p.toLocaleString('vi-VN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatDate(dateStr) {
  // "2026-05-22T00:00:00" → "22/05/2026"
  if (!dateStr) return '—';
  const datePart = dateStr.split('T')[0];
  const [y, m, d] = datePart.split('-');
  return `${d}/${m}/${y}`;
}

function fmtVolume(v) {
  if (v == null || v === 0) return '—';
  // Format with thousand separator. K/M/B for compactness on small screens.
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(2) + 'M';
  if (v >= 1_000) return (v / 1_000).toFixed(1) + 'K';
  return v.toLocaleString('vi-VN');
}

function fmtValue(price, volume) {
  // Total turnover in VND. Price is in 1000s VND, so:
  // GTGD = close * 1000 * volume
  if (price == null || volume == null) return '—';
  const totalVND = price * 1000 * volume;
  if (totalVND >= 1_000_000_000) return (totalVND / 1_000_000_000).toFixed(2) + ' tỷ';
  if (totalVND >= 1_000_000) return (totalVND / 1_000_000).toFixed(0) + ' tr';
  return Math.round(totalVND).toLocaleString('vi-VN');
}

function formatTime(date) {
  return date.toLocaleString('vi-VN', {
    timeZone: 'Asia/Ho_Chi_Minh',
    hour: '2-digit', minute: '2-digit',
    day: '2-digit', month: '2-digit',
  });
}

function exportCSV() {
  if (state.filtered.length === 0) return;
  const headers = ['Ticker', 'Exchange', 'Date', 'Close', 'Change5D%',
                   'Volume', 'ValueVND', 'VolRatio',
                   'RSI', 'DistHigh20%', 'Score', 'Rating',
                   ...currentCriteria().map(c => c.name),
                   'UpcomingEvent'];
  const rows = state.filtered.map(s => [
    s.ticker, s.exchange, (s.date || '').split('T')[0],
    s.close, s.m_change_5d_pct,
    s.volume, Math.round((s.close || 0) * 1000 * (s.volume || 0)),
    s.m_vol_ratio, s.m_rsi14, s.m_dist_to_high20_pct,
    s.total_score, s.rating,
    ...currentCriteria().map(c => s[c.key]),
    s.m_upcoming_event ? `${s.m_upcoming_event.type}@${s.m_upcoming_event.ex_date}` : '',
  ]);
  const csv = [headers, ...rows].map(r => r.join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `vn_breakout_signals_${state.currentDate || 'latest'}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

window.closeDrawer = closeDrawer;

init();
