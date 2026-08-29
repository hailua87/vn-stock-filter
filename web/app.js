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
      // Không cộng điểm (trùng với TK bullish) — giữ làm nhãn chất lượng ⭐
      { key: 'ich_recent_tk_cross',   name: 'TK vừa cắt lên (≤5 phiên) ⭐', cat: 'squeeze', noScore: true },
      { key: 'ich_price_above_cloud', name: 'Giá trên Cloud',               cat: 'trend' },
      { key: 'ich_cloud_bullish',     name: 'Cloud bullish (A > B)',        cat: 'trend' },
      { key: 'ich_chikou_free',       name: 'Chikou thoát kháng cự',        cat: 'flow' },
      { key: 'ich_future_cloud_bullish', name: 'Mây tương lai bullish (+26)', cat: 'trend' },
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

// Exchange override map — fixes vnstock listing bugs where ticker is reported
// on wrong exchange (e.g. DVN appears as HOSE but actually trades on UPCOM).
// This is a frontend safety net; the backend also corrects via top_liquid.py.
// Source: VN stock listing as of 2026, ticker → correct exchange.
const EXCHANGE_OVERRIDES = {
  // UPCOM tickers commonly misreported
  'DVN': 'UPCOM',
  'ACV': 'UPCOM', 'BSR': 'UPCOM', 'VEA': 'UPCOM', 'VGI': 'UPCOM',
  'OIL': 'UPCOM', 'QNS': 'UPCOM', 'VTP': 'UPCOM', 'MCH': 'UPCOM',
  'MSR': 'UPCOM', 'SIP': 'UPCOM', 'VGT': 'UPCOM', 'LTG': 'UPCOM',
  'FOX': 'UPCOM', 'MFS': 'UPCOM', 'BVB': 'UPCOM', 'AAS': 'UPCOM',
  'VAB': 'UPCOM', 'SBS': 'UPCOM', 'NAB': 'UPCOM',
};

function correctExchange(ticker, originalExchange) {
  return EXCHANGE_OVERRIDES[ticker] || originalExchange;
}

let activeStrategy = 'pre_breakout';
function currentConfig()   { return STRATEGIES[activeStrategy]; }
function currentCriteria() { return currentConfig().criteria; }
function currentMaxScore() { return currentConfig().maxScore; }
function currentDataDir()  { return currentConfig().dataDir; }

// ──────────── Thống kê: khoá thiếu phải hiện "—", không được hiện 0 ────────
//
// `|| 0` cũ biến khoá VẮNG thành một con số trông hợp lệ. Dashboard hiện
// "0 mã quét" cạnh 105 tín hiệu — một điều kiện báo động mà không ai thấy vô
// lý, vì 0 là một con số và con số thì trông như dữ liệu. Nếu chỗ đó hiện "—"
// thì lỗi đọc sai tên khoá (`universe_size` vs `total_scanned`) đã lộ ngay ngày
// đầu thay vì sống nhiều tháng.
//
// Số không phải là "không biết".
const STAT_UNKNOWN = '—';

function statNumber(v) {
  if (v === null || v === undefined) return STAT_UNKNOWN;
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString() : STAT_UNKNOWN;
}

const state = {
  raw: [],
  filtered: [],
  currentDate: null,
  latestDate: null,
  availableDates: [],
  selectedTicker: null,
  // FIX (2026-05-26): metadata về lần chạy gần nhất của workflow (intraday vs EOD).
  // Đọc từ JSON metadata fields: run_type, run_time_ict, run_date_ict.
  // Dùng để hiển thị badge "INTRADAY 12:00" / "EOD 17:00" cho user biết độ tươi data.
  runMetadata: { runType: null, runTimeIct: null, runDateIct: null },
  // Bối cảnh thị trường từ metadata.market_context — dùng làm CỔNG cho tỷ trọng
  // khuyến nghị, không cộng vào điểm số (xem buildRecommendation).
  marketContext: null,
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

  // Click mot hang -> mo drawer chi tiet. O MOI be rong, khong chi mobile.
  //
  // Truoc day co cong `matchMedia('(max-width: 768px)')` o day. Bo di la thay
  // doi BAT BUOC cho bo cuc moi: panel chi tiet khong con la track grid, nen
  // tren desktop no chi hien khi co .mobile-open. Giu cong lai thi panel bien
  // mat han o desktop ma khong co gi thay the.
  document.addEventListener('detail-opened', () => {
    detailCol.classList.add('mobile-open');
    backdrop.classList.add('show');
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
      document.getElementById('market-text').textContent = 'ĐANG GIAO DỊCH';
    } else {
      stateEl.classList.remove('open');
      document.getElementById('market-text').textContent = 'NGOÀI GIỜ';
    }
  };
  tick();
  setInterval(tick, 1000);
}

/**
 * Thay chỉ báo "LIVE" bằng ĐỘ TƯƠI THẬT của dữ liệu.
 *
 * Vì sao: header có chấm xanh "LIVE" + đồng hồ chạy từng giây, trong khi dữ
 * liệu chỉ cập nhật 2 lần/ngày. Người dùng mới sẽ hiểu là realtime. Đây cùng
 * một họ lỗi với bug banner demo: giao diện hứa nhiều hơn dữ liệu thực có.
 * Với sản phẩm tài chính, đó không phải chuyện thẩm mỹ.
 */
