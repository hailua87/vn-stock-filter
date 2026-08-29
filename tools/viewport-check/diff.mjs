import { readFileSync } from 'node:fs';
const [base, cur] = process.argv.slice(2);
const A = JSON.parse(readFileSync(base, 'utf8')), B = JSON.parse(readFileSync(cur, 'utf8'));

// Khoa on dinh cho tung loi, de so hai lan chay khac nhau.
const keys = (v) => {
  const out = new Set();
  for (const run of ['top', 'scrolled']) {
    const r = v.runs?.[run]; if (!r) continue;
    (r.overflow || []).forEach(o => out.add(`${run}|tran|${o.el}`));
    (r.textOverflow || []).forEach(o => out.add(`${run}|tranChu|${o.el}|${o.text}`));
    (r.overlap || []).forEach(o => out.add(`${run}|che|${o.covered}<-${o.cover}`));
  }
  (v.functional || []).filter(f => !f.ok).forEach(f => out.add(`fn|${f.name}`));
  return out;
};

let fixed = 0, left = 0, neu = 0;
const NEW = [];
const names = [...new Set([...Object.keys(A.viewports), ...Object.keys(B.viewports)])];
for (const n of names) {
  const a = A.viewports[n] ? keys(A.viewports[n]) : new Set();
  const b = B.viewports[n] ? keys(B.viewports[n]) : new Set();
  const f = [...a].filter(k => !b.has(k));
  const l = [...a].filter(k => b.has(k));
  const x = [...b].filter(k => !a.has(k));
  fixed += f.length; left += l.length; neu += x.length;
  if (x.length) NEW.push([n, x]);
  if (f.length || x.length)
    console.log(`${n.padEnd(21)} DA SUA ${String(f.length).padStart(3)}  CON LAI ${String(l.length).padStart(3)}  MOI ${String(x.length).padStart(3)}`);
}
console.log(`\nTONG   DA SUA ${fixed}   CON LAI ${left}   MOI PHAT SINH ${neu}`);
if (neu) {
  console.log('\n!!! MOI PHAT SINH — phai rong. Chi tiet:');
  for (const [n, x] of NEW) x.forEach(k => console.log(`   ${n.padEnd(21)} ${k}`));
  process.exit(1);
}
