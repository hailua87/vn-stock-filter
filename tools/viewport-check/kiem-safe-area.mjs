// Bom gia tri gia vao dung cac khai bao ma khoi @supports safe-area dat, roi
// do bo cuc. KHONG do duoc safe-area that (xem muc SAFE AREA trong README);
// day la phep kiem HE QUA: neu inset khac 0 thi bo cuc co chiu duoc khong.
//
// Chay:  node kiem-safe-area.mjs
//        LUI=1 node kiem-safe-area.mjs    (ep ve trang thai truoc fix .chip,
//                                          de kiem tra phep kiem con DO duoc)
import { chromium } from 'playwright';
import { PROBE } from './probe.mjs';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8765';
// Ep .chip ve `min-width: 0` — trang thai truoc 13d6ddd. Dung de chung minh
// phep kiem nay khong phai lo vo dung.
const LUI = process.env.LUI === '1';

// TO HOP CO THAT, khong phai ca bon canh cung luc — xem README, muc
// "hai kieu do SAI da mac".
const CA = [
  { ten: 'doc, thanh dia chi da thu', w: 402, h: 874, t: 59, r: 0,  b: 34, l: 0  },
  { ten: 'ngang',                     w: 874, h: 402, t: 0,  r: 59, b: 21, l: 59 },
];

const css = ({ t, r, b, l }) => `
.topbar{padding-top:calc(var(--topbar-pad-y) + ${t}px);
        padding-left:calc(var(--topbar-pad-x) + ${l}px);
        padding-right:calc(var(--topbar-pad-x) + ${r}px)}
.site-disclaimer{padding-bottom:calc(var(--foot-pad-y) + ${b}px);
        padding-left:calc(var(--foot-pad-x) + ${l}px);
        padding-right:calc(var(--foot-pad-x) + ${r}px)}
.col-filters{padding-top:${t}px;padding-bottom:${b}px;padding-left:${l}px}
.col-detail{padding-top:${t}px;padding-bottom:${b}px;padding-right:${r}px}`;

const br = await chromium.launch();
let hong = 0;
if (LUI) console.log('LUI=1 — ep .chip ve min-width:0, phep kiem PHAI bao do\n');

for (const c of CA) {
  const ctx = await br.newContext({ viewport: { width: c.w, height: c.h },
                                    isMobile: true, hasTouch: true, deviceScaleFactor: 3 });
  const p = await ctx.newPage();
  await p.goto(BASE + '/index.html', { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(1200);

  const truoc = await p.evaluate(PROBE);
  await p.addStyleTag({ content: css(c) });
  if (LUI) await p.addStyleTag({ content: '@media (max-width:1280px){ .chip-row .chip{min-width:0} }' });
  await p.waitForTimeout(400);
  const sau = await p.evaluate(PROBE);

  const hang = s => `tran=${s.overflow.length} tranChu=${s.textOverflow.length} ` +
                    `voDong=${s.textWrap.length} che=${s.overlap.length}`;
  const moi = sau.overflow.length + sau.textOverflow.length +
              sau.textWrap.length + sau.overlap.length -
              (truoc.overflow.length + truoc.textOverflow.length +
               truoc.textWrap.length + truoc.overlap.length);
  console.log(`${c.ten}  ${c.w}x${c.h}  (tren ${c.t}, phai ${c.r}, duoi ${c.b}, trai ${c.l})`);
  console.log(`   inset 0 : ${hang(truoc)}`);
  console.log(`   inset do: ${hang(sau)}   ${moi > 0 ? `>>> THEM ${moi} MUC` : 'khong them muc nao'}`);
  for (const o of sau.textOverflow)
    console.log(`      tran chu: ${o.el} chu ${o.textW}px / hop ${o.boxW}px tran ${o.tran}px "${o.text}"`);
  for (const o of sau.textWrap)
    console.log(`      vo dong : ${o.el} ${o.soDong} dong w=${o.w} "${o.text}"`);
  if (moi > 0) hong++;
  await ctx.close();
}
await br.close();
console.log(hong ? `\n${hong}/${CA.length} to hop SINH MUC MOI` : `\n${CA.length}/${CA.length} to hop sach`);
process.exit(hong ? 1 : 0);
