// ════════════════════════════════════════════════════════════
// Watchlist dài hạn (Module B) — đọc web/data/quality/latest.json
//
// Ngưỡng, danh sách chỉ tiêu, trọng số lấy từ metadata của file JSON
// (backend/run_quality.py). Ở đây chỉ có NHÃN và CÁCH ĐỊNH DẠNG — không
// chép lại hay tự tính lại ngưỡng (blueprint v3, quy ước cập nhật).
// ════════════════════════════════════════════════════════════

const DATA_URL = '../data/quality/latest.json';
// Tu vung va cach dinh dang dung chung voi man Chi tiet ma —
// xem web/shared/quality-view.js (nap truoc tep nay trong index.html).
const {
  DIMS, DIM_LABEL, STATUS_ORDER, STATUS_LABEL, MODEL_LABEL, BAND_ORDER,
  FLAG_LABEL, MISSING_GOV_LABEL, METRIC, esc, fmtMetric, nf1,
} = window.QV;

const state = {
  items: [], meta: {}, filtered: [],
  status: '', model: '', search: '',
  sort: { column: 'status', direction: 'asc' },
  selected: null,
};

// ──────────── Tiện ích ────────────
const dimScore = (it, d) => (it.dims?.[d] || {}).score ?? null;
const qualifyOf = d => (state.meta.thresholds?.qualify || {})[d];
const reviewOf = d => (state.meta.thresholds?.review_below || {})[d];

