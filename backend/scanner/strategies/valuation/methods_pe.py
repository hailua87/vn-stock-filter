"""
PHƯƠNG PHÁP P/E MULTIPLE VALUATION
================================================================================
Định giá theo P/E mục tiêu, kết hợp 3 cách tiếp cận:
  1. Justified P/E (Gordon model)        - weight 35%
  2. Peer/historical multiple             - weight 40%
  3. Forward P/E từ consensus growth      - weight 25%

Áp dụng tốt cho:
  ✅ Consumer Staples (VNM, MSN, SAB...)
  ✅ Technology (FPT...)
  ✅ Stable industrials
  ⚠️  Không dùng cho cyclical (HPG, DBC, hóa chất) tại đỉnh/đáy chu kỳ
  ❌ Không phù hợp với doanh nghiệp thua lỗ hoặc EPS biến động mạnh
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List
import math

from .normalizer import MARKET_PARAMS
from .methods_pb_roe import (
    ValuationResult,
    calculate_cost_of_equity,
    calculate_sustainable_growth,
)


# Dải P/E mục tiêu hợp lý cho cổ phiếu VN. Dùng để kẹp cấu phần PEG và để kẹp
# target khi không có historical band thật.
PE_FLOOR = 6.0
PE_CEILING = 25.0


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def quality_factor_roe(sustainable_roe, benchmark_roe):
    """Hệ số chất lượng cho P/E peer = căn(ROE / ROE tham chiếu), hoặc None.

    None nghĩa là "không tính được" → bên gọi phải LOẠI cấu phần peer khỏi
    blend rồi chuẩn hoá lại trọng số, chứ không thay bằng một con số bịa.

    Vì sao phải có hàm này thay vì viết thẳng `(a / b) ** 0.5` tại chỗ:

      - ROE ÂM: `(-2.0) ** 0.5` trong Python KHÔNG raise — nó trả về SỐ PHỨC
        (`1.41j`). Số phức đi tiếp vào `peer_pe` rồi nổ ở bước blend với
        `TypeError: '>' not supported between instances of 'complex' and
        'int'`, mà `engine.value_ticker` bọc try/except quanh TỪNG method, nên
        hậu quả thật không phải một lượt chạy đỏ: cấu phần P/E bị bỏ LẶNG LẼ,
        để lại một dòng `✗ P/E Multiple failed` lẫn trong tối đa 8 `notes`.
        Đo ngày 16/10/2026, 200 mã: 5 mã nổ (VDL, WSS, DQC, DTL, DRH).
      - ROE ÂM mà ngành KHÔNG có peer ROE median: nhánh `else` cũ cho
        `quality = 1.0`, tức định giá doanh nghiệp đang lỗ bằng đúng P/E trung
        vị ngành — "chất lượng ngang trung bình ngành". Không nổ, chỉ ra số
        sai, nên không ai thấy. Cùng lượt đo: 3 mã (VHL, HAS, HID — ngành
        Construction, peer ROE median là None).

    Vì sao None, chứ không phải các cách khác:
      - `abs()`: biến ROE −20% thành chất lượng y như ROE +20%. Sai hẳn.
      - kẹp về 0: `peer_pe = 0` rồi bị bộ lọc `v > 0` của blend loại — ra ĐÚNG
        kết quả, nhưng qua một "P/E mục tiêu 0x" ghi vào `notes` và
        `key_outputs`, nên người đọc không phân biệt được "không tính được"
        với "tính ra bằng 0".
      - floor 3% như `methods_pb_roe`: ở đó floor là để tránh chia cho ~0 trong
        công thức P/B hai giai đoạn; ở đây nó bịa ra hệ số căn(0,03/0,15) =
        0,45 không đọc được từ dữ liệu nào.
      - None: đúng khuôn kho này đã dùng cho historical multiple — thiếu dữ
        liệu đáng tin thì loại cấu phần, không bịa số.

    `benchmark_roe` thiếu/âm mà ROE doanh nghiệp dương thì trả 1.0: không có
    mốc để so, nên không điều chỉnh (giữ nguyên hành vi cũ).
    """
    if sustainable_roe is None or sustainable_roe <= 0:
        return None
    if not benchmark_roe or benchmark_roe <= 0:
        return 1.0
    return (sustainable_roe / benchmark_roe) ** 0.5


def calculate_eps_stability(eps_history: List[float]) -> Dict[str, float]:
    """Đo độ ổn định của EPS - kiểm tra xem P/E có phù hợp không.

    Returns:
      - cv: Coefficient of variation (std/mean)
      - has_loss_year: có năm nào EPS âm
      - max_change: thay đổi lớn nhất giữa 2 năm liên tiếp
    """
    if not eps_history or len(eps_history) < 3:
        return {"cv": float("inf"), "has_loss_year": False, "max_change": 0}

    has_loss = any(e <= 0 for e in eps_history)
    avg = sum(eps_history) / len(eps_history)
    if avg <= 0:
        return {"cv": float("inf"), "has_loss_year": True, "max_change": float("inf")}

    variance = sum((e - avg) ** 2 for e in eps_history) / len(eps_history)
    std = math.sqrt(variance)
    cv = std / abs(avg)

    max_change = 0
    for i in range(1, len(eps_history)):
        prev = eps_history[i - 1]
        if prev != 0:
            change = abs(eps_history[i] - prev) / abs(prev)
            max_change = max(max_change, change)

    return {"cv": cv, "has_loss_year": has_loss, "max_change": max_change}


def calculate_pe_valuation(data: Dict[str, Any]) -> ValuationResult:
    """Định giá theo P/E với 3 approaches blend."""
    ticker = data["ticker"]
    market = data["market"]
    ratios = data["ratios"]
    growth = data["growth"]
    per_share = data["per_share"]
    income = data.get("income", {})
    warnings = []
    notes = []

    eps_ttm = per_share["eps_ttm"]
    current_price = market["current_price"]

    # --- 1. Kiểm tra tính phù hợp của P/E ---
    profit_5y = income.get("net_profit_5y") or income.get("net_profit_parent_5y", [])
    stability = calculate_eps_stability(profit_5y)

    if stability["has_loss_year"]:
        warnings.append("Có năm thua lỗ trong 5 năm gần đây - P/E có thể không phù hợp")
    if stability["cv"] > 0.6:
        warnings.append(f"EPS rất biến động (CV={stability['cv']:.2f}) - cân nhắc EV/EBITDA")
    if stability["max_change"] > 1.0:
        warnings.append(f"EPS có cú nhảy >100% giữa các năm - dấu hiệu cyclical")

    # --- 2. Justified P/E (Gordon) ---
    # Sử dụng sustainable ROE và payout
    roe_5y = income.get("roe_5y", [])
    if roe_5y and len(roe_5y) >= 3:
        sorted_roe = sorted(roe_5y)
        trimmed = sorted_roe[1:-1] if len(sorted_roe) >= 5 else sorted_roe
        sustainable_roe = sum(trimmed) / len(trimmed)
    else:
        sustainable_roe = ratios.get("roe_ttm", 0.15)

    # payout None = không suy được từ BCTC (lỗ, hoặc thiếu lưu chuyển tiền tệ).
    # Gordon cần payout thật; thiếu thì LOẠI cấu phần này và để blend tự chuẩn
    # hoá trọng số — đúng khuôn historical multiple ngay dưới. Mặc định 0,30 cũ
    # ở đây chưa bao giờ chạy (normalizer luôn gán sẵn khoá) và nếu chạy thì
    # cũng chỉ là bịa chính sách cổ tức.
    payout = ratios.get("payout_ratio")
    beta = market.get("beta_2y", 1.0)
    coe = calculate_cost_of_equity(beta)["cost_of_equity"]

    if payout is None:
        justified_pe = None
        # Không có payout thì không có g bền vững. Lưới an toàn của forward-PEG
        # (bước 5) lấy 0 — "không giả định tăng trưởng" — chứ không lấy ROE,
        # vì giữ lại 100% lợi nhuận là giả định do THIẾU dữ liệu sinh ra, không
        # phải do BCTC nói.
        g_for_fallback = 0.0
        notes.append("Không suy được payout từ BCTC → loại cấu phần justified P/E khỏi blend")
    else:
        g = calculate_sustainable_growth(sustainable_roe, payout)
        g_cap = MARKET_PARAMS["long_term_gdp_growth"]
        g = min(g, g_cap)

        if coe - g < 0.015:
            g = coe - 0.020
            warnings.append("CoE - g quá nhỏ, ép g về CoE - 2%")

        justified_pe = payout / (coe - g)
        g_for_fallback = g
        notes.append(f"Justified P/E = {payout:.0%} / ({coe:.1%} - {g:.1%}) = {justified_pe:.1f}x")

    # --- 3. Historical P/E ---
    # Có thể là None: normalizer KHÔNG còn suy historical median từ pe_ttm nữa
    # (fix circularity). Thiếu thì loại cấu phần này khỏi blend, chứ không thay
    # bằng một con số dính giá thị trường.
    pe_hist_median = ratios.get("pe_5y_median")
    pe_hist_p25 = ratios.get("pe_5y_p25")
    pe_hist_p75 = ratios.get("pe_5y_p75")
    if pe_hist_median:
        notes.append(f"Historical P/E 5y: median={pe_hist_median:.1f}x "
                     f"[P25={pe_hist_p25:.1f}, P75={pe_hist_p75:.1f}]")
    else:
        notes.append("Không có historical P/E thực → loại cấu phần lịch sử khỏi blend")
        warnings.append("Thiếu historical P/E (cần OHLCV cache >= 3 năm) — "
                        "định giá dựa nhiều hơn vào peer và justified P/E")

    # --- 4. Peer comparison ---
    # Ưu tiên peer database thực, fallback VN-Index nếu chưa có
    peer_pe = None
    peer_backed = False
    # ROE <= 0 → không có "chất lượng hơn/kém ngành bao nhiêu" nào đọc được từ
    # dữ liệu, nên CẢ HAI nhánh dưới đều không dùng được. Chốt ở đây, trước khi
    # tra peer DB, để nhánh VN-Index không chạy lại đúng phép tính đó.
    # Xem `quality_factor_roe` cho lý do đầy đủ.
    roe_dung_duoc = sustainable_roe is not None and sustainable_roe > 0
    if roe_dung_duoc:
        try:
            from ...peer_database import get_peer_band
            industry = data.get('_industry')
            if industry:
                peer_band = get_peer_band(industry, 'pe')
                if peer_band and peer_band.get('median'):
                    peer_median = peer_band['median']
                    # Quality adjustment dựa trên ROE vs peer ROE
                    peer_roe_band = get_peer_band(industry, 'roe')
                    peer_roe = (peer_roe_band.get('median') if peer_roe_band
                                else sustainable_roe)
                    quality_factor = quality_factor_roe(sustainable_roe, peer_roe)
                    if quality_factor is not None:
                        peer_pe = peer_median * quality_factor
                        peer_backed = True
                        notes.append(
                            f"Peer P/E (ngành {industry}, n={peer_band.get('n', '?')}): "
                            f"median={peer_median:.1f}x, quality={quality_factor:.2f} → {peer_pe:.1f}x"
                        )
        except Exception:
            pass  # Fall back to VN-Index

    if peer_pe is None and roe_dung_duoc:
        # Fallback: VN-Index proxy
        market_pe = MARKET_PARAMS["vnindex_pe_current"]
        market_roe = 0.15
        quality_factor = quality_factor_roe(sustainable_roe, market_roe)
        peer_pe = market_pe * quality_factor
        notes.append(f"Peer P/E (VN-Index fallback {market_pe:.1f}x): quality {quality_factor:.2f} → {peer_pe:.1f}x")
    elif peer_pe is None:
        notes.append(f"Sustainable ROE = {sustainable_roe:.1%} <= 0 → không có hệ số "
                     f"chất lượng → loại cấu phần peer khỏi blend")
        warnings.append("Sustainable ROE <= 0 (doanh nghiệp lỗ) → loại cấu phần peer "
                        "P/E khỏi blend; P/E không phù hợp với doanh nghiệp thua lỗ")

    # --- 5. Forward P/E (PEG approach) ---
    # `g` chỉ tồn tại khi suy được payout (xem bước 2), nên KHÔNG dùng nó làm
    # default của .get() — Python tính default ngay cả khi khoá có mặt, nên
    # viết `get(..., g)` làm cả hàm nổ UnboundLocalError ở mọi mã thiếu payout.
    # `eps_growth_consensus_fwd` vốn luôn được normalizer gán, nên nhánh thiếu
    # chỉ là lưới an toàn.
    growth_fwd = growth.get("eps_growth_consensus_fwd")
    if growth_fwd is None:
        growth_fwd = g_for_fallback
    # PEG = 1.0 cho doanh nghiệp tăng trưởng bình thường, cao hơn cho premium growth
    if growth_fwd > 0.20:
        peg_target = 1.2
    elif growth_fwd > 0.10:
        peg_target = 1.0
    elif growth_fwd > 0:
        peg_target = 0.8
    else:
        peg_target = 0.5  # Doanh nghiệp suy giảm

    # FIX ĐIỂM GIÁN ĐOẠN: `peg_target × (g × 100)` cho P/E = 0.4x khi g = 0,5%
    # rồi NHẢY sang pe_hist_p25 (~10x) khi g = 0. Một thay đổi 0,5% trong giả
    # định tăng trưởng làm target P/E đổi 25 lần. Nay kẹp trong dải hợp lý.
    forward_pe = _clamp(peg_target * (growth_fwd * 100), PE_FLOOR, PE_CEILING)
    notes.append(f"Forward P/E (PEG): growth={growth_fwd:.1%}, PEG target={peg_target}, "
                 f"P/E={forward_pe:.1f}x (kẹp trong {PE_FLOOR:.0f}-{PE_CEILING:.0f}x)")

    # --- 6. Blend final target P/E ---
    # FIX: peer_pe trước đây được tính đầy đủ (có quality adjustment theo ROE,
    # có peer DB) rồi CHỈ ghi vào key_outputs mà KHÔNG vào công thức — dù
    # docstring ghi "Peer/historical multiple — weight 40%". Toàn bộ
    # peer_database.py gần như vô dụng với P/E.
    # Trọng số tự chuẩn hoá khi một cấu phần vắng mặt.
    components = {
        'justified': (justified_pe, 0.30),
        'historical': (pe_hist_median, 0.30),
        'peer': (peer_pe, 0.25),
        'forward_peg': (forward_pe, 0.15),
    }
    available = {k: (v, w) for k, (v, w) in components.items() if v and v > 0}
    total_w = sum(w for _, w in available.values())
    target_pe = sum(v * w for v, w in available.values()) / total_w
    notes.append(
        "Blend target P/E = " +
        " + ".join(f"{w/total_w:.0%}×{k}({v:.1f})" for k, (v, w) in available.items()) +
        f" = {target_pe:.1f}x"
    )

    # Cap target P/E trong dải hợp lý (P25 - P75) của historical — chỉ khi có
    # historical thật; nếu không, kẹp trong dải P/E tuyệt đối.
    if pe_hist_p75 and pe_hist_p25:
        if target_pe > pe_hist_p75 * 1.2:
            notes.append(f"Cap target P/E từ {target_pe:.1f} về {pe_hist_p75*1.2:.1f} (1.2× P75)")
            target_pe = pe_hist_p75 * 1.2
        elif target_pe < pe_hist_p25 * 0.8:
            notes.append(f"Floor target P/E từ {target_pe:.1f} lên {pe_hist_p25*0.8:.1f} (0.8× P25)")
            target_pe = pe_hist_p25 * 0.8
    else:
        target_pe = _clamp(target_pe, PE_FLOOR, PE_CEILING)

    # --- 7. Fair value ---
    # Dùng EPS forward = EPS_ttm × (1 + g_fwd) nếu g_fwd hợp lý, không thì dùng EPS_ttm
    if -0.30 < growth_fwd < 0.40:
        fwd_eps = eps_ttm * (1 + growth_fwd)
        notes.append(f"Forward EPS = {eps_ttm:,.0f} × (1 + {growth_fwd:.1%}) = {fwd_eps:,.0f}")
    else:
        fwd_eps = eps_ttm
        notes.append(f"Growth bất thường → dùng EPS TTM = {fwd_eps:,.0f}")

    fair_value = target_pe * fwd_eps
    upside = (fair_value - current_price) / current_price if current_price else 0

    # --- 8. Confidence ---
    confidence = 0.75
    if stability["has_loss_year"]:
        confidence -= 0.25
    if stability["cv"] > 0.6:
        confidence -= 0.15
    if stability["max_change"] > 1.0:
        confidence -= 0.10
    if not pe_hist_median:
        confidence -= 0.10      # thiếu neo lịch sử
    if not peer_backed:
        confidence -= 0.10      # peer là VN-Index proxy, không phải cùng ngành
    if eps_ttm <= 0:
        confidence = 0.0        # P/E vô nghĩa khi EPS <= 0
        warnings.append("EPS <= 0 → P/E không áp dụng được")
    confidence = max(0.0, min(1.0, confidence))

    return ValuationResult(
        method="P/E Multiple",
        ticker=ticker,
        fair_value_per_share=fair_value,
        current_price=current_price,
        upside_pct=upside,
        confidence=confidence,
        key_inputs={
            "eps_ttm": eps_ttm,
            "forward_eps": fwd_eps,
            "eps_growth_fwd": growth_fwd,
            "sustainable_roe": sustainable_roe,
            "payout_ratio": payout,
            "cost_of_equity": coe,
            "eps_stability_cv": stability["cv"],
        },
        key_outputs={
            "justified_pe": justified_pe,
            "historical_pe_median": pe_hist_median,
            "peer_pe": peer_pe,
            "forward_pe_peg": forward_pe,
            "target_pe": target_pe,
            "current_pe": ratios.get("pe_ttm"),
            "fair_value": fair_value,
            "upside_pct": upside,
        },
        warnings=warnings,
        notes=notes,
    )


