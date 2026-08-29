# viewport-check

Kiem bo cuc bang Playwright + Chromium tren mot dai viewport. Chay tren
`web/` phuc vu qua HTTP tinh, so ket qua voi `baseline.json`.

## Chay

```
cd web && python -m http.server 8765 --bind 127.0.0.1 &
cd tools/viewport-check
npm install && npx playwright install chromium
node check.mjs result.json          # SHOTS=1 de chup anh
node diff.mjs baseline.json result.json
```

## Hai truc, khong phai mot

**Be rong** — nguong @media trong styles.css: 1280, 1100, 1024, 900, 860, 768,
700, 600, 420. Moi nguong chay ca hai phia (vd 769 va 767). Loi cascade khong
lo o giua dai, no lo dung luc mot khoi bat hoac tat.

**Con tro** — `@media (pointer: coarse)` CAT NGANG moi nguong be rong. Baseline
dau tien dat `hasTouch = !!v.mobile` nen 18 nguong ranh gioi deu chay chuot, va
duong dan coarse-pointer KHONG he duoc kiem — dung cho nguyen nhan goc so 2 nam.
Nay moi nguong chay hai lan.

## PHAM VI BAO VE CUA TUNG BO DO — doc truoc khi tin mot o mau xanh

Bon bo do bat bon lop loi KHAC NHAU. Khong cai nao thay the duoc cai nao.

### `overflow` — tran ra ngoai viewport
Phan tu co `right > vw+1` hoac `left < -1`.
Da loai: phan tu nam TRON ngoai man (skip-link `-9999px`, drawer dong bi day
sang phai) va phan tu trong vung cuon ngang hop le (`overflow-x: auto`).
**Khong bat duoc**: chu tran ra khoi hop cua chinh no khi hop van trong viewport.

### `textOverflow` — chu rong hon hop chua no
Do bang `Range` tren noi dung phan tu, so voi content box.
Chi xet phan tu co `white-space: nowrap|pre` VA `clientWidth > 0` — hop inline
co clientWidth = 0 theo spec nen phep so vo nghia (208 `<span>` bao nham o lan
chay dau).
**Day la bo do DUY NHAT bat duoc loi dai tab dinh chu.**

### `textWrap` — chu VO DONG (khac han `textOverflow`)
Chi xet con chau cua `.topbar`. Do rieng tung NUT VAN BAN TRUC TIEP, dem so vi
tri `top` khac nhau; >1 la vo dong.

`textOverflow` MU voi loai loi nay: no chi xet phan tu `white-space: nowrap`.
Nhan trong topbar deu `white-space: normal`, nen chung khong tran — chung XUONG
DONG, va truoc dot nay khong bo do nao thay.

Hai bay da dinh, ghi lai de khoi lap:
- `getClientRects()` tra ve MANH rect chu khong phai dong. Dem tho `.length`
  cho ba bao nham o 1920px, vi `<span>emoji</span> + chu` cho nhieu rect cung
  mot dong.
- Do ca noi dung phan tu thi phan tu `inline-flex` cho moi flex item mot rect,
  lech `top` vi chieu cao khac nhau — `💰 VALUATION` bao 2 dong o 1920px du no
  co `white-space: nowrap` va khong the xuong dong.
Do rieng tung nut van ban tranh duoc ca hai. Sau khi sua: 1920px = 0.

### `overlap` — bi phan tu khac che
`elementFromPoint` tai TAM phan tu co text truc tiep.
Da loai phan tu bi to tien CAT (tam roi ra ngoai client rect cua mot to tien
`overflow != visible`) — 19 cap gia o desktop 1366px o lan chay dau.

### `functional` — bam that, khong chi nhin
Drawer chi tiet mo/dong, drawer bo loc + backdrop, sau tab bam duoc, o nhap
analyzer khong bi che. Vu `.col-detail` la loi CHUC NANG: drawer chet tren
desktop ma anh tinh van trong binh thuong.

## CANH BAO: `functional` KHONG bat duoc loi tab dinh chu

Do la ket qua thuc te, khong phai gia dinh:

| | be rong tab | `elementFromPoint` tai tam | `textOverflow` |
| --- | ---: | --- | --- |
| bp-767 chuot | 94px | `div.mobile-bar` — BAT DUOC | 0 |
| m-402 cam ung | 63px | `button.strat-tab` — XANH | 6 tab, tran 21-38px |

O 402px sau tab da hong hoan toan ve mat hinh (chu tran 21-38px khoi hop, dinh
sang nut ben), nhung TAM cua nut 63px van thuoc ve chinh nut do, nen phep kiem
"6 tab bam duoc" VAN XANH.

