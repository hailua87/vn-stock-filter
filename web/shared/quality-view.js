// ════════════════════════════════════════════════════════════
// Từ vựng và mẩu hiển thị dùng chung cho dữ liệu Module B
// (web/data/quality/latest.json + web/data/valuation/latest.json).
//
// Màn Watchlist và góc dài hạn của màn Chi tiết mã đọc CÙNG một tệp JSON,
// nên nhãn chỉ tiêu, nhãn trạng thái và cách định dạng số phải nằm MỘT chỗ.
// Hai bản sao sẽ trôi khỏi nhau: đổi nhãn ở một trang, trang kia im lặng
// hiển thị nhãn cũ mà không ai biết.
//
// Ở đây chỉ có NHÃN và CÁCH ĐỊNH DẠNG. Ngưỡng, danh sách chỉ tiêu và trọng
// số luôn lấy từ metadata của tệp JSON (backend/run_quality.py) và được
// truyền vào — không chép lại, không tự tính lại (blueprint v3, quy ước
// cập nhật tài liệu).
// ════════════════════════════════════════════════════════════

window.QV = (function () {
  const DIMS = ['quality', 'growth', 'governance', 'resilience'];
  const DIM_LABEL = {
    quality: 'Chất lượng', growth: 'Tăng trưởng',
    governance: 'Quản trị', resilience: 'Chống chịu',
  };
  const STATUS_ORDER = ['QUAL', 'MON', 'REV', 'RES', 'EXC'];
  const STATUS_LABEL = {
    QUAL: 'Đủ chuẩn', MON: 'Theo dõi', REV: 'Cần xem lại',
    RES: 'Thiếu dữ liệu', EXC: 'Loại',
  };
  const MODEL_LABEL = {
    NON_FINANCIAL: 'Phi tài chính', BANK: 'Ngân hàng', SECURITIES: 'Chứng khoán',
    INSURANCE: 'Bảo hiểm', REAL_ESTATE: 'Bất động sản',
  };
  const BAND_ORDER = { ATTRACTIVE: 0, FAIR: 1, EXPENSIVE: 2, NOT_AVAILABLE: 3 };
  const FLAG_LABEL = {
    dilution_strong: 'Pha loãng mạnh (phát hành lấy tiền > 10%/năm)',
    dilution_mild: 'Pha loãng vừa (5–10%/năm)',
    earnings_cash_gap: 'Lợi nhuận lệch dòng tiền',
    late_filing: 'Công bố BCTC quý chậm',
    warning_status: 'Đang bị cảnh báo',
    qualified_opinion: 'Ý kiến kiểm toán ngoại trừ',
  };
  const MISSING_GOV_LABEL = {
    dilution: 'pha loãng', earnings_cash_gap: 'lệch dòng tiền',
    late_filing: 'công bố chậm',
  };

  // Nhãn + kiểu định dạng từng chỉ tiêu.
  // pct: 0,203 → 20,3%   x: 0,63 → 0,63×   years: 0,8 → 4/5 năm
  const METRIC = {
    roic_avg5: ['ROIC trung bình 5 năm', 'pct'],
    gross_margin_std5: ['Độ lệch chuẩn biên gộp 5 năm', 'pct'],
    ebit_margin_std5: ['Độ lệch chuẩn biên EBIT 5 năm', 'pct'],
    cash_conversion3: ['CFO / LN ròng 3 năm', 'x'],
    asset_turnover: ['Vòng quay tổng tài sản', 'x'],
    revenue_cagr5: ['CAGR doanh thu 5 năm', 'pct'],
    ebit_cagr5: ['CAGR EBIT 5 năm', 'pct'],
    cfo_cagr5: ['CAGR CFO 5 năm', 'pct'],
    revenue_up_years5: ['Số năm doanh thu tăng', 'years'],
    reinvestment_rate: ['Tỷ lệ tái đầu tư', 'pct'],
    net_debt_ebitda: ['Nợ ròng / EBITDA', 'x'],
    interest_coverage: ['Khả năng trả lãi (EBIT / lãi vay)', 'x'],
    current_ratio: ['Thanh khoản hiện hành', 'x'],
    profit_drawdown5: ['Sụt giảm lợi nhuận lớn nhất 5 năm', 'pct'],
    roa_avg3: ['ROA trung bình 3 năm', 'pct'],
    roe_avg3: ['ROE trung bình 3 năm', 'pct'],
    nim_std: ['Độ ổn định NIM', 'pct'],
    npl_ratio: ['Tỷ lệ nợ xấu', 'pct'],
    cost_income: ['Chi phí / thu nhập hoạt động', 'pct'],
    toi_cagr5: ['CAGR thu nhập hoạt động 5 năm', 'pct'],
    pbt_cagr5: ['CAGR LN trước thuế 5 năm', 'pct'],
    loans_cagr5: ['CAGR cho vay khách hàng 5 năm', 'pct'],
    nonint_income_cagr3: ['Tăng trưởng thu nhập ngoài lãi 3 năm', 'pct'],
    npl_coverage: ['Bao phủ nợ xấu', 'pct'],
    equity_assets: ['VCSH / tổng tài sản', 'pct'],
    credit_cost_std: ['Độ ổn định chi phí tín dụng', 'pct'],
    ldr: ['Cho vay / tiền gửi khách hàng', 'pct'],
    recurring_share: ['Tỷ trọng doanh thu lặp lại', 'pct'],
    fvtpl_equity: ['Tài sản FVTPL / VCSH', 'x'],
    npat_cagr5: ['CAGR LN sau thuế 5 năm', 'pct'],
    margin_loans_cagr3: ['Tăng trưởng dư nợ ký quỹ 3 năm', 'pct'],
    margin_loans_equity: ['Dư nợ ký quỹ / VCSH', 'x'],
    debt_equity: ['Tổng nợ vay / VCSH', 'x'],
  };

  const nf1 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1, minimumFractionDigits: 1 });
  const nf2 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2, minimumFractionDigits: 2 });

  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function fmtMetric(key, v) {
    if (v === null || v === undefined) return '—';
    const kind = (METRIC[key] || [])[1];
    if (kind === 'pct') return nf1.format(v * 100) + '%';
    if (kind === 'x') return nf2.format(v) + '×';
    if (kind === 'years') return `${Math.round(v * 5)}/5 năm`;
    return nf2.format(v);
  }

  const metricLabel = key => (METRIC[key] || [key])[0];

  /**
   * Thanh ngắn 0–100, vạch = ngưỡng Đủ chuẩn; dưới ngưỡng "Cần xem lại" tô khác.
   * `thresholds` là metadata.thresholds của chính tệp JSON đang hiển thị.
   */
  function dimBar(item, d, thresholds) {
    const dim = item.dims?.[d] || {};
    const q = (thresholds?.qualify || {})[d];
    const rv = (thresholds?.review_below || {})[d];
    if (dim.score === null || dim.score === undefined) {
      const cov = dim.coverage !== undefined ? ` · phủ ${Math.round(dim.coverage * 100)}%` : '';
      return `<span class="wl-na" title="Thiếu dữ liệu${cov}">—<small>${cov}</small></span>`;
    }
    const s = dim.score;
    const cls = rv !== undefined && s < rv ? 'low' : (q !== undefined && s >= q ? 'pass' : 'mid');
    return `<div class="wl-bar" role="img" aria-label="${DIM_LABEL[d]} ${Math.round(s)}${q !== undefined ? `, ngưỡng Đủ chuẩn ${q}` : ''}">
      <div class="wl-bar-track"><div class="wl-bar-fill ${cls}" style="width:${Math.max(2, s)}%"></div>
        ${q !== undefined ? `<div class="wl-bar-tick" style="left:${q}%"></div>` : ''}</div>
      <span class="wl-bar-num">${Math.round(s)}</span></div>`;
  }

  /**
   * Bảng chỉ tiêu của một chiều. `specRows` là metadata.model_specs[model][dim]:
   * [{key, weight, higher_better}]. Không có spec thì trả '' — mô hình ngành
   * chưa kích hoạt, và bịa ra danh sách chỉ tiêu còn tệ hơn là để trống.
   */
  function metricsTable(item, specRows) {
    if (!specRows || !specRows.length) return '';
    const rows = specRows.map(m => {
      const pct = item.percentiles?.[m.key];
      const missing = item.metrics?.[m.key] == null;
      return `<tr class="${missing ? 'wl-miss' : ''}">
        <td>${esc(metricLabel(m.key))}<small> ${m.higher_better ? '↑' : '↓'} ${m.weight}%</small></td>
        <td class="td-num">${fmtMetric(m.key, item.metrics?.[m.key])}</td>
        <td class="td-num">${pct == null ? '—' : Math.round(pct)}</td></tr>`;
    }).join('');
    return `<table class="wl-metrics"><thead><tr>
        <th>Chỉ tiêu</th><th class="th-num">Giá trị</th><th class="th-num">Percentile</th>
      </tr></thead><tbody>${rows}</tbody></table>`;
  }

  /**
   * Danh sách cờ quản trị. `penalties` là metadata.governance_penalty.
   * Không biết mức phạt thì KHÔNG in dấu trừ trống: "−" đứng một mình đọc như
   * một con số bị mất, trong khi thật ra tệp này không khai mức phạt.
   */
  function flagList(item, penalties) {
    const flags = item.governance_flags || [];
    if (!flags.length) return '';
    return `<ul class="wl-flags">${flags.map(f => {
      const p = (penalties || {})[f];
      return `<li>${esc(FLAG_LABEL[f] || f)}${p == null ? '' : ` <small>−${p}</small>`}</li>`;
    }).join('')}</ul>`;
  }

  function bandBadge(v) {
    const band = v?.band || 'NOT_AVAILABLE';
    return `<span class="band-badge band-${band}" title="${esc(v?.reason || '')}">${esc(v?.label || 'Chưa có')}</span>`;
  }

  function statusBadge(st) {
    return `<span class="wl-status st-${st}">${esc(STATUS_LABEL[st] || st)}</span>`;
  }

  return {
    DIMS, DIM_LABEL, STATUS_ORDER, STATUS_LABEL, MODEL_LABEL, BAND_ORDER,
    FLAG_LABEL, MISSING_GOV_LABEL, METRIC,
    esc, fmtMetric, metricLabel, dimBar, metricsTable, flagList, bandBadge, statusBadge,
    nf1, nf2,
  };
})();
