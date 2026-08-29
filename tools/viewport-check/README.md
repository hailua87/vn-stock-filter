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

## Gioi han khong khac phuc duoc

Chromium **khong phai** Safari iOS. Hai thu SE KHONG tai hien duoc, phai xac
nhan tay tren may that:
  - `env(safe-area-inset-*)` — notch, Dynamic Island, thanh Home
  - thanh dia chi Safari che dong cuoi khi cuon

Ket qua desktop dang tin hon ket qua mobile.
