// ════════════════════════════════════════════════════════════
// VN Valuation Dashboard
// Load latest.json → render table + detail panel
// ════════════════════════════════════════════════════════════

const DATA_URL = '../data/valuation/latest.json';

const state = {
  signals: [],       // raw signals from JSON
  filtered: [],      // after filter
  selectedTicker: null,
  sort: { column: 'upside_pct', direction: 'desc' },
  filters: {
    search: '',
    verdict: '',
    industry: '',
    minUpside: -100,
    minConfidence: 30,
    holding: '',
  },
  metadata: {},
};

// ──────────── Boot ────────────
document.addEventListener('DOMContentLoaded', async () => {
  startClock();
  bindFilters();
  bindSort();
  await loadData();
});

// ──────────── Clock ────────────
function startClock() {
  const el = document.getElementById('clock');
  const tick = () => {
    const d = new Date();
    el.textContent = d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
  };
  tick();
  setInterval(tick, 30000);
}

// ──────────── Data Loading ────────────
async function loadData() {
  try {
    const r = await fetch(`${DATA_URL}?_=${Date.now()}`);
    if (!r.ok) {
      throw new Error(`HTTP ${r.status}`);
    }
    const data = await r.json();
    state.signals = data.signals || [];
    state.metadata = data.metadata || {};

    if (state.signals.length === 0) {
      showDemoBanner();
    }

    populateIndustryFilter();
    updateTopbarStats(data);
    applyFiltersAndRender();
  } catch (e) {
    console.warn('Load failed:', e.message);
    showDemoBanner();
    document.getElementById('valuation-tbody').innerHTML =
      `<tr><td colspan="8" class="td-empty">Chưa có dữ liệu định giá.<br>
       Chạy <code>python backend/run_valuation.py --limit 100</code> trước.</td></tr>`;
  }
}

function showDemoBanner() {
  document.getElementById('demo-banner').style.display = 'block';
}

function updateTopbarStats(data) {
  const counts = (data.metadata?.verdict_counts) || {};
  const total = data.total || state.signals.length;
  const buy = (counts['STRONG BUY'] || 0) + (counts['BUY'] || 0);
  const hold = counts['HOLD'] || 0;
  const sell = (counts['SELL'] || 0) + (counts['STRONG SELL'] || 0);

  document.getElementById('stat-total').textContent = total;
  document.getElementById('stat-buy').textContent = buy;
  document.getElementById('stat-hold').textContent = hold;
  document.getElementById('stat-sell').textContent = sell;

  if (data.generated_at) {
    const d = new Date(data.generated_at);
    document.getElementById('stat-date').textContent = d.toLocaleDateString('vi-VN');
  }
}

function populateIndustryFilter() {
  const select = document.getElementById('filter-industry');
  const industries = [...new Set(state.signals.map(s => s.industry))].sort();
  for (const ind of industries) {
    const opt = document.createElement('option');
    opt.value = ind;
    opt.textContent = ind.replace(/_/g, ' ');
    select.appendChild(opt);
  }
}

// ──────────── Filter binding ────────────
function bindFilters() {
  document.getElementById('ticker-search').addEventListener('input', e => {
    state.filters.search = e.target.value.toUpperCase().trim();
    applyFiltersAndRender();
  });

  document.getElementById('filter-industry').addEventListener('change', e => {
    state.filters.industry = e.target.value;
    applyFiltersAndRender();
  });

  const upsideEl = document.getElementById('filter-upside');
  upsideEl.addEventListener('input', e => {
    state.filters.minUpside = parseInt(e.target.value);
    document.getElementById('filter-upside-value').textContent = state.filters.minUpside;
    applyFiltersAndRender();
  });

  const confEl = document.getElementById('filter-confidence');
  confEl.addEventListener('input', e => {
    state.filters.minConfidence = parseInt(e.target.value);
    document.getElementById('filter-confidence-value').textContent = state.filters.minConfidence;
    applyFiltersAndRender();
  });

  document.querySelectorAll('#filter-verdict .chip').forEach(chip => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('#filter-verdict .chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.filters.verdict = chip.dataset.verdict;
      applyFiltersAndRender();
    });
  });

  document.querySelectorAll('#filter-holding .chip').forEach(chip => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('#filter-holding .chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.filters.holding = chip.dataset.holding;
      applyFiltersAndRender();
    });
  });

  document.getElementById('reset-filters').addEventListener('click', () => {
    state.filters = {
      search: '', verdict: '', industry: '',
      minUpside: -100, minConfidence: 30, holding: '',
    };
    document.getElementById('ticker-search').value = '';
    document.getElementById('filter-industry').value = '';
    document.getElementById('filter-upside').value = -100;
    document.getElementById('filter-upside-value').textContent = '-100';
    document.getElementById('filter-confidence').value = 30;
    document.getElementById('filter-confidence-value').textContent = '30';
    document.querySelectorAll('#filter-verdict .chip').forEach((c, i) =>
      c.classList.toggle('active', i === 0));
    document.querySelectorAll('#filter-holding .chip').forEach((c, i) =>
      c.classList.toggle('active', i === 0));
    applyFiltersAndRender();
  });
}

