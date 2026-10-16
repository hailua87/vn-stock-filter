"""
Nhịp gọi nguồn phải tính CHUNG cho mọi tiến trình, không riêng từng tiến trình.

`MIN_INTERVAL = 1.0` trong `sources/http.py` được giữ bằng `threading.Lock`, mà
khoá đó chỉ có tác dụng trong MỘT tiến trình. Ngày 16/10/2026 đo được năm phiên
làm việc song song trên kho này, mỗi phiên một worktree và một bộ tiến trình
riêng — trần thật thành 1 lượt/giây NHÂN số phiên, trong khi CLAUDE.md mục 3
nói rõ 1 lượt/giây là mức cố ý chọn để không đập vào máy chủ bên thứ ba.

Mọi phép kiểm ở đây đo HÀNH VI (thời gian thật của tiến trình thật), không đọc
mã nguồn: một khoá liên tiến trình "có vẻ đúng" mà không serialize thì vô dụng,
và chỉ chạy hai tiến trình thật mới biết.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Tiến trình con in ra mốc thời gian của TỪNG lượt gọi.
#
# Bản đầu tôi đo thời gian tường của cả tiến trình con và nó làm HAI phép kiểm
# đỏ oan: khởi động Python trên Windows mất ~2 s (phải nạp `requests`), gấp 8
# lần cái nhịp 0,25 s đang đo, nên thước đo gần như chỉ đo khởi động. Đo mốc
# từng lượt thì bỏ hẳn phần khởi động ra khỏi số.
CON = '''
import json, sys, time
sys.path.insert(0, {backend!r})
from scanner.sources import http
moc = []
for _ in range({n}):
    http._throttle()
    moc.append(time.time())
print(json.dumps(moc))
'''


def _chay_song_song(tmp_path, *, so_tien_trinh: int, so_luot: int,
                    nhip: float, lien_tien_trinh: bool):
    """Chạy nhiều tiến trình cùng lúc, trả về thời gian tường đã trôi."""
    kich = tmp_path / 'con.py'
    kich.write_text(CON.format(backend=str(ROOT), n=so_luot), encoding='utf-8')

    moi = dict(os.environ)
    moi['SOURCE_MIN_INTERVAL'] = str(nhip)
    moi['SOURCE_PACE_LOCK'] = str(tmp_path / 'nhip.lock')
    moi['SOURCE_CROSS_PROCESS_PACE'] = '1' if lien_tien_trinh else '0'

    ps = [subprocess.Popen([sys.executable, str(kich)], env=moi,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True)
          for _ in range(so_tien_trinh)]
    ra = []
    for p in ps:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, f'tiến trình con lỗi: {err[:300]}'
        ra.append(json.loads(out.strip().splitlines()[-1]))
    return ra


def _khoang_cach_nho_nhat(moc_theo_tien_trinh):
    """Khoảng cách NHỎ NHẤT giữa hai lượt gọi liền nhau, gộp mọi tiến trình."""
    tat_ca = sorted(m for moc in moc_theo_tien_trinh for m in moc)
    return min(b - a for a, b in zip(tat_ca, tat_ca[1:]))


# ── Điều phải đúng ─────────────────────────────────────────────────────────

def test_hai_tien_trinh_khong_co_hai_luot_nao_gan_hon_mot_nhip(tmp_path):
    """
    HAI tiến trình × 4 lượt = 8 lượt. Gộp mốc của cả hai rồi sắp theo thời
    gian: nếu nhịp tính chung thì KHÔNG cặp liền nhau nào gần hơn một nhịp.

    Đo khoảng cách giữa các lượt, không đo tổng thời gian tiến trình — khởi
    động Python trên Windows mất ~2 s, gấp 8 lần cái nhịp đang đo, nên tổng
    thời gian gần như chỉ đo khởi động.
    """
    nhip = 0.25
    moc = _chay_song_song(tmp_path, so_tien_trinh=2, so_luot=4,
                          nhip=nhip, lien_tien_trinh=True)
    gan_nhat = _khoang_cach_nho_nhat(moc)
    assert gan_nhat >= nhip * 0.9, (
        f'có hai lượt gọi chỉ cách nhau {gan_nhat:.3f}s trong khi nhịp là '
        f'{nhip}s — hai tiến trình đang gọi SONG SONG, mỗi cái tự giữ nhịp '
        f'riêng. Tổng 8 lượt từ 2 tiến trình: {[len(m) for m in moc]}')


def test_tat_di_thi_hai_tien_trinh_goi_song_song(tmp_path):
    """
    Mặt sau của phép kiểm trên, và chính là HÀNH VI CŨ: tắt nhịp liên tiến
    trình thì hai tiến trình chen vào giữa nhịp của nhau.

    Giữ cho phép kiểm trên khỏi xanh rỗng — nếu cả hai cấu hình đo ra như nhau
    thì thước đo không đo gì cả.
    """
    nhip = 0.25
    moc = _chay_song_song(tmp_path, so_tien_trinh=2, so_luot=4,
                          nhip=nhip, lien_tien_trinh=False)
    gan_nhat = _khoang_cach_nho_nhat(moc)
    assert gan_nhat < nhip * 0.9, (
        f'tắt nhịp liên tiến trình mà khoảng cách nhỏ nhất vẫn là '
        f'{gan_nhat:.3f}s (>= {nhip * 0.9:.3f}s) — thước đo này không phân '
        f'biệt được hai cấu hình, nên phép kiểm kia không chứng minh gì.')


def test_mot_tien_trinh_khong_bi_cham_them(tmp_path):
    """
    Rủi ro thật khi thêm một tầng chờ: chờ HAI LẦN (một lần ở đường liên tiến
    trình, một lần ở đường dự phòng). CI chỉ có một tiến trình, nên nếu chỗ này
    cộng thêm nhịp thì mọi lượt quét đều dài ra và ba tầng ngân sách thời gian
    ở CLAUDE.md mục 4 bị phá từ dưới lên.

    Đo khoảng từ lượt đầu tới lượt cuối TRONG tiến trình con, nên khởi động
    Python không tính vào.
    """
    nhip, luot = 0.1, 10
    moc = _chay_song_song(tmp_path, so_tien_trinh=1, so_luot=luot,
                          nhip=nhip, lien_tien_trinh=True)[0]
    khoang = moc[-1] - moc[0]
    tran = (luot - 1) * nhip * 1.6      # 60% dư cho vào/ra tệp và nhiễu hệ
    assert khoang <= tran, (
        f'{luot} lượt trong MỘT tiến trình trải {khoang:.3f}s, trần '
        f'{tran:.3f}s (lý thuyết {(luot - 1) * nhip:.3f}s). Nhịp liên tiến '
        f'trình đang CỘNG THÊM thời gian chờ thay vì thay thế.')


def test_dong_ho_nhay_lui_khong_lam_cho_mai_mai(tmp_path):
    """
    Mốc dùng chung là thời gian TƯỜNG, nên nó chịu ảnh hưởng của đồng hồ hệ
    thống. Một mốc ở tương lai (đồng hồ nhảy lùi, hoặc tệp khoá còn lại từ máy
    khác qua thư mục đồng bộ) không được làm lượt chạy đứng vô hạn.

    Chạy trong TIẾN TRÌNH CON có trần thời gian, không gọi `_throttle()` trực
    tiếp: bỏ chặn trên `min(..., MIN_INTERVAL)` thì hàm ngủ 86.400 giây, tức
    phép kiểm TREO chứ không đỏ. Một phép kiểm treo không canh được gì — trên
    CI nó đốt trọn `timeout-minutes` rồi báo một lỗi không liên quan.
    """
    tep = tmp_path / 'nhip.lock'
    tep.write_text(repr(time.time() + 86400), encoding='utf-8')
    kich = tmp_path / 'con.py'
    kich.write_text(f'''
import sys, time
sys.path.insert(0, {str(ROOT)!r})
from scanner.sources import http
t0 = time.monotonic()
http._throttle()
print(time.monotonic() - t0)
''', encoding='utf-8')

    moi = dict(os.environ)
    moi['SOURCE_MIN_INTERVAL'] = '0.2'
    moi['SOURCE_PACE_LOCK'] = str(tep)
    moi['SOURCE_CROSS_PROCESS_PACE'] = '1'
    try:
        r = subprocess.run([sys.executable, str(kich)], env=moi,
                           capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        pytest.fail('mốc ở tương lai 1 ngày làm lượt gọi đứng hẳn (>15s) — '
                    'chặn trên `min(..., MIN_INTERVAL)` không còn tác dụng.')
    assert r.returncode == 0, r.stderr[:300]
    troi = float(r.stdout.strip().splitlines()[-1])
    assert troi <= 0.2 + 0.5, (
        f'mốc ở tương lai 1 ngày làm lượt gọi chờ {troi:.2f}s — chặn trên '
        f'`min(..., MIN_INTERVAL)` không còn tác dụng.')


def test_khong_khoa_duoc_thi_quay_ve_duong_cu_chu_khong_dung(monkeypatch):
    """
    Fail-open. Một cơ chế an toàn mà có thể TREO cả lượt chạy thì tệ hơn không
    có — cùng lý lẽ với `scripts/claude_guard.py`.
    """
    sys.path.insert(0, str(ROOT))
    from scanner.sources import http
    monkeypatch.setattr(http, '_khoa_doc_quyen', lambda f: False)
    assert http._nhip_lien_tien_trinh() is False

    monkeypatch.setattr(http, 'MIN_INTERVAL', 0.2)
    monkeypatch.setattr(http, '_last_call', time.monotonic())
    t0 = time.monotonic()
    http._throttle()                      # phải đi đường dự phòng, vẫn giữ nhịp
    assert time.monotonic() - t0 >= 0.15, (
        'không khoá được tệp thì phải quay về nhịp trong tiến trình, chứ không '
        'phải bỏ nhịp luôn.')


def test_tep_khoa_dung_chung_ca_may_chu_khong_rieng_tung_worktree():
    """
    Mặc định phải nằm ngoài kho và KHÔNG phụ thuộc worktree. Mỗi worktree một
    tệp khoá thì khoá không chặn được gì — đúng cái lỗi đang vá.
    """
    sys.path.insert(0, str(ROOT))
    from scanner.sources import http
    duong = Path(http._TEP_NHIP).resolve()
    assert ROOT.parent not in duong.parents and duong != ROOT, (
        f'tệp khoá {duong} nằm trong kho — mỗi worktree sẽ có một bản riêng.')
    assert 'worktree' not in str(duong).lower()


@pytest.mark.parametrize('moi,mong_doi', [
    ({}, True),
    ({'SOURCE_CROSS_PROCESS_PACE': '1'}, True),
    ({'SOURCE_CROSS_PROCESS_PACE': '0'}, False),
])
def test_doc_dung_bien_moi_truong_tat_bat(moi, mong_doi):
    """
    Phải tắt được, để đo lại hành vi cũ bằng cùng một thước.

    KHÔNG dùng `importlib.reload` để kiểm chuyện này. Bản đầu của phép kiểm
    này nạp lại module và làm 4 phép kiểm trong `test_sources.py` đỏ — nhưng
    chỉ khi chạy CẢ BỘ, chạy riêng thì xanh. Hành vi thật của cờ (có serialize
    hay không) đã được hai phép kiểm hai-tiến-trình ở trên đo qua tiến trình
    con, nên ở đây chỉ cần chốt đúng TÊN biến.
    """
    sys.path.insert(0, str(ROOT))
    from scanner.sources import http
    assert http._bat_nhip_lien_tien_trinh(moi) is mong_doi