// ──────────── Tải dữ liệu ────────────
document.addEventListener('DOMContentLoaded', async () => {
  bindControls();
  try {
    const r = await fetch(`${DATA_URL}?_=${Date.now()}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    state.items = data.items || [];
    state.meta = { ...(data.metadata || {}), as_of: data.as_of, generated_at: data.generated_at };
    showBanner(data);
    renderStats();
    renderTabs();
    populateModels();
    render();
  } catch (e) {
    showBanner(null, e.message);
    document.getElementById('wl-tbody').innerHTML =
      '<tr><td colspan="7" class="td-empty">Chưa có dữ liệu chất lượng. File được tạo bởi ' +
      '<code>backend/run_quality.py</code> trong workflow định giá hằng tuần.</td></tr>';
  }
});

function showBanner(data, err) {
  const el = document.getElementById('wl-banner');
  let msg = '';
  if (!data) msg = `⚠ Không tải được dữ liệu chất lượng (${esc(err)}).`;
  else {
    const age = data.as_of ? Math.floor((Date.now() - new Date(data.as_of)) / 864e5) : null;
    if (age !== null && age > 8) msg = `⚠ Dữ liệu chấm ngày ${esc(data.as_of)}, đã ${age} ngày — cũ hơn một chu kỳ tuần.`;
    const fails = data.metadata?.failures?.length || 0;
    if (fails) msg += `${msg ? ' ' : '⚠ '}${fails} mã không lấy được BCTC.`;
  }
  el.innerHTML = msg;
  el.style.display = msg ? 'block' : 'none';
}

function renderStats() {
  document.getElementById('stat-total').textContent = state.items.length;
  document.getElementById('stat-date').textContent = state.meta.as_of
    ? 'chấm ' + new Date(state.meta.as_of).toLocaleDateString('vi-VN') : '—';
}

function renderTabs() {
  const counts = {};
  state.items.forEach(it => { counts[it.status] = (counts[it.status] || 0) + 1; });
  const tabs = [['', 'Tất cả', state.items.length], ...STATUS_ORDER.map(s => [s, STATUS_LABEL[s], counts[s] || 0])];
  const nav = document.getElementById('wl-tabs');
  nav.innerHTML = tabs.map(([k, label, n]) =>
    `<button class="wl-tab ${k === state.status ? 'active' : ''}" data-status="${k}" aria-pressed="${k === state.status}">
       ${k ? `<span class="wl-status-swatch st-${k}" aria-hidden="true"></span>` : ''}${esc(label)} <span class="wl-tab-n">${n}</span>
     </button>`).join('');
  nav.querySelectorAll('.wl-tab').forEach(b => b.addEventListener('click', () => {
    state.status = b.dataset.status;
    renderTabs();
    render();
  }));
}

function populateModels() {
  const sel = document.getElementById('wl-model');
  const models = [...new Set(state.items.map(it => it.model).filter(Boolean))].sort();
  sel.innerHTML = '<option value="">Tất cả</option>' +
    models.map(m => `<option value="${m}">${esc(MODEL_LABEL[m] || m)}</option>`).join('');
}

function bindControls() {
  document.getElementById('wl-search').addEventListener('input', e => {
    state.search = e.target.value.trim().toUpperCase();
    render();
  });
  document.getElementById('wl-model').addEventListener('change', e => {
    state.model = e.target.value;
    render();
  });
  document.querySelectorAll('#wl-table th.th-sort').forEach(th => th.addEventListener('click', () => {
    const col = th.dataset.sort;
    state.sort = { column: col, direction: state.sort.column === col && state.sort.direction === 'desc' ? 'asc' : 'desc' };
    if (col === 'ticker' || col === 'status' || col === 'band') {
      state.sort.direction = state.sort.column === col && th.classList.contains('sort-asc') ? 'desc' : 'asc';
    }
    render();
  }));
}

// ──────────── Bảng ────────────
function sortKey(it, col) {
  if (col === 'ticker') return it.ticker;
  if (col === 'status') return STATUS_ORDER.indexOf(it.status);
  if (col === 'band') return BAND_ORDER[it.valuation?.band] ?? 9;
  const v = dimScore(it, col);
  return v === null ? -1 : v;               // thiếu điểm xếp cuối khi giảm dần
}

function render() {
  const rows = state.items.filter(it =>
    (!state.status || it.status === state.status) &&
    (!state.model || it.model === state.model) &&
    (!state.search || it.ticker.includes(state.search)));
  const { column, direction } = state.sort;
  const dir = direction === 'asc' ? 1 : -1;
  rows.sort((a, b) => {
    const ka = sortKey(a, column), kb = sortKey(b, column);
    const c = typeof ka === 'string' ? ka.localeCompare(kb) : ka - kb;
    return c ? dir * c : (dimScore(b, 'quality') ?? -1) - (dimScore(a, 'quality') ?? -1);
  });
  state.filtered = rows;

  document.querySelectorAll('#wl-table th.th-sort').forEach(th => {
    th.classList.toggle('sort-asc', th.dataset.sort === column && direction === 'asc');
    th.classList.toggle('sort-desc', th.dataset.sort === column && direction === 'desc');
  });
  document.getElementById('result-count').textContent = `— ${rows.length}/${state.items.length} hiển thị`;

  const tbody = document.getElementById('wl-tbody');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="td-empty">Không có mã nào khớp bộ lọc</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(it => `
    <tr data-ticker="${esc(it.ticker)}" class="${it.ticker === state.selected ? 'selected' : ''}" tabindex="0">
      <td><span class="ticker-cell">${esc(it.ticker)}</span>
          <div class="wl-sub">${esc(MODEL_LABEL[it.model] || it.industry || '—')}</div></td>
      <td class="wl-col-status">${statusBadge(it.status)}
          <div class="wl-reason" title="${esc(it.reason)}">${esc(it.reason)}</div>${it.sharp_drops?.length
        ? `<span class="wl-drop" title="Giảm ≥ 15 điểm so với lần chấm trước">↓ ${it.sharp_drops.map(d => DIM_LABEL[d]).join(', ')}</span>` : ''}</td>
      ${DIMS.map(d => `<td>${dimBar(it, d)}</td>`).join('')}
      <td class="td-center">${bandBadge(it.valuation)}</td>
    </tr>`).join('');
  tbody.querySelectorAll('tr[data-ticker]').forEach(tr => {
    const open = () => select(tr.dataset.ticker);
    tr.addEventListener('click', open);
    tr.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
  });
}

const statusBadge = window.QV.statusBadge;

const bandBadge = window.QV.bandBadge;

// Nguong lay tu metadata cua chinh tep JSON dang hien thi.
const dimBar = (it, d) => window.QV.dimBar(it, d, state.meta.thresholds);

// ──────────── Chi tiết ────────────
function select(ticker) {
  state.selected = ticker;
  document.querySelectorAll('#wl-tbody tr').forEach(tr => tr.classList.toggle('selected', tr.dataset.ticker === ticker));
  const it = state.items.find(x => x.ticker === ticker);
  if (!it) return;
  document.getElementById('detail-empty').style.display = 'none';
  const box = document.getElementById('detail-content');
  box.style.display = 'block';

  const spec = (state.meta.model_specs || {})[it.model] || {};
  const dimSections = ['quality', 'growth', 'resilience'].map(d => {
    const dim = it.dims?.[d];
    const table = window.QV.metricsTable(it, spec[d]);
    const head = dim?.score == null ? '—' : Math.round(dim.score);
    const cov = dim ? ` · phủ ${Math.round((dim.coverage || 0) * 100)}%` : '';
    return `<div class="detail-section">
      <div class="detail-section-title">${DIM_LABEL[d]}: <b>${head}</b><small>${cov}</small></div>
      ${table || '<p class="muted">Mô hình ngành chưa kích hoạt.</p>'}
    </div>`;
  }).join('');

  const gov = it.dims?.governance || {};
  const flags = window.QV.flagList(it, state.meta.governance_penalty);
  const govMissing = (gov.missing || []).map(k => MISSING_GOV_LABEL[k] || k).join(', ');
  const v = it.valuation || {};

  box.innerHTML = `
    <div class="detail-header">
      <div class="detail-ticker">${esc(it.ticker)}</div>
      <div class="detail-industry">${esc(MODEL_LABEL[it.model] || '—')} · ${esc((it.industry || '').replace(/_/g, ' '))}</div>
    </div>
    <div class="detail-verdict-row">${statusBadge(it.status)}<span class="wl-period">BCTC năm ${esc(it.latest_annual || '—')} · quý ${esc(it.latest_quarter || '—')}</span></div>
    <div class="band-reason">${esc(it.reason)}</div>
    ${dimSections}
    <div class="detail-section">
      <div class="detail-section-title">Quản trị: <b>${gov.score ?? '—'}</b><small> · phủ ${Math.round((gov.coverage || 0) * 100)}%</small></div>
      ${flags || '<p class="muted">Không có cờ.</p>'}
      ${govMissing ? `<p class="muted">Thiếu dữ liệu cho: ${esc(govMissing)}</p>` : ''}
      ${window.QV.notEvaluated({ ...(state.meta.governance_not_evaluated || {}),
                                 ...(state.meta.veto_not_evaluated || {}),
                                 ...(it.model === 'BANK' ? (state.meta.bank_not_evaluated || {}) : {}) })}
      ${it.veto ? `<p class="wl-veto">Veto: ${esc(it.veto)}</p>` : ''}
    </div>
    <div class="detail-section">
      <div class="detail-section-title">Định giá</div>
      <div>${bandBadge(v)} ${v.upside_pct == null ? '' : `<span class="wl-upside">${v.upside_pct > 0 ? '+' : ''}${nf1.format(v.upside_pct)}%</span>`}
        ${v.confidence == null ? '' : `<small class="muted"> · tin cậy ${Math.round(v.confidence)}%</small>`}</div>
      ${v.reason ? `<p class="muted">${esc(v.reason)}</p>` : ''}
      <p><a class="link-btn" href="../valuation/index.html">Xem trang định giá →</a></p>
    </div>
    <div class="band-disclaimer">Thứ tự ưu tiên nghiên cứu, không phải khuyến nghị mua bán.</div>
    <p class="wl-back"><a href="#wl-table" class="link-btn">↑ Về bảng</a></p>`;
  if (window.matchMedia('(max-width: 1024px)').matches) {
    document.getElementById('wl-detail').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}
