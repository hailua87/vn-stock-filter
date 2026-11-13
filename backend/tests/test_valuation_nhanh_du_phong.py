"""
Nhánh dự phòng của engine định giá bỏ qua chính ngưỡng của nó (17/10/2026).

`value_ticker` áp `confidence >= 0,15` cho từng cấu phần ở hai chỗ — chọn ứng
viên để trộn, và vòng trộn. Nhưng khi **không cấu phần nào** qua được ngưỡng,
nó rơi vào nhánh dự phòng, và nhánh đó **không đọc `confidence` nữa**:

    if total_effective_weight == 0:
        valid_fvs = [r.fair_value_per_share for r in results.values()
                     if r.fair_value_per_share > 0]        # CHI xet fv > 0
        fair_value = sum(valid_fvs)/len(valid_fvs) if valid_fvs \
                     else data["market"]["current_price"]  # gia = fair value
        overall_confidence = 0.20

Hai ca thật, đo trên rổ 200 mã ngày 16/10/2026 (cache ấm, `--min-confidence 0`):

* **WSS** — cấu phần P/E `confidence = 0,05`, tức engine vừa loại nó ở trên vì
  dưới 0,15, vẫn thành fair value công bố **22.671 (+284%)**. Chỉ cổng
  `MAX_PUBLISHED_UPSIDE` của `run_valuation` chặn được nó.
* **UNI** — bốn cấu phần ra `0 / −1.577 / −1.611 / 0`, nên `valid_fvs` rỗng và
  engine công bố **`fair_value = 6.700 = đúng giá, upside 0,0%`**, độ tin cậy
  17. Mã này **có trong `latest.json`** của lượt đo.

UNI là ca nguy hiểm hơn, và là lý do không giữ nhánh dự phòng có kèm cờ:
`upside 0,0%` **lọt** cả hai cổng (`MIN/MAX_PUBLISHED_UPSIDE` chỉ chặn < −80%
và > +200%), nên "fair value = giá" là trạng thái **được công bố**, không phải
bị chặn.

Nay engine **từ chối kết luận**: không cấu phần nào đủ điều kiện thì trả `None`
— cùng tinh thần `diff.mjs` từ chối so sánh khi thiếu font (CLAUDE.md §8) và
`kiem-nhanh-da-vao-main.sh` thoát mã 2 khi xung đột (§13).

Khảo sát đầy đủ: `docs/engine-nhanh-du-phong-bo-nguong.md`
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner.strategies.valuation import engine as E  # noqa: E402
from scanner.strategies.valuation.methods_pb_roe import ValuationResult  # noqa: E402


# Tên hàm tính của MỌI phương pháp, đúng như `value_ticker` tra trong globals
# của module khi dựng `method_runners`. Thay hết thì không phụ thuộc vào việc
# phân ngành chọn bộ phương pháp nào.
MOI_HAM_TINH = (
    'calculate_pb_roe_valuation', 'calculate_pe_valuation',
    'calculate_ev_ebitda_valuation', 'calculate_dcf_fcff', 'calculate_ddm',
    'calculate_rnav_simplified', 'calculate_sotp_simplified',
    '_historical_multiple_valuation',
)

GIA = 66_400.0


def _raw_toi_thieu():
    """Dữ liệu tối thiểu để `value_ticker` chạy tới bước trộn."""
    from test_valuation_quality_fixes import _raw
    raw = _raw('FPT', overview={'industry': 'Computer Services',
                                'outstanding_share': 1_000_000_000})
    raw['current_price'] = GIA
    return raw


def _ep_moi_cau_phan(monkeypatch, fv: float, conf: float):
    """Mọi phương pháp trả đúng (fair value, confidence) này."""
    def gia_lap(data, *a, **k):
        return ValuationResult(
            method='gia lập', ticker=data['ticker'],
            fair_value_per_share=fv, current_price=GIA,
            upside_pct=(fv - GIA) / GIA, confidence=conf)
    for ten in MOI_HAM_TINH:
        monkeypatch.setattr(E, ten, gia_lap)


def _chay(monkeypatch, fv: float, conf: float):
    _ep_moi_cau_phan(monkeypatch, fv, conf)
    return E.value_ticker('FPT', raw_fundamentals=_raw_toi_thieu(),
                          enrich_market_metrics=False)


# ── Ca WSS: cấu phần có fair value dương nhưng dưới ngưỡng ──────────────────

def test_cau_phan_duoi_nguong_KHONG_tro_thanh_fair_value_cong_bo():
    """
    Ca WSS. `confidence = 0,05` — engine vừa loại cấu phần này ở vòng trộn.
    Nhánh dự phòng không được phép công bố lại chính nó.
    """
    with pytest.MonkeyPatch.context() as mp:
        r = _chay(mp, fv=22_671.0, conf=0.05)
    assert r is None, (
        f'mọi cấu phần đều dưới ngưỡng {E.NGUONG_CONF_CAU_PHAN} nhưng engine '
        f'vẫn công bố fair value {getattr(r, "fair_value", None)}')


# ── Ca UNI: không cấu phần nào có fair value dương ──────────────────────────

@pytest.mark.parametrize('fv', [0.0, -1_610.8])
def test_khong_cau_phan_nao_duong_thi_KHONG_lay_GIA_lam_fair_value(fv):
    """
    Ca UNI — ca nguy hiểm nhất, vì `upside 0,0%` LỌT cả hai cổng công bố của
    `run_valuation`, tức nó là trạng thái ĐƯỢC công bố chứ không bị chặn.

    `confidence` để 0,75 đúng như UNI thật: cấu phần tự tin, chỉ fair value là
    không dùng được. Nên phép kiểm này không thể xanh nhờ cổng độ tin cậy.
    """
    with pytest.MonkeyPatch.context() as mp:
        r = _chay(mp, fv=fv, conf=0.75)
    assert r is None, (
        f'không cấu phần nào có fair value > 0 nhưng engine vẫn trả báo cáo: '
        f'fair_value={getattr(r, "fair_value", None)}, '
        f'current_price={getattr(r, "current_price", None)}')


def test_fair_value_bang_dung_GIA_khong_bao_gio_duoc_tra_ra():
    """
    Chốt riêng con số giả, không chỉ chốt `None`: nếu ai đó sau này thay `None`
    bằng "giữ nhánh dự phòng nhưng gắn cờ", phép kiểm này vẫn phải đỏ — vì vấn
    đề là bản thân con số, không phải cái cờ.
    """
    with pytest.MonkeyPatch.context() as mp:
        r = _chay(mp, fv=-1.0, conf=0.75)
    if r is not None:
        assert r.fair_value != r.current_price, (
            'engine lấy chính giá làm fair value — một dòng trông như định giá '
            'mà không có định giá nào')


# ── Phản chứng: không được chặn quá tay ─────────────────────────────────────

def test_mot_cau_phan_du_nguong_thi_VAN_cong_bo():
    """
    Phản chứng. Phép kiểm trên xanh được bằng cách trả `None` cho MỌI mã, nên
    phải có chốt ngược: đủ điều kiện thì vẫn ra báo cáo.
    """
    with pytest.MonkeyPatch.context() as mp:
        r = _chay(mp, fv=80_000.0, conf=0.60)
    assert r is not None, 'cấu phần đủ điều kiện mà engine vẫn không kết luận'
    assert r.methods_used, 'phải ghi ra phương pháp đã dùng'
    assert r.fair_value == pytest.approx(80_000.0)


def test_dung_bang_nguong_thi_duoc_dung():
    """Ngưỡng là `>=`, không phải `>`. Đổi dấu so sánh phải làm phép kiểm đỏ."""
    with pytest.MonkeyPatch.context() as mp:
        r = _chay(mp, fv=80_000.0, conf=E.NGUONG_CONF_CAU_PHAN)
    assert r is not None and r.methods_used


def test_ngay_duoi_nguong_thi_KHONG_duoc_dung():
    with pytest.MonkeyPatch.context() as mp:
        r = _chay(mp, fv=80_000.0, conf=E.NGUONG_CONF_CAU_PHAN - 0.001)
    assert r is None


# ── Ngưỡng là MỘT hằng số, cả ba chỗ đọc cùng giá trị ───────────────────────

def test_ca_ba_cho_doc_CUNG_mot_nguong():
    """
    Hành vi, không phải tìm chuỗi (CLAUDE.md §6): nâng hằng số lên thì mã vốn
    đủ điều kiện phải rụng. Nếu một trong hai chỗ còn viết cứng `0.15` thì
    phép kiểm này đỏ.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(E, 'NGUONG_CONF_CAU_PHAN', 0.80)
        r = _chay(mp, fv=80_000.0, conf=0.60)
    assert r is None, ('nâng ngưỡng lên 0,80 mà cấu phần conf=0,60 vẫn được '
                       'công bố — còn chỗ viết cứng 0.15')
    # Và hạ xuống thì nhận lại
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(E, 'NGUONG_CONF_CAU_PHAN', 0.01)
        r = _chay(mp, fv=80_000.0, conf=0.05)
    assert r is not None and r.methods_used


