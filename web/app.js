// ────────────────────────────────────────────────────────────
// VN Breakout Scanner — Dashboard logic
// ────────────────────────────────────────────────────────────

const DATA_DIR = './data';
const ARCHIVE_DIR = './data/archive';

const CRITERIA = [
  { key: 'c1_atr_squeeze',  name: 'ATR Squeeze',        group: 1 },
  { key: 'c2_bb_squeeze',   name: 'Bollinger Squeeze',  group: 1 },
  { key: 'c3_near_high20',  name: 'Gần đỉnh 20 phiên',  group: 1 },
  { key: 'c4_stealth_accum',name: 'Stealth Accumulation',group: 2 },
  { key: 'c5_vol_surge',    name: 'Volume Surge',       group: 2 },
  { key: 'c6_upper_close',  name: 'Đóng cửa nửa trên',  group: 2 },
  { key: 'c9_pocket_pivot', name: 'Pocket Pivot',       group: 2 },
  { key: 'c7_ma_align',     name: 'MA10 > MA20',        group: 3 },
  { key: 'c8_rsi_zone',     name: 'RSI 50-65',          group: 3 },
  { key: 'c10_no_gap_down', name: 'Không gap down',     group: 3 },
];

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

// ──────────── Load latest.json first ────────────
async function loadLatestFirst() {
  setStatus('connecting', 'LOADING');
  try {
    const res = await fetch(`${DATA_DIR}/latest.json?_=${Date.now()}`);
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
    const res = await fetch(`${ARCHIVE_DIR}/index.json?_=${Date.now()}`);
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
      url = `${DATA_DIR}/latest.json?_=${Date.now()}`;
    } else {
      url = `${ARCHIVE_DIR}/${dateStr}.json?_=${Date.now()}`;
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

  const pills = CRITERIA.map(c => {
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
    <td class="num">${(s.m_dist_to_high20_pct || 0).toFixed(2)}%</td>
    <td><div class="criteria-pills">${pills}</div></td>
    <td class="num score-cell ${scoreClass}">${s.total_score}/10</td>
    <td><span class="rating-tag ${ratingClass}">${s.rating}</span></td>
  </tr>`;
}

function renderEmpty(msg) {
  document.getElementById('signal-rows').innerHTML =
    `<tr><td colspan="13" class="empty" style="white-space: pre-line;">${msg}</td></tr>`;
}

// ──────────── Drawer ────────────
function openDrawer(s) {
  document.getElementById('drawer-ticker').textContent = `${s.ticker} · ${s.exchange}`;
  const passed = CRITERIA.filter(c => s[c.key] === 1).length;
  const body = document.getElementById('drawer-body');

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

    <div class="drawer-section">
      <div class="drawer-section-title">Tiêu chí đạt được (${passed}/10)</div>
      <ul class="criteria-detail-list">
        ${CRITERIA.map(c => {
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
                   ...CRITERIA.map(c => c.name),
                   'UpcomingEvent'];
  const rows = state.filtered.map(s => [
    s.ticker, s.exchange, (s.date || '').split('T')[0],
    s.close, s.m_change_5d_pct,
    s.volume, Math.round((s.close || 0) * 1000 * (s.volume || 0)),
    s.m_vol_ratio, s.m_rsi14, s.m_dist_to_high20_pct,
    s.total_score, s.rating,
    ...CRITERIA.map(c => s[c.key]),
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