// ──────────── Sort binding ────────────
function bindSort() {
  document.querySelectorAll('th.th-sort').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.sort;
      if (state.sort.column === col) {
        state.sort.direction = state.sort.direction === 'asc' ? 'desc' : 'asc';
      } else {
        state.sort.column = col;
        state.sort.direction = col === 'ticker' ? 'asc' : 'desc';
      }
      applyFiltersAndRender();
    });
  });
}

// ──────────── Filter + Sort + Render ────────────
function applyFiltersAndRender() {
  let result = state.signals.filter(s => {
    if (state.filters.search && !s.ticker.includes(state.filters.search)) return false;
    if (state.filters.verdict && s.verdict !== state.filters.verdict) return false;
    if (state.filters.industry && s.industry !== state.filters.industry) return false;
    if (s.upside_pct < state.filters.minUpside) return false;
    if (s.confidence < state.filters.minConfidence) return false;
    if (state.filters.holding === 'true' && !s.is_holding) return false;
    if (state.filters.holding === 'false' && s.is_holding) return false;
    return true;
  });

  // Sort
  const col = state.sort.column;
  const dir = state.sort.direction === 'asc' ? 1 : -1;
  if (col === 'verdict') {
    const order = { 'STRONG BUY': 0, 'BUY': 1, 'HOLD': 2, 'SELL': 3, 'STRONG SELL': 4 };
    result.sort((a, b) => dir * (order[a.verdict] - order[b.verdict]));
  } else {
    result.sort((a, b) => {
      const va = a[col];
      const vb = b[col];
      if (typeof va === 'number') return dir * (va - vb);
      return dir * String(va).localeCompare(String(vb));
    });
  }

  state.filtered = result;
  renderTable();
  updateSortIndicators();
  document.getElementById('result-count').textContent =
    `— ${result.length}/${state.signals.length} hiển thị`;
}

function updateSortIndicators() {
  document.querySelectorAll('th.th-sort').forEach(th => {
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.sort === state.sort.column) {
      th.classList.add(state.sort.direction === 'asc' ? 'sort-asc' : 'sort-desc');
    }
  });
}

