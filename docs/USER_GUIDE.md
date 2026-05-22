# Hướng dẫn cho người mới (Non-technical Guide)

> Tài liệu này dành cho **nhà đầu tư cá nhân, trader, hoặc người không có nền tảng lập trình**.
> Nếu bạn quen Python/Git, hãy đọc [QUICKSTART.md](../QUICKSTART.md).

## Bạn sẽ cần gì?

Một trong 2 lựa chọn:

### 🟢 Lựa chọn A (đơn giản nhất) — Dùng web đã deploy
Nếu ai đó (bạn hoặc cộng đồng) đã deploy lên Vercel → chỉ cần mở URL trên trình duyệt. Không cần cài đặt gì. Bỏ qua phần cài đặt bên dưới.

### 🟡 Lựa chọn B — Tự deploy lên web miễn phí
- Tài khoản GitHub (miễn phí, đăng ký tại github.com)
- Tài khoản Vercel (miễn phí, đăng ký bằng GitHub tại vercel.com)
- 30 phút thời gian
- **Không cần biết lập trình**

### 🔴 Lựa chọn C — Chạy trên máy tính của bạn
- Máy tính (Windows/Mac/Linux)
- Cài Python 3.10 trở lên
- Kết nối internet (để fetch giá)
- Quen dùng terminal/command line cơ bản

---

## Lựa chọn B: Deploy lên web (chi tiết từng bước)

### Bước 1: Tải code về (5 phút)

1. Tải file `vn-breakout-scanner.zip` (đã có sẵn)
2. Giải nén ra một thư mục
3. Bạn sẽ có thư mục `vn-breakout-scanner` với các file bên trong

### Bước 2: Tạo tài khoản GitHub (nếu chưa có)

1. Vào https://github.com → "Sign up"
2. Nhập email, tạo password
3. Verify email

### Bước 3: Upload code lên GitHub

**Cách dễ nhất — không cần Git:**

1. Trên GitHub, click nút **"New"** màu xanh (hoặc icon "+") để tạo repository mới
2. Đặt tên: `vn-breakout-scanner` (hoặc tên khác)
3. Chọn **Public** (để dùng free GitHub Actions)
4. **KHÔNG** tick "Add a README" (vì chúng ta đã có sẵn)
5. Click **"Create repository"**
6. Ở trang repo mới, click **"uploading an existing file"**
7. Kéo thả toàn bộ nội dung trong thư mục `vn-breakout-scanner` (không phải bản thân thư mục) vào trình duyệt
8. Click **"Commit changes"** — đợi 1-2 phút upload xong

