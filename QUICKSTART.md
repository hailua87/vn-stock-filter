# Hướng dẫn nhanh — 5 phút để chạy

## Tùy chọn 1: Xem ngay web demo (không cần cài đặt)

```bash
cd vn-breakout-scanner/web
python -m http.server 3000
# Mở: http://localhost:3000
```

Web sẽ load dữ liệu mẫu từ `web/data/latest.json` (32 tín hiệu demo).

## Tùy chọn 2: Chạy scan thực với dữ liệu thật

```bash
# 1. Cài Python dependencies
cd vn-breakout-scanner
pip install -r backend/requirements.txt

# 2. Chạy scan (lần đầu sẽ tốn ~15 phút để fetch toàn bộ 1,600 mã)
python backend/run_daily.py --min-score 6

# 3. Kết quả nằm ở:
#    - backend/data/results/signals_YYYY-MM-DD.xlsx  (Excel)
#    - web/data/latest.json                          (cho web dashboard)
```

## Tùy chọn 3: Chạy backend API

```bash
# Khởi động REST API tại http://localhost:8000
cd backend
uvicorn api:app --reload

# Test endpoints:
curl http://localhost:8000/api/health
curl "http://localhost:8000/api/signals/latest?rating=A%2B&limit=5"
```

API docs tự động tại: http://localhost:8000/docs

## Tùy chọn 4: Deploy lên web miễn phí (Vercel + GitHub Actions)

```bash
# 1. Push lên GitHub
git init && git add . && git commit -m "init"
git remote add origin https://github.com/USERNAME/vn-breakout-scanner.git
git push -u origin main

# 2. Vào https://vercel.com → New Project → Import repo
#    - Framework: Other
#    - Root Directory: web
#    - Deploy

# 3. GitHub Actions sẽ tự chạy scan mỗi ngày 16:00 ICT
#    và commit JSON mới → Vercel auto-rebuild
```

Sau ~5 phút bạn có URL `https://your-project.vercel.app`.

## Cấu trúc thư mục

```
vn-breakout-scanner/
├── README.md                      ← Tổng quan
├── QUICKSTART.md                  ← (file này)
├── LICENSE                        ← MIT
├── Dockerfile, docker-compose.yml ← Docker setup
├── vercel.json                    ← Vercel config
│
├── backend/                       ← Python backend
│   ├── scanner/                   ← Core engine (10 tiêu chí)
│   ├── tests/                     ← Unit tests (pytest)
│   ├── api.py                     ← FastAPI server
│   ├── run_daily.py               ← CLI entrypoint cron
│   ├── generate_demo_data.py      ← Script sinh dữ liệu mẫu
│   └── requirements.txt
│
├── web/                           ← Frontend dashboard
│   ├── index.html
│   ├── styles.css                 ← Bloomberg terminal style
│   ├── app.js
│   └── data/latest.json           ← Sinh tự động bởi backend
│
├── docs/                          ← Tài liệu kỹ thuật
│   ├── ARCHITECTURE.md
│   ├── DATA_SOURCES.md            ← Nguồn dữ liệu, vnstock/VCI/TCBS
│   ├── CRITERIA.md                ← Chi tiết 10 tiêu chí + công thức
│   ├── DEPLOYMENT.md              ← Hướng dẫn deploy
│   └── BACKTEST.md                ← Backtest + API docs
│
├── scripts/setup.sh               ← Setup tự động
└── .github/workflows/             ← CI + cron
    ├── daily-scan.yml             ← Chạy hằng ngày 16:00 ICT
    └── ci.yml                     ← Tests on push
```

## 10 Tiêu chí Pre-Breakout (tóm tắt)

| # | Tên | Nhóm | Logic ngắn gọn |
|---|---|---|---|
| 1 | ATR Squeeze | Nén | Biên độ < 85% trung bình 20 phiên |
| 2 | Bollinger Squeeze | Nén | BB width thuộc 25% thấp nhất 60 phiên |
| 3 | Gần đỉnh 20 | Nén | Cách đỉnh ≤ 3% (chưa break) |
| 4 | Stealth Accumulation | Dòng tiền | OBV tăng > 5%, giá tăng < 3% |
| 5 | Volume Surge | Dòng tiền | Vol 5d > 1.15 × MA20 |
| 6 | Upper-half Close | Dòng tiền | ≥ 3/5 phiên đóng cửa nửa trên |
| 7 | MA Alignment | Trend | MA10 > MA20, MA20 hướng lên |
| 8 | RSI 50-65 | Trend | Vùng "khỏe nhưng chưa quá mua" |
| 9 | Pocket Pivot | Dòng tiền | Phiên up có vol > max vol down 10 phiên |
| 10 | No Gap Down | Trend | Không có gap down > 4% trong 5 phiên |

**Tổng điểm 0-10**, xếp loại: A+ (≥8) · A (≥6) · B (≥4) · C (loại)

Xem chi tiết công thức tại [docs/CRITERIA.md](docs/CRITERIA.md).
