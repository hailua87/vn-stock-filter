// KIEM CHUC NANG — khong chi kiem hinh.
// Vu .col-detail la loi CHUC NANG: drawer chet tren desktop ma anh tinh van
// trong binh thuong. Nen moi lan chay deu phai bam that.
//
// MOI NHOM TU TAI LAI TRANG. Khong lam vay thi trang thai ro ri: drawer bo loc
// con mo se che dai tab, va phep kiem tab bao hong oan.
const URL_ = base => base + '/index.html';
// Cho BO CUC THOI DOI thay vi cho mot khoang doan mo. 600ms co luc du co
// luc khong: cung mot trang o 1281px co luc bao 0 nhan vo dong, co luc 4.
// Do hai lan cach nhau 250ms, bang nhau va font da nap xong thi coi la xong.
// Xem chu thich day du o choOnDinh() trong check.mjs.
const settle = async (p) => {
  const chup = () => p.evaluate(() => {
    const q = s => { const e = document.querySelector(s); if (!e) return '-';
                     const r = e.getBoundingClientRect();
                     // PHAI co ca VI TRI, khong chi kich thuoc. Drawer truot NGANG
                     // (`transform: translateX`) nen width/height BAT BIEN suot qua
                     // trinh — lay mau kich thuoc khong the phat hien no dang chay.
                     return `${r.x.toFixed(1)},${r.y.toFixed(1)} ${r.width.toFixed(1)}x${r.height.toFixed(1)}`; };
    // PHAI co ca hai drawer. Chung co `transition: transform 0.25s ease`
    // (styles.css:1041 .col-detail, :1629 .col-filters). Thieu chung thi
    // settle() tra ve trong khi drawer VAN DANG TRUOT, va moi so do ve
    // chung deu la anh chup giua chung.
    // KHONG lay mau .brand-mark: no co `animation: pulse 2s infinite`.
    // May la pulse chi doi opacity nen khong doi hinh hoc — nhung neu lay
    // mau mot phan tu co animation lap vo han thi settle() se KHONG BAO GIO
    // on dinh.
    return [q('.topbar'), q('.topbar-left'), q('.topbar-right'),
            q('.strategy-tabs'), q('.table-wrap'),
            q('.col-detail'), q('.col-filters'), document.fonts.status].join('|');
  });
  let truoc = await chup();
  for (let i = 0; i < 32; i++) {
    await p.waitForTimeout(250);
    const nay = await chup();
    if (nay === truoc && nay.endsWith('loaded')) return;
    truoc = nay;
  }
};