Nguoc lai o bp-767 chuot, tab rong 94px nen khong tran chu, nhung ca dai tab bi
`.mobile-bar` (z-30) ve de len — `functional` bat duoc, `textOverflow` khong.

**Mot o xanh o `functional` KHONG co nghia la dai tab lanh.** Doc ca bon cot.

## PHEP KIEM PHAT HIEN vs PHEP KIEM XAC NHAN

Do bang cach chay chinh bo cong cu nay tren mot `git worktree` tai 0dce064 —
trang thai TRUOC moi ban va — roi xem tung phep kiem co DO hay khong.
Mot phep kiem chua tung do chua chung minh duoc no bat duoc gi.

| phep kiem | o trang thai LOI GOC | loai |
| --- | --- | --- |
| `textOverflow` tren `.strat-tab` | **DO** — 6 tab, chu 74px / hop 43px | **PHAT HIEN** |
| `tab:khong-bi-bop-chu` (scrollW > clientW) | XANH — scrollW=412 clientW=386 | XAC NHAN |
| `tab:cuon-den-cuoi-duoc` | XANH — dat=26 doc lai=26 | XAC NHAN |
| `tab:cuoi-toi-duoc-sau-khi-cuon` | XANH — w=72 hit=chinh no | XAC NHAN |
| `textWrap` tren nhan `.topbar` | **DO** — 4 nhan vo dong o 1281-1600px | **PHAT HIEN** |

**Ba trong bon phep kiem cuon dai tab la XAC NHAN, khong phai PHAT HIEN.**

VI SAO chung xanh — va day la cho de doc nham. KHONG phai vi chung khong lien
quan toi loi. Chung rat lien quan:

```
hong:  scrollWidth 412  /  clientWidth 386     (nut bi bop xuong 43px)
dung:  scrollWidth 560  /  clientWidth 386     (nut giu be rong that)
```

O trang thai hong dai tab VAN cuon duoc, chi 26px thay vi 174px. `scrollWidth`
phan anh loi RAT RO — lech 148px. Phep kiem xanh vi no dat cau hoi NHI PHAN
(`scrollW > clientW ?`) cho mot dai luong LIEN TUC, roi vut bo chinh tin hieu do
khi rut ve true/false.

Khac biet nay quan trong: phep kiem khong lien quan thi bo di cung duoc; phep
kiem dung sai nguong thi SUA DUOC thanh phat hien.

Vi vay `scrollWidth`, `clientWidth`, `tabCount` va be rong tung tab duoc ghi vao
baseline duoi dang SO DO (`runs.top.metrics`), va `diff.mjs` so chung voi nguong
8px (tabCount: 0). So do doi khong lam fail build — no la thong tin — nhung no
KHONG con nam im trong baseline ma khong ai doc.

## Gioi han khong khac phuc duoc

Chromium **khong phai** Safari iOS. Hai thu SE KHONG tai hien duoc, phai xac
nhan tay tren may that:
  - `env(safe-area-inset-*)` — notch, Dynamic Island, thanh Home
  - thanh dia chi Safari che dong cuoi khi cuon

Ket qua desktop dang tin hon ket qua mobile.

## SAFE AREA — chi do duoc tren may that

`env(safe-area-inset-*)` KHONG do duoc bang bat cu cong cu nao trong repo nay:

- Chromium headless khong co thanh dia chi de an, va khong co API nao (ke ca
  CDP) dat duoc safe-area inset khac 0.
- WebKit cua Playwright la build headless tren desktop — khong notch, khong
  home indicator, nen cung tra 0. Cai them no khong giai quyet duoc gi.

Do tren iPhone 16 Pro that o ban `f2137be`: ca bon canh deu **0px**, va do la
KET QUA HOP LE — khi Safari hien thanh dia chi o day, no thu vung noi dung con
402x714 va tu chua cho Dynamic Island lan home indicator, nen vung do da nam
tron trong safe area.

Bon so chi khac 0 o hai luc:
  (a) Safari thu thanh dia chi khi cuon xuong — vung noi dung gian ra sat mep
  (b) chay standalone tu man hinh chinh — chua the xay ra: repo khong co
      manifest.json lan the apple-mobile-web-app-capable

**Khong tu do duoc (a). Phai do tren may that**, o trang thai da cuon cho thanh
dia chi thu lai, va o ca hai chieu xoay.

Cai bo do o day LAM DUOC la kiem HE QUA: bom gia tri gia vao dung cac khai bao
ma khoi @supports dat, roi xem bo cuc co chiu duoc khong. Xem chu thich khoi
`@supports (padding: env(...))` o cuoi `web/styles.css`.

