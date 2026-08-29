# Ngoai pham vi dot sua bo cuc mobile — 29/08/2026

Ghi lai kem SO DO de lan sau khong phai do lai. Khong lam trong dot nay.

Nhanh `fix/mobile-layout`, do bang `tools/viewport-check` tren Chromium.

Cac so co ghi "Safari that" la do tren iPhone 16 Pro that, khong phai Chromium
gia lap. Hai nguon nay KHAC NHAU o chieu cao khung nhin (xem muc 1), nen cho
nao dung so nao deu ghi ro.

## 1. topbar cao 138px o 402x714 — THIET KE, khong phai loi

Muc (g) cua audit dong o day.

**Chieu cao man KHONG phai 874px.** Do tren Safari iPhone 16 Pro that:
`visualViewport = 402 x 714`, `innerHeight = 714`, man hinh 874. Safari lay
**160px** cho thanh dia chi duoi. Moi tinh toan cho bang phai tinh tren 714px.
Day cung la ly do anh chup goc thay 10 hang con do trong Chromium (gia dinh
874px) ra 11.

DA THEM khung `safari-ios-thuc-402x714` vao dai viewport (`cc9bc34`), vi day la
chieu cao NGUOI DUNG THAT SU THAY. Giu ca `m-402x874` — cai do la chieu cao MAN
HINH, ung voi trang thai da cuon khi Safari thu thanh dia chi. Dai gio 45 khung.

Phan LOI da sua o hai commit:
- commit 1 (`f0aafbb`): `min-height` tuong minh thay san `auto` cua Flexbox 4.5
  nen topbar bi flex ep tu chieu cao that xuong 48px, noi dung tran ra ngoai.
- commit 5 (`832fd9c`): `[hidden]` bi `display: flex` de len nen hop phan tich
  280px luon chiem mot dong goi. **Topbar 176px -> 138px, bot 38px.**

138px con lai la KICH THUOC THAT. Phan tich, do o 402x714:

| phan | px |
| --- | ---: |
| `.topbar-left` (brand + trang thai) | 18 |
| `.topbar-right` (VALUATION + `?` + NGOAI GIO + dong ho) | 44 |
| `.strategy-tabs` (wrap thanh dong rieng) | 50 |
| padding 6/6 + hai khe 6 | 24 |

Cho bang, do bang cach DEM HANG NAM TRONG KHUNG NHIN — khong phai lay chieu
cao chia. O mobile `.dashboard` la `display: block` nen `.table-wrap` cao het
noi dung (5645px); lay so do chia ra "104 hang" la vo nghia. Da mac dung loi
nay mot lan, ghi lai de khoi lap.

| | truoc commit 5 | sau commit 5 |
| --- | ---: | ---: |
| 402x714 (Safari that) | 11 hang | **12 hang** |
| 402x874 (gia dinh cu) | 15 hang | 16 hang |

**Chieu cao hang: 39px, khong phai 53px.** So 53px trong ban ghi truoc la so
TIEN-SUA bi bo quen lai. Do doi chieu o 402px, cung 5/15 cot `<th>` hien:

| | cot `<th>` hien | cao hang |
| --- | --- | ---: |
| `0dce064` tien-sua | 5/15 | 53px |
| `832fd9c` hien tai | 5/15 | 39px |

So cot nhu nhau, nen 53px khong do cot. No do commit `06b028b`: truoc do 9
`<td>` thieu class `prio-*` nen o van hien du `<th>` da an, o chen nhau lam
hang cao len. Commit do ha chieu cao hang 26% — ket qua truoc day chua ghi.

Giam tiep 62px con lai (18+44) la QUYET DINH THIET KE — bo bot phan tu khoi
topbar mobile — chu khong phai sua loi. Xem M1 o muc 6.

## 2. `.chip { min-width: 44px }` — cung mau loi, CHUA LO

`styles.css` dong 561, va lai o `@media (pointer: coarse)`. Cung co che voi
`.topbar` va `.strat-tab`: gia tri tuong minh thay san `auto`, cho phep nut co
duoi be rong noi dung.

