import { readFileSync, existsSync } from 'node:fs';
const [base, cur] = process.argv.slice(2);
const A = JSON.parse(readFileSync(base, 'utf8')), B = JSON.parse(readFileSync(cur, 'utf8'));

// Muc DA CHAP NHAN: da do, da can nhac, quyet dinh KHONG sua (co tai lieu kem).
// KHAC "nhieu": nhieu la bo do sai, phai vut di. Day la loi CO THAT ma ta chon
// song chung — nen van in ra moi lan chay, va van co canh gac: neu con so tut
// xuong duoi muc hom nay thi do, vi luc do no khong con la "muc da chap nhan"
// nua ma la mot buoc lui moi.
const ACC = existsSync('accepted.json')
  ? JSON.parse(readFileSync('accepted.json', 'utf8')).muc || [] : [];
const laChapNhan = (n, k) => ACC.find(a => a.khoa === k && a.khung.includes(n));

// Che chu so trong khoa. Dong ho va nhan phien doi theo tung giay/tung ngay:
// "21:16:55 ICT" o lan chay nay khac "20:01:32 ICT" o moc chuan, nen CUNG MOT
// khuyet diem bi dem hai lan — "da sua" ben nay, "moi phat sinh" ben kia (10 muc
// ma o lan dau). Che chu so van giu duoc kha nang phan biet phan tu.
const chuan = (t) => String(t).replace(/\d/g, '#').slice(0, 60);

// Khoa on dinh cho tung loi, de so hai lan chay khac nhau.
const keys = (v) => {
  const out = new Set();
  for (const run of ['top', 'scrolled']) {
    const r = v.runs?.[run]; if (!r) continue;
    (r.overflow || []).forEach(o => out.add(`${run}|tran|${o.el}`));
    (r.textOverflow || []).forEach(o => out.add(`${run}|tranChu|${o.el}|${chuan(o.text)}`));
    (r.textWrap || []).forEach(o => out.add(`${run}|voDong|${o.el}|${chuan(o.text)}`));
    (r.overlap || []).forEach(o => out.add(`${run}|che|${o.covered}<-${o.cover}`));
    if (r.cols && !r.cols.khop) out.add(`${run}|cotLech|th=${r.cols.thHien} td=${r.cols.tdHien}`);
  }
  (v.functional || []).filter(f => !f.ok).forEach(f => out.add(`fn|${f.name}`));
  return out;
};

// So SO DO, khong chi so co. Mot truong so nam im trong baseline ma khong ai so
// thi no khong khac gi khong co.
// Nguong 8px: du de bo qua sai lech lam tron / khac font metrics giua may, du
// chat de bat mot tab bi bop (412 vs 560 la lech 148px).
const NGUONG_PX = 8;
const METRIC_KEYS = ['tabsScrollWidth', 'tabsClientWidth', 'tabCount'];
const metricDiffs = [];
const cmpMetrics = (n, a, b) => {
  const ma = a?.runs?.top?.metrics, mb = b?.runs?.top?.metrics;
  if (!ma || !mb) return;
  for (const k of METRIC_KEYS) {
    const d = Math.abs((mb[k] ?? 0) - (ma[k] ?? 0));
    const nguong = k === 'tabCount' ? 0 : NGUONG_PX;
    if (d > nguong) metricDiffs.push({ n, k, truoc: ma[k], sau: mb[k], lech: d });
  }
};

let fixed = 0, left = 0, neu = 0;
const NEW = [], ACCHIT = [], GAC = [], LEFT = new Map();
const names = [...new Set([...Object.keys(A.viewports), ...Object.keys(B.viewports)])];
for (const n of names) {
  const a = A.viewports[n] ? keys(A.viewports[n]) : new Set();
  const b = B.viewports[n] ? keys(B.viewports[n]) : new Set();
  const f = [...a].filter(k => !b.has(k));
  const l = [...a].filter(k => b.has(k));
  const x = [...b].filter(k => !a.has(k) && !laChapNhan(n, k));
  // Gom tu TOAN BO b, khong chi tu cot "moi": muc da chap nhan thuong co san
  // trong moc chuan nen no roi vao CON LAI, ma van phai in ra moi lan chay.
  [...b].filter(k => laChapNhan(n, k)).forEach(k => ACCHIT.push([n, k]));
  fixed += f.length; left += l.length; neu += x.length;
  l.forEach(k => LEFT.set(k, (LEFT.get(k) || 0) + 1));
  if (x.length) NEW.push([n, x]);
  cmpMetrics(n, A.viewports[n], B.viewports[n]);
  // Canh gac: muc da chap nhan van phai KHONG te them.
  for (const acc of ACC.filter(m => m.khung.includes(n) && m.san)) {
    const fn = (B.viewports[n]?.functional || []).find(p => `fn|${p.name}` === acc.khoa);
    const v = fn?.so?.[acc.san.truong];
    // San rieng tung khung: cung mot loi nhung do co dan khac nhau (chuot 82px,
    // cam ung 64px vi nut 44px an them cho ngang cua topbar).
    const san = acc.san.toiThieu[n];
    if (v != null && san != null && v < san)
      GAC.push({ n, khoa: acc.khoa, truong: acc.san.truong, do: v, san });
  }
  if (f.length || x.length)
    console.log(`${n.padEnd(21)} DA SUA ${String(f.length).padStart(3)}  CON LAI ${String(l.length).padStart(3)}  MOI ${String(x.length).padStart(3)}`);
}
console.log(`\nTONG   DA SUA ${fixed}   CON LAI ${left}   MOI PHAT SINH ${neu}`);
if (LEFT.size) {
  console.log('\n--- CON LAI (co o ca moc chuan lan lan chay nay) ---');
  [...LEFT.entries()].sort((p, q) => q[1] - p[1])
    .forEach(([k, c]) => console.log(`   ${String(c).padStart(3)}x  ${k}`));
}
if (ACCHIT.length) {
  console.log('\n--- DA CHAP NHAN (khong tinh la loi, nhung van in ra moi lan) ---');
  const daIn = new Set();
  for (const [n, k] of ACCHIT) {
    const a = laChapNhan(n, k);
    if (!daIn.has(k)) { console.log(`   ${k}\n      ly do : ${a.lyDo}\n      ho so : ${a.taiLieu}`); daIn.add(k); }
    console.log(`      khung : ${n}`);
  }
}
if (GAC.length) {
  console.log('\n!!! MUC DA CHAP NHAN BI TE THEM — do:');
  GAC.forEach(g => console.log(`   ${g.n.padEnd(21)} ${g.khoa}  ${g.truong}=${g.do} < san ${g.san}`));
}
if (neu || GAC.length) {
  if (neu) {
    console.log('\n!!! MOI PHAT SINH — phai rong. Chi tiet:');
    for (const [n, x] of NEW) x.forEach(k => console.log(`   ${n.padEnd(21)} ${k}`));
  }
  process.exit(1);
}
