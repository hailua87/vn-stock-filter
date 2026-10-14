"""
Loại phương pháp lạc TRƯỚC khi trộn (13/10/2026).

Engine vốn đã tính `method_dispersion` và chia đôi độ tin cậy khi nó vượt 40%.
Nhưng đó là bắt **hậu quả**, không chặn **nguyên nhân** — và cái phễu đó không
bắt hết. Số thật ngày 13/10:

  PVT: DCF FCFF ra **94.998** trong khi EV/EBITDA nói 34.179 và P/E nói 20.235.
       Trung vị cả bốn phương pháp là 27.207, nên DCF lệch **3,49×**. Nó vẫn
       được trộn với trọng số 20%, đẩy fair value tổng hợp lên **+54,4%**, và
       mã này **KHÔNG rụng** khỏi bản công bố.

## Ngưỡng 3,0× có căn cứ từ dữ liệu

Đo 245 cặp (mã × phương pháp) trên hai lượt chạy 200 mã, tỷ lệ fair value của
một phương pháp so với **trung vị các phương pháp còn lại**:

    p50=1,15   p75=1,37   p90=1,81   p95=2,38   p99=3,51   max=4,39

(503 cặp, độ lạc = `max(tỷ, 1/tỷ)` so với **trung vị của tất cả** phương pháp.)

3,0 nằm khoảng phân vị 98 — bỏ 9/503 cặp (1,8%, 6 mã). Hai ngưỡng khác đều tệ
hơn, và đó là lý do không chọn chúng:

* **2,0** (p95) loại 8,2% — ăn vào bất đồng ý thông thường. P/E lệch EV/EBITDA
  hai lần là hai ý kiến, không phải mô hình hỏng.
* **3,5** (p99) **bỏ sót chính PVT** (3,49×) — ca đã gây ra bản sửa này.

## Cái bẫy chính của bản sửa này

Nếu phân tán cũng chỉ tính trên phần đã giữ thì loại giá trị lạc làm phân tán
tụt, ngưỡng 40% không nổ, độ tin cậy **không** bị chia đôi — tức mô hình hỏng
lại làm kết quả trông **đáng tin hơn**. Đúng bẫy "phạt sự trung thực, thưởng
cho nhiễu" đã gặp ở beta (`docs/beta-weak-regression.md`).

Nên: fair value trộn từ phần đã giữ (sạch), còn phân tán đọc trên **toàn bộ**
(thật). Loại giá trị lạc làm fair value đúng hơn mà **không** làm nó trông chắc
chắn hơn. Không thêm hằng số nào.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner.strategies.valuation.engine import (  # noqa: E402
    NGUONG_LAC,
    TOI_THIEU_DE_LOAI,
    _do_lac,
    _loai_phuong_phap_lac,
    _method_dispersion,
)


# ── Hàm loại ────────────────────────────────────────────────────────────────

def test_PVT_that_bi_loai():
    """Số thật ngày 13/10 — đây là ca đã gây ra bản sửa này."""
    giu, loai = _loai_phuong_phap_lac({
        'EV/EBITDA': 34_179.0, 'DCF FCFF': 94_998.0,
        'P/E Multiple': 20_235.0, 'Historical Multiple': 14_192.0,
    })
    assert set(loai) == {'DCF FCFF'}
    assert loai['DCF FCFF'] == pytest.approx(3.49, abs=0.01)
    assert set(giu) == {'EV/EBITDA', 'P/E Multiple', 'Historical Multiple'}


def test_lac_ve_phia_THAP_cung_bi_loai():
    """
    ANV/GEX/HSG có P/B-ROE ở 0,20-0,22× trung vị (ROE bị ép sàn 3% cho mã
    cyclical). Chỉ canh một chiều thì bỏ sót đúng nhóm hay lệch nhất theo SỐ
    LẦN: P/B-ROE là 5-6 ca, nhiều hơn DCF.
    """
    giu, loai = _loai_phuong_phap_lac({
        'P/B-ROE Justified': 5_434.0, 'P/E Multiple': 27_367.0,
        'EV/EBITDA': 26_000.0, 'Historical Multiple': 28_000.0,
    })
    assert set(loai) == {'P/B-ROE Justified'}
    assert loai['P/B-ROE Justified'] < 1 / 3


def test_bat_dong_y_thong_thuong_KHONG_bi_loai():
    """
    Phần quan trọng hơn: phép loại không được ăn vào ý kiến khác nhau bình
    thường. 2,38× là phân vị 95 của phân bố thật — vẫn phải giữ.
    """
    giu, loai = _loai_phuong_phap_lac({
        'a': 100.0, 'b': 200.0, 'c': 150.0, 'd': 120.0,
    })
    assert loai == {}
    assert len(giu) == 4


def test_duoi_3_phuong_phap_thi_KHONG_loai_gi():
    """
    Với 2 phương pháp, "trung vị các cái còn lại" chính là phương pháp kia, nên
    phép so thành đối xứng và chọn bỏ cái nào là TUỲ Ý.

    DRH ngày 13/10 là ca thật: P/B-ROE 474 so với Historical 3.042 (6,4×). Lệch
    thật, nhưng không có cơ sở nào nói cái nào sai — nên giữ cả hai và để phân
    tán hạ độ tin cậy, đúng như trước.
    """
    assert _loai_phuong_phap_lac(
        {'P/B-ROE Justified': 474.0, 'Historical Multiple': 3042.0}) == (
        {'P/B-ROE Justified': 474.0, 'Historical Multiple': 3042.0}, {})
    assert TOI_THIEU_DE_LOAI == 3


def test_khong_loai_gi_khi_chia_doi_khong_co_da_so():
    """
    PHEP KIEM NAY DA BAT DUOC MOT LOI THAT TRONG BAN DAU CUA TOI.

    Ban dau `_do_lac` lay "trung vi CAC CAI CON LAI" (bo chinh no ra). Voi bo
    chia doi {100, 110, 400, 420} thi trung vi cac cai con lai cua 100 la
    trung vi{110, 400, 420} = 400, nen 100 bi coi la lac 4 lan. Thuat toan
    loai tung cai da bo 100 roi bo 110 — tuc GIU HAI GIA TRI LAC va VUT PHAN
    LOI.

    Nay dung trung vi TOAN BO (= 255 o day), khong cai nao vuot 3 lan, nen
    khong loai gi. Do la cau tra loi thanh that: mot bo chia doi khong co da
    so thi khong co co so nao noi ben nao sai.
    """
    giu, loai = _loai_phuong_phap_lac({'a': 100.0, 'b': 110.0,
                                       'c': 400.0, 'd': 420.0})
    assert loai == {}, f'chia doi 2-2 thi khong duoc loai gi, nhung loai {loai}'
    assert len(giu) == 4


def test_loai_TUNG_CAI_va_tinh_lai_trung_vi():
    """
    Bo mot gia tri lac di thi trung vi dich ve phia phan loi, nen cai lac thu
    hai moi lo ra. Tinh MOT LAN roi loai mot lot se bo sot.

    {100, 105, 110, 900, 1000}: trung vi = 110, nen 900 lech 8,2x va 1000
    lech 9,1x — ca hai deu qua nguong ngay tu luot dau. Chon bo nay la de
    chung minh vong lap chay DUOC NHIEU LAN (loai 1000 roi loai 900), chu khong
    dung lai sau lan dau.
    """
    giu, loai = _loai_phuong_phap_lac({'a': 100.0, 'b': 105.0, 'c': 110.0,
                                       'd': 900.0, 'e': 1000.0})
    assert set(loai) == {'d', 'e'}, f'phai loai ca hai, chi loai {set(loai)}'
    assert set(giu) == {'a', 'b', 'c'}


def test_bo_gia_tri_khong_duong():
    giu, loai = _loai_phuong_phap_lac({'a': 100.0, 'b': 0.0, 'c': -5.0, 'd': 110.0})
    assert set(giu) == {'a', 'd'} and loai == {}


def test_do_lac_dung_trung_vi_TOAN_BO():
    """
    Chot chan cho `_do_lac`: no phai so voi trung vi TOAN BO, va phai dung
    trung binh hai gia tri giua khi so phan tu CHAN.

    Dung `duong[n // 2]` cho moi truong hop la sai o nhom chan: voi
    {100, 110, 400, 420} no cho 400 thay vi 255, va bo chia doi 2-2 lai bi
    loai sai — dung cai loi `test_khong_loai_gi_khi_chia_doi_khong_co_da_so`
    canh.
    """
    assert _do_lac({'a': 10.0, 'b': 10.0, 'c': 1000.0})['c'] == pytest.approx(100.0)
    # Nhom CHAN: trung vi = (110 + 400) / 2 = 255
    lac = _do_lac({'a': 100.0, 'b': 110.0, 'c': 400.0, 'd': 420.0})
    assert lac['a'] == pytest.approx(100 / 255, rel=1e-9), (
        f'trung vi nhom chan phai la 255, khong phai 400 hay 110: {lac}')


def test_nguong_la_3_khong_phai_so_khac():
    """
    Ngưỡng này có căn cứ từ phân bố thật (p99=3,22). Đổi nó là đổi kết luận,
    nên phải đổi có ý thức — và phải đo lại, không phải chỉnh cho đẹp số liệu.
    """
    assert NGUONG_LAC == 3.0


# ── Hành vi trong engine ────────────────────────────────────────────────────

def _bo_du_lieu(**gia):
    """Dữ liệu tối thiểu cho `value_ticker` qua fixture có sẵn."""
    from test_valuation_quality_fixes import _raw
    raw = _raw('FPT', overview={'industry': 'Computer Services',
                                'outstanding_share': 1_000_000_000})
    raw['current_price'] = 66_400.0
    raw.update(gia)
    return raw


def test_loai_gia_tri_lac_KHONG_lam_do_tin_cay_TANG():
    """
    ĐÂY LÀ PHÉP KIỂM QUAN TRỌNG NHẤT Ở ĐÂY.

    Nếu phân tán chỉ tính trên phần đã giữ thì loại giá trị lạc làm phân tán
    tụt, độ tin cậy không bị chia đôi, và mô hình hỏng lại làm kết quả trông
    đáng tin hơn. Phân tán PHẢI đọc trên toàn bộ phương pháp đủ điều kiện.
    """
    from scanner.strategies.valuation import value_ticker
    beta = {'fallback': False, 'weak': False, 'std_error': 0.09,
            'r_squared': 0.42, 'method': 'weekly_log_returns_blume_adjusted'}
    r = value_ticker('FPT', raw_fundamentals=_bo_du_lieu(
        beta_info={**beta, 'beta': 2.3}), enrich_market_metrics=False)

    assert r.methods_excluded, 'cấu hình này phải có phương pháp bị loại'
    # Phân tán phải còn phản ánh ĐỘ LỆCH THẬT, tức vẫn tính cả cái bị loại.
    fv_giu = [r.method_results[m].fair_value_per_share for m in r.methods_used]
    pt_chi_giu = _method_dispersion(fv_giu)
    assert r.method_dispersion > pt_chi_giu, (
        f'phân tán ghi ra ({r.method_dispersion:.2f}) phải LỚN HƠN phân tán '
        f'của riêng phần đã giữ ({pt_chi_giu:.2f}) — nếu không thì loại giá '
        f'trị lạc đang che mất bất đồng và làm kết quả trông chắc hơn')


def test_phuong_phap_bi_loai_duoc_ghi_ra_dau_ra():
    """Bỏ lặng lẽ một phương pháp là đổi fair value mà không để lại dấu vết."""
    from scanner.strategies.valuation import value_ticker
    r = value_ticker('FPT', raw_fundamentals=_bo_du_lieu(
        beta_info={'beta': 2.3, 'fallback': False, 'weak': False,
                   'std_error': 0.09, 'r_squared': 0.42,
                   'method': 'weekly_log_returns_blume_adjusted'}),
        enrich_market_metrics=False)
    d = r.to_dict()
    assert d['methods_excluded'], 'phải có khoá methods_excluded trong JSON'
    assert all(isinstance(v, float) for v in d['methods_excluded'].values()), \
        'phải ghi cả TỶ LỆ, không chỉ tên — để người đọc tự kiểm'


def test_khong_co_gi_bi_loai_thi_khoa_la_None_chu_khong_phai_dict_rong():
    """
    `None` thay vì `{}`: đầu ra JSON phục vụ web, và `{}` với `None` đọc khác
    nhau ở phía JS (`{}` là truthy). Đa số mã không có gì bị loại.
    """
    from scanner.strategies.valuation import value_ticker
    r = value_ticker('FPT', raw_fundamentals=_bo_du_lieu(
        beta_info={'beta': 1.0, 'fallback': False, 'weak': False,
                   'std_error': 0.09, 'r_squared': 0.42,
                   'method': 'weekly_log_returns_blume_adjusted'}),
        enrich_market_metrics=False)
    assert not r.methods_excluded
    assert r.to_dict()['methods_excluded'] is None
