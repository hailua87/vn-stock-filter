# Ngoai pham vi dot sua bo cuc mobile — 29/08/2026

Ghi lai kem SO DO de lan sau khong phai do lai. Khong lam trong dot nay.

Nhanh `fix/mobile-layout`, do bang `tools/viewport-check` tren Chromium.

## 1. topbar cao 176px o 402x874 — THIET KE, khong phai loi

Muc (g) cua audit dong o day. Phan LOI da sua xong o commit 1: `min-height`
tuong minh thay san `auto` cua Flexbox 4.5 nen topbar bi flex ep tu 176px xuong
48px va noi dung tran ra ngoai hop. Sau khi chan co ep, 176px la KICH THUOC
THAT — von bi loi che giau.

Phan tich 176px:

| phan | px | danh gia |
| --- | ---: | --- |
| hang tren: brand + trang thai + VALUATION + `?` + NGOAI GIO + dong ho | 118 | qua nhieu cho man 402px |
| dai tab (`.strategy-tabs`, wrap thanh dong rieng) | 50 | chinh dang |
| padding topbar | 8 | |

Chi phi: ba thanh (topbar 176 + mobile-bar 51 + footer 32) chiem **259px / 874px**,
tuc 30% man hinh. Bang con **615px**, hien **11 hang** (moi hang 53px).

Giam 118px do la QUYET DINH THIET KE — bo bot phan tu khoi topbar mobile — chu
khong phai sua loi. Vi du: an `NGOAI GIO` va dong ho o <=768px (chung da co
`.topbar-center { display: none }` lam tien le), hoac gop VALUATION vao mot menu.

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
