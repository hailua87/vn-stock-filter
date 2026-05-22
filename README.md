# VN Breakout Scanner 🇻🇳📈

> Bộ lọc cổ phiếu Việt Nam phát hiện tín hiệu tăng giá **trước nhịp break 2-5 ngày**
> Áp dụng cho HOSE / HNX / UPCOM — chạy hằng ngày, deploy lên web cho người dùng

[![CI](https://github.com/your-org/vn-breakout-scanner/actions/workflows/daily-scan.yml/badge.svg)](https://github.com/your-org/vn-breakout-scanner/actions)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-green.svg)](https://python.org)

## 🎯 Mục tiêu

Phát hiện các cổ phiếu đang trong giai đoạn **"tích lũy âm thầm"** — nơi smart money đang gom hàng nhưng giá chưa thực sự bứt phá. Tín hiệu thường xuất hiện 2-5 phiên trước khi giá break qua vùng kháng cự.

## 🚀 Tính năng

- ✅ Thu thập dữ liệu **tự động hằng ngày** từ HOSE/HNX/UPCOM (qua vnstock + VCI/TCBS)
- ✅ Quét **toàn bộ ~1,600 mã** trong < 5 phút
- ✅ **10 tiêu chí kỹ thuật** đa chiều (giá, volume, momentum, volatility)
- ✅ Chấm điểm 0-10, xếp loại A+/A/B/C
- ✅ Xuất Excel + JSON + Web Dashboard
- ✅ Backtest framework để kiểm tra hit rate
- ✅ Deploy được lên Vercel/Netlify (frontend) + Railway/Render (backend)
- ✅ GitHub Actions chạy tự động lúc 16h00 mỗi phiên

## 📁 Cấu trúc project

```
vn-breakout-scanner/
├── backend/                      # Python backend
│   ├── scanner/
│   │   ├── __init__.py
│   │   ├── indicators.py         # ATR, RSI, OBV, Bollinger...
│   │   ├── criteria.py           # 10 tiêu chí pre-breakout
│   │   ├── data_fetcher.py       # Lấy dữ liệu vnstock
│   │   ├── scanner.py            # Engine quét chính
│   │   ├── backtest.py           # Kiểm tra hit rate
│   │   └── exporter.py           # Excel/JSON/HTML
│   ├── data/                     # Cache dữ liệu (gitignored)
│   ├── tests/                    # Unit tests
│   ├── api.py                    # FastAPI server
│   ├── run_daily.py              # Script chạy hằng ngày
│   └── requirements.txt
├── web/                          # Frontend (React/HTML)
│   ├── index.html                # Dashboard
│   ├── app.js
│   └── styles.css
├── docs/                         # Tài liệu kỹ thuật
│   ├── ARCHITECTURE.md           # Kiến trúc hệ thống
│   ├── DATA_SOURCES.md           # Nguồn & cách lấy dữ liệu
│   ├── CRITERIA.md               # Chi tiết 10 tiêu chí
│   ├── DEPLOYMENT.md             # Triển khai lên web
│   ├── BACKTEST.md               # Hướng dẫn backtest
│   └── API.md                    # API documentation
├── scripts/
│   ├── setup.sh                  # Cài đặt môi trường
│   ├── run_local.sh              # Chạy local
│   └── deploy.sh                 # Deploy
├── .github/workflows/
│   └── daily-scan.yml            # Chạy tự động hằng ngày
├── docker-compose.yml
├── Dockerfile
└── README.md
```

## ⚡ Quick Start

```bash
# 1. Clone & cài đặt
git clone https://github.com/your-org/vn-breakout-scanner.git
cd vn-breakout-scanner
bash scripts/setup.sh

# 2. Chạy quét hôm nay
python backend/run_daily.py

# 3. Khởi động web dashboard
python backend/api.py  # backend tại http://localhost:8000
cd web && python -m http.server 3000  # frontend tại http://localhost:3000
```

## 📚 Tài liệu

**👉 Bắt đầu tại: [docs/README.md](docs/README.md)** — index điều hướng theo mục tiêu

### Theo level

**🟢 Người mới / Non-technical:**
- [USER_GUIDE.md](docs/USER_GUIDE.md) — Hướng dẫn cho người không-kỹ-thuật (deploy web, dùng dashboard)
- [FAQ.md](docs/FAQ.md) — Câu hỏi thường gặp + troubleshooting

**🟡 Developer:**
- [QUICKSTART.md](QUICKSTART.md) — Setup nhanh trong 5 phút
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — Kiến trúc hệ thống & data flow
- [DATA_SOURCES.md](docs/DATA_SOURCES.md) — Nguồn dữ liệu, API endpoints, rate limit
- [CRITERIA.md](docs/CRITERIA.md) — Chi tiết 10 tiêu chí + công thức toán
- [CORPORATE_ACTIONS.md](docs/CORPORATE_ACTIONS.md) — Xử lý chia tách/cổ tức/phát hành

**🔴 Production / DevOps:**
- **[GITHUB_DEPLOY.md](docs/GITHUB_DEPLOY.md)** ⭐ Hướng dẫn deploy GitHub + Vercel (từng bước, 30 phút)
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) — Các phương án deploy khác (Railway, Docker)
- [BACKTEST.md](docs/BACKTEST.md) — Backtest framework + REST API docs

## 🌐 Web App

Production: **https://vn-breakout-scanner.vercel.app** *(ví dụ)*

- Bảng xếp hạng tín hiệu cập nhật hằng ngày
- Filter theo sàn (HOSE/HNX/UPCOM), điểm số, ngành
- Biểu đồ giá + đánh dấu các tiêu chí đạt
- Xuất Excel/CSV
- Lịch sử tín hiệu (xem mã nào break thành công sau khi xuất hiện)

## ⚠️ Disclaimer

Đây là công cụ **hỗ trợ phân tích kỹ thuật**, KHÔNG phải lời khuyên đầu tư. Tín hiệu chỉ ra *xác suất* break, không đảm bảo. Luôn kết hợp:
- Phân tích cơ bản
- Bối cảnh thị trường chung (VN-Index)
- Quản trị rủi ro (stop-loss, position sizing)

Tác giả không chịu trách nhiệm cho thiệt hại tài chính khi sử dụng.

## 📄 License

MIT License - xem [LICENSE](LICENSE)