function updateDataFreshness() {
  const dot = document.getElementById('live-dot');
  const text = document.getElementById('live-text');
  if (!text) return;

  // Doc state.runMetadata, KHONG doc thang metadata cua mot nguon.
  // O che do Tong hop co 4 nguon; vong lap o loadCombinedData chon nguon co
  // run_time_ict MOI NHAT roi gan vao state.runMetadata. Doc thang tung nguon
  // se hien nguon CUOI CUNG trong vong lap, khong phai nguon moi nhat.
  const meta = state.runMetadata || {};

  // Doc run_time_ict / run_date_ict, KHONG doc generated_at.
  //
  // generated_at la `datetime.now().isoformat()` cua runner — gio UTC. Cho nay
  // in ra "EOD 29/08 03:28" trong khi #run-badge ngay ben duoi in "EOD 10:28"
  // tu run_time_ict. CUNG MOT SU KIEN, hai con so lech 7 tieng, hien cung luc
  // tren mot man hinh. Nguoi doc khong co cach nao biet cai nao dung.
  // run_time_ict la mui gio nguoi dung dang song, nen no la cai dung.
  const hhmm = meta.runTimeIct;
  const ymd  = meta.runDateIct;
  const runType = meta.runType;

  if (!hhmm || !ymd) {
    // Thieu thi noi KHONG BIET, KHONG quay ve generated_at: mot con so sai mui
    // gio con te hon mot dau gach. Cung nguyen tac voi statNumber().
    text.textContent = STAT_UNKNOWN;
    text.title = 'Khong ro thoi diem ghi du lieu';
    if (dot) dot.className = 'live-dot stale';
    return;
  }

  const [y, mo, da] = ymd.split('-');
  const label = runType === 'intraday' ? 'GIỮA PHIÊN' : 'EOD';
  text.textContent = `${label} ${da}/${mo} ${hhmm}`;

  // Tooltip phan biet intraday/eod — chuyen tu renderRunBadge (da go). Do la
  // phan duy nhat cua badge noi dieu ma nhan van ban khong noi duoc.
  // Ban cu ghi "Lan update tiep theo: 17:00 ICT" — SAI tu khi doi cron; lich
  // that la 12:05 ICT (intraday) va 23:05 ICT (EOD), xem daily-scan.yml:34-35.
  text.title = runType === 'intraday'
    ? `Ghi lúc ${hhmm} ICT ngày ${da}/${mo}/${y} (giữa phiên). Giá khớp tại thời `
      + `điểm quét — chưa phải giá đóng cửa. Ca EOD chạy 23:05 ICT.`
    : `Ghi lúc ${hhmm} ICT ngày ${da}/${mo}/${y} (sau đóng cửa). Đây là giá đóng `
      + `cửa chính thức của phiên. Không phải realtime.`;

  if (dot) {
    // Tuoi du lieu dung chinh moc ICT do, dung lai gio UTC.
    // > 30 gio nghia la da lo it nhat mot phien.
    const wroteAt = new Date(`${ymd}T${hhmm}:00+07:00`);
    const ageHours = (Date.now() - wroteAt.getTime()) / 3600000;
    dot.className = 'live-dot' + (Number.isFinite(ageHours) && ageHours > 30 ? ' stale' : '');
  }
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

  // GỘP HAI Ô TÌM KIẾM: trước đây ô tìm của Analyzer luôn nằm trên topbar,
  // cạnh ô "Tìm mã" trong sidebar — hai ô trông giống nhau nhưng hành vi khác
  // hẳn (một cái mở phân tích chi tiết, một cái lọc bảng), người dùng không
  // biết dùng cái nào. Nay ô Analyzer chỉ xuất hiện đúng lúc nó có tác dụng.
  const analyzerBox = document.querySelector('.topbar-analyzer');
  if (analyzerBox) analyzerBox.hidden = (strategy !== 'analyzer');

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
      return { key, signals: applyExchangeOverrides(d.signals || []), metadata: d.metadata || {} };
    } catch (e) {
      console.warn(`Combined: failed to load ${key}:`, e.message);
      return { key, signals: [], metadata: {} };
    }
  };

  const results = await Promise.all(sources.map(loadOne));

  // Index signals by ticker per strategy
  const byTicker = {};      // ticker -> { strategies: Set, data: best signal record }
  // null chứ không phải 0: chưa file nào khai `total_scanned` thì đó là KHÔNG
  // BIẾT, khác hẳn với đã biết và bằng 0.
  let universeSize = null;   // = metadata.total_scanned, tên khoá backend thực ghi
  let demoFlag = false;
  let scanDate = null;

  for (const { key, signals, metadata } of results) {
    state.combined.sourceData[key] = { signals, metadata };
    if (metadata.total_scanned && metadata.total_scanned > universeSize) universeSize = metadata.total_scanned;
    if (metadata.demo) demoFlag = true;
    if (metadata.session_date) scanDate = metadata.session_date;
    if (metadata.market_context && metadata.market_context.available) {
      state.marketContext = metadata.market_context;
      renderMarketContext(metadata.market_context, metadata.intraday);
    }
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

  // FIX (2026-05-26): pick run metadata từ nguồn có run_time_ict mới nhất.
  // 4 strategy bình thường chạy cùng workflow → metadata giống nhau, nhưng phòng
  // trường hợp 1 nguồn fail và còn data cũ → ưu tiên nguồn có timestamp mới hơn.
  let bestRunMeta = { runType: null, runTimeIct: null, runDateIct: null };
  for (const { metadata } of results) {
    const m = extractRunMetadata({ metadata });
    if (!m.runDateIct) continue;
    const isNewer = !bestRunMeta.runDateIct
      || m.runDateIct > bestRunMeta.runDateIct
      || (m.runDateIct === bestRunMeta.runDateIct && (m.runTimeIct || '') > (bestRunMeta.runTimeIct || ''));
    if (isNewer) bestRunMeta = m;
  }
  state.runMetadata = bestRunMeta;

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
    document.getElementById('stat-scanned').textContent = statNumber(universeSize);
    const demoBanner = document.getElementById('demo-banner');
    // `has-banner` da bo: .dashboard dung flex: 1 nen no tu co lai khi banner
    // chiem cho, khong con hang 33px nao de bat/tat.
    demoBanner.style.display = demoFlag ? 'block' : 'none';
    render();
  }
}