### Bom gia tri gia vao safe-area: hai kieu do SAI da mac

Do mot to hop KHONG XAY RA THAT la tu bia ra thiet hai. Hai lan da mac:

**1. Bom ca bon canh cung luc.** Khong bao gio xay ra. Tren iPhone:
  - DOC : trai/phai = 0 (khong co gi che hai ben), tren/duoi khac 0
  - NGANG: tren = 0 (Dynamic Island nam mot ben), trai/phai va duoi khac 0
Bom ca bon canh o che do doc lam topbar mat 118px be ngang va bao 2 nhan vo
dong — mot ket qua khong co that. Bom theo to hop dung: 0 muc.

**2. Bom inset khac 0 ma giu nguyen chieu cao cu.** Inset chi khac 0 khi Safari
DA THU thanh dia chi, ma luc do khung nhin CAO HON (402x714 -> 402x874). Do voi
714px roi bao "mat 2 hang" la sai: thuc te duoc 15 hang, nhieu hon ca truoc.

To hop dung de bom:
| che do | tren | phai | duoi | trai | khung |
| --- | ---: | ---: | ---: | ---: | --- |
| doc, thanh da thu | 59 | 0 | 34 | 0 | 402x874 |
| ngang | 0 | 59 | 21 | 59 | 874x402 |

(Cac so tren la gia tri DO, khong phai so do duoc — xem muc safe-area o tren.)

### Nhieu lam tron cua flex o 1281px

`.chip-row` o 1281px la flex; chip `flex: 1 1 auto` chia sub-pixel khong on
dinh: cung mot trang chay bon lan cho 57.38 roi 57.92 ba lan, lam tron thanh
57 vs 58. Truoc khi ket luan mot thay doi CSS gay ra chenh lech 1px, do lai
NHIEU LAN o cung dieu kien. Da mot lan doc nham nhieu nay thanh hoi quy.

## HAI MOC CHUAN — dung cai nao o dau

| tep | do o dau | ai dung |
| --- | --- | --- |
| `baseline.json` | Chromium tren **Windows**, font Windows | do tai may khi phat trien |
| `baseline-ci.json` | Chromium tren **ubuntu-latest**, font Linux | cong CI (`.github/workflows/viewport-check.yml`) |

**KHONG DUNG CHUNG DUOC.** Font Windows va font Linux cho be rong chu khac
nhau, ma `textOverflow` va `textWrap` do CHINH be rong chu. Lay moc chuan
Windows di so tren Linux thi cong do ngay luot dau, khong phai vi trang sai.

Khong the do khac biet nay tai may neu may khong co Docker/WSL — nen moc chuan
CI phai SINH TRONG CI, khong doan ra duoc.

### Sinh / dung lai `baseline-ci.json`

1. Chay workflow o che do `workflow_dispatch` (khong so sanh, chi tai ket qua
   len artifact).
2. Tai artifact `ket-qua-viewport-<run_id>` ve.
3. Doi ten `ket-qua-ci.json` thanh `baseline-ci.json`, commit.
4. Chay `workflow_dispatch` lan thu hai va so voi ban vua commit. **Phai xanh.**
   Khong xanh nghia la co gi do khong tat dinh trong chinh moi truong CI —
   dieu tra, dung va cho qua.

### Dung lai `baseline.json` (tai may) khi DOM doi HOP LE

Doi DOM hop le (them cot, doi nhan, them phan tu) lam moc chuan cu het nghia:
moi khoa deu "da sua" hoac "moi phat sinh" ma khong noi len dieu gi.

1. Xac nhan thay doi la CO Y, khong phai hoi quy — doc ba cot trong lan chay
   cuoi truoc khi doi.
2. Khoi dong DUNG MOT may chu: `cd web && python -m http.server 8765 --bind 127.0.0.1`
   (hai tien trinh cung cong tren Windows chia yeu cau bat dinh va gay treo).
3. `node check.mjs baseline-moi.json` roi doi ten thanh `baseline.json`.
4. Chay lai mot luot va so voi moc chuan vua chot: phai ra 0 muc moi. Neu
   khong, bo do co cho khong tat dinh — sua bo do truoc, dung chot moc chuan.
5. Ghi trong commit message: doi cai gi, vi sao, va so khung truoc/sau.

`accepted.json` KHONG bi anh huong khi dung lai moc chuan — no doc lap, va do
la chu y: muc da can nhac khong sua van phai duoc in ra va canh gac du moc
chuan co doi.
