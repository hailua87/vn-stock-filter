# Triển khai (Deployment)

## Tổng quan kiến trúc deployment

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  GitHub Actions  │     │  Railway/Render  │     │  Vercel/Netlify  │
│  (cron 16:00)    │     │  (FastAPI)       │     │  (Web static)    │
├──────────────────┤     ├──────────────────┤     ├──────────────────┤
│ Daily scan       │────>│ Serve API        │<────│ Dashboard        │
│ Push to GitHub   │     │ /api/signals/... │     │ Fetch JSON       │
└──────────────────┘     └──────────────────┘     └──────────────────┘
        │                                                  ▲
        │                                                  │
        └──── Commit web/data/latest.json ─── trigger ────┘
                                              Vercel rebuild
```

3 phương án deploy (chọn 1 theo nhu cầu):

| Phương án | Chi phí | Phù hợp khi |
|---|---|---|
| **A. Static-only** (Vercel + GitHub cron) | $0 | Solo, < 100 user, không cần API động |
| **B. Hybrid** (Vercel static + Railway API) | $0-5/tháng | < 1,000 user, cần search/filter động |
| **C. Full backend** (Railway/Fly.io với worker) | $10-30/tháng | Production, có user accounts |

## Phương án A: Static-only (khuyến nghị bắt đầu)

### Bước 1: Push code lên GitHub

```bash
cd vn-breakout-scanner
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<your-username>/vn-breakout-scanner.git
git push -u origin main
```

### Bước 2: Setup GitHub Actions

File `.github/workflows/daily-scan.yml` đã có sẵn. Nó:
- Chạy mỗi ngày 16:00 ICT (= 09:00 UTC)
- Cài Python + dependencies
- Chạy `python backend/run_daily.py`
- Commit `web/data/latest.json` vào repo

### Bước 3: Deploy frontend lên Vercel

1. Đăng nhập https://vercel.com bằng GitHub
2. Click "Add New Project" → chọn repo `vn-breakout-scanner`
3. Configure:
   - **Framework Preset**: Other
   - **Root Directory**: `web`
   - **Build Command**: (để trống)
   - **Output Directory**: `.`
4. Click "Deploy"

Sau ~30 giây bạn có URL như `https://vn-breakout-scanner.vercel.app`.

### Bước 4: Tự động rebuild khi data mới

Vercel tự rebuild mỗi lần có commit. GitHub Actions commit `latest.json` mỗi ngày → web auto-update.

## Phương án B: Hybrid với Railway API

Khi bạn cần API động (filter, search, user query nhiều tham số).

### Deploy backend lên Railway

1. Tạo tài khoản https://railway.app
2. New Project → Deploy from GitHub repo
3. Configure:
   - **Root directory**: `backend`
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `uvicorn api:app --host 0.0.0.0 --port $PORT`
4. Sau khi deploy, lấy URL như `vn-scanner-api.railway.app`

### Cấu hình frontend gọi API

Edit `web/app.js`:
```javascript
const API_BASE = 'https://vn-scanner-api.railway.app';
// thay vì: '/data/latest.json'
const response = await fetch(`${API_BASE}/api/signals/latest?min_score=6`);
```

### Lưu data persistent

Railway free tier có ephemeral filesystem. Để giữ dữ liệu:
- **Option 1**: Railway volume (paid) — $5/month
- **Option 2**: Lưu output lên S3/R2/Supabase Storage (free tier)
- **Option 3**: Cứ chạy scan trong API container (mỗi sáng) — đơn giản nhất

## Phương án C: Production full

Khi có user accounts, lịch sử search, alert, etc.

**Stack**:
- Frontend: Next.js trên Vercel
- API: FastAPI trên Fly.io / Railway
- DB: Supabase Postgres (free tier 500MB)
- Auth: Supabase Auth hoặc Clerk
- Queue: Inngest hoặc Trigger.dev (cron + retry tốt hơn GH Actions)

## Cron alternative ngoài GitHub Actions

| Tool | Pros | Cons |
|---|---|---|
| **GitHub Actions** | Free, log tốt | Đôi khi cron delay 5-15 phút |
| **Cloudflare Workers Cron** | Free, đúng giờ | Không chạy Python được trực tiếp |
| **Cron-job.org** | Free, đúng giờ | Chỉ trigger HTTP, cần endpoint sẵn |
| **EasyCron** | Free 20 job | Tương tự |
| **Server VPS + crontab** | Hoàn toàn kiểm soát | Tốn $4-5/month, phải maintain |

## Domain custom

1. Mua domain tại Namecheap / Cloudflare Registrar (~$10/năm)
2. Vercel → Settings → Domains → Add `yourdomain.com`
3. Cập nhật DNS theo hướng dẫn

## Monitoring

### Health check
- Endpoint `/api/health` trả về `last_scan` timestamp
- Setup UptimeRobot (free) ping mỗi 5 phút
- Alert qua email/Slack/Telegram nếu down

### Theo dõi data freshness
```bash
curl https://your-api.railway.app/api/health
# {"status":"ok","last_scan":"2026-05-16T16:05:00","signal_count":42}
```

Nếu `last_scan` > 24h cũ → có vấn đề với cron, kiểm tra GitHub Actions log.

## Chi phí ước tính

### Mức 1 (start, $0/tháng)
- Vercel static: free (100GB bandwidth)
- GitHub Actions: free (2,000 phút/tháng cho public repo, 500 cho private)
- Daily scan ~3 phút × 22 ngày làm việc = 66 phút/tháng ✅

### Mức 2 (có API, $5/tháng)
- + Railway hobby plan ($5/month, $5 free credit đầu)

### Mức 3 (production, $25-50/tháng)
- Railway pro: $20
- Supabase pro: $25
- Domain: $1/tháng

## Bảo mật

- **KHÔNG commit API keys** vào repo
- Dùng GitHub Secrets cho credentials
- Vercel/Railway env variables cho production
- Rate limit API: 60 req/phút per IP (dùng slowapi middleware)

```python
# Thêm vào api.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.get("/api/signals/latest")
@limiter.limit("60/minute")
def latest_signals(...):
    ...
```

## Troubleshooting

### vnstock lỗi 403/429
- Rate limit bị chặn → giảm `max_workers` xuống 2, tăng `delay` lên 0.5s
- Hoặc đổi source: `VCI` → `TCBS` → `MSN`

### Data không update trên web
- Check GitHub Actions log: Repo → Actions tab
- Check Vercel deployment log
- Force rebuild: Vercel → Deployments → Redeploy

### API trả về 500
- Check Railway log
- Đa số là do `data/results/` rỗng (scan chưa chạy lần nào)
- Chạy `python backend/run_daily.py` manual 1 lần để có data
