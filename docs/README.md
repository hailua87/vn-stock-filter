# Tài liệu kỹ thuật — Mục lục

> Đây là **trang index** giúp bạn điều hướng giữa các tài liệu của project.

## 📚 Bản đồ tài liệu

```
┌─ Cấp 1: Bắt đầu ──────────────────────────────────────┐
│  Đọc trước nếu bạn mới biết đến project                │
│                                                         │
│  README.md             — Tổng quan, cấu trúc folder    │
│  QUICKSTART.md         — Setup nhanh trong 5 phút      │
│  USER_GUIDE.md ⭐ MỚI  — Hướng dẫn cho người mới       │
└────────────────────────────────────────────────────────┘
        ↓
┌─ Cấp 2: Hiểu sâu hệ thống ────────────────────────────┐
│  Đọc khi muốn hiểu cách scanner hoạt động              │
│                                                         │
│  CRITERIA.md           — Công thức 10 tiêu chí         │
│  ARCHITECTURE.md       — Sơ đồ kiến trúc, data flow   │
│  DATA_SOURCES.md       — vnstock, VCI, TCBS, schema   │
│  CORPORATE_ACTIONS.md  — Xử lý chia tách, cổ tức       │
└────────────────────────────────────────────────────────┘
        ↓
┌─ Cấp 3: Triển khai & kiểm thử ────────────────────────┐
│  Đọc khi muốn deploy lên production                    │
│                                                         │
│  GITHUB_DEPLOY.md ⭐ MỚI — GitHub + Vercel từng bước  │
│  DEPLOYMENT.md         — Vercel, Railway, GitHub      │
│  BACKTEST.md           — Backtest framework + API     │
└────────────────────────────────────────────────────────┘
        ↓
┌─ Cấp 4: Khi gặp vấn đề ───────────────────────────────┐
│  Tham khảo khi có lỗi hoặc câu hỏi cụ thể              │
│                                                         │
│  FAQ.md ⭐ MỚI         — Câu hỏi thường gặp + troubleshooting │
└────────────────────────────────────────────────────────┘
```

## 🎯 Theo mục tiêu sử dụng

### "Tôi chỉ muốn xem tín hiệu hằng ngày"
→ Mở web app đã deploy (nếu có URL từ tác giả)
→ Đọc [USER_GUIDE.md](USER_GUIDE.md) phần "Cách dùng dashboard"

### "Tôi muốn tự deploy lên web miễn phí"
→ **[GITHUB_DEPLOY.md](GITHUB_DEPLOY.md)** ⭐ — Chi tiết từng bước, có ảnh, 30 phút
→ Sau khi quen: [DEPLOYMENT.md](DEPLOYMENT.md) cho phương án nâng cao (Railway, Docker)

### "Tôi muốn chạy trên máy tính cá nhân"
→ [USER_GUIDE.md](USER_GUIDE.md) Lựa chọn C
→ [QUICKSTART.md](../QUICKSTART.md) cho lệnh terminal nhanh

### "Tôi muốn hiểu phương pháp đằng sau"
→ [CRITERIA.md](CRITERIA.md) — toán học của 10 tiêu chí
→ [BACKTEST.md](BACKTEST.md) — đo độ chính xác

### "Tôi muốn customize scanner cho chiến lược của tôi"
→ [FAQ.md](FAQ.md) câu "Có thể custom threshold không?"
→ [CRITERIA.md](CRITERIA.md) hiểu logic trước khi sửa
→ Tự sửa `backend/scanner/criteria.py`

### "Tôi muốn build feature mới"
→ [ARCHITECTURE.md](ARCHITECTURE.md) hiểu cấu trúc code
→ Chạy `pytest backend/tests/ -v` trước và sau khi sửa
→ Reference [DATA_SOURCES.md](DATA_SOURCES.md) khi cần thêm nguồn data

### "Tôi gặp lỗi"
→ [FAQ.md](FAQ.md) → phần "Lỗi kỹ thuật thường gặp"
→ Nếu không có trong FAQ → mở issue trên GitHub

## 📖 Mô tả ngắn từng file

| File | Đối tượng | Độ dài | Nội dung chính |
|---|---|---|---|
| [README.md](../README.md) | Mọi người | ~5KB | Pitch, cấu trúc, quick start |
| [QUICKSTART.md](../QUICKSTART.md) | Dev | ~4KB | 4 cách chạy, lệnh terminal |
| [USER_GUIDE.md](USER_GUIDE.md) | Non-tech | ~8KB | Setup chi tiết, dùng dashboard |
| [CRITERIA.md](CRITERIA.md) | Trader, Dev | ~8KB | Toán học 10 tiêu chí, sách tham khảo |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Dev | ~6KB | Data flow, components, performance |
| [DATA_SOURCES.md](DATA_SOURCES.md) | Dev | ~5KB | vnstock API, rate limit, fallback |
| [CORPORATE_ACTIONS.md](CORPORATE_ACTIONS.md) | Dev, Trader | ~6KB | Xử lý chia tách/cổ tức |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Dev/DevOps | ~7KB | 3 phương án deploy + cost |
| [GITHUB_DEPLOY.md](GITHUB_DEPLOY.md) | Mọi người | ~12KB | Deploy GitHub + Vercel từng bước |
| [BACKTEST.md](BACKTEST.md) | Dev, Trader | ~7KB | Backtest framework + REST API |
| [FAQ.md](FAQ.md) | Mọi người | ~12KB | Câu hỏi thường gặp + troubleshooting |

**Tổng: ~70KB tài liệu, đủ để vận hành project độc lập.**

## 🛠️ Tài liệu vs Code

| Tài liệu | Liên quan đến file code |
|---|---|
| [CRITERIA.md](CRITERIA.md) | `backend/scanner/criteria.py`, `indicators.py` |
| [DATA_SOURCES.md](DATA_SOURCES.md) | `backend/scanner/data_fetcher.py` |
| [CORPORATE_ACTIONS.md](CORPORATE_ACTIONS.md) | `backend/scanner/corporate_actions.py` |
| [BACKTEST.md](BACKTEST.md) | `backend/scanner/backtest.py`, `api.py` |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Toàn bộ `backend/` và `web/` |
| [DEPLOYMENT.md](DEPLOYMENT.md) | `.github/workflows/`, `Dockerfile`, `vercel.json` |

## 🔄 Roadmap tài liệu

**Đã có (v0.2.0)**:
- ✅ Tổng quan & quick start
- ✅ Hướng dẫn cho non-tech user
- ✅ Phương pháp luận chi tiết
- ✅ Kiến trúc hệ thống
- ✅ Nguồn dữ liệu
- ✅ Corporate actions
- ✅ Deployment (3 phương án)
- ✅ Backtest + API
- ✅ FAQ & troubleshooting

**Chưa có (TODO cho v0.3+):**
- ⏳ `CONTRIBUTING.md` — guide cho contributor
- ⏳ `CHANGELOG.md` — lịch sử version
- ⏳ Video tutorial (YouTube)
- ⏳ Tài liệu API tiếng Anh (cho audience quốc tế)
- ⏳ Case studies (mã nào break thành công, mã nào fail, vì sao)

---

## 💡 Đóng góp tài liệu

Nếu bạn thấy chỗ nào chưa rõ trong tài liệu:
1. Mở issue trên GitHub với tag `documentation`
2. Hoặc sửa trực tiếp và tạo Pull Request
3. Ghi rõ phần nào, đề xuất sửa thế nào

Tài liệu tốt = sản phẩm tốt. Mọi đóng góp đều được trân trọng.
