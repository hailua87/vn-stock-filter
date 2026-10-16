"""
Peer DB phải được cô lập khỏi tệp cache gitignored (16/10/2026).

`backend/data/peer_multiples.json` bị `.gitignore` (dòng 38), nên **CI không
bao giờ có nó**. Nhưng `run_valuation.py` tại máy GHI RA đúng đường dẫn cứng
đó, và `methods_pe.py` / `methods_ev_ebitda.py` đọc nó qua `get_peer_band()` —
kể cả khi đang chạy test. Kết quả: bộ test cho kết luận khác nhau trên **cùng
một mã nguồn**, tuỳ theo máy người chạy đã từng chạy pipeline hay chưa.

Đây là loại lỗi CLAUDE.md §6 gọi là "thước đo không tất định", cùng họ với năm
nguồn đã gỡ ở bộ đo bố cục — chỉ khác là nó nằm ở bộ test Python, và nó đổi
kết luận theo một tệp **không có trong kho**.

Bản sửa là fixture `autouse` `_co_lap_peer_db` trong `backend/conftest.py`.
Tệp này canh nó. Lập luận gồm hai nửa:

* `test_PEER_DB_PATH_khong_tro_vao_tep_that`: lớp cô lập **đang bật**.
* `test_noi_dung_peer_DB_la_don_bay_that`: nội dung peer DB **thật sự lật được**
  kết luận — nên lớp cô lập ở trên là thứ chịu lực, không phải thủ tục trang trí.

Bỏ fixture đi thì phép kiểm thứ nhất ĐỎ ngay. Giữ fixture mà peer DB hoá ra
không còn ảnh hưởng gì thì phép kiểm thứ hai ĐỎ — lúc đó lớp cô lập thành vô
nghĩa và cần đọc lại, chứ không phải im lặng giữ mãi.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scanner import peer_database  # noqa: E402

# Đường dẫn THẬT trong kho — thứ mà fixture phải trỏ đi chỗ khác.
TEP_THAT = (Path(peer_database.__file__).resolve().parent.parent
            / 'data' / 'peer_multiples.json')

# Nội dung đã ĐO ĐƯỢC là lật kết luận của `test_valuation_loai_lac.py` ở beta
# 2,3: tỷ lệ DCF/trung vị nhảy từ 0,3327 (bị loại) lên 1,0000 (không loại gì).
# Technology vì fixture FPT thuộc ngành đó ('Computer Services' → Technology).
NOI_DUNG_LAT_KET_LUAN = {
    'updated_at': '2026-10-16T00:00:00',
    'total_tickers': 5,
    'industries': {
        'Technology': {
            'ticker_count': 5,
            'tickers': ['FPT', 'CMG', 'VTC', 'UNI', 'ELC'],
            'pe': {'median': 5.0, 'p25': 5.0, 'p75': 5.0, 'mean': 5.0, 'n': 5},
            'pb': None,
            'ev_ebitda': {'median': 4.0, 'p25': 4.0, 'p75': 4.0,
                          'mean': 4.0, 'n': 5},
            'roe': {'median': 0.30, 'p25': 0.30, 'p75': 0.30,
                    'mean': 0.30, 'n': 5},
            'npl_ratio': None,
        },
    },
}


def _co_loai_phuong_phap_nao(beta: float = 2.3) -> bool:
    """Chạy engine trên đúng fixture FPT của `test_valuation_loai_lac.py`."""
    from scanner.strategies.valuation import value_ticker
    from test_valuation_loai_lac import _bo_du_lieu

    r = value_ticker('FPT', raw_fundamentals=_bo_du_lieu(
        beta_info={'beta': beta, 'fallback': False, 'weak': False,
                   'std_error': 0.09, 'r_squared': 0.42,
                   'method': 'weekly_log_returns_blume_adjusted'}),
        enrich_market_metrics=False)
    return bool(r.methods_excluded)


def test_PEER_DB_PATH_khong_tro_vao_tep_that():
    """
    Nửa thứ nhất: lớp cô lập đang bật.

    Hai khẳng định, không phải một. "Khác đường dẫn thật" chưa đủ — nếu fixture
    trỏ sang một tệp nào đó CÓ nội dung thì lại là một nguồn bất định khác, chỉ
    là ở chỗ mới. Điều kiện phải chốt là điều kiện của CI: **không có tệp**.
    """
    assert peer_database.PEER_DB_PATH != TEP_THAT, (
        f'PEER_DB_PATH vẫn trỏ vào tệp gitignored trong kho ({TEP_THAT}) — '
        f'fixture `_co_lap_peer_db` ở backend/conftest.py đã bị bỏ hoặc đổi '
        f'tên. Xem docstring của fixture đó: 18/75 nội dung peer DB làm ba '
        f'phép kiểm định giá đỏ ở beta 2,3.')
    assert not peer_database.PEER_DB_PATH.exists(), (
        f'PEER_DB_PATH ({peer_database.PEER_DB_PATH}) đã trỏ ra ngoài kho '
        f'nhưng lại CÓ nội dung — thế thì chỉ đổi chỗ nguồn bất định, chưa '
        f'gỡ. Điều kiện phải chốt là điều kiện CI: không có tệp.')


def test_doc_peer_DB_trong_test_luon_tra_None():
    """
    Hệ quả hành vi của lớp cô lập, đo ở đúng cái hàm mà các method gọi.

    `get_peer_band()` là cửa duy nhất `methods_pe.py` và `methods_ev_ebitda.py`
    đi qua. Nó phải trả `None` cho mọi ngành, bất kể máy người chạy có tệp
    cache hay không.
    """
    assert peer_database.load_peer_database() is None
    for nganh in ('Technology', 'Banking', 'Steel_Metals'):
        assert peer_database.get_peer_band(nganh, 'pe') is None
        assert peer_database.get_peer_median(nganh, 'pe') is None


def test_noi_dung_peer_DB_la_don_bay_that(tmp_path, monkeypatch):
    """
    Nửa thứ hai: nội dung peer DB thật sự lật được kết luận.

    Phép kiểm này **cố tình tháo** lớp cô lập (trỏ PEER_DB_PATH sang một tệp có
    nội dung trong tmp_path) để chứng minh con số đo được là thật:

        không có tệp                         → CÓ phương pháp bị loại
        tệp có Technology pe=5, ev=4, roe=.3 → KHÔNG loại gì

    Nếu một ngày nào đó hai nhánh này cho cùng kết quả, phép kiểm đỏ và đó là
    tin tốt — nhưng phải xem lại: hoặc peer DB không còn vào P/E và EV/EBITDA
    nữa (lúc đó lớp cô lập hết tác dụng và cần đọc lại), hoặc fixture FPT đã
    dịch xa biên đến mức nội dung không lật nổi.

    Tháo lớp cô lập **trong phạm vi một phép kiểm** là an toàn: `monkeypatch`
    hoàn lại khi phép kiểm kết thúc, và tệp nằm trong `tmp_path`, không phải
    trong kho.
    """
    assert _co_loai_phuong_phap_nao() is True, (
        'không có peer DB thì fixture FPT ở beta 2,3 phải có phương pháp bị '
        'loại — đo được tỷ lệ DCF/trung vị = 0,3327 so với ngưỡng 0,3333. '
        'Beta 2,3 là con số của phép kiểm NÀY, không đọc từ tệp khác, nên nó '
        'không đổi theo beta mà test_valuation_loai_lac.py dùng.')

    tep = tmp_path / 'peer_multiples.json'
    tep.write_text(json.dumps(NOI_DUNG_LAT_KET_LUAN, ensure_ascii=False),
                   encoding='utf-8')
    monkeypatch.setattr(peer_database, 'PEER_DB_PATH', tep)

    assert _co_loai_phuong_phap_nao() is False, (
        'nội dung peer DB này đã ĐO ĐƯỢC là lật kết luận (0,3327 → 1,0000). '
        'Nếu nó không lật nữa thì lớp cô lập ở conftest đang canh một thứ '
        'không còn tồn tại — đọc lại docstring của tệp này trước khi bỏ nó.')


def test_ghi_peer_DB_khong_tham_so_KHONG_tao_tep_trong_kho():
    """
    Chiều ngược lại: test không được ngầm TẠO RA tệp cache.

    `save_peer_database(db)` không tham số ghi vào `PEER_DB_PATH`. Trước bản
    sửa, một phép kiểm gọi nó sẽ để lại tệp trong kho và làm bẩn mọi lượt chạy
    sau — đúng cách tệp này sinh ra ở máy lần đầu.
    """
    truoc = TEP_THAT.exists()
    peer_database.save_peer_database({'updated_at': 'x', 'total_tickers': 0,
                                      'industries': {}})
    assert peer_database.PEER_DB_PATH.exists(), 'phải ghi được vào chỗ đã cô lập'
    assert TEP_THAT.exists() is truoc, (
        f'save_peer_database() không tham số đã tạo/đổi tệp thật trong kho '
        f'({TEP_THAT}) — lớp cô lập không bắt được đường ghi')
