"""
Beta phải đi ra đầu ra (04/10/2026).

Beta quyết định WACC trong DCF, và `methods_pb_roe` trừ 5% độ tin cậy khi beta
là giá trị dự phòng 1.0 — tức nó ĐỔI KẾT QUẢ. Nhưng trước ngày này nó không
được ghi ra bất kỳ đâu.

Hậu quả cụ thể: ngày 04/10 không ai — kể cả người viết — nói được từ dữ liệu
công bố rằng lượt chạy đó dùng beta thật hay 1.0. Một đầu vào làm đổi kết quả
mà không để lại dấu vết thì không kiểm chứng được, và không sửa được khi hỏng.

Phép kiểm quan trọng nhất ở đây là cái CUỐI: con số ghi ra phải là con số đã
THỰC SỰ được dùng, không phải một con số tính lại ở chỗ khác.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from run_valuation import _tong_hop_beta
from test_valuation_quality_fixes import _raw, no_dispersion  # noqa: F401 (fixture)

THAT = {'beta': 1.3, 'fallback': False, 'r_squared': 0.42,
        'weak': False, 'std_error': 0.09,
        'method': 'weekly_log_returns_blume_adjusted'}


def _dinh_gia(beta_info=None, price=66_400.0, shares=1_000_000_000):
    # FPT: fixture phi tai chinh co san, du khoan muc de DCF chay that.
    from scanner.strategies.valuation import value_ticker
    raw = _raw('FPT', overview={'industry': 'Computer Services',
                                'outstanding_share': shares})
    raw['current_price'] = price
    if beta_info is not None:
        raw['beta_info'] = beta_info
    # enrich_market_metrics=False: mac dinh value_ticker TU TINH LAI beta tu
    # cache OHLCV va ghi de beta_info. De bat thi phep kiem nay chay khac nhau
    # giua may co cache (beta that) va CI khong cache (beta du phong) — tuc no
    # khong kiem cai no tuong la dang kiem.
    return value_ticker('FPT', raw_fundamentals=raw, enrich_market_metrics=False)


def test_the_report_records_the_beta_it_used(no_dispersion):
    d = _dinh_gia(THAT).to_dict()
    assert d['beta'] == {'value': 1.3, 'fallback': False, 'weak': False,
                         'method': 'weekly_log_returns_blume_adjusted',
                         'r_squared': 0.42, 'std_error': 0.09}


def test_a_fallback_beta_says_so_instead_of_looking_real(no_dispersion):
    """
    Không có regression thì beta là 1.0 — nhưng 1.0 cũng là một giá trị beta
    hợp lệ. Nếu đầu ra chỉ ghi con số, người đọc không phân biệt được "beta đo
    được đúng bằng 1.0" với "không đo được nên lấy mặc định".
    """
    d = _dinh_gia(None).to_dict()
    assert d['beta']['value'] == 1.0
    assert d['beta']['fallback'] is True
    assert d['beta']['r_squared'] is None


def test_the_rollup_separates_real_from_fallback():
    """
    Từ 13/10/2026 bản tổng hợp có BA ô, không phải hai: xem
    `test_beta_weak.py`. "Tính được" và "tính được mà khác 1,0 có ý nghĩa" là
    hai chuyện khác nhau, và gộp lại thì lượt 11/10 báo "84/84 beta thật"
    trong khi 35 mã không phân biệt được với 1,0.
    """
    tong = _tong_hop_beta([
        {'beta': {'value': 1.2, 'fallback': False, 'weak': False, 'r_squared': 0.4}},
        {'beta': {'value': 0.9, 'fallback': False, 'weak': False, 'r_squared': 0.6}},
        {'beta': {'value': 1.0, 'fallback': True, 'weak': True, 'r_squared': None}},
        {'beta': None},
    ])
    assert tong == {'n': 3, 'real': 2, 'weak': 0, 'fallback': 1,
                    'median_r_squared': 0.6}


def test_the_rollup_survives_a_run_with_no_beta_at_all():
    assert _tong_hop_beta([{'beta': None}, {}]) == {
        'n': 0, 'real': 0, 'weak': 0, 'fallback': 0, 'median_r_squared': None}


def test_the_exported_beta_is_the_one_that_actually_drove_the_numbers(no_dispersion):
    """
    ĐÂY LÀ PHÉP KIỂM CÓ GIÁ TRỊ NHẤT.

    Một trường `beta` ghi ra đầu ra mà không gắn với con số đã dùng thì tệ hơn
    là không ghi: nó trông như bằng chứng. Đổi beta phải làm ĐỔI CẢ HAI — con
    số ghi ra VÀ kết quả định giá. Nếu chỉ đổi con số ghi ra thì đó là trang
    trí; nếu chỉ đổi kết quả thì đầu ra đang nói dối.
    """
    # 0,8 va 1,5 chu khong 0,6 va 1,9 — DOI 13/10/2026, va doi vi fixture CU
    # KHONG chung minh duoc dieu no noi:
    #
    #   beta=0,6 -> DCF ra 283.055 voi confidence 0% -> engine BO no tu truoc
    #               (luat `confidence < 0.15` da co san). Tuc "ket qua cua beta
    #               thap" that ra la ket qua KHONG CO DCF.
    #   beta=1,9 -> DCF ra 53.734 = 0,29x trung vi cac phuong phap con lai.
    #
    # Nen phep kiem cu so "khong co DCF" voi "DCF lech 3,46 lan" — hai dau deu
    # benh, va no xanh nho dung cai sai thu hai. Tu 13/10 co phep loai gia tri
    # lac (NGUONG_LAC=3,0) nen dau thu hai bi bo, va phep kiem do.
    #
    # 1,9 cung ngoai dai thuc te: `beta_info['beta']` la gia tri DA dieu chinh
    # Blume (0,67*raw + 0,33), nen 1,9 ung voi raw = 2,34 — do tren ro that thi
    # beta_raw cao nhat vao khoang 1,4.
    #
    # Trong dai 0,8-1,5, tinh chat nay VAN DUNG va manh (do 13/10):
    #   beta 0,8 -> 170.871     beta 1,3 -> 140.514     beta 1,5 -> 134.810
    thap = _dinh_gia({**THAT, 'beta': 0.8})
    cao = _dinh_gia({**THAT, 'beta': 1.5})

    assert thap.to_dict()['beta']['value'] == 0.8
    assert cao.to_dict()['beta']['value'] == 1.5

    # Chot chan: phep kiem chi co nghia khi DCF THAT SU duoc dung o CA HAI dau.
    # Thieu buoc nay thi no lai xanh vi mot ly do khac (nhu truoc 13/10).
    for ten, r in (('beta thap', thap), ('beta cao', cao)):
        assert 'DCF FCFF' in r.methods_used, (
            f'{ten}: DCF khong duoc dung, nen phep kiem nay khong do beta')
        assert not r.methods_excluded, (
            f'{ten}: co phuong phap bi loai ({r.methods_excluded}) — fixture da '
            f'troi ra ngoai dai do duoc')

    # Beta cao -> WACC cao -> chiết khấu mạnh hơn -> fair value THẤP hơn.
    assert cao.fair_value < thap.fair_value, (
        f'beta phải đổi được kết quả: beta 1,5 ra {cao.fair_value:,.0f} '
        f'nhưng beta 0,8 ra {thap.fair_value:,.0f}')


def test_beta_qua_cao_lam_DCF_lac_ra_thi_no_bi_LOAI_va_duoc_GHI_RA(no_dispersion):
    """
    Mat sau cua phep kiem tren, va la hanh vi moi tu 13/10/2026.

    Beta 2,7 (ngoai han dai thuc te — beta_raw cao nhat do duoc vao khoang 1,4)
    keo DCF xuong 0,26x trung vi cac phuong phap. Tron mot con so nhu vay vao
    voi trong so 20% la lay mot mo hinh chay ngoai mien cua no lam y kien. Nay
    no bi loai — nhung PHAI de lai dau vet, neu khong thi fair value doi ma
    khong ai kiem lai duoc.

    Dung 2,7 chu khong 1,9: o 1,9 do lac chi la 2,2x, DUOI nguong 3,0. Tuc tren
    ro that, beta MOT MINH khong du de day DCF qua nguong — ca PVT (3,49x) lac
    vi ly do khac, beta chi lam DCF XUAT HIEN tro lai.

    CON SO DOI 2,3 -> 2,7 NGAY 15/10/2026. O 2,3 ty le DCF/trung vi roi DUNG
    tren bien nguong (0,333x) nen phep kiem can bang tren dau dao, va HAI thu
    doc lap nhau deu du suc lam no do:

      1. Sua loi payout_ratio (xem test_payout_ratio.py). Payout = 0,0 o moi ma
         lam justified_pe = 0 va bi loai khoi blend P/E; sua xong P/E cua FPT
         tu 185.654 ve 119.039 (thap hon 36%), trung vi tut theo, DCF len
         0,34x — het lac.
      2. Chi can ton tai file backend/data/peer_multiples.json. No bi gitignore
         nen CI khong co, nhung mot luot chay pipeline tai may se tao ra, va
         tu do ba phep kiem nay DO tren cay sach. Do la mot manh vun doc lap
         voi PR nay, chua sua.

    2,7 cho 0,26x — cach bien 22%, du cho ca hai nguyen nhan tren.

    Moc chuan o day la con so DAN XUAT, khong phai hang so tu nhien: doi nguong
    loai lac hay bat ky cau phan nao cua blend P/E deu phai do lai ty le nay.
    """
    r = _dinh_gia({**THAT, 'beta': 2.7})
    assert 'DCF FCFF' in r.methods_excluded, r.methods_excluded
    assert r.methods_excluded['DCF FCFF'] < 1 / 3, 'phai lac ve phia THAP'
    assert 'DCF FCFF' not in r.methods_used
    d = r.to_dict()
    assert d['methods_excluded'] and 'DCF FCFF' in d['methods_excluded'], (
        'phai ghi ra dau ra JSON, khong chi giu trong bo nho')
    assert any('bị loại' in n for n in r.recommendation_notes), (
        'phai noi ro trong ghi chu, kem ty le')