> 💡 **Lưu ý**: Nếu kéo thả nhiều file lỗi, dùng GitHub Desktop app (https://desktop.github.com) — UI dễ dùng hơn.

### Bước 4: Deploy lên Vercel

1. Vào https://vercel.com → "Sign Up" → chọn **"Continue with GitHub"**
2. Cho phép Vercel truy cập repo của bạn
3. Trang chủ Vercel → click **"Add New..."** → **"Project"**
4. Tìm repo `vn-breakout-scanner` → click **"Import"**
5. Trong màn hình cấu hình:
   - **Framework Preset**: chọn **"Other"**
   - **Root Directory**: click "Edit" → chọn `web` → click "Continue"
   - **Build Command**: để trống
   - **Output Directory**: để mặc định (`.`)
6. Click **"Deploy"**
7. Đợi 30 giây — Vercel sẽ build xong và cho bạn URL như `https://vn-breakout-scanner-xxx.vercel.app`

### Bước 5: Bật tự động cập nhật hằng ngày

1. Quay lại trang GitHub repo của bạn
2. Click tab **"Actions"** (phía trên trang)
3. Nếu có thông báo "Workflows aren't being run on this forked repository" → click **"I understand my workflows, go ahead and enable them"**
4. Xong! Hệ thống sẽ tự chạy lúc 16:00 ICT mỗi ngày làm việc

### Bước 6: Chạy thử ngay lần đầu (tuỳ chọn)

Nếu bạn không muốn đợi đến chiều mai:

1. Trang Actions → click vào workflow **"Daily Scan"** (cột bên trái)
2. Click **"Run workflow"** (nút màu xám bên phải) → chọn branch `main` → **"Run workflow"**
3. Đợi 15-20 phút (lần đầu chạy lâu vì phải fetch toàn bộ data)
4. Khi xong, web URL của bạn sẽ tự cập nhật dữ liệu mới trong vài phút

🎉 **Hoàn tất!** Web của bạn đã chạy và tự cập nhật hằng ngày miễn phí.

---

## Lựa chọn C: Chạy trên máy tính

### Bước 1: Cài Python

**Windows:**
1. Vào https://python.org/downloads
2. Tải Python 3.11
3. Chạy installer — **TICK ô "Add Python to PATH"** (rất quan trọng!)
4. Click "Install Now"

**Mac:**
```
brew install python@3.11
```
Hoặc tải installer từ python.org

**Linux:**
```bash
sudo apt install python3.11 python3-pip
```

### Bước 2: Mở terminal/command line

- **Windows**: Phím Windows → gõ "cmd" → Enter
- **Mac**: Cmd+Space → gõ "Terminal" → Enter
- **Linux**: Ctrl+Alt+T

### Bước 3: Vào thư mục project

```bash
cd đường/dẫn/đến/vn-breakout-scanner
```

Trên Windows ví dụ:
```
cd C:\Users\TenBan\Downloads\vn-breakout-scanner
```

### Bước 4: Cài thư viện

```bash
pip install -r backend/requirements.txt
```

Nếu lỗi `pip not found`, thử:
```bash
python -m pip install -r backend/requirements.txt
```

Đợi 2-3 phút.

### Bước 5: Chạy scan

```bash
python backend/run_daily.py
```

**Lần đầu sẽ tốn 15-20 phút** vì phải tải dữ liệu của 1,600 mã. Lần sau chỉ ~3 phút.

Khi xong, terminal sẽ in:
```
✅ Found 42 signals with score >= 6
TOP 10 SIGNALS:
ticker exchange  close rating  total_score  ...
FPT    HOSE     138.50    A+            9  ...
...
```

### Bước 6: Mở dashboard

```bash
cd web
python -m http.server 3000
```

Mở trình duyệt vào: **http://localhost:3000**

Để dừng: Ctrl+C trong terminal.

---

## Cách dùng dashboard

### Màn hình chính

```
┌────────────────────────────────────────────────────────────┐
│  VN-BREAKOUT  ● LIVE      15:38 ICT       Last scan: 16:05 │ ← Thanh trạng thái
├────────────────────────────────────────────────────────────┤
│  Bắt sóng trước khi giá break                              │ ← Tiêu đề
│  [3 stats: tổng tín hiệu, A+, mã đã quét]                 │
├────────────────────────────────────────────────────────────┤
│  [Date Picker] [Sàn] [Xếp loại] [Tìm mã]      [↓ CSV]    │ ← Filters
├────────────────────────────────────────────────────────────┤
│  📅 Ngày phân tích: Thứ Sáu · 15/05/2026                  │ ← Banner ngày
│     ✓ Giá đã điều chỉnh  ✓ Lọc corporate actions          │
├────────────────────────────────────────────────────────────┤
│  Bảng tín hiệu (click row để xem chi tiết)                │
└────────────────────────────────────────────────────────────┘
```

### Đọc bảng kết quả

| Cột | Ý nghĩa |
|---|---|
| **#** | Thứ hạng theo điểm |
| **MÃ** | Mã cổ phiếu. ⚑ = có sự kiện sắp tới |
| **SÀN** | HOSE / HNX / UPCOM |
| **GIÁ** | Giá đóng cửa phiên gần nhất (nghìn VND) |
| **±5D** | % thay đổi 5 phiên (xanh tăng, đỏ giảm) |
| **VOL×** | Volume hiện tại so với MA20 (1.5× = cao gấp 1.5 lần) |
| **RSI** | Chỉ số RSI(14), vùng 50-65 là tốt |
| **→ĐỈNH** | % cách đỉnh 20 phiên (càng nhỏ càng gần break) |
| **TIÊU CHÍ** | 10 ô vuông: hồng=Nén, xanh dương=Dòng tiền, xanh lá=Trend. Sáng = đạt |
| **ĐIỂM** | Tổng điểm /10 |
| **HẠNG** | A+ (rất mạnh) / A (mạnh) / B (trung bình) |

### Filter

- **NGÀY PHÂN TÍCH**: Chọn ngày trong dropdown, hoặc bấm `‹ ›` để lùi/tiến
- **SÀN**: Click chip để chỉ xem 1 sàn
- **XẾP LOẠI**: Click chip để chỉ xem hạng cụ thể (vd: chỉ A+)
- **TÌM MÃ**: Gõ mã (vd: FPT) để tìm nhanh

### Click vào 1 mã

Bên phải sẽ mở ra panel chi tiết:
- Thông tin giá: close, change, đỉnh 20, RSI, vol ratio
- Danh sách 10 tiêu chí đạt/không đạt
- Cảnh báo sự kiện sắp tới (nếu có)
- Link nhanh đến TradingView / StockBiz / CafeF

### Export CSV

Nút **↓ CSV** ở góc phải filter — tải file Excel-compatible với toàn bộ tín hiệu hiện đang filter.

---

## Sử dụng tín hiệu thế nào?

> ⚠️ **Đây không phải lời khuyên đầu tư.** Tín hiệu chỉ là input cho quá trình ra quyết định của bạn.

### Quy trình đề xuất

1. **Sáng**: Mở dashboard, lọc rating **A+** trên sàn HOSE
2. Xem **2-3 mã top** điểm cao nhất
3. Mở chart TradingView (qua link trong drawer) để xem trực quan
4. Kiểm tra:
   - Có sự kiện cận kề không? (flag ⚑ đỏ) → Cẩn thận
   - Khối lượng có thực sự âm thầm tăng không?
   - Vùng kháng cự rõ ràng chưa?
5. Đặt cảnh báo giá break trên app môi giới của bạn
6. **CHỈ vào lệnh khi giá thực sự break** với volume xác nhận

### Tránh các bẫy

❌ **KHÔNG** mua chỉ vì điểm A+ — phải có xác nhận break
❌ **KHÔNG** all-in vào 1 mã — chia nhỏ 3-5 mã
❌ **KHÔNG** lờ đi flag sự kiện ⚑ — đặc biệt cổ tức cổ phiếu
❌ **KHÔNG** vào lệnh trong vùng VN-Index downtrend mạnh

✓ Luôn đặt **stop-loss** ngay dưới vùng tích lũy
✓ Chốt lời từng phần (1/3 - 1/3 - 1/3)
✓ Theo dõi 5-7 mã, không quá 10

---

## Câu hỏi thường gặp

Xem [FAQ.md](FAQ.md) để có danh sách đầy đủ.

## Cần giúp đỡ?

- **Vấn đề kỹ thuật**: Mở issue trên GitHub repo
- **Câu hỏi về phương pháp**: Đọc [CRITERIA.md](CRITERIA.md)
- **Câu hỏi về deploy**: Đọc [DEPLOYMENT.md](DEPLOYMENT.md)