Chua lo vi `.chip-row` co 204px cho 173px noi dung — du 31px. Do thuc te tren
iPad Pro 1366x1024 co cam ung (to hop nguy hiem nhat: tren 1280px nen
`.chip-row` van la flex, va `pointer: coarse` bat): **0 chip tran chu**.

Se lo neu them mot nut vao hang San, hoac doi nhan dai hon "Tất cả" (52px).

## 3. `.icon-btn` bi `min-width: 44px` de len `width: 26px`

`@media (pointer: coarse)` ap `min-width: 44px` cho `.icon-btn`, ma theo spec
`min-width` thang `width`. Nut icon vuong 26px vi the thanh 44px rong tren MOI
thiet bi cam ung. Khong phai loi tran, nhung khong ai chu y — `.icon-btn` duoc
thiet ke la o vuong.

## 4. Dai tab cuon ngang khong co tin hieu bao con tab ben phai

Phat sinh tu commit 2 (`ef88f16`). Truoc do tab bi bop cho vua man hinh nen
nguoi dung thay het (du chu dinh vao nhau). Nay dai tab cuon dung cach —
`scrollWidth=560` tren `clientWidth=386` o 402px — nhung khong co bong mo o
mep, mui ten, hay thanh cuon nhin thay duoc. Nguoi dung khong biet con hai tab
nua ben phai.

Van de thiet ke, khong phai loi bo cuc.

## 5. O nhap ma bi co o 1281-1365px — DA DO, DA CAN NHAC, KHONG SUA

Phep kiem `analyzer:o-nhap-du-rong` (nguong `w >= 200`) bao do o bon khung:
`bp-1281`, `bp-1281-touch`, `d-1366`, `ipad-1366`.

Nguyen nhan: o dai 1281-1365px KHONG con `flex-wrap` (dai tab chi xuong dong
rieng o <=1280px) ma cung CHUA du cho cho topbar mot hang. `.topbar-analyzer`
khong co `flex-shrink: 0` nen no la thu bi co truoc. Khai `width: 280px`, do
that:

| be rong man | o nhap | vung chu | placeholder 115px | "FPT" 22px |
| ---: | ---: | ---: | --- | --- |
| 1281 | 82 | 56 | **cat mat 59px** | lot |
| 1300 | 101 | 75 | **cat mat 40px** | lot |
| 1340 | 141 | 115 | vua du | lot |
| 1366 | 167 | 141 | lot | lot |
| 1920 | 280 | 254 | lot | lot |

Vi sao khong sua:

- Chuc nang khong hong o dau. `maxlength="10"` nhung ma co phieu Viet Nam dai
  3 ky tu; "FPT" chi can 22px, con thua o ca 1281px (vung chu 56px).
- Chi PHAN GOI Y bi cat, va chi trong dai 1281-1339px — rong 59px, khong co
  thiet bi pho bien nao nam trong do (1280, 1366, 1440 deu ngoai).
- Chan co (`flex-shrink: 0`) se day phan co lai sang `.topbar-left` /
  `.topbar-right`, tuc doi mot muc khong ai thay lay chuyen nhan vo dong nang
  them (xem muc 7).

**Luu y ve chinh phep kiem**: nguong 200px la con so ap dat, khong buoc vao yeu
cau nao. Hai khung 1366 that ra KHONG co gi sai — placeholder lot, chu lot — ma
van do chi vi 167 < 200. Nguong dung nghia hon la "placeholder co lot khong".
Chua doi vi doi nguong luc nay la sua phep kiem cho no xanh, khong phai sua
trang. Ghi lai de lan sau quyet dinh co du so.

Bon khung nay duoc danh dau `accepted` trong `tools/viewport-check/accepted.json`.
`diff.mjs` KHONG tinh la loi, nhung VAN IN RA moi lan chay kem ly do va tro ve
day. Van con canh gac: neu `w` tut xuong duoi muc hom nay (82 o 1281, 167 o
1366) thi bao do — luc do khong con la "muc da chap nhan" nua ma la buoc lui moi.

`accepted` KHAC "nhieu". Nhieu la bo do sai, phai vut bo do di. Day la muc co
that ma ta chon song chung, co ho so.

## 6. Ba viec thuoc dot sau (M1, M2, M3)

