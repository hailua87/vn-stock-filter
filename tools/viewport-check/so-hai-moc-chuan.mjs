// So baseline.json (Windows) voi baseline-ci.json (Linux) va bao khac biet.
//
// KHONG phai de "hoa giai" hai moc chuan — chung khong dung chung duoc, xem
// README. Muc dich: neu Linux lo ra loi THAT ma Windows khong thay (hoac
// nguoc lai), do la thong tin dang gia. Dung lang le chap nhan ca hai.
//
// Chay: node so-hai-moc-chuan.mjs [a.json] [b.json]
import { readFileSync } from 'node:fs';

const [fa = 'baseline.json', fb = 'baseline-ci.json'] = process.argv.slice(2);
const A = JSON.parse(readFileSync(fa, 'utf8'));
const B = JSON.parse(readFileSync(fb, 'utf8'));

const chuan = t => String(t).replace(/\d/g, '#').slice(0, 60);
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

console.log(`A = ${fa}  (${Object.keys(A.viewports).length} khung, chay ${A.at})`);
console.log(`B = ${fb}  (${Object.keys(B.viewports).length} khung, chay ${B.at})\n`);

const ten = [...new Set([...Object.keys(A.viewports), ...Object.keys(B.viewports)])];
const chiA = new Map(), chiB = new Map();
let lech = 0;

for (const n of ten) {
  if (!A.viewports[n]) { console.log(`   ${n.padEnd(24)} CHI CO O B`); lech++; continue; }
  if (!B.viewports[n]) { console.log(`   ${n.padEnd(24)} CHI CO O A`); lech++; continue; }
  const a = keys(A.viewports[n]), b = keys(B.viewports[n]);
  const ka = [...a].filter(k => !b.has(k));
  const kb = [...b].filter(k => !a.has(k));
  if (ka.length || kb.length) {
    lech++;
    console.log(`   ${n.padEnd(24)} chi A: ${String(ka.length).padStart(2)}   chi B: ${String(kb.length).padStart(2)}`);
    ka.forEach(k => chiA.set(k, (chiA.get(k) || 0) + 1));
    kb.forEach(k => chiB.set(k, (chiB.get(k) || 0) + 1));
  }
}

console.log(`\n${lech}/${ten.length} khung co khac biet`);
const bang = (m, nhan) => {
  if (!m.size) { console.log(`\n${nhan}: khong co`); return; }
  console.log(`\n${nhan}:`);
  [...m.entries()].sort((p, q) => q[1] - p[1])
    .forEach(([k, c]) => console.log(`   ${String(c).padStart(3)}x  ${k}`));
};
bang(chiA, `CHI XUAT HIEN O A (${fa})`);
bang(chiB, `CHI XUAT HIEN O B (${fb})`);

// So them tri so lien tuc de thay muc do chenh lech chu khong chi co/khong
console.log('\nTRI SO (khung co trong ca hai):');
for (const n of ten) {
  const ma = A.viewports[n]?.runs?.top?.metrics, mb = B.viewports[n]?.runs?.top?.metrics;
  if (!ma || !mb) continue;
  const d = ['tabsScrollWidth', 'tabsClientWidth'].map(k => [k, (mb[k] ?? 0) - (ma[k] ?? 0)])
    .filter(([, v]) => Math.abs(v) > 8);
  if (d.length) console.log(`   ${n.padEnd(24)} ${d.map(([k, v]) => `${k} ${v > 0 ? '+' : ''}${v}px`).join('  ')}`);
}