// ──────────── Render Table ────────────
function renderTable() {
  const tbody = document.getElementById('valuation-tbody');
  if (state.filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="td-empty">Không có mã nào khớp bộ lọc</td></tr>`;
    return;
  }

  tbody.innerHTML = state.filtered.map(s => {
    const upsideCls = s.upside_pct >= 0 ? 'upside-pos' : 'upside-neg';
    const upsideStr = (s.upside_pct >= 0 ? '+' : '') + s.upside_pct.toFixed(1) + '%';
    const verdictKey = s.verdict.replace(/ /g, '\\ ');
    const verdictClassSuffix = s.verdict.replace(/ /g, '\\ ');
    const confCls = s.confidence >= 70 ? 'high' : (s.confidence >= 45 ? 'mid' : 'low');
    const methodPills = (s.methods_used || []).slice(0, 3).map(m => {
      const short = abbrevMethod(m);
      return `<span class="method-pill">${short}</span>`;
    }).join('');
    const holdingIcon = s.is_holding ? '<span class="holding-icon" title="Holding company">⚙</span>' : '';

    return `
      <tr data-ticker="${s.ticker}" class="${s.ticker === state.selectedTicker ? 'selected' : ''}">
        <td><span class="ticker-cell">${s.ticker}</span>${holdingIcon}</td>
        <td><span class="industry-tag">${s.industry.replace(/_/g, ' ')}</span></td>
        <td class="td-num">${fmtNum(s.current_price)}</td>
        <td class="td-num">${fmtNum(s.fair_value)}</td>
        <td class="td-num ${upsideCls}">${upsideStr}</td>
        <td class="td-center">
          <span class="verdict-badge verdict-${verdictClassSuffix}">${s.verdict}</span>
        </td>
        <td class="td-num">
          <div class="confidence-bar">
            <div class="confidence-bar-track">
              <div class="confidence-bar-fill ${confCls}" style="width: ${s.confidence}%"></div>
            </div>
            <span>${s.confidence.toFixed(0)}%</span>
          </div>
        </td>
        <td class="td-center"><div class="method-pills">${methodPills}</div></td>
      </tr>
    `;
  }).join('');

  // Bind click events
  tbody.querySelectorAll('tr[data-ticker]').forEach(tr => {
    tr.addEventListener('click', () => {
      const ticker = tr.dataset.ticker;
      state.selectedTicker = ticker;
      document.querySelectorAll('tbody tr').forEach(r => r.classList.remove('selected'));
      tr.classList.add('selected');
      renderDetail(state.filtered.find(s => s.ticker === ticker));
    });
  });
}

function abbrevMethod(method) {
  const map = {
    'P/B-ROE Justified': 'P/B-ROE',
    'P/E Multiple': 'P/E',
    'EV/EBITDA': 'EV/EBITDA',
    'EV/EBITDA (Mid-cycle)': 'EV/EBITDA*',
    'DCF FCFF': 'DCF',
    'DDM': 'DDM',
    'Historical Multiple': 'Hist',
  };
  return map[method] || method;
}

function fmtNum(n) {
  if (n == null || isNaN(n)) return '—';
  return n.toLocaleString('vi-VN', { maximumFractionDigits: 0 });
}

// ──────────── Detail Panel ────────────
function renderDetail(signal) {
  if (!signal) return;
  document.getElementById('detail-empty').style.display = 'none';
  const content = document.getElementById('detail-content');
  content.style.display = 'block';

  const upsideCls = signal.upside_pct >= 0 ? 'upside-pos' : 'upside-neg';
  const upsideStr = (signal.upside_pct >= 0 ? '+' : '') + signal.upside_pct.toFixed(1) + '%';
  const verdictClassSuffix = signal.verdict.replace(/ /g, '\\ ');

  // Fair value range bar
  const range = signal.fair_value_high - signal.fair_value_low;
  const fairPos = range > 0 ? ((signal.fair_value - signal.fair_value_low) / range) * 100 : 50;
  const currentPos = range > 0 ? ((signal.current_price - signal.fair_value_low) / range) * 100 : 50;
  const clampPos = (p) => Math.max(2, Math.min(98, p));

  const methodRows = (signal.method_details || []).map(m => {
    const cls = m.upside_pct >= 0 ? 'upside-pos' : 'upside-neg';
    const sign = m.upside_pct >= 0 ? '+' : '';
    return `
      <div class="method-row">
        <span class="method-name">${m.method}</span>
        <span class="method-weight">${m.weight}%</span>
        <span class="method-value">${fmtNum(m.fair_value)}</span>
        <span class="method-upside ${cls}">${sign}${m.upside_pct.toFixed(1)}%</span>
      </div>
    `;
  }).join('');

  const warnings = (signal.warnings || []).map(w =>
    `<div class="warning-item">⚠ ${escapeHtml(w)}</div>`
  ).join('');

  const notes = (signal.notes || []).slice(0, 6).map(n =>
    `<div class="note-item">${escapeHtml(n)}</div>`
  ).join('');

  content.innerHTML = `
    <div class="detail-header">
      <div class="detail-ticker">${signal.ticker}
        ${signal.is_holding ? '<span class="holding-icon" title="Holding company">⚙ Holding</span>' : ''}
      </div>
      <div class="detail-industry">${signal.industry.replace(/_/g, ' ')} · phân loại: ${signal.industry_source}</div>
    </div>

    <div class="detail-prices">
      <div class="price-box">
        <div class="price-label">Giá hiện tại</div>
        <div class="price-value">${fmtNum(signal.current_price)}</div>
      </div>
      <div class="price-box">
        <div class="price-label">Fair value</div>
        <div class="price-value">${fmtNum(signal.fair_value)}</div>
      </div>
    </div>

    <div class="detail-verdict-row">
      <span class="verdict-badge verdict-${verdictClassSuffix}">${signal.verdict}</span>
      <span class="detail-upside ${upsideCls}">${upsideStr}</span>
    </div>

    <div class="detail-section">
      <div class="detail-section-title">Khoảng giá trị hợp lý</div>
      <div class="fv-range-bar">
        <div class="fv-range-fill" style="left: 0; width: 100%;"></div>
        <div class="fv-range-fair" style="left: calc(${clampPos(fairPos)}% - 4px);" title="Fair value: ${fmtNum(signal.fair_value)}"></div>
        <div class="fv-range-current" style="left: ${clampPos(currentPos)}%;" title="Current: ${fmtNum(signal.current_price)}"></div>
      </div>
      <div class="fv-range-labels">
        <span>${fmtNum(signal.fair_value_low)}</span>
        <span>${fmtNum(signal.fair_value_high)}</span>
      </div>
      <div style="font-size: 10px; color: var(--text-mute); margin-top: 4px;">
        Vạch trắng = giá hiện tại · Vạch xanh = fair value
      </div>
    </div>

    <div class="detail-section">
      <div class="detail-section-title">Chi tiết phương pháp · confidence ${signal.confidence}%</div>
      ${methodRows}
    </div>

    ${warnings ? `
      <div class="detail-section">
        <div class="detail-section-title">Cảnh báo</div>
        ${warnings}
      </div>
    ` : ''}

    ${notes ? `
      <div class="detail-section">
        <div class="detail-section-title">Ghi chú hệ thống</div>
        ${notes}
      </div>
    ` : ''}
  `;
}

function escapeHtml(str) {
  if (typeof str !== 'string') return '';
  return str.replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}
