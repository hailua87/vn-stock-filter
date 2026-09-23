"""
Mô hình chấm chất lượng cho chủ đầu tư bất động sản (blueprint §8.4).

Khác `NON_FINANCIAL` ở ba chỗ, và mỗi test dưới đây chốt một chỗ:
  1. Lợi nhuận lồi lõm theo chu kỳ bàn giao → mọi trung bình lấy 5 năm.
  2. EBITDA nhảy theo năm bàn giao → dùng `debt_equity`, không `net_debt_ebitda`.
  3. "Người mua trả tiền trước" ĐÃ THỬ VÀ BỎ vì nó xếp mã kiệt quệ lên đầu.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scanner.quality import config as C
from scanner.quality import metrics as M


def annual(**over):
    """5 kỳ, cũ → mới. Doanh nghiệp lành mạnh làm mốc."""
    base = {
        'period_end': ['2021-12-31', '2022-12-31', '2023-12-31', '2024-12-31', '2025-12-31'],
        'revenue': [100.0, 110.0, 120.0, 130.0, 150.0],
        'gross_profit': [40.0, 44.0, 48.0, 52.0, 60.0],
        'net_income': [20.0, 22.0, 24.0, 26.0, 30.0],
        'cfo': [18.0, 20.0, 22.0, 24.0, 28.0],
        'equity': [200.0, 210.0, 220.0, 240.0, 260.0],
        'inventories': [80.0, 85.0, 90.0, 95.0, 100.0],
        'debt': [100.0, 100.0, 105.0, 110.0, 115.0],
        'cash': [30.0] * 5,
        'total_assets': [400.0, 420.0, 440.0, 470.0, 500.0],
        'current_assets': [200.0] * 5,
        'current_liabilities': [100.0] * 5,
        'ebit': [30.0, 33.0, 36.0, 39.0, 45.0],
        'interest_expense': [-5.0] * 5,
    }
    base.update(over)
    return base


# ─── Bộ chỉ tiêu ───────────────────────────────────────────────────────────

def test_model_is_active_and_weights_sum_to_100():
    assert 'REAL_ESTATE' in C.ACTIVE_MODELS
    for dim, specs in C.MODELS['REAL_ESTATE'].items():
        assert sum(w for _, w, _ in specs) == 100, dim


def test_every_configured_metric_is_actually_computed():
    """Khai trong cấu hình mà hàm không trả ra thì chỉ tiêu đó vĩnh viễn thiếu,
    kéo độ phủ xuống và không ai biết vì sao."""
    produced = set(M.compute('REAL_ESTATE', annual()))
    for dim, specs in C.MODELS['REAL_ESTATE'].items():
        for key, _, _ in specs:
            assert key in produced, f'{dim}: {key} không được tính'


def test_does_not_use_net_debt_ebitda():
    """EBITDA của chủ đầu tư nhảy theo năm bàn giao; năm không bàn giao thì mẫu
    số gần 0 và tỷ số vô nghĩa. Chống chịu phải dựa vào vốn chủ."""
    keys = {k for _, specs in C.MODELS['REAL_ESTATE'].items() for k, _, _ in specs}
    assert 'net_debt_ebitda' not in keys
    assert 'debt_equity' in keys


def test_presales_was_tried_and_dropped():
    """
    Chốt bằng test để không ai thêm lại mà không đọc lý do.

    Đo thật 23/09/2026, ứng trước / doanh thu: NVL 2,92 (cao nhất rổ, mã kiệt
    quệ nhất) so với VHM 0,61 (mã khỏe nhất). NVL đứng đầu chỉ vì doanh thu sụp,
    tức mẫu số co lại. Ba mẫu số khác — tồn kho, tổng tài sản, vốn chủ — đều
    không tách được "hợp đồng sắp bàn giao" khỏi "tiền đã thu của dự án đắp
    chiếu", vì tiền thật sự nằm đó ở cả hai.
    """
    keys = {k for _, specs in C.MODELS['REAL_ESTATE'].items() for k, _, _ in specs}
    assert 'presales_coverage' not in keys
    assert 'presales_coverage' not in M.compute('REAL_ESTATE', annual())


# ─── Từng chỉ tiêu ─────────────────────────────────────────────────────────

def test_averages_use_five_years_not_three():
    """Ba năm rơi trọn vào giữa một chu kỳ xây dựng là chuyện bình thường; khi
    đó số 3 năm nói về giai đoạn chứ không nói về doanh nghiệp."""
    # Hai năm đầu lãi cao, ba năm sau lãi thấp: trung bình 5 năm phải cao hơn 3 năm.
    a = annual(net_income=[60.0, 60.0, 10.0, 10.0, 10.0])
    roe5 = M.compute('REAL_ESTATE', a)['roe_avg5']
    assert roe5 is not None
    three_year_only = sum(10.0 / e for e in (220.0, 240.0, 260.0)) / 3
    assert roe5 > three_year_only, 'roe_avg5 đang chỉ nhìn 3 năm gần nhất'


def test_cash_conversion_spans_five_years():
    """Chủ đầu tư đốt tiền suốt lúc xây, thu về lúc bàn giao. Cửa sổ 3 năm bắt
    trọn phần đốt mà trượt phần thu."""
    a = annual(cfo=[80.0, 80.0, -10.0, -10.0, -10.0])
    cc = M.compute('REAL_ESTATE', a)['cash_conversion5']
    assert cc == pytest.approx(130.0 / 122.0, rel=1e-3)   # tổng 5 năm, không phải 3


def test_inventory_turnover_uses_average_of_two_years():
    a = annual()
    got = M.compute('REAL_ESTATE', a)['inventory_turnover']
    assert got == pytest.approx(150.0 / ((95.0 + 100.0) / 2))


def test_dead_land_bank_scores_low_turnover():
    """Quỹ đất nằm im là vốn chết — đây là chỉ báo bắt đúng NVL (0,05)."""
    stuck = M.compute('REAL_ESTATE', annual(revenue=[100, 90, 50, 20, 7],
                                            inventories=[150.0] * 5))
    healthy = M.compute('REAL_ESTATE', annual())
    assert stuck['inventory_turnover'] < healthy['inventory_turnover']


def test_zero_inventory_gives_none_not_infinity():
    """Chia cho 0 phải ra None. Vô cực lọt vào percentile sẽ kéo lệch cả nhóm."""
    m = M.compute('REAL_ESTATE', annual(inventories=[0.0] * 5))
    assert m['inventory_turnover'] is None


def test_no_debt_interest_is_capped_not_infinite():
    m = M.compute('REAL_ESTATE', annual(interest_expense=[0.0] * 5))
    assert m['interest_coverage'] == 100.0


def test_missing_data_gives_none_not_zero():
    """Thiếu phải là KHÔNG BIẾT, không phải 0 — 0 là một điểm số thật và sẽ
    xếp doanh nghiệp xuống đáy vì lý do sai."""
    m = M.compute('REAL_ESTATE', annual(inventories=[None] * 5, gross_profit=[None] * 5))
    assert m['inventory_turnover'] is None
    assert m['gross_margin_avg5'] is None
    assert m['roe_avg5'] is not None          # phần còn lại vẫn tính được


def test_empty_input_does_not_raise():
    m = M.compute('REAL_ESTATE', {'period_end': []})
    assert isinstance(m, dict) and all(v is None for v in m.values())


# ─── Thứ hạng trên dữ liệu thật ────────────────────────────────────────────

def test_distressed_developer_ranks_below_healthy_one():
    """
    Hình dạng số liệu lấy từ NVL và VHM (BCTC năm 2025, đo 23/09/2026).
    Không chốt điểm tuyệt đối — chỉ chốt THỨ TỰ, thứ duy nhất có nghĩa khi
    điểm là percentile trong nhóm.
    """
    nvl = M.compute('REAL_ESTATE', annual(
        revenue=[15000, 11000, 9000, 8000, 6966],
        gross_profit=[5000, 3700, 3000, 2700, 2369],
        net_income=[3400, 2100, 300, 100, 50],
        cfo=[-2000, -3000, -4000, -5000, -6000],
        equity=[25000, 26000, 26000, 26000, 26000],
        inventories=[110000, 125000, 140000, 150000, 153324],
        debt=[28000, 29000, 30000, 30000, 29600],
        ebit=[4000, 2600, 800, 500, 400],
        interest_expense=[-1500] * 5))
    vhm = M.compute('REAL_ESTATE', annual(
        revenue=[85000, 62000, 103000, 120000, 153271],
        gross_profit=[34000, 25000, 42000, 49000, 62841],
        net_income=[39000, 29000, 33000, 35000, 40000],
        cfo=[20000, -5000, 15000, 25000, 30000],
        equity=[130000, 150000, 170000, 190000, 210000],
        inventories=[60000, 80000, 100000, 120000, 131415],
        debt=[60000, 70000, 90000, 100000, 124000],
        ebit=[45000, 33000, 38000, 41000, 47000],
        interest_expense=[-4000] * 5))
    assert nvl['roe_avg5'] < vhm['roe_avg5']
    assert nvl['cash_conversion5'] < vhm['cash_conversion5']
    assert nvl['inventory_turnover'] < vhm['inventory_turnover']
    assert nvl['debt_equity'] > vhm['debt_equity']
