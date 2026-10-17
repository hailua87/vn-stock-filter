# TradingAgents — đã khảo, KHÔNG tích hợp (17/10/2026)

Chủ kho quyết định không áp dụng vào dự án. Tài liệu này ghi **đã hỏi những
đâu** và **đo được gì**, theo `CLAUDE.md` mục 10 — một kết luận âm không ghi
nguồn sẽ bị khảo lại từ đầu, hoặc tệ hơn, được tin mà không ai kiểm.

## Đối tượng đã khảo

[TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
— Apache-2.0, Python ≥3.11, dựng trên LangGraph. Kèm
[bài báo arXiv 2412.20138](https://arxiv.org/html/2412.20138v4).

Không có repo nào tên đúng "TradingAgent"; đây là repo được hỏi tới.

Kiến trúc: 4 Analyst (cơ bản, tâm lý, tin tức, kỹ thuật) chạy song song → 2
Researcher tranh luận bên mua/bên bán → Trader → Risk management → Portfolio
Manager phê duyệt. Dữ liệu: Yahoo Finance, SEC EDGAR, FRED, Alpha Vantage,
Polymarket, StockTwits/Reddit. Có `run_backtest` tính alpha thực so với chỉ số
vùng, nhóm theo hạng.

## Ba rào CỨNG — lý do thật của quyết định

Không phải "framework dở". Kiến trúc vai trò của nó hợp lý, và README của nó
**trung thực hơn bài báo** (tự gọi là "research scaffold", nói rõ "backtest
không bảo đảm khớp bất kỳ con số đã công bố", và tự nhận **không tất định**).

### 1. Không có đường vào dữ liệu cơ bản Việt Nam

- **SEC EDGAR là Mỹ.** Toàn bộ tầng cơ bản của kho — balance sheet tính bằng
  **tỷ đồng**, section `NOTE` của VCI (chỗ mở được NPL cho 17/17 ngân hàng) —
  không có cổng nào vào framework đó.
- Yahoo Finance **có** mã hậu tố `.VN`, nhưng BCTC doanh nghiệp VN trên đó rất
  mỏng. Giá thì có, cơ bản thì không đủ cho `methods_pe`, `methods_pb_roe`,
  `methods_ev_ebitda`, `methods_dcf_ddm`.
- **StockTwits và Reddit gần như không có mã VN.** Analyst tâm lý vì vậy chạy
  trên rỗng — tệ hơn là chạy trên nhiễu mà vẫn trả ra một con số.

### 2. Gấp khoảng 50 lần ngân sách thời gian

Chính bài báo nêu **11 lượt LLM + hơn 20 lượt gọi công cụ cho MỘT dự đoán**, và
nêu đó là lý do họ chỉ kiểm được 3 tháng. Nhân rổ 232 mã của kho:

```
~2.550 lượt LLM     và     >4.600 lượt gọi công cụ     mỗi ngày
```

`MIN_INTERVAL = 1.0` áp cho **mọi nguồn cộng lại** (mục 3, và từ PR #103 còn
siết thành liên tiến trình). Chỉ riêng 4.600 lượt gọi ở nhịp 1 giây đã là
**~77 phút**, chưa tính thời gian LLM. Không vừa bất kỳ tầng nào trong ba tầng
`FETCH_BUDGET_S < script tự dừng < timeout-minutes` (mục 4).

### 3. Không tất định, ngược toàn bộ hướng của kho

README tự nói không tất định: LLM sampling, mô hình reasoning bỏ qua
`temperature`, và dữ liệu tin tức/xã hội sống thay đổi theo thời gian. Hệ quả:

- Kỷ luật mục 6 — **mỗi test mới phải phá cho ĐỎ** — không áp được lên một
  phán đoán LLM.
- Bộ đo bố cục đã phải gỡ **năm** nguồn bất định (mục 8). Thêm một nguồn bất
  định ở tầng **quyết định** là đi ngược chính việc đó.

### 4. Bẫy đơn vị, nếu ai đó vẫn nối thử

Yahoo trả giá cổ phiếu VN bằng **đồng**; pipeline kỹ thuật của kho tính bằng
**nghìn đồng** (mục 2). Nối thẳng là tái tạo đúng lớp lỗi đã cho upside
**+98.600%**.

### 5. Bề mặt phụ thuộc

LangGraph cộng SDK của hàng chục nhà cung cấp. Kho vừa **rút** `vnstock` và
`vnai` để gọi thẳng API (mục 3); `vnai` còn từng tự ghi prompt vào tệp cấu hình
của agent.

## Phản biện chất lượng bằng chứng — chiều so sánh bị ĐẢO

Điểm đáng ghi nhất: thước đo của kho **nghiêm hơn** thước đo trong bài báo.

| | TradingAgents (bài báo) | `vn-stock-filter` (mục 11) |
|---|---|---|
| Số mã | **3** (AAPL, GOOGL, AMZN) | 232 mã, 4 chiến lược |
| Kỳ | **3 tháng** (01–03/2024) | sổ theo dõi liên tục |
| Đối chứng | 5 quy tắc cứng (B&H, MACD, KDJ&RSI, ZMR, SMA) | **giả dược**: vào ngẫu nhiên cùng rổ, cùng phiên |
| Khoảng tin cậy | **không có** | 95%, bootstrap **khối ngày** |
| Phí / slippage | **không mô hình hoá** | — |
| Kết luận | "vượt mọi baseline" | **"không chiến lược nào khác chọn bừa"** |

Ba con số của họ đáng nghi, đã kiểm:

- **Sharpe 8,21** trên AAPL. Mức đó không phải "chiến lược tốt", nó là dấu hiệu
  lỗi phương pháp. Chính tác giả chú thích rằng nó vượt dải họ kỳ vọng.
- **AAPL CR +26,62% với max drawdown 0,91%** trong đúng quý AAPL **giảm ~10,7%**
  (Jan −4,2% · Feb −1,8% · Mar −5,1%, theo
  [bảng mùa vụ TickerLeague](https://tickerleague.com/companies/AAPL/seasonality)
  — một nguồn thứ ba, giá thuần, nên con số chính xác cần kiểm lại ở nguồn gốc).
  Vừa lãi 26,6% vừa chỉ sụt 0,91% trên một cổ phiếu giảm hai chữ số thì phải
  vào/ra gần như hoàn hảo. Đó là hình dạng của **bias**, không của kỹ năng.
- **AR không khớp kỳ**: 26,62% trong ~0,24 năm quy ra 30,5%/năm là ngược chiều;
  giải phương trình ra N ≈ 0,89 năm, không được giải thích.

Bài báo nói "agent chỉ dùng dữ liệu tới ngày giao dịch" nên không có
look-ahead, **nhưng không bàn mốc cắt kiến thức** của gpt-4o/o1-preview so với
cửa sổ kiểm. Công bằng: 01–03/2024 nằm **sau** mốc cắt công bố của những mô hình
đó, nên nhiễm dữ liệu huấn luyện **yếu hơn vẻ ngoài** — nhưng việc không kiểm
chứng điều đó là một lỗ hổng, đúng loại "xanh rỗng" ở mục 6.

## Những gì KHÔNG bị loại — ba ý đáng lấy, làm TẤT ĐỊNH

Lấy **ý tưởng**, không lấy mã, và cả ba làm được không cần LLM:

1. **Luận điểm ngược có cấu trúc** (từ cặp Researcher mua/bán). Nguyên liệu đã
   có sẵn: `methods_excluded`, `dispersion`, `beta_weak`, `warnings`, chất lượng
   rổ peer. Gom thành một trường "luận cứ phản bác" sinh bằng quy tắc từ chính
   các con số đó. **Giá trị cao nhất, không thêm bất định nào** — và vá đúng chỗ
   đang yếu: báo cáo định giá nói mã này đáng mua mà không nói **vì sao có thể
   sai**.
2. **Alpha so chỉ số vùng, nhóm theo hạng** (cách `run_backtest` của họ tính
   điểm). Giả dược của kho mạnh hơn, nhưng lăng kính này trả lời câu **khác**:
   "hạng STRONG BUY có thật chạy hơn hạng HOLD không". Rẻ, vì kho đã lấy
   VN-Index.
3. **Risk manager tách khỏi trader** → trần phơi nhiễm ở tầng danh mục. Kho có
   `trade_levels` cho từng mã nhưng không có ràng buộc tổng.

**Module reflection (học từ giao dịch cũ): KHUYÊN CHƯA LÀM.** Kho đã có
`web/data/outcomes/`, nhưng mục 11 ghi khoảng tin cậy của cả bốn chiến lược
**đều chứa 0**. Lấy kết quả quá khứ điều chỉnh trọng số khi chưa phân biệt được
với chọn bừa là **khớp vào nhiễu** — đúng bẫy mục 12 đã vạch với `beta`.

## Nếu ai muốn khảo lại: hãy đặt nó vào cân của kho

1. Chạy **độc lập, ngoài kho**, 10–15 mã vốn hoá lớn qua Yahoo `.VN`,
   `temperature=0`, mô hình non-reasoning (README nói cách này cho tái lập chặt
   hơn nhưng **không bảo đảm**).
2. Đem kết quả qua **đúng phép kiểm mục 11**: giả dược vào ngẫu nhiên cùng rổ
   cùng phiên, 95% CI, bootstrap khối ngày.
3. **Dự đoán ghi trước để kiểm được: khoảng tin cậy sẽ chứa 0**, như cả bốn
   chiến lược hiện có. Nếu nó vượt, đó là phát hiện thật và đáng làm tiếp.

Ghi dự đoán trước là cố ý: không ghi thì lượt khảo sau sẽ đọc kết quả rồi tự
thấy nó hợp lý.

## Đã hỏi những đâu

| Hỏi gì | Ở đâu | Kết quả |
|---|---|---|
| Repo nào, giấy phép, phụ thuộc | README trên GitHub | Apache-2.0, LangGraph, Python ≥3.11 |
| Nguồn dữ liệu, có thị trường ngoài Mỹ không | README | Yahoo có `.VN`; cơ bản thì SEC EDGAR, chỉ Mỹ |
| Chi phí mỗi dự đoán | bài báo, phần hạn chế | 11 lượt LLM + >20 lượt gọi công cụ |
| Có tất định không | README, mục reproducibility | **không**; `temperature=0` chỉ chặt hơn, không bảo đảm |
| Phương pháp đánh giá | bài báo arXiv v4, Bảng 1 | 3 mã, 3 tháng, không CI, không phí giao dịch |
| AAPL thật sự diễn biến thế nào trong kỳ đó | tìm web, bảng mùa vụ TickerLeague | **giảm ~10,7%** trong 01–03/2024 |

**Chưa hỏi** (ghi để biết giới hạn của kết luận này): chưa đọc mã nguồn
`run_backtest` của họ, chưa chạy thử trên mã VN, chưa đo chi phí tiền thật cho
một lượt 232 mã. Ba rào cứng ở trên đủ để quyết định mà không cần ba việc đó,
nhưng nếu ai muốn lật lại kết luận thì đó là chỗ nên bắt đầu.
