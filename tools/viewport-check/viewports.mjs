// HAI TRUC, khong phai mot.
//
// Truc 1 — BE RONG: nguong @media trong styles.css la 1280, 1100, 1024, 900,
// 860, 768, 700, 600, 420. Loi cascade khong lo o giua dai, no lo dung luc mot
// khoi bat/tat, nen moi nguong deu chay ca hai phia.
//
// Truc 2 — CON TRO: `@media (pointer: coarse)` CAT NGANG moi nguong be rong va
// dat min-width/min-height 44px cho .chip, .dp-nav, .icon-btn, .strat-tab.
// Dat gia tri tuong minh la THAY THE sang `auto` cua Flexbox §4.5, tuc XOA san
// kich thuoc noi dung — chinh la nguyen nhan goc so 2. Baseline lan dau chi
// bat coarse cho ba viewport mobile, nen 18 nguong ranh gioi deu KHONG di qua
// duong dan do. Nay moi nguong chay HAI LAN: chuot va cam ung.
const BOUNDARIES = [1281, 1279, 1101, 1099, 1025, 1023, 901, 899, 861, 859,
                    769, 767, 701, 699, 601, 599, 421, 419];

const list = [];
// desktop chuot
for (const [w, h] of [[1440, 900], [1366, 768], [1280, 800]])
  list.push({ name: `d-${w}x${h}`, w, h, touch: false });

// iPad Pro 12.9 — CAM UNG o be rong TREN 1280px. O do .chip-row van la flex
// (luoi 2 cot chi tu 1280 tro xuong) va pointer: coarse bat cung luc. Do la
// to hop ma bao cao audit da chi ra la con ho o .chip { min-width: 44px }.
list.push({ name: 'ipad-1366x1024-touch', w: 1366, h: 1024, touch: true });
list.push({ name: 'ipad-1024x1366-touch', w: 1024, h: 1366, touch: true });

// ranh gioi: moi nguong hai lan
for (const w of BOUNDARIES) {
  list.push({ name: `bp-${w}-mouse`, w, h: 800, touch: false });
  list.push({ name: `bp-${w}-touch`, w, h: 800, touch: true });
}

// mobile that (luon cam ung)
for (const [w, h] of [[375, 667], [402, 874], [440, 956]])
  list.push({ name: `m-${w}x${h}`, w, h, touch: true });

// CHIEU CAO THAT NGUOI DUNG THAY tren iPhone 16 Pro, khong phai 874.
// Do tren Safari that: visualViewport = 402x714, innerHeight = 714, man
// hinh 874 — Safari lay 160px cho thanh dia chi duoi. Khung m-402x874 o
// tren la chieu cao MAN HINH; khung nay la chieu cao KHUNG NHIN. Giu ca
// hai: cai tren cho trang thai da cuon (thanh dia chi thu lai), cai nay
// cho trang thai thuong.
list.push({ name: 'safari-ios-thuc-402x714', w: 402, h: 714, touch: true });

export const VIEWPORTS = list;