Ghi lai tu ban dung mau. **Canh bao ve ban dung mau**: no do AI sinh ra, so lieu
trong do SAI va khong duoc dung lam chuan — AAPL lap ba lan voi ba muc gia khac
nhau, mot cho go nham thanh "APPL", thang do ghi nhan "Bullish Neutral Bullish",
hang chip tran ra ngoai khung. **Bang mau trong ban mau KHONG ap dung**: du an
nay da chot nam mau trang thai gia theo quy uoc san Viet Nam va thu tu nap
`tokens.css` truoc `styles.css`. Chi lay Y TUONG BO CUC.

### M1 — thanh dieu huong duoi

Chuyen viec chuyen chien luoc xuong thanh co dinh o day man hinh. Dung ngon
cai voi toi hon dai tab cuon ngang o tren cung.

Cho lay lai duoc, do o 402x714 sau commit 5: dai tab 50px, cong hai nhom nhan
`.topbar-left` 18px + `.topbar-right` 44px la 62px nua neu don luon. Topbar
138px co the ve khoang 76px hoac thap hon. Moi 39px lay lai duoc la them mot
hang bang tren man 714px.

(Con so 118px trong ban ghi truoc da cu: no do TRUOC commit 5, khi hop phan
tich con chiem mot dong goi.)

Dung vao topbar, nen phai co luoi truoc. Phep kiem `textWrap` (them o dot nay)
la luoi do. Sau commit 5 no da sach o 1366-1920px; con **4 nhan vo dong o
1281px** — phan ep that, doc lap voi hop phan tich, chua sua.

### M2 — duong gia thu nho 5 phien

Mot o dinh huong trong moi hang bang, ve gia dong cua nam phien gan nhat.
Can du lieu lich su ma bang hien khong co — phai doi backend, nen khong the
lam trong dot bo cuc.

### M3 — bo cuc the hai cot tren mobile — DA XEM XET, TU CHOI

Ban mau dat moi ma thanh mot the, hai the mot hang. Tu choi vi:

- 402px chia doi con ~193px moi the, tru padding con ~170px cho gia + thay doi
  + khoi luong + tieu chi. It hon mot hang bang hien tai (386px) rat nhieu.
- Bang hien tai da co `prio-*` de an cot theo do rong; the khong tan dung duoc.
- Mat kha nang so sanh theo cot, von la muc dich chinh cua man loc.

## 7. Bon nhan topbar con vo dong o 1281-1299px — DA DO, CHUA SUA

Sau commit 5, phep kiem `textWrap` sach o 1300px tro len. Con lai mot dai hep:

| be rong | so nhan vo dong |
| ---: | ---: |
| 1281 - 1298 | 4 |
| 1300 tro len | 0 |

Bon nhan: `.brand-name` ("VN-SCANNER"), `#live-text` ("EOD dd/mm hh:mm"),
`#market-text` ("NGOÀI GIỜ"), `#clock.time` ("hh:mm:ss ICT") — moi cai 2 dong.

Cung co che voi muc 5: o 1281-1299px khong con `flex-wrap` (dai tab chi xuong
dong rieng o <=1280px) ma cung chua du cho. Khac muc 5 o cho day la phan ep
THAT — no khong biet mat khi an hop phan tich di, nen commit 5 khong dong toi.

Chua sua vi:

- Dai chi rong 19px. Khong co thiet bi pho bien nao trong do; 1280 va 1366 deu
  ngoai. Dung mot diem ngat rieng cho 19px la them mot nhanh CSS phai nuoi.
- Cach sua that (bo bot phan tu khoi topbar) chinh la M1 o muc 6. Sua vat o day
  se phai go ra khi lam M1.
- Khong danh dau `accepted`: bon muc nay co san trong moc chuan nen chung roi
  vao cot CON LAI, khong lam do phep kiem. Danh dau `accepted` chi can khi mot
  muc se roi vao cot MOI PHAT SINH.

Ba cot sau commit 5: DA SUA 582, CON LAI 20, MOI PHAT SINH 0. CON LAI 20 =
16 (4 nhan x 2 khung 1281 x 2 luot do) + 4 (muc 5).
