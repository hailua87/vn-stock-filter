// BA TRANG, khong phai mot.
//
// Bo do nay von chi chay `index.html`. Hai trang kia — Watchlist va Dinh gia —
// dung CHUNG styles.css va shared/quality-view.css, nen moi lan sua bo cuc o
// do la sua ca ba trang ma chi mot trang duoc do. Da mac dung kieu hong do
// ngay 21/09 tren chinh index.html.
//
// `khoa` la tien to cua khoa ket qua. index.html KHONG co tien to: giu nguyen
// khoa cu de baseline.json va baseline-ci.json con dung duoc, chi them khoa
// moi cho hai trang kia.
//
// `khung` la danh sach ten viewport duoc chay cho trang do. index chay ca 49;
// hai trang kia chay mot tap con quanh CHINH nguong @media cua chung — chay
// ca 49 cho ba trang la 147 luot, khoang 15 phut, dat hon phan gia tri no
// them vao.

// Nguong @media that cua tung trang, doc tu CSS ngay 24/09/2026:
//   watchlist.css : 1440 (va 1025), 1024, 480
//   valuation.css : 1280, 1024
// Moi nguong chay ca hai phia, cong hai khung desktop va ba khung dien thoai.
const KHUNG_WATCHLIST = [
  'd-1440x900', 'd-1366x768',
  'bp-1441-mouse', 'bp-1439-mouse',
  'bp-1025-mouse', 'bp-1023-mouse',
  'bp-1025-touch', 'bp-1023-touch',
  'bp-421-mouse', 'bp-419-mouse',
  'm-375x667', 'm-402x874', 'm-440x956',
];

const KHUNG_VALUATION = [
  'd-1440x900', 'd-1366x768',
  'bp-1281-mouse', 'bp-1279-mouse',
  'bp-1025-mouse', 'bp-1023-mouse',
  'bp-1025-touch', 'bp-1023-touch',
  'm-375x667', 'm-402x874', 'm-440x956',
];

export const PAGES = [
  {
    ten: 'index',
    khoa: '',                       // khong tien to — giu tuong thich moc chuan cu
    duongDan: '/index.html',
    sanSang: '.table-wrap tbody tr',
    chucNang: true,                 // runFunctional chi viet cho trang nay
    khung: null,                    // null = chay TAT CA
  },
  {
    ten: 'watchlist',
    khoa: 'wl:',
    duongDan: '/watchlist/',
    sanSang: '#wl-tbody tr',
    chucNang: false,
    khung: KHUNG_WATCHLIST,
  },
  {
    ten: 'valuation',
    khoa: 'val:',
    duongDan: '/valuation/',
    sanSang: '#valuation-tbody tr',
    chucNang: false,
    khung: KHUNG_VALUATION,
  },
];

/** Trang nao chay khung nay. */
export function trangChoKhung(tenKhung) {
  return PAGES.filter(p => p.khung === null || p.khung.includes(tenKhung));
}