// Helper: apply EXCHANGE_OVERRIDES to a list of signals (mutates exchange field)
function applyExchangeOverrides(signals) {
  if (!Array.isArray(signals)) return signals;
  for (const s of signals) {
    if (s && s.ticker && EXCHANGE_OVERRIDES[s.ticker]) {
      const corrected = EXCHANGE_OVERRIDES[s.ticker];
      if (s.exchange !== corrected) {
        s.exchange = corrected;
      }
    }
  }
  return signals;
}

// ──────────── Load data ────────────

// FIX (2026-05-26): trích run metadata (intraday vs EOD) từ JSON.
// Workflow tag JSON với 3 fields: run_type, run_time_ict, run_date_ict.
// Data cũ (chưa có tag) → trả null cho các field → badge không hiển thị.
function extractRunMetadata(data) {
  const m = data?.metadata || {};
  // KHONG goi updateDataFreshness o day: ham nay chay trong VONG LAP o che do
  // Tong hop (mot lan moi nguon), nen goi tu day se hien nguon cuoi cung. Chi
  // bao do tuoi duoc cap nhat mot lan trong render(), doc state.runMetadata.
  return {
    runType: m.run_type || null,          // 'intraday' | 'eod' | null
    runTimeIct: m.run_time_ict || null,    // 'HH:MM' | null
    runDateIct: m.run_date_ict || null,    // 'YYYY-MM-DD' | null
  };
}

async function loadLatestFirst() {
  try {
    const url = `${currentDataDir()}/latest.json?_=${Date.now()}`;
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    state.raw = applyExchangeOverrides(data.signals || []);
    state.currentDate = data.metadata?.session_date || null;
    state.latestDate = state.currentDate;
    state.runMetadata = extractRunMetadata(data);

    document.getElementById('stat-scanned').textContent =
      statNumber(data.metadata?.total_scanned);
    const demoBanner = document.getElementById('demo-banner');
    // Xem ghi chu ve `has-banner` o loadCombinedData.
    demoBanner.style.display = data.metadata?.demo ? 'block' : 'none';

    render();
  } catch (e) {
    console.error('Load latest failed:', e);
    document.getElementById('signal-rows').innerHTML =
      `<tr><td colspan="15" class="empty error-state">
         <div class="error-title">Không tải được dữ liệu</div>
         <div class="error-detail">${escapeAttr(e.message)}</div>
         <div class="error-detail">${navigator.onLine ? 'Máy chủ dữ liệu có thể đang bận.' : 'Thiết bị đang offline.'}</div>
         <button class="btn-ghost" onclick="location.reload()">↻ Thử lại</button>
       </td></tr>`;
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
    state.raw = applyExchangeOverrides(data.signals || []);
    state.currentDate = data.metadata?.session_date || date;
    state.runMetadata = extractRunMetadata(data);
    document.getElementById('stat-scanned').textContent =
      statNumber(data.metadata?.total_scanned);
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
      ${isLatest ? '• ' : ''}${formatDateLong(d)}
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

/**
 * Gộp nhiều lần gọi liên tiếp thành một, chờ `wait` ms sau lần gọi cuối.
 * Sự kiện được giữ lại vì handler cần `e.target`.
 */
/**
 * Đơn vị giá hiển thị.
 *
 * Toàn bộ pipeline technical dùng đơn vị quote của vnstock (NGHÌN VND) — giống
 * bảng điện. Nhưng trước đây không chỗ nào trên giao diện viết ra điều đó: cột
 * hiện "137.3" và người dùng phải tự đoán.
 *
 * Đây đúng là loại nhầm lẫn đã gây ra bug sai 1000× trong module định giá.
 * Nếu chính hệ thống còn nhầm được thì không thể trách người dùng.
 */
const PRICE_UNIT_LABEL = 'nghìn đ';
function fmtPriceUnit() { return PRICE_UNIT_LABEL; }

function debounce(fn, wait = 150) {
  let timer = null;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), wait);
  };
}