export async function runFunctional(page, isMobile, base) {
  // Nhanh mobile chon theo BE RONG, khong theo co isMobile cua context.
  // bp-767 khong mang co do nhung 767 <= 768 nen no VAN o che do drawer —
  // lan chay dau bao 8 loi oan chi vi di nham nhanh desktop.
  const vpw = page.viewportSize().width;
  const drawerMode = vpw <= 768;
  const out = [];
  // `so`: cac tri so LIEN TUC di kem phep kiem. Nguong nhi phan (ok/khong)
  // vut mat do lon; giu so lai de diff.mjs con canh gac duoc muc da chap nhan.
  const rec = (name, ok, detail = '', so = null) => out.push({ name, ok, detail, ...(so ? { so } : {}) });
  // Cung ly do nhu check.mjs: trang co dong ho va polling nen `networkidle`
  // la dieu kien co the khong bao gio den. Cho DUNG thu can thay vi cho mang im.
  const load = async () => {
    await page.goto(URL_(base), { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForSelector('.table-wrap tbody tr', { timeout: 15000 });
    await settle(page);
  };
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
    // M1 (13/10/2026): o nhap KHONG con tren topbar. No nam dau than
    // `#analyzer-view`, va khoi do duoc an/hien thay cho co `hidden` cu.
    // Phep kiem phai hoi DIEU DUNG: o co HIEN RA that khong — `offsetParent`
    // bat ca ba duong an (display:none cua chinh no, cua to tien, va [hidden]).
    // Do ma khong mo tab do truoc thi o khong hien va phep kiem duoi xanh gia.
    const shown = await page.$eval('.analyzer-searchbar',
      el => el.offsetParent !== null && el.getBoundingClientRect().width > 0
    ).catch(() => false);
    rec('analyzer:o-nhap-hien-ra', shown, shown ? 'hien ra' : 'van an — phep kiem duoi vo nghia');

    const r = await page.$eval('#analyzer-search', el => {
      const b = el.getBoundingClientRect();
      const h = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
      const box = el.parentElement.getBoundingClientRect();
      return { self: h === el, hit: h ? (h.tagName.toLowerCase() + '.' + String(h.className).split(' ')[0]) : null,
               w: Math.round(b.width), h: Math.round(b.height),
               // Tran ra ngoai viewport hay bi ep co duoi be rong khai bao
               boxW: Math.round(box.w || box.width), right: Math.round(b.right), vw: innerWidth };
    }).catch(() => null);
    rec('analyzer:input-khong-bi-che', !!r && r.self, r ? `w=${r.w} h=${r.h} hit=${r.hit}` : 'khong tim thay');
    // NGUONG 141px, va day la lan dau no CO CO SO: do la be rong placeholder
    // "Nhap ma, vd: FPT" (16 ky tu, JetBrains Mono 12px, padding+border 26px).
    // Nguong cu la 200px va duoc ghi ro la CON SO AP DAT.
    //
    // Doi duoc nguong vi M1 doi BAN CHAT cua o nay: tren topbar no la thu bi
    // flex ep co dau tien (tung tut 135 -> 63px khi them tab MA7x25), nen phai
    // canh bang mot nguong rong de bat viec bi ep. O than trang no khai 320px
    // va khong canh tranh cho voi ai — nen cau hoi dung la "placeholder co lot
    // khong", chinh la dieu nguong cu muon hoi ma khong hoi duoc.
    // Xem docs/mobile-layout-out-of-scope.md muc 5.
    rec('analyzer:o-nhap-du-rong', !!r && r.w >= 141, r ? `w=${r.w} (khai 320px, san 141 = be rong placeholder)` : 'loi', r ? { w: Math.round(r.w) } : null);
    rec('analyzer:khong-tran-mep', !!r && r.right <= r.vw + 1, r ? `right=${r.right} vw=${r.vw}` : 'loi');
  } catch (e) { rec('analyzer:input-khong-bi-che', false, String(e).slice(0, 70)); }

  // ── 5. Mobile: chieu cao VO truoc hang du lieu dau tien ──
  //
  // Do that o 402x714 (iPhone, deviceScaleFactor 3) ngay 13/10/2026 TRUOC khi
  // sua: hang du lieu dau tien o y=431 tren man 714px, tuc 60% man hinh la vo.
  // Thanh phan: topbar 138 + market-context 161 + mobile-bar 51.
  //
  // Dieu bat ngo khi do: `.market-context` (161px) LON HON ca topbar (138px),
  // trong khi tai lieu mobile-layout-out-of-scope.md muc 6 chi nham vao topbar.
  //
  // Sau khi sua: market-context 45px (gop mot dong, phan phu vao nut "chi
  // tiet"), topbar 114px (bo TEN thuong hieu nen hai hang tren gop lai duoc).
  // Hang dau len y=292, so hang thay duoc 8 -> 11.
  //
  // Nguong duoi day la CHAN TREN co bien, khong phai so do: 60px cho
  // market-context (do 45) va 125px cho topbar (do 114). Bien de chiu khac
  // biet font giua Windows va ubuntu — hai moc chuan rieng ton tai vi ly do do.
  // Phinh lai hai dong thi market-context ~80px+ va phep kiem do.
  if (drawerMode) {
    await load();
    const mc = await page.$eval('.market-context', el => {
      const r = el.getBoundingClientRect();
      const nut = el.querySelector('.mc-more');
      const ct = el.querySelector('.mc-detail');
      return { h: Math.round(r.height),
               co_nut: !!nut && nut.offsetParent !== null,
               ct_an: !ct || ct.offsetParent === null };
    }).catch(() => null);
    rec('mobile:market-context-gon', !!mc && mc.h <= 60,
        mc ? `h=${mc.h} (nguong 60)` : 'khong tim thay', mc ? { h: mc.h } : null);
    rec('mobile:market-context-co-nut-chi-tiet', !!mc && mc.co_nut && mc.ct_an,
        mc ? `nut=${mc.co_nut} phan-phu-an=${mc.ct_an}` : 'loi');

    // Nguong 60px o tren KHONG tach duoc mot dong (45px) voi HAI dong (~52px) —
    // bien de chiu khac biet font da nuot mat chenh lech do. Lan pha thu nhat
    // ("bo ellipsis cua .mc-label") da LOT qua vi dung ly do nay.
    //
    // Tinh chat that can canh la "nhan o MOT dong", va no do duoc khong phu
    // thuoc font: so chieu cao nhan voi line-height cua chinh no. Day moi la
    // thuoc do dung; nguong 60px giu lai lam chan tren tho.
    const nhan = await page.$eval('.mc-label', el => {
      const s = getComputedStyle(el);
      const lh = parseFloat(s.lineHeight) ||
                 parseFloat(s.fontSize) * 1.2;   // `normal` -> xap xi 1,2em
      return { h: Math.round(el.getBoundingClientRect().height),
               lh: Math.round(lh), cat: s.textOverflow === 'ellipsis' };
    }).catch(() => null);
    rec('mobile:nhan-boi-canh-mot-dong',
        !!nhan && nhan.h <= nhan.lh * 1.6,
        nhan ? `h=${nhan.h} line-height=${nhan.lh} cat=${nhan.cat}` : 'loi',
        nhan ? { h: nhan.h } : null);

    // Bam that: phan phu PHAI mo ra. Khong co phep kiem nay thi "gon" co the
    // dat duoc bang cach VUT phan phu di, va khong ai biet.
    const mo = await page.evaluate(async () => {
      const el = document.querySelector('.market-context');
      el.querySelector('.mc-more')?.click();
      await new Promise(r => setTimeout(r, 250));
      const ct = el.querySelector('.mc-detail');
      return { hien: !!ct && ct.offsetParent !== null,
               cao_hon: Math.round(el.getBoundingClientRect().height) };
    }).catch(() => null);
    rec('mobile:bam-chi-tiet-thi-mo-ra', !!mo && mo.hien && mo.cao_hon > 60,
        mo ? `hien=${mo.hien} h=${mo.cao_hon}` : 'loi');

    await load();
    const tb = await page.$eval('.topbar', el => {
      const vis = e => e && getComputedStyle(e).display !== 'none' && e.offsetParent !== null;
      const con = [...el.children].filter(vis);
      const y = con.map(c => Math.round(c.getBoundingClientRect().y));
      return { h: Math.round(el.getBoundingClientRect().height),
               so_khoi: con.length,
               // So HANG = so nhom y khac nhau qua xa nhau. Hai khoi cung hang
               // thi y chenh nhau duoi chieu cao mot hang (~44px).
               so_hang: new Set(y.map(v => Math.round(v / 40))).size };
    }).catch(() => null);
    rec('mobile:topbar-khong-qua-125px', !!tb && tb.h <= 125,
        tb ? `h=${tb.h} so_hang=${tb.so_hang} (nguong 125)` : 'loi',
        tb ? { h: tb.h } : null);
  }

  // ── 6. Bieu do ba tang o man Chi tiet ma ──
  //
  // TRUOC khi co phan nay, bo do KHONG BAO GIO ve bieu do: `functional.mjs`
  // mo tab Phan tich ma nhung khong phan tich ma nao, nen `#analyzer-chart`
  // van rong. Do that 14/10/2026 tren ket qua cua ca hai schema: 0 dau vet
  // cua moi phan tu `cd-*`. Tuc hai lan "0 moi phat sinh" khong noi gi ve
  // bieu do — dung bay "test khong di qua entrypoint" (CLAUDE.md muc 6).
  //
  // Chi chay o hai dai BIEN (rong nhat va hep nhat): phan tich mot ma ton
  // ~4s, nhan voi 77 khung se gap doi thoi gian chay ca bo do. Bieu do dung
  // mot bo cuc cho moi be rong nen hai dau la du de bat tran ngang.
  if (vpw >= 1400 || vpw <= 430) {
    await load();
    try {
      await page.click('.strat-tab[data-strategy="analyzer"]', { timeout: 4000 });
      await page.waitForTimeout(1200);
      await page.click('.analyzer-quick-btn[data-ticker="FPT"]', { timeout: 4000 });
      await page.waitForSelector('#analyzer-chart .cd-wrap', { timeout: 15000 });
      await settle(page);

      const bd = await page.$eval('#analyzer-chart', el => {
        const box = el.querySelector('.cd-wrap');
        // HIEN RA, khong chi ton tai. Dem `querySelectorAll` khong thi
        // `display: none` van qua — da pha thu va no XANH RONG.
        const q = sel => [...el.querySelectorAll(sel)]
          .filter(e => e.offsetParent !== null).length;
        const r = box.getBoundingClientRect();
        return {
          nen: q('.cd-body'),
          vol: q('.cd-vol'),
          macd: q('.cd-hist, [class*="cd-macd"]'),
          ma: q('.cd-ma'),
          doc: q('.cd-readout'),
          // Tran ngang: dung ca hai thuoc. `scrollWidth` bat noi dung vuot hop;
          // `right > innerWidth` bat chinh hop vuot khung nhin.
          tran_trong: box.scrollWidth > box.clientWidth + 1,
          tran_khung: Math.round(r.right) > innerWidth + 1,
          rong: Math.round(r.width), vw: innerWidth,
          // Du lieu schema 1 thi khong co khoi luong/MACD — phai co ghi chu
          // thay the, neu khong nguoi dung chi thay bieu do thieu tang ma
          // khong biet vi sao.
          //
          // Kiem NOI DUNG, khong chi su ton tai: pha thu bang cach doi chu
          // ghi chu thanh mot cau vo nghia thi phep kiem "co phan tu .muted"
          // VAN XANH. Doi hoi ghi chu nhac ten tang bi thieu — "MACD" la tu
          // on dinh nhat, nguoi viet lai cau van se giu no.
          ghi_chu: [...el.querySelectorAll('.muted, .cd-note')]
            .filter(e => e.offsetParent !== null)
            .some(e => /MACD/i.test(e.textContent || '')),
        };
      }).catch(() => null);

      // Chot chan TRUOC moi phep kiem duoi: khong co nen thi khong do gi ca.
      rec('chart:ve-duoc', !!bd && bd.nen > 0,
          bd ? `nen=${bd.nen} ma=${bd.ma} doc=${bd.doc}` : 'khong tim thay .cd-wrap');

      if (bd && bd.nen > 0) {
        rec('chart:khong-tran-ngang', !bd.tran_trong && !bd.tran_khung,
            `trong=${bd.tran_trong} khung=${bd.tran_khung} rong=${bd.rong} vw=${bd.vw}`,
            { rong: bd.rong });
        rec('chart:co-dong-so-lieu', bd.doc >= 1, `so dong doc=${bd.doc}`);
        // Hoac du ba tang (schema 2), hoac co ghi chu giai thich (schema 1).
        const ba_tang = bd.vol > 0 && bd.macd > 0;
        rec('chart:du-ba-tang-hoac-co-ghi-chu', ba_tang || bd.ghi_chu,
            ba_tang ? `ba tang: vol=${bd.vol} macd=${bd.macd}`
                    : `thieu tang (vol=${bd.vol} macd=${bd.macd}) nhung CO ghi chu=${bd.ghi_chu}`);
      }
    } catch (e) {
      rec('chart:ve-duoc', false, String(e).slice(0, 70));
    }
  }

  return out;
}
