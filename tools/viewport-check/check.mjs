import { chromium } from 'playwright';
import { writeFileSync } from 'node:fs';
import { VIEWPORTS } from './viewports.mjs';
import { PROBE } from './probe.mjs';
import { runFunctional } from './functional.mjs';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8765';
const OUT  = process.argv[2] || 'result.json';
const SHOTS = process.env.SHOTS === '1';

const browser = await chromium.launch();
const report = { base: BASE, at: new Date().toISOString(), viewports: {} };

const ONLY = process.env.ONLY ? process.env.ONLY.split(',') : null;
for (const v of VIEWPORTS) {
  if (ONLY && !ONLY.includes(v.name)) continue;
  const ctx = await browser.newContext({
    viewport: { width: v.w, height: v.h },
    deviceScaleFactor: 3,
    // isMobile keo theo viewport meta + touch events; hasTouch quyet dinh
    // `pointer: coarse`. Tach ro de truc con tro doc lap voi be rong.
    isMobile: !!v.touch,
    hasTouch: !!v.touch,
  });
  const page = await ctx.newPage();
  const entry = { w: v.w, h: v.h, touch: !!v.touch, runs: {}, functional: [], errors: [] };
  page.on('pageerror', e => entry.errors.push(String(e).slice(0, 120)));

  try {
    await page.goto(BASE + '/index.html', { waitUntil: 'networkidle', timeout: 20000 });
    await page.waitForTimeout(700);

    // Lan 1: dau trang
    entry.runs.top = await page.evaluate(PROBE);
    if (SHOTS) await page.screenshot({ path: `shot-${v.name}-top.png`, fullPage: true });

    // Lan 2: sau khi cuon — loi sticky chi lo khi da cuon
    await page.evaluate(() => window.scrollBy(0, 300));
    await page.waitForTimeout(300);
    entry.runs.scrolled = await page.evaluate(PROBE);
    if (SHOTS) await page.screenshot({ path: `shot-${v.name}-scrolled.png` });

    // Kiem chuc nang: moi nhom tu tai lai trang (xem functional.mjs)
    entry.functional = await runFunctional(page, !!v.touch, BASE);
  } catch (e) {
    entry.errors.push('FATAL: ' + String(e).slice(0, 160));
  }
  report.viewports[v.name] = entry;
  await ctx.close();

  // Ghi lai cau hinh THUC TE trang nhin thay, khong tin khai bao cua context.
  entry.env = entry.runs.top?.env || null;
  const t = entry.runs.top || {};
  const nf = entry.functional.filter(f => !f.ok).length;
  console.log(`${v.name.padEnd(21)} tran=${String((t.overflow||[]).length).padStart(3)}  ` +
              `tranChu=${String((t.textOverflow||[]).length).padStart(3)}  ` +
              `che=${String((t.overlap||[]).length).padStart(3)}  ` +
              `chucNangHong=${String(nf).padStart(2)}  ${entry.errors.length ? 'ERR' : ''}`);
}
await browser.close();
writeFileSync(OUT, JSON.stringify(report, null, 2));
console.log('\nda ghi ' + OUT);