// ──────────── Filters ────────────
function bindFilters() {
  document.querySelectorAll('.chip-row').forEach(group => {
    const filter = group.dataset.filter;
    group.querySelectorAll('.chip').forEach(chip => {
      // aria-pressed: truoc day trang thai bat/tat cua chip CHI ton tai bang mau.
      // Nguoi dung trinh doc man hinh khong biet bo loc nao dang bat.
      chip.setAttribute('aria-pressed', chip.classList.contains('active') ? 'true' : 'false');
      chip.addEventListener('click', () => {
        group.querySelectorAll('.chip').forEach(c => {
          c.classList.remove('active');
          c.setAttribute('aria-pressed', 'false');
        });
        chip.classList.add('active');
        chip.setAttribute('aria-pressed', 'true');
        state.filters[filter] = chip.dataset.value;
        // Update Ichimoku filter hint dynamically
        if (filter === 'ich_special') {
          const hint = document.getElementById('ich-filter-hint');
          if (hint) {
            const map = {
              '': 'Lọc tín hiệu Ichimoku theo loại',
              'recent_cross': 'Lọc mã có Tenkan vừa cắt lên Kijun (≤5 phiên)',
              'turnaround': 'Đảo chiều sớm (CHẶT): TK ≤2 phiên + giá break cloud + vol ≥1.5× + tăng ≥2.5%',
            };
            hint.textContent = map[chip.dataset.value] || map[''];
          }
        }
        render();
      });
    });
  });

  // Debounce: mỗi ký tự gõ vào từng dựng lại TOÀN BỘ tbody bằng innerHTML.
  // Với 50-200 dòng thì tạm ổn, nhưng universe lên 400 mã sẽ giật, và việc
  // thay innerHTML còn xoá luôn trạng thái chọn dòng của người dùng.
  document.getElementById('search').addEventListener('input', debounce(e => {
    state.filters.search = e.target.value.trim().toUpperCase();
    render();
  }, 150));

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
//
// Modal cũ chỉ đổi `display` — thiếu 4 hành vi mà người dùng mong đợi ở một hộp
// thoại: đóng bằng Esc, giam focus bên trong, trả focus về nút mở khi đóng, và
// ẩn nội dung nền khỏi trình đọc màn hình.
function bindHelp() {
  const modal = document.getElementById('help-modal');
  const openBtn = document.getElementById('help-btn');
  const closeBtn = document.getElementById('help-close');
  let lastFocused = null;

  const FOCUSABLE = 'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])';

  function open() {
    lastFocused = document.activeElement;
    modal.hidden = false;
    modal.style.display = 'flex';
    openBtn.setAttribute('aria-expanded', 'true');
    (modal.querySelector(FOCUSABLE) || modal).focus();
    document.addEventListener('keydown', onKeydown, true);
  }

  function close() {
    modal.style.display = 'none';
    modal.hidden = true;
    openBtn.setAttribute('aria-expanded', 'false');
    document.removeEventListener('keydown', onKeydown, true);
    // Trả focus về đúng nơi người dùng đã rời đi
    if (lastFocused && lastFocused.focus) lastFocused.focus();
  }

  function onKeydown(e) {
    if (e.key === 'Escape') {
      e.stopPropagation();
      close();
      return;
    }
    if (e.key !== 'Tab') return;

    // Giam focus: Tab ở phần tử cuối quay về đầu và ngược lại. Không có cái này,
    // Tab sẽ đi ra ngoài modal và người dùng bàn phím lạc mất hộp thoại.
    const items = [...modal.querySelectorAll(FOCUSABLE)].filter(el => el.offsetParent !== null);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  openBtn.setAttribute('aria-expanded', 'false');
  openBtn.setAttribute('aria-controls', 'help-modal');
  openBtn.addEventListener('click', open);
  closeBtn.addEventListener('click', close);
  modal.addEventListener('click', e => {
    if (e.target === modal) close();
  });
}

// ──────────── Collapse filters column ────────────
function bindCollapseFilters() {
  const btn  = document.getElementById('collapse-filters');
  const title = document.querySelector('.col-filters .col-title');
  const dash = document.getElementById('dashboard');
  if (!btn || !dash) return;

  // Trang thai duoc phan anh vao ARIA, khong chi vao ky tu mui ten.
  // Ban cu doi huong mui ten bang `transform: rotate(180deg)` — hinh hoc thuan
  // tuy, trinh doc man hinh khong thay gi, nen aria-label van doc "Thu gon cot
  // bo loc" ke ca khi cot DA thu gon.
  const apply = () => {
    const collapsed = dash.classList.contains('filters-collapsed');
    btn.textContent = collapsed ? '›' : '‹';
    btn.title = collapsed ? 'Mở lại bộ lọc' : 'Thu gọn bộ lọc';
    btn.setAttribute('aria-label', collapsed ? 'Mở lại cột bộ lọc' : 'Thu gọn cột bộ lọc');
    btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
  };

  const toggle = () => { dash.classList.toggle('filters-collapsed'); apply(); };

  btn.setAttribute('aria-controls', 'col-filters');
  btn.addEventListener('click', toggle);

  // Ca dai chu "BỘ LỌC" xoay doc cung mo lai duoc: o trang thai thu gon no la
  // thu to nhat trong 36px, nguoi dung bam vao do theo ban nang.
  if (title) {
    title.addEventListener('click', () => {
      if (dash.classList.contains('filters-collapsed')) toggle();
    });
  }

  apply();
}


// ──────────── Render table ────────────
function render() {
  state.filtered = applyFilters();
  document.getElementById('result-count').textContent = state.filtered.length;
  // `stat-total` da duoc go: no trung lap voi `result-count` ngay tren bang.
  document.getElementById('stat-total')?.replaceChildren(String(state.raw.length));
  document.getElementById('stat-aplus').textContent =
    state.raw.filter(s => s.rating === 'A+').length;

  // Update date in topbar
  const statDate = document.getElementById('stat-date');
  if (state.currentDate) {
    const [y, m, day] = state.currentDate.split('-');
    const isLatest = state.currentDate === state.latestDate;
    // Ky hieu phien moi nhat la "•", GIONG #date-select trong panel bo loc.
    //
    // Truoc day cho nay dung chu "LIVE" con o chon ngay dung "•" — hai ky hieu
    // cho cung mot y, tren cung mot man hinh. Chon "•" chu khong phai "LIVE":
    // chinh chu thich cua updateDataFreshness da ghi rang nhan "LIVE" bi go khoi
    // header vi no hua realtime trong khi du lieu cap nhat 2 lan/ngay. Giu no o
    // day la dua lai dung loi do vao.
    //
    // Bo luon dau "· " dan dau: da co <span class="hs-sep">·</span> ngay truoc
    // trong index.html, nen chuoi cu hien ra HAI dau cham lien nhau.
    statDate.textContent = isLatest ? `• ${day}/${m}` : `${day}/${m}`;
    // --text-dim chu khong phai --text-mute: mute chi 3.34x khi hover, duoi AA.
    statDate.style.color = isLatest ? 'var(--up)' : 'var(--text-dim)';
  } else {
    // Không có ngày phiên thì nói KHÔNG BIẾT, đừng để nguyên giá trị lần trước:
    // một ngày cũ nằm lại trên màn hình còn tệ hơn một dấu gạch.
    statDate.textContent = STAT_UNKNOWN;
    statDate.style.color = 'var(--text-dim)';
  }

  // Chi bao do tuoi o topbar. Goi tu day, mot lan, sau khi state.runMetadata da
  // duoc chot — ke ca o che do Tong hop noi co nhieu nguon.
  updateDataFreshness();

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
    tbody.innerHTML = `<tr><td colspan="15" class="empty">Không có tín hiệu khớp bộ lọc</td></tr>`;
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


/**
 * Ô %1D với màu theo quy ước bảng điện Việt Nam.
 *
 * Vì sao quan trọng hơn thẩm mỹ: mã đang dư mua TRẦN thì bạn KHÔNG MUA ĐƯỢC.
 * Một "tín hiệu breakout" trên mã trần cứng là tín hiệu không thực hiện được.
 * Tương tự, mã nằm sàn thì không thoát được hàng — rủi ro thực tế lớn hơn
 * nhiều so với những gì mức cắt lỗ trên giấy thể hiện.
 *
 * Quy ước: TÍM = trần · XANH LAM = sàn · VÀNG = tham chiếu · xanh/đỏ = tăng/giảm
 */
function renderChange1D(s) {
  const v = s.m_change_1d_pct;
  if (v === null || v === undefined) return '<span class="dim">—</span>';

  const status = s.m_limit_status || 'normal';
  const locked = s.m_limit_locked;
  const sign = v > 0 ? '+' : '';
  const text = `${sign}${Number(v).toFixed(2)}%`;

  const cls = {
    ceiling: 'limit-up',
    floor: 'limit-down',
    reference: 'limit-ref',
  }[status] || (v > 0 ? 'up' : v < 0 ? 'down' : 'flat');

  const mark = status === 'ceiling' ? '▲' : status === 'floor' ? '▼' : '';
  const lock = locked && (status === 'ceiling' || status === 'floor')
    ? '<span class="limit-lock" title="Khoá cứng — cả phiên chỉ khớp một mức giá">🔒</span>'
    : '';
  const title = s.m_tradable_warning ? ` title="${escapeAttr(s.m_tradable_warning)}"` : '';

  return `<span class="${cls}"${title}>${mark}${text}</span>${lock}`;
}

/** Thoát ký tự cho thuộc tính HTML — dữ liệu tuy tự sinh nhưng mã đến từ API ngoài. */
function escapeAttr(str) {
  return String(str).replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

// LUU Y KHI SUA BANG: moi <td> phai mang DUNG class prio-* nhu <th> tuong ung
// trong index.html. Khoi @media an cot bang `.signal-table .prio-N { display: none }`
// — quy tac do ap cho CA th LAN td, nhung neu td thieu class thi chi HANG TIEU DE
// mat o, con hang du lieu giu nguyen => bang LECH COT.
// Truoc 29/08/2026 co 9/15 cot thieu, nen o 402px tieu de chi con 5 cot ma moi
// hang du lieu van 15 o: nguoi dung thay HOSE va KLGD duoi tieu de GIA va DIEM.
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
      <td class="th-idx prio-4">${idx}</td>
      <td class="ticker-with-badges"><span class="ticker-cell">${s.ticker}</span>${eventFlag}<span class="ticker-badges">${badgesInline}</span></td>
      <td class="prio-3"><span class="exchange-cell">${s.exchange}</span></td>
      <td class="num td-price">${fmtPrice(s.close)}</td>
      <td class="num prio-1">${renderChange1D(s)}</td>
      <td class="num prio-3 ${changeClass}">${sign}${change.toFixed(2)}%</td>
      <td class="num prio-2">${fmtVolume(s.volume)}</td>
      <td class="num prio-3">${fmtValue(s.close, s.volume)}</td>
      <td class="num prio-3">${(s.m_vol_ratio || 0).toFixed(2)}×</td>
      <td class="num prio-3">${(s.m_rsi14 || 0).toFixed(0)}</td>
      <td class="num prio-4">${supCell}</td>
      <td class="num prio-4">${resCell}</td>
      <td class="combined-criteria-cell prio-4" style="display:none;"></td>
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
    <td class="th-idx prio-4">${idx}</td>
    <td><span class="ticker-cell">${s.ticker}</span>${tkCrossFlag}${turnaroundFlag}${eventFlag}</td>
    <td class="prio-3"><span class="exchange-cell">${s.exchange}</span></td>
    <td class="num td-price">${fmtPrice(s.close)}</td>
    <td class="num prio-1">${renderChange1D(s)}</td>
    <td class="num prio-3 ${changeClass}">${sign}${change.toFixed(2)}%</td>
    <td class="num prio-2">${fmtVolume(s.volume)}</td>
    <td class="num prio-3">${fmtValue(s.close, s.volume)}</td>
    <td class="num prio-3">${(s.m_vol_ratio || 0).toFixed(2)}×</td>
    <td class="num prio-3">${(s.m_rsi14 || 0).toFixed(0)}</td>
    <td class="num prio-4">${supCell}</td>
    <td class="num prio-4">${resCell}</td>
    <td class="prio-4"><div class="criteria-pills">${pills}</div></td>
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
  // Dang ngan T2..T7/CN thay vi "Thứ Sáu". Ly do la be rong: <select> trong
  // panel bo loc chi co ~168px cho chu, ma "Thứ Sáu · 28/08/2026" can 168px va
  // "Thứ Sáu · 28/08/2026  (mới nhất)" can ~248px — tran ra ngoai cot 240px,
  // sinh thanh cuon ngang keo lech moi khoi khac trong panel.
  // T2..T7/CN la quy uoc quen thuoc o VN, khong mat thong tin nao.
  const days = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'];
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

  // ── Relative strength vs VN-Index ──────────────────────────────────────
  // RS là yếu tố dự báo mạnh nhất trong các nghiên cứu momentum, nhưng nó KHÔNG
  // được cộng vào điểm số (điểm số thuộc về từng chiến lược). Ở đây nó điều
  // chỉnh mức độ tự tin của khuyến nghị.
  const rsRank = primarySignal?.m_rs_rank;
  if (typeof rsRank === 'number') {
    if (rsRank < 40) {
      warnings.push(`RS ${rsRank}/99 — mã đang YẾU hơn thị trường. Tín hiệu kỹ thuật ` +
                    `trên nền sức mạnh tương đối kém có tỷ lệ thất bại cao hơn đáng kể`);
    } else if (rsRank >= 80) {
      warnings.push(`RS ${rsRank}/99 — mã dẫn dắt, khoẻ hơn ${rsRank}% thị trường`);
    }
  }
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
    // Diễn đạt trung thực: 4 chiến lược này KHÔNG độc lập. Cả bốn đều là bộ lọc
    // xu hướng mua lên, dùng chung MA của cùng một chuỗi giá, nên tương quan rất
    // cao. Gọi đó là "4 nguồn xác nhận độc lập" là sai về mặt thống kê và khiến
    // người dùng tự tin quá mức.
    desc = 'Mã pass cả 4 chiến lược với nhiều A+ — setup kỹ thuật rất đồng thuận. ' +
           'Lưu ý: 4 chiến lược này cùng nhóm xu hướng nên tương quan cao, ' +
           'không phải 4 nguồn xác nhận độc lập.';
    position = '8-12% NAV';
  } else if (passCount === 4) {
    cls = 'rec-strong-buy';
    stars = '⭐⭐⭐⭐';
    title = 'MUA MẠNH';
    desc = 'Mã pass cả 4 chiến lược — setup kỹ thuật đồng thuận cao. ' +
           'Lưu ý: 4 chiến lược cùng nhóm xu hướng nên tương quan cao với nhau.';
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
    position = scalePosition(position, 0.7);
  }

  // ── CỔNG BỐI CẢNH THỊ TRƯỜNG ──────────────────────────────────────────
  // Phần lớn tín hiệu breakout thất bại khi VN-Index dưới MA50/MA200. Trước
  // đây UI đưa ra cùng một tỷ trọng "8-12% NAV" bất kể thị trường đang uptrend
  // hay downtrend — đó là thiếu sót lớn nhất về mặt quản trị rủi ro.
  //
  // Regime KHÔNG được cộng vào điểm (điểm đo chất lượng setup của từng mã);
  // nó nhân vào TỶ TRỌNG, tức tách bạch "tín hiệu tốt đến đâu" khỏi "nên đặt
  // bao nhiêu tiền".
  const ctx = state.marketContext;
  if (ctx && ctx.available && ctx.position_size_multiplier < 1) {
    position = scalePosition(position, ctx.position_size_multiplier);
    const pct = Math.round(ctx.position_size_multiplier * 100);
    warnings.unshift(
      `Bối cảnh thị trường ${ctx.regime === 'risk_off' ? 'BẤT LỢI' : 'trung tính'} — ` +
      `đã giảm tỷ trọng đề xuất còn ~${pct}% mức thường. ${ctx.label}`
    );
    if (ctx.regime === 'risk_off' && (passCount >= 3)) {
      desc += ' Lưu ý: setup đẹp nhưng thị trường chung đang bất lợi — ' +
              'phần lớn breakout thất bại trong giai đoạn này.';
    }
  }

  // Độ rộng thị trường: chỉ số có thể được kéo bởi vài mã vốn hoá lớn trong
  // khi đa số cổ phiếu đã giảm.
  const breadth = ctx?.breadth?.pct_above_ma50;
  if (typeof breadth === 'number' && breadth < 35) {
    warnings.push(`Độ rộng yếu — chỉ ${breadth}% số mã nằm trên MA50`);
  }

  return { cls, stars, title, desc, position, warnings };
}

/**
 * Co giãn chuỗi tỷ trọng dạng "8-12% NAV" theo hệ số.
 * Tách riêng để logic co tỷ trọng chỉ tồn tại ở MỘT chỗ — trước đây nó nằm
 * inline trong nhánh RSI với công thức trừ cứng (−2/−3 điểm phần trăm).
 */
function scalePosition(position, factor) {
  if (!position || factor >= 1) return position;
  return position.replace(/(\d+)-(\d+)%\s*NAV/, (_, a, b) => {
    const lo = Math.max(1, Math.round(+a * factor));
    const hi = Math.max(lo + 1, Math.round(+b * factor));
    return `${lo}-${hi}% NAV`;
  });
}

// Compute entry levels for analyzer (similar to existing detail panel)
/**
 * Kế hoạch vào lệnh.
 *
 * LỖI ĐÃ SỬA — LỜI KHUYÊN TỰ MÂU THUẪN:
 *   Bản cũ luôn đặt entry tại Fibonacci golden support, tức THẤP HƠN giá hiện
 *   tại, trong khi Pre-Breakout lại đi tìm mã ĐANG cách đỉnh 20 phiên ≤ 3%.
 *   Người dùng làm theo sẽ hoặc không bao giờ khớp lệnh (giá chạy tiếp), hoặc
 *   nếu giá về tới đó thì setup breakout đã hỏng rồi.
 *   Stop lại lấy hỗ trợ SÂU NHẤT trong 3 mức — có khi −15% dưới entry, gấp đôi
 *   rủi ro mà người dùng nghĩ mình đang nhận.
 *
 * Cách làm mới — hai kịch bản, và nói thẳng đang dùng cái nào:
 *   BREAKOUT (giá sát đỉnh) : mua khi vượt đỉnh; stop = max(hỗ trợ gần, 2×ATR)
 *   PULLBACK (giá xa đỉnh)  : chờ về vùng hỗ trợ mới mua
 *
 * Stop luôn bị chặn ở mức lỗ tối đa, và kế hoạch bị TỪ CHỐI nếu R:R quá thấp —
 * thà không đưa lời khuyên còn hơn đưa lời khuyên xấu.
 */
const MAX_STOP_PCT = 0.08;        // không bao giờ đề xuất cắt lỗ quá 8%
const MIN_ACCEPTABLE_RR = 1.5;

function computeAnalyzerLevels(s) {
  if (!s) return null;
  const supports = s.m_supports || [];
  const resistances = s.m_resistances || [];
  const price = s.close;
  if (!price) return null;

  const high20 = s.m_high20;
  const atrPct = (s.m_atr_pct || 2.5) / 100;
  const nearestSup = supports[0];
  const nearestRes = resistances[0];

  // Cách đỉnh 20 phiên bao nhiêu % — đây là thứ quyết định kịch bản
  const distToHigh = high20 ? (high20 - price) / price * 100 : null;
  const isBreakoutSetup = distToHigh !== null && distToHigh <= 3;

  let entry, stop, mode, entryNote;

  if (isBreakoutSetup) {
    mode = 'breakout';
    entry = high20 * 1.005;      // đệm 0,5% phòng phá vỡ giả
    entryNote = `Mua khi vượt đỉnh 20 phiên (${fmtPrice(high20)})`;
    const atrStop = entry * (1 - 2 * atrPct);
    const supStop = nearestSup ? nearestSup.price : atrStop;
    stop = Math.max(atrStop, supStop);   // lấy mức chặt hơn
  } else {
    mode = 'pullback';
    const golden = supports.find(x => x.is_golden);
    entry = golden ? golden.price : (nearestSup ? nearestSup.price : price * 0.97);
    const away = (price - entry) / price * 100;
    entryNote = `Chờ giá chỉnh về vùng hỗ trợ (còn ${away.toFixed(1)}% nữa)`;
    const deeper = supports.find(x => x.price < entry * 0.99);
    stop = deeper ? deeper.price : entry * (1 - 2 * atrPct);
  }

  // Chặn cứng mức lỗ tối đa — bản cũ có thể cho stop −15%
  stop = Math.max(stop, entry * (1 - MAX_STOP_PCT));

  const target = nearestRes && nearestRes.price > entry * 1.02
    ? nearestRes.price
    : entry * 1.08;

  const riskPct = (entry - stop) / entry * 100;
  const gainPct = (target - entry) / entry * 100;
  const rr = riskPct > 0.1 ? gainPct / riskPct : 0;

  return {
    entry, stop, target, riskPct, gainPct, rr, mode, entryNote,
    acceptable: rr >= MIN_ACCEPTABLE_RR,
    rejectReason: rr < MIN_ACCEPTABLE_RR
      ? `R:R chỉ ${rr.toFixed(1)} — dưới ngưỡng ${MIN_ACCEPTABLE_RR}, không đáng vào lệnh`
      : null,
  };
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
    // Nói rõ đang dùng kịch bản nào — trước đây UI im lặng đưa ra một mức giá
    // mà không cho biết đó là "mua ngay khi vượt đỉnh" hay "chờ chỉnh mới mua",
    // hai việc hoàn toàn khác nhau.
    const modeBadge = levels.mode === 'breakout'
      ? '<span class="plan-mode plan-breakout">KỊCH BẢN BREAKOUT</span>'
      : '<span class="plan-mode plan-pullback">KỊCH BẢN CHỜ CHỈNH</span>';

    const rejectBanner = levels.acceptable ? '' :
      `<div class="plan-reject">⚠ ${escapeAttr(levels.rejectReason)} —
       thà bỏ lỡ còn hơn vào một lệnh có tỷ lệ lời/lỗ xấu.</div>`;

    levelsHtml = `<div class="rec-plan${levels.acceptable ? '' : ' rec-plan-rejected'}">
      <div class="plan-head">${modeBadge}<span class="plan-note">${levels.entryNote}</span></div>
      ${rejectBanner}
      <div class="rec-levels">
      <div class="rec-level rec-level-entry">
        <div class="rec-level-label">VÀO LỆNH</div>
        <div class="rec-level-value">${levels.entry.toFixed(2).replace('.',',')}</div>
        <div class="rec-level-sub">${fmtPriceUnit()}</div>
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
        <div class="rec-level-sub">${levels.rr >= 2 ? 'Tốt' : levels.rr >= 1.5 ? 'Khá' : 'Không đạt'}</div>
      </div>
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

// ════════════════════════════════════════════════════════════
// BỐI CẢNH THỊ TRƯỜNG (market regime + breadth)
// ════════════════════════════════════════════════════════════
// Vì sao quan trọng: phần lớn tín hiệu breakout thất bại khi VN-Index dưới
// MA50/MA200. Trước đây dashboard hiển thị "MUA MẠNH 8-12% NAV" giống hệt nhau
// bất kể thị trường đang uptrend hay downtrend.
function renderMarketContext(ctx, isIntraday) {
  const el = document.getElementById('market-context');
  if (!el || !ctx || !ctx.available) return;

  const cls = {
    risk_on: 'mc-on',
    neutral: 'mc-neutral',
    risk_off: 'mc-off',
  }[ctx.regime] || 'mc-neutral';

  const icon = { risk_on: '🟢', neutral: '🟡', risk_off: '🔴' }[ctx.regime] || '⚪';
  const breadth = ctx.breadth && ctx.breadth.pct_above_ma50 != null
    ? `${ctx.breadth.pct_above_ma50}% mã trên MA50`
    : 'độ rộng: —';

  const sizing = ctx.position_size_multiplier < 1
    ? `<span class="mc-warn">Gợi ý giảm tỷ trọng còn ~${Math.round(ctx.position_size_multiplier * 100)}% mức thường</span>`
    : '';

  const intradayTag = isIntraday
    ? '<span class="mc-intraday">Bản giữa phiên — khối lượng chưa đủ ngày</span>'
    : '';

  el.className = `market-context ${cls}`;
  el.innerHTML = `
    <span class="mc-icon">${icon}</span>
    <span class="mc-label">${ctx.label}</span>
    <span class="mc-stats">
      VN-Index ${Number(ctx.close).toLocaleString('vi-VN')}
      · MA50 ${ctx.ma50 ? Number(ctx.ma50).toLocaleString('vi-VN') : '—'}
      · 20 phiên ${ctx.change_20d_pct > 0 ? '+' : ''}${ctx.change_20d_pct}%
      · ${breadth}
    </span>
    ${sizing}
    ${intradayTag}
  `;
  el.style.display = 'flex';
}
