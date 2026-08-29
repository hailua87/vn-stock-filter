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

// ── CHONG TREO ──
// Lan chay truoc treo hang gio: may chu cuc bo chet ma Playwright van cho
// `networkidle`, moi viewport cho toi het timeout, nhan 44 khung. Bon thay doi:
//
// 1. KIEM MAY CHU truoc moi khung. Chet thi thoat NGAY voi thong bao ro, khong
//    de 44 khung lan luot het gio.
// 2. BO `networkidle`. Trang co dong ho chay va polling nen mang co the KHONG
//    BAO GIO im — `networkidle` la dieu kien co the khong bao gio den. Dung
//    `domcontentloaded` roi cho DUNG thu can: hang dau tien cua bang.
// 3. Timeout tuong minh 15s cho ca dieu huong lan cho selector.
// 4. In tien do TRUOC khi chay moi khung, khong phai sau — treo o dau nhin ra
//    ngay thay vi im lang.
const HAN_MS = 15000;
const TONG_HAN_MS = Number(process.env.TONG_HAN_MS || 45 * 60 * 1000);
const batDau = Date.now();

async function kiemMayChu() {
  const c = new AbortController();
  const h = setTimeout(() => c.abort(), 5000);
  try {
    const r = await fetch(BASE + '/index.html', { signal: c.signal });
    return r.ok;
  } catch { return false; } finally { clearTimeout(h); }
}

async function moTrang(page) {
  await page.goto(BASE + '/index.html', { waitUntil: 'domcontentloaded', timeout: HAN_MS });
  // Cho DUNG thu can chu khong cho mang im: hang dau tien cua bang da render.
  await page.waitForSelector('.table-wrap tbody tr', { timeout: HAN_MS });
  await page.waitForTimeout(600);
}

if (!(await kiemMayChu())) {
  console.error(`MAY CHU CHET: ${BASE} khong tra loi.`);
  console.error('Khoi dong lai:  cd web && python -m http.server 8765 --bind 127.0.0.1');
  console.error('Luu y: dung de HAI tien trinh cung mot cong — tren Windows chung');
  console.error('chia yeu cau bat dinh va gay treo. Kiem bang:');
  console.error("  Get-CimInstance Win32_Process -Filter \"Name='python.exe'\"");
  process.exit(2);
}

const TONG = ONLY ? VIEWPORTS.filter(v => ONLY.includes(v.name)).length : VIEWPORTS.length;
let dem = 0;
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

  dem++;
  const giay = Math.round((Date.now() - batDau) / 1000);
  process.stdout.write(`[${String(dem).padStart(2)}/${TONG}] ${v.name.padEnd(22)} (${giay}s) ... `);
  if (Date.now() - batDau > TONG_HAN_MS) {
    console.error(`
QUA HAN TONG ${Math.round(TONG_HAN_MS / 60000)} phut — dung lai.`);
    await ctx.close(); break;
  }
  if (!(await kiemMayChu())) {
    console.error(`
MAY CHU CHET giua chung tai khung ${v.name}. Dung ngay.`);
    await ctx.close(); process.exit(2);
  }

  try {
    await moTrang(page);

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