def test_khong_con_so_0_15_viet_cung_trong_value_ticker():
    """
    Chốt bằng AST, không tìm chuỗi: trong thân `value_ticker` không được còn
    hằng số 0.15 nào. Bảng trọng số ngành ở đầu tệp có rất nhiều 0.15 hợp lệ,
    nên phép kiểm phải khoanh đúng hàm.
    """
    cay = ast.parse(Path(E.__file__).read_text(encoding='utf-8'))
    ham = next(n for n in ast.walk(cay)
               if isinstance(n, ast.FunctionDef) and n.name == 'value_ticker')
    so = [n.value for n in ast.walk(ham)
          if isinstance(n, ast.Constant) and n.value == 0.15]
    assert so == [], f'còn {len(so)} hằng số 0.15 viết cứng trong value_ticker'


def test_nguong_la_0_15():
    """Đổi ngưỡng là đổi mã nào được công bố — phải đổi có ý thức."""
    assert E.NGUONG_CONF_CAU_PHAN == 0.15


# ── run_valuation ghi lại mã bị từ chối ────────────────────────────────────

def test_run_valuation_ghi_ma_bi_tu_choi_vao_metadata(tmp_path, monkeypatch):
    """
    Một mã lặng lẽ biến mất khỏi đầu ra thì không ai nói được là nó bị chặn hay
    bị bỏ sót. Dùng lại bộ giả lập của `test_weekly_budget` — ở đó
    `value_ticker` vốn đã trả `None` cho mọi mã.
    """
    import json

    from test_weekly_budget import _stub_valuation
    RV = _stub_valuation(monkeypatch, [])
    rc = RV.main(['--tickers', 'A,B,C,D', '--fetch-budget', '60',
                  '--snapshot-registry', '', '--web-data-dir', str(tmp_path)],
                 clock=lambda: 0)
    assert rc == 0
    m = json.loads((tmp_path / 'valuation' / 'latest.json')
                   .read_text(encoding='utf-8'))['metadata']
    assert m['khong_co_dinh_gia'] == ['A', 'B', 'C', 'D'], (
        f"mã engine từ chối kết luận phải được ghi ra, thực tế "
        f"{m.get('khong_co_dinh_gia')!r}")
