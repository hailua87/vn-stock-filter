// KIEM CHUC NANG — khong chi kiem hinh.
// Vu .col-detail la loi CHUC NANG: drawer chet tren desktop ma anh tinh van
// trong binh thuong. Nen moi lan chay deu phai bam that.
//
// MOI NHOM TU TAI LAI TRANG. Khong lam vay thi trang thai ro ri: drawer bo loc
// con mo se che dai tab, va phep kiem tab bao hong oan.
const URL_ = base => base + '/index.html';
const settle = p => p.waitForTimeout(600);

export async function runFunctional(page, isMobile, base) {
  // Nhanh mobile chon theo BE RONG, khong theo co isMobile cua context.
  // bp-767 khong mang co do nhung 767 <= 768 nen no VAN o che do drawer —
  // lan chay dau bao 8 loi oan chi vi di nham nhanh desktop.
  const vpw = page.viewportSize().width;
  const drawerMode = vpw <= 768;
  const out = [];
  const rec = (name, ok, detail = '') => out.push({ name, ok, detail });
  const load = async () => { await page.goto(URL_(base), { waitUntil: 'networkidle', timeout: 20000 }); await settle(page); };
  const box = sel => page.$eval(sel, el => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return { x: r.x, y: r.y, w: r.width, h: r.height, display: s.display, vw: innerWidth,
             visible: s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0,
             inViewport: r.left >= -1 && r.right <= innerWidth + 1 };
  }).catch(() => null);

  // ── 1. Drawer chi tiet ──
  await load();
  try {
    const row = await page.$('tbody tr[data-ticker]');
    if (!row) rec('detail:mo', false, 'khong co hang nao trong bang');
    else {
      await row.click({ timeout: 3000 });
      await settle(page);
      const d = await box('#col-detail');
      rec('detail:mo', !!d && d.visible && d.w > 100 && d.x < d.vw - 10,
          d ? `x=${Math.round(d.x)} w=${Math.round(d.w)} vw=${d.vw}` : 'khong tim thay');
      rec('detail:trong-viewport', !!d && d.inViewport, d ? `${Math.round(d.x)}..${Math.round(d.x + d.w)}` : '');
      await page.click('#detail-close', { timeout: 3000 }).catch(() => {});
      await settle(page);
      const d2 = await box('#col-detail');
      // Dong dung = day han ra ngoai mep phai (x >= vw) hoac an
      rec('detail:dong', !!d2 && (!d2.visible || d2.x >= d2.vw - 1),
          d2 ? `x=${Math.round(d2.x)} vw=${d2.vw}` : 'da an');
    }
  } catch (e) { rec('detail:mo', false, String(e).slice(0, 70)); }

  // ── 2. Cot bo loc ──
  await load();
  if (drawerMode) {
    try {
      await page.click('#mobile-filter-btn', { timeout: 3000 });
      await settle(page);
      const f = await box('#col-filters'), b = await box('#mobile-backdrop');
      rec('loc:drawer-mo', !!f && f.x > -10, f ? `x=${Math.round(f.x)}` : '');
      rec('loc:backdrop-hien', !!b && b.visible, b ? `display=${b.display}` : '');
      // Bam vao GOC PHAI DUOI cua backdrop: giua man hinh dang bi drawer che.
      const vp = page.viewportSize();
      await page.mouse.click(vp.width - 8, vp.height - 8);
      await settle(page);
      const b2 = await box('#mobile-backdrop');
      const f2 = await box('#col-filters');
      rec('loc:backdrop-dong', (!b2 || !b2.visible) && (!f2 || f2.x < -10),
          `backdrop=${b2 ? b2.display : 'an'} colX=${f2 ? Math.round(f2.x) : '?'}`);
    } catch (e) { rec('loc:drawer-mo', false, String(e).slice(0, 70)); }
  } else {
    const f = await box('#col-filters');
    const pos = await page.$eval('#col-filters', el => getComputedStyle(el).position).catch(() => '?');
    rec('loc:cot-co-dinh-desktop', !!f && f.visible && pos !== 'fixed',
        `position=${pos} w=${f ? Math.round(f.w) : '?'}`);
  }

  // ── 3. Sau tab ──
  await load();
  const tabs = await page.$$eval('.strat-tab', els => els.map(e => e.dataset.strategy));
  for (const t of tabs) {
    // Cuon tab vao tam nhin TRUOC khi do. Sau khi .strategy-tabs cuon ngang
    // duoc (dung nhu thiet ke), tab nam ngoai vung cuon tra ve hit=null — do la
    // dung, khong phai bi che. Do ma khong cuon la trach trang vi da lam dung.
    await page.$eval(`.strat-tab[data-strategy="${t}"]`,
      el => el.scrollIntoView({ block: 'nearest', inline: 'nearest' })).catch(() => {});
    await page.waitForTimeout(120);
    const hit = await page.$eval(`.strat-tab[data-strategy="${t}"]`, el => {
      const r = el.getBoundingClientRect();
      const h = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return { self: h === el || el.contains(h),
               hit: h ? (h.tagName.toLowerCase() + '.' + String(h.className).split(' ')[0]) : null,
               w: Math.round(r.width) };
    }).catch(() => null);
    rec(`tab:${t}:khong-bi-che`, !!hit && hit.self, hit ? `w=${hit.w} hit=${hit.hit}` : 'loi');
  }

  // ── 3b. Dai tab CO THUC SU CUON NGANG khong ──
  // `overflow-x: auto` chi co nghia neu noi dung that su rong hon hop. Khi nut
  // con bi ep co, scrollWidth == clientWidth va thuoc tinh do la lenh chet.
  if (drawerMode) {
    const sc = await page.$eval('.strategy-tabs', el => {
      const before = el.scrollLeft;
      const max = el.scrollWidth - el.clientWidth;
      el.scrollLeft = max;
      const after = el.scrollLeft;
      return { scrollWidth: el.scrollWidth, clientWidth: el.clientWidth, max, after, before };
    }).catch(() => null);
    // Chi doi CUON DUOC khi noi dung that su rong hon hop. O 599px chuot sau tab
    // vua khit (scrollW == clientW) nen khong co gi de cuon — do khong phai loi.
    const canScroll = !!sc && sc.scrollWidth > sc.clientWidth + 1;
    rec('tab:khong-bi-bop-chu', !!sc,
        sc ? `scrollW=${sc.scrollWidth} clientW=${sc.clientWidth} ${canScroll ? '(can cuon)' : '(vua khit)'}` : 'loi');
    if (canScroll)
      rec('tab:cuon-den-cuoi-duoc', Math.abs(sc.after - sc.max) <= 1,
          `dat=${sc.max} doc lai=${sc.after}`);
    // Tab cuoi phai TOI DUOC bang cuon
    const last = await page.$eval('.strat-tab[data-strategy="analyzer"]', el => {
      const r = el.getBoundingClientRect();
      const h = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return { self: h === el || el.contains(h), w: Math.round(r.width),
               hit: h ? (h.tagName.toLowerCase() + '.' + String(h.className).split(' ')[0]) : null };
    }).catch(() => null);
    rec('tab:cuoi-toi-duoc-sau-khi-cuon', !!last && last.self,
        last ? `w=${last.w} hit=${last.hit}` : 'loi');
  }

  // ── 4. Tab Phan tich ma: o nhap khong bi che ──
  await load();
  try {
    await page.click('.strat-tab[data-strategy="analyzer"]', { timeout: 4000 });
    await settle(page);
    const r = await page.$eval('#analyzer-search', el => {
      const b = el.getBoundingClientRect();
      const h = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
      return { self: h === el, hit: h ? (h.tagName.toLowerCase() + '.' + String(h.className).split(' ')[0]) : null,
               w: Math.round(b.width), h: Math.round(b.height) };
    }).catch(() => null);
    rec('analyzer:input-khong-bi-che', !!r && r.self, r ? `w=${r.w} h=${r.h} hit=${r.hit}` : 'khong tim thay');
  } catch (e) { rec('analyzer:input-khong-bi-che', false, String(e).slice(0, 70)); }

  return out;
}
