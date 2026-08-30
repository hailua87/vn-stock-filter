// Chan doan: vi tri THAT cua .col-detail sau khi dong, khong lam tron.
// Khong phai phep kiem — chi in so de so hai nen.
import { chromium } from 'playwright';
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8765';
const b = await chromium.launch();
for (const [ten, w, h, touch] of [['bp-899-touch', 899, 800, true], ['d-1440x900', 1440, 900, false]]) {
  const c = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 3,
                                 isMobile: touch, hasTouch: touch });
  const p = await c.newPage();
  await p.goto(BASE + '/index.html', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await p.waitForSelector('.table-wrap tbody tr', { timeout: 15000 });
  await p.waitForTimeout(1500);
  await p.click('.table-wrap tbody tr', { timeout: 3000 }).catch(() => {});
  await p.waitForTimeout(800);
  await p.click('#detail-close', { timeout: 3000 }).catch(() => {});
  await p.waitForTimeout(1200);
  const o = await p.evaluate(() => {
    const e = document.querySelector('#col-detail') || document.querySelector('.col-detail');
    if (!e) return null;
    const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    const tamX = r.x + r.width / 2, tamY = r.y + r.height / 2;
    const hit = document.elementFromPoint(Math.min(Math.max(tamX, 0), innerWidth - 1),
                                          Math.min(Math.max(tamY, 0), innerHeight - 1));
    const giao = Math.max(0, Math.min(r.right, innerWidth) - Math.max(r.left, 0));
    return {
      x: r.x, y: r.y, w: r.width, h: r.height, right: r.right, left: r.left,
      vw: innerWidth, dpr: devicePixelRatio,
      transform: s.transform, display: s.display, visibility: s.visibility, opacity: s.opacity,
      hienTheoSpec: e.checkVisibility ? e.checkVisibility() : null,
      hit: hit ? (hit.id || hit.className || hit.tagName) : null,
      hitLaDrawer: hit ? (hit === e || e.contains(hit)) : false,
      giaoViewport: giao, tiLeGiao: r.width ? giao / r.width : 0,
    };
  });
  console.log(`\n=== ${ten} (${w}x${h}, touch=${touch}) ===`);
  if (!o) { console.log('  khong tim thay .col-detail'); await c.close(); continue; }
  console.log(`  x            = ${o.x}`);
  console.log(`  right        = ${o.right}   left = ${o.left}`);
  console.log(`  w x h        = ${o.w} x ${o.h}`);
  console.log(`  vw           = ${o.vw}   dpr = ${o.dpr}`);
  console.log(`  transform    = ${o.transform}`);
  console.log(`  display=${o.display} visibility=${o.visibility} opacity=${o.opacity}`);
  console.log(`  checkVisibility() = ${o.hienTheoSpec}`);
  console.log(`  elementFromPoint tai tam = ${o.hit}   la drawer? ${o.hitLaDrawer}`);
  console.log(`  phan GIAO voi viewport   = ${o.giaoViewport}px  (${(o.tiLeGiao * 100).toFixed(3)}% be rong)`);
  console.log(`  phep kiem hien tai: x >= vw - 1  ->  ${o.x} >= ${o.vw - 1}  ->  ${o.x >= o.vw - 1}`);
  await c.close();
}
await b.close();
